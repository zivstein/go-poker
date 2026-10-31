from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.chips import commit_chips
from go_poker.game.betting.collection import collect_round
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.rounds import first_pending_after, is_eligible, is_round_complete, settle_pending
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand, _require_unsettled


class NotPlayersTurnError(RuntimeError):
    """Raised when a player acts while it is not their turn, including after the betting round is complete."""


class IllegalActionError(ValueError):
    """Raised when the current actor requests an action, or a target amount, that is not legal for them."""


def _is_legal_target(target: int, legal: LegalActions) -> bool:
    """A short all-in allows only its exact all-in target; otherwise any target from the full minimum to the maximum."""
    if legal.short_all_in_target is not None:
        return target == legal.short_all_in_target
    return (
        legal.min_full_target is not None
        and legal.max_target is not None
        and legal.min_full_target <= target <= legal.max_target
    )


def _validated_target(action: Action, legal: LegalActions) -> int | None:
    """Check the action against the current legal actions; return the target of a legal bet or raise, else None."""
    match action.type:
        case ActionType.FOLD:
            is_legal = legal.can_fold
        case ActionType.CHECK:
            is_legal = legal.can_check
        case ActionType.CALL:
            is_legal = legal.can_call
        case ActionType.BET | ActionType.RAISE:
            can_size = legal.can_bet if action.type is ActionType.BET else legal.can_raise
            target = action.amount
            if can_size and target is not None and _is_legal_target(target, legal):
                return target
            is_legal = False
    if not is_legal:
        raise IllegalActionError(f"{action} is not legal for the current actor: {legal}")
    return None


def apply_action(hand: PokerHand, seat_number: int, action: Action) -> None:
    """Apply the current actor's action, then pass the action on or end the betting round.

    A settled hand is rejected first (`HandAlreadySettledError`), before any other validation. The action must come
    from the current actor and be legal for them (see `legal_actions`); a rejection leaves the hand unchanged.
    Check, call and fold settle the actor's obligation; a call commits the legal call amount, which may be a short
    all-in below the current bet, and never changes the current bet. A bet or raise to a target makes it the current
    bet and makes every other eligible player owe a response again. It is full when the target reaches the full
    minimum target and then sets the last full raise size; a short all-in leaves that size unchanged. Every action
    records the current bet right after it in `acted_at_bet`. The round ends early when only one player has not
    folded, or when no opponent can respond and nothing is owed to the call target. Otherwise the next pending player
    clockwise acts. An action that completes the round also collects it (see `collect_round`): unmatched chips go back
    to their player and every player's chips in front move into the middle.
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    if is_round_complete(betting):
        raise NotPlayersTurnError(f"The {betting.street.value} betting round is complete; nobody is to act")
    if seat_number != betting.current_actor:
        raise NotPlayersTurnError(f"Seat {seat_number} acted, but it is seat {betting.current_actor}'s turn")

    legal = legal_actions(hand)
    target = _validated_target(action, legal)

    actor = next(hand_player for hand_player in hand.players if hand_player.seat_number == seat_number)
    pending = set(betting.pending_actors)
    pending.discard(seat_number)

    if target is not None:  # a legal bet or raise to this street contribution
        commit_chips(actor, target - actor.street_contribution)
        # Only a full bet or raise sets the full-raise context; a short all-in below the full minimum never changes it.
        if legal.min_full_target is not None and target >= legal.min_full_target:
            betting.last_full_raise_size = target - betting.current_bet
        betting.current_bet = target
        pending = {
            hand_player.seat_number
            for hand_player in hand.players
            if hand_player is not actor and is_eligible(hand_player)
        }
    elif action.type is ActionType.FOLD:
        actor.folded = True
    elif action.type is ActionType.CALL:
        commit_chips(actor, legal.call_amount)  # a short call commits the whole stack; the current bet stays nominal
    # A check moves no chips; like every action, it only settles the actor's obligation.

    # Every action, a check included, records the bet the actor has now acted at; raise rights are derived from it.
    betting.acted_at_bet[seat_number] = betting.current_bet
    betting.pending_actors = settle_pending(hand.players, pending, betting.current_bet)
    betting.current_actor = first_pending_after(hand.players, seat_number, betting.pending_actors)
    if is_round_complete(betting):
        collect_round(hand.players)

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.chips import commit_chips
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.rounds import first_pending_after, is_eligible, is_round_complete, settle_pending
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand


class NotPlayersTurnError(RuntimeError):
    """Raised when a player acts while it is not their turn, including after the betting round is complete."""


class IllegalActionError(ValueError):
    """Raised when the current actor requests an action, or a target amount, that is not legal for them."""


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
            if (
                can_size
                and target is not None
                and legal.min_full_target is not None
                and legal.max_target is not None
                and legal.min_full_target <= target <= legal.max_target
            ):
                return target
            is_legal = False
    if not is_legal:
        raise IllegalActionError(f"{action} is not legal for the current actor: {legal}")
    return None


def apply_action(hand: PokerHand, seat_number: int, action: Action) -> None:
    """Apply the current actor's action, then pass the action on or end the betting round.

    The action must come from the current actor and be legal for them (see `legal_actions`); a rejection leaves the
    hand unchanged. Check, call and fold settle the actor's obligation; a bet or raise to a target makes every other
    eligible player owe a response again. Every action records the current bet right after it in `acted_at_bet`. The
    round ends early when only one player has not folded, or when no opponent can respond and nothing is owed.
    Otherwise the next pending player clockwise acts.
    """
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
        commit_chips(actor, legal.call_amount)
    # A check moves no chips; like every action, it only settles the actor's obligation.

    # Every action, a check included, records the bet the actor has now acted at; raise rights are derived from it.
    betting.acted_at_bet[seat_number] = betting.current_bet
    betting.pending_actors = settle_pending(hand.players, pending, betting.current_bet)
    betting.current_actor = first_pending_after(hand.players, seat_number, betting.pending_actors)

from dataclasses import dataclass

from go_poker.game.betting.no_limit import max_target, min_bet_target, min_raise_target
from go_poker.game.betting.rounds import is_eligible
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand


@dataclass(frozen=True)
class LegalActions:
    """What the current actor may do. Derived from the hand on request and never stored.

    `call_amount` is the chips the actor must add to match the current bet. `min_target` and `max_target` bound the
    "bet to" / "raise to" target and are set only when a bet or raise is legal.
    """

    can_fold: bool
    can_check: bool
    can_call: bool
    call_amount: int
    can_bet: bool
    can_raise: bool
    min_target: int | None
    max_target: int | None


NOTHING_LEGAL = LegalActions(
    can_fold=False,
    can_check=False,
    can_call=False,
    call_amount=0,
    can_bet=False,
    can_raise=False,
    min_target=None,
    max_target=None,
)


def legal_actions(hand: PokerHand) -> LegalActions:
    """Return the No-Limit actions the current actor may take; nothing is legal when nobody is to act.

    Fold is always legal for the actor, check when nothing is owed, and call when the actor can cover the whole call
    (short all-in calls are not supported in Milestone 2). A bet (when the current bet is zero) or raise (otherwise)
    needs the actor's maximum target to reach the minimum target and at least one other player who can respond.
    """
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    if betting.current_actor is None:
        return NOTHING_LEGAL

    actor = next(hand_player for hand_player in hand.players if hand_player.seat_number == betting.current_actor)
    call_amount = betting.current_bet - actor.street_contribution
    opponent_can_respond = any(is_eligible(hand_player) for hand_player in hand.players if hand_player is not actor)

    is_unopened = betting.current_bet == 0
    min_target = min_bet_target(betting) if is_unopened else min_raise_target(betting)
    highest_target = max_target(actor)
    can_size = opponent_can_respond and highest_target >= min_target

    return LegalActions(
        can_fold=True,
        can_check=call_amount == 0,
        can_call=0 < call_amount <= actor.player.stack,
        call_amount=call_amount,
        can_bet=can_size and is_unopened,
        can_raise=can_size and not is_unopened,
        min_target=min_target if can_size else None,
        max_target=highest_target if can_size else None,
    )

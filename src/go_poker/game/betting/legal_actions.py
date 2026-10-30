from dataclasses import dataclass

from go_poker.game.betting.no_limit import has_raise_rights, max_target, min_bet_target, min_raise_target
from go_poker.game.betting.rounds import call_target, can_opponent_respond
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand


@dataclass(frozen=True)
class LegalActions:
    """What the current actor may do. Derived from the hand on request and never stored.

    - `amount_owed`: the additional chips the actor needs to match what the remaining live opponents can contest, their
      call target (see `call_target`) minus their street contribution; 0 when nothing is owed.
    - `call_amount`: the chips a CALL commits, the amount owed or the whole stack if that is less (a short call); 0
      when CALL is not legal.
    - `call_is_all_in`: CALL is legal and uses the actor's whole remaining stack, whether short or exactly enough.
    - `can_bet` / `can_raise`: some bet (the current bet is zero) or raise (otherwise) is legal, full or short all-in.
    - `min_full_target`: the normal minimum full "bet to" / "raise to" target: the big blind for a bet, the current bet
      plus the last full raise size for a raise. Set whenever a bet or raise is legal, even when the actor cannot
      reach it.
    - `max_target`: the actor's all-in target, their street contribution plus their stack. Set whenever a bet or raise
      is legal.
    - `short_all_in_target`: set only when the actor's all-in target is below `min_full_target`; it then equals
      `max_target` and is the only legal target. None when a full bet or raise is possible, from `min_full_target`
      through `max_target`.
    """

    can_fold: bool
    can_check: bool
    can_call: bool
    amount_owed: int
    call_amount: int
    call_is_all_in: bool
    can_bet: bool
    can_raise: bool
    min_full_target: int | None
    max_target: int | None
    short_all_in_target: int | None


NOTHING_LEGAL = LegalActions(
    can_fold=False,
    can_check=False,
    can_call=False,
    amount_owed=0,
    call_amount=0,
    call_is_all_in=False,
    can_bet=False,
    can_raise=False,
    min_full_target=None,
    max_target=None,
    short_all_in_target=None,
)


def legal_actions(hand: PokerHand) -> LegalActions:
    """Return the No-Limit actions the current actor may take; nothing is legal when nobody is to act.

    Fold is always legal for the actor, check when nothing is owed, and call whenever chips are owed: a call the stack
    cannot cover commits the whole stack (a short all-in call). A bet (when the current bet is zero) or raise
    (otherwise) needs at least one other player who can respond, raise rights for the actor (see `has_raise_rights`),
    and chips beyond the current bet. When the actor's all-in target is below the full minimum target, that all-in
    target is the only legal one (a short all-in bet or raise).
    """
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    if betting.current_actor is None:
        return NOTHING_LEGAL

    actor = next(hand_player for hand_player in hand.players if hand_player.seat_number == betting.current_actor)
    stack = actor.player.stack
    amount_owed = max(0, call_target(hand.players, actor, betting.current_bet) - actor.street_contribution)
    can_call = amount_owed > 0
    call_amount = min(amount_owed, stack) if can_call else 0
    opponent_can_respond = can_opponent_respond(hand.players, actor)

    is_unopened = betting.current_bet == 0
    min_full_target = min_bet_target(betting) if is_unopened else min_raise_target(betting)
    all_in_target = max_target(actor)
    can_aggress = (
        opponent_can_respond and has_raise_rights(betting, actor.seat_number) and all_in_target > betting.current_bet
    )
    is_short_all_in = can_aggress and all_in_target < min_full_target

    return LegalActions(
        can_fold=True,
        can_check=amount_owed == 0,
        can_call=can_call,
        amount_owed=amount_owed,
        call_amount=call_amount,
        call_is_all_in=can_call and call_amount == stack,
        can_bet=can_aggress and is_unopened,
        can_raise=can_aggress and not is_unopened,
        min_full_target=min_full_target if can_aggress else None,
        max_target=all_in_target if can_aggress else None,
        short_all_in_target=all_in_target if is_short_all_in else None,
    )

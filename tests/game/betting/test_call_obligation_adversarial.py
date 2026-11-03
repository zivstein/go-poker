"""Adversarial checks of `call_obligation`: it never mutates the hand, a seat that is not the actor owes the nominal
amount, and the obligations of every seat stay coherent through all-in and side-pot shapes in seeded random hands.
"""

import random
from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import CallObligation, LegalActions, call_obligation, legal_actions
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete, start_betting_round
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type BettingLookup = Callable[[PokerHand], BettingState]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type Play = Callable[..., None]
type Snapshot = Callable[[PokerHand], object]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def pick(rng: random.Random, legal: LegalActions) -> Action:
    choices: list[Action] = [FOLD]
    if legal.can_check:
        choices += [CHECK] * 3
    if legal.can_call:
        choices += [CALL] * 3
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        choices.append(Action(kind, legal.short_all_in_target))
    elif legal.min_full_target is not None and legal.max_target is not None:
        choices += [Action(kind, legal.min_full_target), Action(kind, legal.max_target)]
    return rng.choice(choices)


def test_reading_the_obligation_of_every_seat_never_changes_the_hand(
    started_hand: HandFactory, hand_snapshot: Snapshot, play: Play, betting: BettingLookup
) -> None:
    hand = started_hand({1: 1000, 3: 10, 5: 1000, 8: 120}, button_seat_number=5)
    play(hand, (3, CALL), (5, raise_to(40)))
    before = hand_snapshot(hand)
    legal_before = legal_actions(hand)
    for seat in range(0, 12):  # every seat number, in the hand or not
        call_obligation(hand, seat)
        call_obligation(hand, seat)
    assert hand_snapshot(hand) == before
    assert legal_actions(hand) == legal_before
    assert betting(hand).current_actor == 8


def test_a_seat_that_is_not_to_act_owes_the_nominal_amount_while_the_actor_is_live(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """The cap by what all-in opponents can contest applies only to a lone live seat, which is then the one to act.
    Every other seat owes the raw difference to the current bet, whatever its opponents' stacks."""
    hand = started_hand({1: 1000, 3: 25, 5: 1000, 8: 1000}, button_seat_number=5)
    play(hand, (3, raise_to(25)))  # UTG goes all-in with a full raise to 25
    assert betting(hand).current_actor == 5
    assert call_obligation(hand, 5) == CallObligation(amount_owed=25, call_amount=25, call_is_all_in=False)
    assert call_obligation(hand, 8) == CallObligation(amount_owed=20, call_amount=20, call_is_all_in=False)
    assert call_obligation(hand, 1) == CallObligation(amount_owed=15, call_amount=15, call_is_all_in=False)
    assert call_obligation(hand, 3) is None  # all-in


def test_a_short_stacked_seat_waiting_for_its_turn_reports_the_full_amount_and_a_short_call(
    started_hand: HandFactory, play: Play
) -> None:
    hand = started_hand({1: 1000, 3: 60, 5: 1000, 8: 12}, button_seat_number=5)
    play(hand, (3, raise_to(60)))  # UTG goes all-in for 60
    # the small blind (seat 8) posted 5 of its 12, so it owes 55 but a call commits only the 7 it has left
    assert call_obligation(hand, 8) == CallObligation(amount_owed=55, call_amount=7, call_is_all_in=True)


@pytest.mark.parametrize("seed", range(40))
def test_obligations_of_all_seats_are_coherent_through_random_all_in_hands(
    seed: int, started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """At every decision of seeded random hands with mixed short and deep stacks, for every seat: the obligation exists
    exactly for a seat that can act; it is never negative or above what the stack can pay; a non-actor owes exactly the
    raw gap to the current bet; the actor's equals its legal actions; and reading never perturbs `legal_actions`."""
    rng = random.Random(seed)
    seats = sorted(rng.sample(range(1, 10), rng.randint(2, 7)))
    stacks = {seat: rng.choice([3, 6, 15, 40, 120, 1000]) for seat in seats}
    hand = started_hand(stacks, button_seat_number=rng.choice(seats))
    deal_hole_cards(hand)
    state = betting(hand)

    for _ in range(300):
        if is_round_complete(state):
            # no round is open: nobody owes anything
            assert all(call_obligation(hand, seat) is None for seat in seats)
            if is_betting_closed(hand) or hand.street is Street.RIVER:
                break
            deal_next_street(hand)
            start_betting_round(hand)
            continue
        actor = state.current_actor
        assert actor is not None
        legal = legal_actions(hand)
        for seat, hand_player in by_seat(hand).items():
            obligation = call_obligation(hand, seat)
            if hand_player.folded or hand_player.all_in:
                assert obligation is None
                continue
            assert obligation is not None
            stack = hand_player.player.stack
            assert 0 <= obligation.call_amount <= min(obligation.amount_owed, stack)
            assert obligation.call_is_all_in == (obligation.amount_owed > 0 and obligation.call_amount == stack)
            if seat == actor:
                assert obligation == CallObligation(legal.amount_owed, legal.call_amount, legal.call_is_all_in)
            else:
                gap = max(0, state.current_bet - hand_player.street_contribution)
                assert obligation.amount_owed == gap
        assert legal_actions(hand) == legal
        play(hand, (actor, pick(rng, legal)))

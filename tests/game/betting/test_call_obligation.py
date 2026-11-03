import random
from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import CallObligation, LegalActions, call_obligation, legal_actions
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete, start_betting_round
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type BettingLookup = Callable[[PokerHand], BettingState]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type Play = Callable[..., None]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


# =============================================================================
# NONE
# =============================================================================


def test_call_obligation_needs_initialized_betting(make_hand: HandFactory) -> None:
    with pytest.raises(BettingNotInitializedError):
        call_obligation(make_hand({3: 1000, 7: 1000}, button_seat_number=7), 3)


def test_no_obligation_when_no_betting_round_is_open(started_hand: HandFactory, betting: BettingLookup) -> None:
    """Heads-up with the small blind all-in by posting, the round is complete at its start: nobody is to act."""
    hand = started_hand({3: 1000, 7: 5}, button_seat_number=7)
    assert betting(hand).current_actor is None
    assert call_obligation(hand, 3) is None
    assert call_obligation(hand, 7) is None


def test_no_obligation_for_a_seat_that_is_not_in_the_hand(started_hand: HandFactory) -> None:
    hand = started_hand({1: 1000, 3: 1000, 5: 1000}, button_seat_number=1)
    assert call_obligation(hand, 9) is None


def test_no_obligation_for_a_folded_seat(started_hand: HandFactory, play: Play) -> None:
    hand = started_hand({1: 1000, 3: 1000, 5: 1000}, button_seat_number=1)
    play(hand, (1, FOLD))
    assert call_obligation(hand, 1) is None
    assert call_obligation(hand, 3) is not None


def test_no_obligation_for_an_all_in_seat(started_hand: HandFactory, play: Play) -> None:
    hand = started_hand({1: 1000, 3: 1000, 5: 1000}, button_seat_number=1)
    play(hand, (1, raise_to(1000)))
    assert call_obligation(hand, 1) is None
    assert call_obligation(hand, 3) == CallObligation(amount_owed=995, call_amount=995, call_is_all_in=True)


# =============================================================================
# AMOUNTS
# =============================================================================


def test_nothing_owed(started_hand: HandFactory, play: Play) -> None:
    """The big blind with its option, called around, owes nothing."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    play(hand, (1, CALL), (2, CALL))
    assert call_obligation(hand, 3) == CallObligation(0, 0, False)


def test_chips_owed_for_the_actor_and_for_a_seat_waiting_for_its_turn(started_hand: HandFactory) -> None:
    """Four-handed: UTG owes the big blind; seats behind it owe what they still lack to match it."""
    hand = started_hand({1: 1000, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)  # SB 8, BB 1, UTG 3, button 5
    assert call_obligation(hand, 3) == CallObligation(10, 10, False)  # the current actor
    assert call_obligation(hand, 5) == CallObligation(10, 10, False)  # the button owes the whole blind
    assert call_obligation(hand, 8) == CallObligation(5, 5, False)  # the small blind owes the rest
    assert call_obligation(hand, 1) == CallObligation(0, 0, False)  # the big blind owes nothing yet


def test_a_non_actor_seat_owes_what_an_opponent_raised(started_hand: HandFactory, play: Play) -> None:
    hand = started_hand({1: 1000, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    play(hand, (3, raise_to(30)))
    assert call_obligation(hand, 5) == CallObligation(30, 30, False)
    assert call_obligation(hand, 8) == CallObligation(25, 25, False)
    assert call_obligation(hand, 1) == CallObligation(20, 20, False)
    assert call_obligation(hand, 3) == CallObligation(0, 0, False)


def test_short_call_commits_the_whole_stack(started_hand: HandFactory) -> None:
    """UTG has 7 and owes the 10 big blind: the call is short and all-in."""
    hand = started_hand({1: 1000, 3: 7, 5: 1000, 8: 1000}, button_seat_number=5)
    assert call_obligation(hand, 3) == CallObligation(amount_owed=10, call_amount=7, call_is_all_in=True)


def test_call_of_exactly_the_stack_is_all_in(started_hand: HandFactory) -> None:
    hand = started_hand({1: 1000, 3: 10, 5: 1000, 8: 1000}, button_seat_number=5)
    assert call_obligation(hand, 3) == CallObligation(amount_owed=10, call_amount=10, call_is_all_in=True)


def test_call_with_chips_to_spare_is_not_all_in(started_hand: HandFactory) -> None:
    hand = started_hand({1: 1000, 3: 11, 5: 1000, 8: 1000}, button_seat_number=5)
    assert call_obligation(hand, 3) == CallObligation(amount_owed=10, call_amount=10, call_is_all_in=False)


def test_owed_chips_are_capped_by_the_target_all_in_opponents_can_contest(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """The big blind is all-in for 3 of the 10 blind, UTG calls all-in for 7 and the button folds: the small blind owes
    the 2 that UTG can contest, though the current bet is 10."""
    hand = started_hand({5: 1000, 8: 1000, 1: 3, 3: 7}, button_seat_number=5)
    play(hand, (3, CALL), (5, FOLD))
    assert betting(hand).current_bet == 10
    assert call_obligation(hand, 8) == CallObligation(amount_owed=2, call_amount=2, call_is_all_in=False)
    assert call_obligation(hand, 1) is None  # all-in
    assert call_obligation(hand, 3) is None  # all-in


# =============================================================================
# AGREEMENT WITH LEGAL ACTIONS
# =============================================================================


def assert_agrees_with_legal_actions(hand: PokerHand, legal: LegalActions, actor: int) -> None:
    obligation = call_obligation(hand, actor)
    assert obligation == CallObligation(legal.amount_owed, legal.call_amount, legal.call_is_all_in)
    assert (obligation is not None and obligation.amount_owed == 0) == legal.can_check
    assert (obligation is not None and obligation.amount_owed > 0) == legal.can_call


def random_action(rng: random.Random, legal: LegalActions) -> Action:
    """A random legal action, passive ones likelier so that rounds end, with all-in sizes common."""
    choices: list[tuple[Action, int]] = [(FOLD, 1 if legal.can_check else 2)]
    if legal.can_check:
        choices.append((CHECK, 4))
    if legal.can_call:
        choices.append((CALL, 4))
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        choices.append((Action(kind, legal.short_all_in_target), 3))
    elif legal.min_full_target is not None and legal.max_target is not None:
        choices += [(Action(kind, legal.min_full_target), 2), (Action(kind, legal.max_target), 2)]
    return rng.choices([action for action, _ in choices], [weight for _, weight in choices])[0]


@pytest.mark.parametrize("seed", range(60))
def test_obligation_agrees_with_legal_actions_for_the_actor_over_random_hands(
    seed: int, started_hand: HandFactory, by_seat: SeatLookup, play: Play
) -> None:
    """Across every street of seeded random hands, at every decision: the actor's obligation equals the matching legal
    actions fields, and every other seat's is None exactly when it cannot act."""
    rng = random.Random(seed)
    seats = sorted(rng.sample(range(1, 10), rng.randint(2, 6)))
    stacks = {seat: rng.choice([6, 15, 40, 120, 1000]) for seat in seats}
    hand = started_hand(stacks, button_seat_number=rng.choice(seats))
    deal_hole_cards(hand)
    betting = hand.betting
    assert betting is not None

    for _ in range(300):
        if is_round_complete(betting):
            if is_betting_closed(hand) or hand.street is Street.RIVER:
                break
            deal_next_street(hand)
            start_betting_round(hand)
            continue
        actor = betting.current_actor
        assert actor is not None
        legal = legal_actions(hand)
        assert_agrees_with_legal_actions(hand, legal, actor)
        for seat, hand_player in by_seat(hand).items():
            can_act = not hand_player.folded and not hand_player.all_in
            assert (call_obligation(hand, seat) is not None) == can_act
        play(hand, (actor, random_action(rng, legal)))

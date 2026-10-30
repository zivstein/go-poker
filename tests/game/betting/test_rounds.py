from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.rounds import (
    BettingRoundAlreadyStartedError,
    BettingRoundNotCompleteError,
    is_betting_closed,
    start_betting_round,
)
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type BettingLookup = Callable[[PokerHand], BettingState]
type HandSnapshotter = Callable[[PokerHand], object]
type Play = Callable[..., None]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def called_around_to_the_flop(started_hand: HandFactory, stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """Deal hole cards, have every player call the big blind and the big blind check, then deal the flop."""
    hand = started_hand(stacks, button_seat_number=button_seat_number)
    deal_hole_cards(hand)
    betting_state = hand.betting
    assert betting_state is not None
    while betting_state.current_actor is not None:
        seat_number = betting_state.current_actor
        apply_action(hand, seat_number, CHECK if betting_state.pending_actors == {seat_number} else CALL)
    deal_next_street(hand)
    return hand


# =============================================================================
# STARTING A LATER ROUND
# =============================================================================


def test_flop_round_starts_with_no_bet_and_the_first_player_after_the_button(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, stakes: Stakes
) -> None:
    """Four-handed, the flop round starts with nothing in front (the preflop round was collected when it completed),
    totals kept, no bet, the big-blind minimum restored, nobody having acted yet (the preflop actions are cleared),
    everyone pending, and the small blind (first after the button) to act."""
    hand = called_around_to_the_flop(started_hand, {5: 1000, 8: 1000, 1: 1000, 3: 1000}, button_seat_number=5)
    assert betting(hand).acted_at_bet == {5: 10, 8: 10, 1: 10, 3: 10}
    start_betting_round(hand)

    assert {seat: (hp.street_contribution, hp.total_contribution) for seat, hp in by_seat(hand).items()} == {
        5: (0, 10),
        8: (0, 10),
        1: (0, 10),
        3: (0, 10),
    }
    assert betting(hand) == BettingState(
        street=Street.FLOP,
        stakes=stakes,
        current_bet=0,
        last_full_raise_size=stakes.big_blind,
        current_actor=8,
        pending_actors={5, 8, 1, 3},
        acted_at_bet={},
    )


def test_heads_up_big_blind_acts_first_after_the_flop(started_hand: HandFactory, betting: BettingLookup) -> None:
    """Heads-up the button is the small blind, so the big blind is the first player after the button postflop."""
    hand = called_around_to_the_flop(started_hand, {3: 1000, 7: 1000}, button_seat_number=7)
    start_betting_round(hand)
    assert betting(hand).current_actor == 3


def test_round_with_nobody_able_to_respond_is_complete_as_it_starts(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """After the button calls all-in and the small blind folds, the big blind alone can act, so the flop round
    starts complete."""
    hand = started_hand({1: 10, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, FOLD))
    deal_next_street(hand)
    start_betting_round(hand)

    assert betting(hand).street is Street.FLOP
    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()


# =============================================================================
# REJECTED ROUND STARTS
# =============================================================================


def test_round_start_before_previous_round_completes_is_rejected_without_changes(
    started_hand: HandFactory, hand_snapshot: HandSnapshotter
) -> None:
    """The flop has been dealt, but preflop betting still has players to act."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    apply_action(hand, 1, CALL)
    deal_next_street(hand)
    before = hand_snapshot(hand)

    with pytest.raises(BettingRoundNotCompleteError):
        start_betting_round(hand)

    assert hand_snapshot(hand) == before


def test_second_round_start_on_the_same_street_is_rejected_without_changes(
    started_hand: HandFactory, hand_snapshot: HandSnapshotter, play: Play
) -> None:
    """Once the flop round has started and completed, it cannot be started again until the street moves on."""
    hand = called_around_to_the_flop(started_hand, {1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    start_betting_round(hand)
    play(hand, (2, CHECK), (3, CHECK), (1, CHECK))
    before = hand_snapshot(hand)

    with pytest.raises(BettingRoundAlreadyStartedError):
        start_betting_round(hand)

    assert hand_snapshot(hand) == before


def test_round_start_needs_initialized_betting(make_hand: HandFactory) -> None:
    """A hand whose betting was never initialized has no round to start."""
    with pytest.raises(BettingNotInitializedError):
        start_betting_round(make_hand({3: 1000, 7: 1000}, button_seat_number=7))


# =============================================================================
# NO FURTHER BETTING
# =============================================================================


@pytest.mark.parametrize(
    "stacks, actions, expected",
    [
        pytest.param({1: 1000, 2: 500, 3: 500}, [(1, FOLD), (2, raise_to(500)), (3, CALL)], True, id="all-live-all-in"),
        pytest.param({1: 1000, 2: 5, 3: 1000}, [(1, FOLD)], True, id="one-able-player-owes-nothing"),
        pytest.param({1: 1000, 2: 1000, 3: 1000}, [(1, FOLD), (2, FOLD)], True, id="everyone-else-folded"),
        pytest.param({1: 1000, 2: 1000, 3: 1000}, [(1, CALL)], False, id="two-able-players-mid-round"),
        pytest.param(
            {1: 1000, 2: 1000, 3: 1000},
            [(1, CALL), (2, CALL), (3, CHECK)],
            False,
            id="two-able-players-round-complete",
        ),
    ],
)
def test_betting_is_closed_once_the_round_is_complete_and_at_most_one_player_can_act(
    stacks: dict[int, int],
    actions: list[tuple[int, Action]],
    expected: bool,
    started_hand: HandFactory,
    hand_snapshot: HandSnapshotter,
    play: Play,
) -> None:
    """Three-handed preflop (button 1, SB 2, BB 3). Betting is closed when the round is complete and at most one
    player has neither folded nor gone all-in; with two or more able to act, it is not, even with the round complete.
    It is derived on request, never stored."""
    hand = started_hand(stacks, button_seat_number=1)
    play(hand, *actions)
    before = hand_snapshot(hand)

    assert is_betting_closed(hand) is expected
    assert hand_snapshot(hand) == before


def test_betting_is_not_closed_while_the_able_player_owes_an_all_in_opponent(
    started_hand: HandFactory, play: Play
) -> None:
    """Heads-up, the big blind is all-in by posting and the small blind still owes chips: betting closes only once it
    has called."""
    hand = started_hand({3: 10, 7: 1000}, button_seat_number=7)
    assert is_betting_closed(hand) is False

    play(hand, (7, CALL))
    assert is_betting_closed(hand) is True


def test_betting_closed_needs_initialized_betting(make_hand: HandFactory) -> None:
    """A hand whose betting was never initialized has no betting to close."""
    with pytest.raises(BettingNotInitializedError):
        is_betting_closed(make_hand({3: 1000, 7: 1000}, button_seat_number=7))

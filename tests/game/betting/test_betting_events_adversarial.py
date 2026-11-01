"""Adversarial validation of the betting transition events (ADR 0004 §3, §4, §8).

Complements `test_betting_events`: chip amounts on later streets (the street contribution, never the total, is what an
action adds to), the all-in flag of a top contributor whose chips are then returned, returns with a folded larger
contributor, blind boundaries around the stack, seat orders with gaps and wraparound, rounds complete at their start
when everyone is all-in, rejection of every illegal action shape, and the prefix property of a history across a whole
hand. Every expected event is written out here independently of the engine.
"""

from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.rounds import BettingRoundAlreadyStartedError, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindPost,
    BlindsPosted,
    ChipsReturned,
    HandEvent,
    StreetDealt,
)
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type Play = Callable[..., None]

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
PREFLOP_COMPLETED = BettingRoundCompleted(Street.PREFLOP)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def to_flop(hand: PokerHand, play: Play, preflop: tuple[tuple[int, Action], ...]) -> None:
    """Play the preflop actions, deal the hole cards and the flop, and start the flop round."""
    deal_hole_cards(hand)
    play(hand, *preflop)
    deal_next_street(hand)
    start_betting_round(hand)


# =============================================================================
# CHIP AMOUNTS ON LATER STREETS
# =============================================================================


def test_later_street_actions_add_to_the_street_contribution_not_to_the_total(
    started_hand: HandFactory, play: Play, replay_facts: Callable[..., Any]
) -> None:
    """Every seat has 10 from the preflop. On the flop the small blind bets 20, the big blind raises to 60 and the small
    blind re-raises to 200: that re-raise adds 180 (20 were in front), not 170 (the 30 of its total). The big blind
    has 150 in all, so it calls short with its last 80, all-in, and the small blind's 60 uncalled chips go back."""
    hand = started_hand({5: 1000, 8: 1000, 1: 150, 3: 1000}, button_seat_number=5)
    to_flop(hand, play, ((3, CALL), (5, CALL), (8, CALL), (1, CHECK)))
    before = len(hand.history.events)

    play(hand, (8, bet(20)), (1, raise_to(60)), (3, FOLD), (5, FOLD), (8, raise_to(200)), (1, CALL))

    assert hand.history.events[before:] == (
        ActionTaken(8, bet(20), 20, False),
        ActionTaken(1, raise_to(60), 60, False),
        ActionTaken(3, FOLD, 0, False),
        ActionTaken(5, FOLD, 0, False),
        ActionTaken(8, raise_to(200), 180, False),
        ActionTaken(1, CALL, 80, True),
        ChipsReturned(8, 60),
        BettingRoundCompleted(Street.FLOP),
    )
    replay_facts(hand)


def test_a_short_call_on_a_later_street_records_the_remaining_stack_not_the_amount_owed(
    started_hand: HandFactory, play: Play
) -> None:
    """Heads-up with 70 and 300: after the preflop call the button has 60 left. On the flop the big blind bets 100 and
    the button calls with its remaining 60, all-in; the big blind's 40 uncalled chips go back."""
    hand = started_hand({1: 70, 2: 300}, button_seat_number=1)
    to_flop(hand, play, ((1, CALL), (2, CHECK)))
    before = len(hand.history.events)

    play(hand, (2, bet(100)), (1, CALL))

    assert hand.history.events[before:] == (
        ActionTaken(2, bet(100), 100, False),
        ActionTaken(1, CALL, 60, True),
        ChipsReturned(2, 40),
        BettingRoundCompleted(Street.FLOP),
    )


# =============================================================================
# THE ALL-IN FLAG OF A TOP CONTRIBUTOR WHOSE CHIPS COME BACK
# =============================================================================


def test_an_all_in_raise_nobody_calls_is_recorded_all_in_though_the_excess_returns_and_the_seat_is_no_longer_all_in(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup, replay_facts: Callable[..., Any]
) -> None:
    """Heads-up with 200 and 1000: the small blind calls, on the flop the big blind bets 20, the small blind shoves 190
    and the big blind folds. The shove is flagged all-in right after the commit; collecting then returns 170 and the
    live seat holds chips again. The history keeps both facts and the replay ends with the seat not all-in."""
    hand = started_hand({1: 200, 2: 1000}, button_seat_number=1)
    to_flop(hand, play, ((1, CALL), (2, CHECK)))
    before = len(hand.history.events)

    play(hand, (2, bet(20)), (1, raise_to(190)), (2, FOLD))

    assert hand.history.events[before:] == (
        ActionTaken(2, bet(20), 20, False),
        ActionTaken(1, raise_to(190), 190, True),
        ActionTaken(2, FOLD, 0, False),
        ChipsReturned(1, 170),
        BettingRoundCompleted(Street.FLOP),
    )
    seat = by_seat(hand)[1]
    assert not seat.all_in and seat.player.stack == 170
    replay_facts(hand)


# =============================================================================
# RETURNS WITH A FOLDED LARGER CONTRIBUTOR
# =============================================================================


def test_the_return_goes_to_the_top_contributor_and_is_measured_against_a_folded_contribution(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup, replay_facts: Callable[..., Any]
) -> None:
    """UTG raises to 100, the button re-raises to 300, everyone else folds, UTG included. UTG's folded 100 is the most
    anyone else put in, so exactly the button's 200 above it go back, to the button and to nobody else."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 1000}, button_seat_number=5)
    before = len(hand.history.events)

    play(hand, (3, raise_to(100)), (5, raise_to(300)), (8, FOLD), (1, FOLD), (3, FOLD))

    assert hand.history.events[before:] == (
        ActionTaken(3, raise_to(100), 100, False),
        ActionTaken(5, raise_to(300), 300, False),
        ActionTaken(8, FOLD, 0, False),
        ActionTaken(1, FOLD, 0, False),
        ActionTaken(3, FOLD, 0, False),
        ChipsReturned(5, 200),
        PREFLOP_COMPLETED,
    )
    seats = by_seat(hand)
    assert (seats[5].player.stack, seats[3].player.stack) == (900, 900)
    replay_facts(hand)


def test_two_all_ins_of_different_sizes_return_the_largers_excess_to_the_larger(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup, replay_facts: Callable[..., Any]
) -> None:
    """Three-handed with 400, 150 and 1000: the button shoves 400, the small blind calls all-in with 150, the big blind
    folds. The button's 250 above the next largest contribution go back to the button."""
    hand = started_hand({1: 400, 2: 150, 3: 1000}, button_seat_number=1)
    before = len(hand.history.events)

    play(hand, (1, raise_to(400)), (2, CALL), (3, FOLD))

    assert hand.history.events[before:] == (
        ActionTaken(1, raise_to(400), 400, True),
        ActionTaken(2, CALL, 145, True),
        ActionTaken(3, FOLD, 0, False),
        ChipsReturned(1, 250),
        PREFLOP_COMPLETED,
    )
    assert by_seat(hand)[1].player.stack == 250
    replay_facts(hand)


# =============================================================================
# BLIND BOUNDARIES AND SEAT ORDERS
# =============================================================================


@pytest.mark.parametrize(
    ("small_stack", "big_stack", "small_post", "big_post"),
    [
        pytest.param(5, 1000, BlindPost(2, Blind.SMALL, 5, True), BlindPost(3, Blind.BIG, 10, False), id="small-exact"),
        pytest.param(
            6, 1000, BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 10, False), id="small-plus1"
        ),
        pytest.param(4, 1000, BlindPost(2, Blind.SMALL, 4, True), BlindPost(3, Blind.BIG, 10, False), id="small-short"),
        pytest.param(1000, 10, BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 10, True), id="big-exact"),
        pytest.param(1000, 11, BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 10, False), id="big-plus1"),
        pytest.param(1000, 9, BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 9, True), id="big-short"),
    ],
)
def test_the_all_in_flag_of_a_blind_follows_the_stack_boundary(
    make_hand: HandFactory, small_stack: int, big_stack: int, small_post: BlindPost, big_post: BlindPost
) -> None:
    """A blind is all-in exactly when it posts its whole stack; one chip more is not."""
    hand = make_hand({1: 1000, 2: small_stack, 3: big_stack}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert hand.history.events[1:] == (BlindsPosted(STAKES, (small_post, big_post)),)


def test_heads_up_all_in_blinds_of_different_sizes_return_the_big_blinds_excess(make_hand: HandFactory) -> None:
    """A 5-chip small blind and a 10-chip big blind are both all-in; the big blind's 5 chips nobody can call go back."""
    hand = make_hand({1: 5, 2: 10}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert hand.history.events[1:] == (
        BlindsPosted(STAKES, (BlindPost(1, Blind.SMALL, 5, True), BlindPost(2, Blind.BIG, 10, True))),
        ChipsReturned(2, 5),
        PREFLOP_COMPLETED,
    )


@pytest.mark.parametrize(
    ("seats", "button", "small", "big"),
    [
        ((2, 4, 9), 9, 2, 4),
        ((2, 4, 9), 4, 9, 2),
        ((1, 6), 6, 6, 1),
        ((1, 6), 1, 1, 6),
        ((3, 5, 7, 8), 8, 3, 5),
    ],
)
def test_blinds_follow_the_seat_order_with_gaps_and_wraparound(
    make_hand: HandFactory, seats: tuple[int, ...], button: int, small: int, big: int
) -> None:
    """The small blind is listed first and the big blind second wherever the button is, heads-up included."""
    hand = make_hand({seat: 1000 for seat in seats}, button_seat_number=button)
    initialize_betting(hand, STAKES)

    assert hand.history.events[1:] == (
        BlindsPosted(STAKES, (BlindPost(small, Blind.SMALL, 5, False), BlindPost(big, Blind.BIG, 10, False))),
    )


# =============================================================================
# ROUNDS COMPLETE AT THEIR START
# =============================================================================


def test_every_street_after_an_all_in_call_starts_complete_and_each_records_exactly_one_pair(
    started_hand: HandFactory, play: Play
) -> None:
    """Heads-up all-in and called: dealing and starting each later street by hand records, per street, the start then
    the completion, nothing returned, and a second start of the same street is rejected without recording."""
    hand = started_hand({1: 100, 2: 100}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, raise_to(100)), (2, CALL))
    length = len(hand.history.events)

    for _ in range(3):
        deal_next_street(hand)
        start_betting_round(hand)
        before = hand.history
        with pytest.raises(BettingRoundAlreadyStartedError):
            start_betting_round(hand)
        assert hand.history == before

    events: tuple[HandEvent, ...] = hand.history.events[length:]
    assert len(events) == 9
    for index, street in enumerate((Street.FLOP, Street.TURN, Street.RIVER)):
        dealt, started, completed = events[3 * index : 3 * index + 3]
        assert isinstance(dealt, StreetDealt) and dealt.street is street
        assert (started, completed) == (BettingRoundStarted(street), BettingRoundCompleted(street))


# =============================================================================
# REJECTIONS
# =============================================================================


@pytest.mark.parametrize(
    "action",
    [
        pytest.param(CHECK, id="check-facing-a-bet"),
        pytest.param(bet(40), id="bet-facing-a-bet"),
        pytest.param(raise_to(2000), id="raise-beyond-the-stack"),
        pytest.param(raise_to(20), id="raise-to-the-current-bet"),
        pytest.param(raise_to(59), id="raise-below-the-minimum"),
        pytest.param(raise_to(10), id="raise-below-the-current-bet"),
    ],
)
def test_illegal_actions_on_a_later_street_record_nothing(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup, action: Action
) -> None:
    """Facing a flop bet of 20 raised to 40 (the next minimum raise is to 60), each illegal request is rejected and the
    history and stacks are exactly as they were."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 1000}, button_seat_number=5)
    to_flop(hand, play, ((3, CALL), (5, CALL), (8, CALL), (1, CHECK)))
    play(hand, (8, bet(20)), (1, raise_to(40)))
    before = hand.history
    stacks = {seat: state.player.stack for seat, state in by_seat(hand).items()}

    with pytest.raises(IllegalActionError):
        apply_action(hand, 3, action)

    assert hand.history == before
    assert {seat: state.player.stack for seat, state in by_seat(hand).items()} == stacks


# =============================================================================
# HISTORIES ARE VALUES
# =============================================================================


def test_every_earlier_history_is_a_prefix_of_every_later_one_and_never_changes(
    started_hand: HandFactory, play: Play
) -> None:
    """Take the history after each operation of a whole hand: each is a prefix of the next, and each still equals the
    events it had when taken."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 60}, button_seat_number=5)
    taken = [(hand.history, hand.history.events)]
    steps: list[Callable[[], None]] = [
        lambda: deal_hole_cards(hand),
        lambda: play(hand, (3, raise_to(60))),
        lambda: play(hand, (5, CALL), (8, FOLD), (1, CALL)),
        lambda: deal_next_street(hand),
        lambda: start_betting_round(hand),
        lambda: play(hand, (1, bet(50)), (5, FOLD)),
    ]
    for step in steps:
        step()
        taken.append((hand.history, hand.history.events))

    for (earlier, earlier_events), (later, _) in zip(taken, taken[1:], strict=False):
        assert earlier.events == earlier_events
        assert later.events[: len(earlier_events)] == earlier_events
        assert len(later.events) > len(earlier_events)
    assert taken[-1][1] == hand.history.events

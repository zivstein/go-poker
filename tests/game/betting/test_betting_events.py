"""The transition events the betting operations record (ADR 0004 §3, §4, §8).

Every event is recorded by the public low-level operation that causes it, in the same call, so each test drives
`initialize_betting`, `apply_action`, `deal_next_street` and `start_betting_round` and compares the recorded events with
independently written literals. Hole cards are not under test here (see the Hold'em dealing events), so the hands are
unshuffled. Seats: `FOUR_HANDED` has the button 5, the small blind 8, the big blind 1 and UTG 3; UTG acts first
preflop and the small blind first on every later street. The blinds are 5/10.
"""

from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, NotPlayersTurnError, apply_action
from go_poker.game.betting.initialization import (
    BettingAlreadyInitializedError,
    BettingNotPreflopError,
    initialize_betting,
)
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import (
    BettingRoundAlreadyStartedError,
    BettingRoundNotCompleteError,
    is_betting_closed,
    is_round_complete,
    start_betting_round,
)
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindPost,
    BlindsPosted,
    ChipsReturned,
    HandEvent,
    HandStarted,
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
FOUR_HANDED = {5: 1000, 8: 1000, 1: 1000, 3: 1000}  # button 5, SB 8, BB 1, UTG 3
PREFLOP_COMPLETED = BettingRoundCompleted(Street.PREFLOP)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def small_blind(seat: int, chips: int = 5, all_in: bool = False) -> BlindPost:
    return BlindPost(seat, Blind.SMALL, chips, all_in)


def big_blind(seat: int, chips: int = 10, all_in: bool = False) -> BlindPost:
    return BlindPost(seat, Blind.BIG, chips, all_in)


def recorded(hand: PokerHand) -> tuple[HandEvent, ...]:
    """The events after `HandStarted`, which every history here starts with."""
    assert isinstance(hand.history.events[0], HandStarted)
    return hand.history.events[1:]


def call_around(hand: PokerHand, play: Play, seats: tuple[int, ...]) -> None:
    """The given seats call, in order."""
    play(hand, *((seat, CALL) for seat in seats))


# =============================================================================
# BLINDS
# =============================================================================


def test_blinds_are_recorded_as_one_event_in_posting_order_and_the_round_stays_open(
    make_hand: HandFactory,
) -> None:
    """Small blind then big blind, with the chips each posted; nothing else is recorded while players are to act."""
    hand = make_hand(FOUR_HANDED, button_seat_number=5)
    initialize_betting(hand, STAKES)

    assert recorded(hand) == (BlindsPosted(STAKES, (small_blind(8), big_blind(1))),)
    assert hand.history.number == 1


def test_a_short_small_blind_posts_its_stack_all_in_and_the_round_stays_open(make_hand: HandFactory) -> None:
    """Three-handed, a small blind with 3 chips posts them all-in; the other two players still have to act."""
    hand = make_hand({1: 1000, 2: 3, 3: 1000}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert recorded(hand) == (BlindsPosted(STAKES, (small_blind(2, chips=3, all_in=True), big_blind(3))),)
    assert not is_round_complete(hand.betting)  # type: ignore[arg-type]


@pytest.mark.parametrize("stack", [4, 10], ids=["short-big-blind", "exactly-the-big-blind"])
def test_a_big_blind_that_posts_its_whole_stack_is_all_in(make_hand: HandFactory, stack: int) -> None:
    """A big blind with fewer chips than the blind, or exactly as many, posts its stack and is all-in."""
    hand = make_hand({1: 1000, 2: 1000, 3: stack}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert recorded(hand) == (BlindsPosted(STAKES, (small_blind(2), big_blind(3, chips=stack, all_in=True))),)


def test_blinds_that_leave_both_players_all_in_complete_the_round_and_return_the_excess(
    make_hand: HandFactory, by_seat: SeatLookup
) -> None:
    """Heads-up, a small blind of 3 and a big blind of 7 are both all-in: the big blind's unmatched 4 go back in the
    same call, then the preflop round completes. Both posts keep their all-in flag, recorded right after posting."""
    hand = make_hand({1: 3, 2: 7}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert recorded(hand) == (
        BlindsPosted(STAKES, (small_blind(1, chips=3, all_in=True), big_blind(2, chips=7, all_in=True))),
        ChipsReturned(2, 4),
        PREFLOP_COMPLETED,
    )
    seats = by_seat(hand)
    assert (seats[1].player.stack, seats[2].player.stack) == (0, 4)


def test_heads_up_big_blind_below_the_small_blind_gets_the_small_blinds_excess_returned(
    make_hand: HandFactory, by_seat: SeatLookup
) -> None:
    """The big blind posts its 3 chips all-in, the small blind's 2 extra chips cannot be matched and go back."""
    hand = make_hand({1: 1000, 2: 3}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert recorded(hand) == (
        BlindsPosted(STAKES, (small_blind(1), big_blind(2, chips=3, all_in=True))),
        ChipsReturned(1, 2),
        PREFLOP_COMPLETED,
    )
    assert by_seat(hand)[1].player.stack == 997


def test_blinds_that_leave_both_players_all_in_for_the_same_chips_return_nothing(make_hand: HandFactory) -> None:
    """Heads-up, two blinds of 4 chips each are both all-in with nothing unmatched: only the completion follows."""
    hand = make_hand({1: 4, 2: 4}, button_seat_number=1)
    initialize_betting(hand, STAKES)

    assert recorded(hand) == (
        BlindsPosted(STAKES, (small_blind(1, chips=4, all_in=True), big_blind(2, chips=4, all_in=True))),
        PREFLOP_COMPLETED,
    )


# =============================================================================
# ACTIONS
# =============================================================================


def test_a_fold_and_a_check_commit_no_chips(started_hand: HandFactory, play: Play) -> None:
    """A fold and a check are recorded as requested with 0 chips."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    before = len(hand.history.events)
    play(hand, (3, FOLD), (5, CALL), (8, CALL), (1, CHECK))

    assert hand.history.events[before:] == (
        ActionTaken(3, FOLD, 0, False),
        ActionTaken(5, CALL, 10, False),
        ActionTaken(8, CALL, 5, False),
        ActionTaken(1, CHECK, 0, False),
        PREFLOP_COMPLETED,
    )


def test_a_raise_keeps_its_target_and_records_the_chips_it_added(started_hand: HandFactory, play: Play) -> None:
    """A raise to 30 from nothing adds 30; the small blind's re-raise to 100 adds only 95 on top of its 5."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    before = len(hand.history.events)
    play(hand, (3, raise_to(30)), (5, FOLD), (8, raise_to(100)))

    assert hand.history.events[before:] == (
        ActionTaken(3, raise_to(30), 30, False),
        ActionTaken(5, FOLD, 0, False),
        ActionTaken(8, raise_to(100), 95, False),
    )


def test_a_call_records_the_chips_needed_to_match_the_bet(started_hand: HandFactory, play: Play) -> None:
    """The small blind calls a raise to 30 by adding 25."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    before = len(hand.history.events)
    play(hand, (3, raise_to(30)), (5, FOLD), (8, CALL))

    assert hand.history.events[before:] == (
        ActionTaken(3, raise_to(30), 30, False),
        ActionTaken(5, FOLD, 0, False),
        ActionTaken(8, CALL, 25, False),
    )


def test_a_bet_keeps_its_target(started_hand: HandFactory, play: Play) -> None:
    """On the flop the small blind bets to 20, recorded as a bet of 20 with 20 chips."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    deal_hole_cards(hand)
    call_around(hand, play, (3, 5, 8))
    play(hand, (1, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    before = len(hand.history.events)

    play(hand, (8, bet(20)))

    assert hand.history.events[before:] == (ActionTaken(8, bet(20), 20, False),)


def test_an_all_in_raise_to_the_whole_stack_is_flagged_all_in(started_hand: HandFactory, play: Play) -> None:
    """Raising to the whole stack leaves the actor all-in right after committing."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 100}, button_seat_number=5)
    before = len(hand.history.events)
    play(hand, (3, raise_to(100)))

    assert hand.history.events[before:] == (ActionTaken(3, raise_to(100), 100, True),)


def test_a_short_all_in_raise_records_its_target_and_its_chips(started_hand: HandFactory, play: Play) -> None:
    """UTG's 15 chips are below the minimum full raise (to 20), so the raise to 15 is a short all-in raise."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 15}, button_seat_number=5)
    assert legal_actions(hand).short_all_in_target == 15
    before = len(hand.history.events)
    play(hand, (3, raise_to(15)))

    assert hand.history.events[before:] == (ActionTaken(3, raise_to(15), 15, True),)


def test_a_short_call_commits_the_whole_stack_all_in_and_the_raisers_excess_is_returned(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup
) -> None:
    """The big blind has 60 and calls a raise to 100 with its remaining 50: the call is all-in, the round completes,
    and the raiser's 40 uncalled chips go back to the raiser."""
    hand = started_hand({5: 1000, 8: 1000, 1: 60, 3: 1000}, button_seat_number=5)
    before = len(hand.history.events)
    play(hand, (3, FOLD), (5, raise_to(100)), (8, FOLD), (1, CALL))

    assert hand.history.events[before:] == (
        ActionTaken(3, FOLD, 0, False),
        ActionTaken(5, raise_to(100), 100, False),
        ActionTaken(8, FOLD, 0, False),
        ActionTaken(1, CALL, 50, True),
        ChipsReturned(5, 40),
        PREFLOP_COMPLETED,
    )
    seats = by_seat(hand)
    assert (seats[5].player.stack, seats[1].player.stack) == (940, 0)


def test_a_bet_that_everyone_folds_to_is_returned_whole_to_the_bettor(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup
) -> None:
    """Everyone calls preflop, the small blind bets on the flop and the rest fold: the whole bet is uncalled."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    deal_hole_cards(hand)
    call_around(hand, play, (3, 5, 8))
    play(hand, (1, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    before = len(hand.history.events)

    play(hand, (8, bet(40)), (1, FOLD), (3, FOLD), (5, FOLD))

    assert hand.history.events[before:] == (
        ActionTaken(8, bet(40), 40, False),
        ActionTaken(1, FOLD, 0, False),
        ActionTaken(3, FOLD, 0, False),
        ActionTaken(5, FOLD, 0, False),
        ChipsReturned(8, 40),
        BettingRoundCompleted(Street.FLOP),
    )
    assert by_seat(hand)[8].player.stack == 990


def test_a_raise_that_everyone_folds_to_returns_only_the_uncalled_part(
    started_hand: HandFactory, play: Play, by_seat: SeatLookup
) -> None:
    """UTG raises to 30 and the rest fold: the big blind's 10 are matched, so 20 of the 30 go back."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    before = len(hand.history.events)
    play(hand, (3, raise_to(30)), (5, FOLD), (8, FOLD), (1, FOLD))

    assert hand.history.events[before:] == (
        ActionTaken(3, raise_to(30), 30, False),
        ActionTaken(5, FOLD, 0, False),
        ActionTaken(8, FOLD, 0, False),
        ActionTaken(1, FOLD, 0, False),
        ChipsReturned(3, 20),
        PREFLOP_COMPLETED,
    )
    assert by_seat(hand)[3].player.stack == 990


def test_a_call_that_matches_the_bet_exactly_returns_nothing(started_hand: HandFactory, play: Play) -> None:
    """Heads-up, the big blind checks its option after a call: the round completes with no return."""
    hand = started_hand({1: 1000, 2: 1000}, button_seat_number=1)
    before = len(hand.history.events)
    play(hand, (1, CALL), (2, CHECK))

    assert hand.history.events[before:] == (
        ActionTaken(1, CALL, 5, False),
        ActionTaken(2, CHECK, 0, False),
        PREFLOP_COMPLETED,
    )


# =============================================================================
# ROUND STARTS AND COMPLETIONS
# =============================================================================


def test_a_betting_round_starts_after_its_street_is_dealt_and_never_for_the_preflop(
    started_hand: HandFactory, play: Play
) -> None:
    """The flop round is recorded as started; the preflop round start is the blinds event alone."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    deal_hole_cards(hand)
    call_around(hand, play, (3, 5, 8))
    play(hand, (1, CHECK))
    deal_next_street(hand)
    before = len(hand.history.events)

    start_betting_round(hand)

    assert hand.history.events[before:] == (BettingRoundStarted(Street.FLOP),)
    assert BettingRoundStarted(Street.PREFLOP) not in hand.history.events


def test_every_completed_round_records_exactly_one_completion(started_hand: HandFactory, play: Play) -> None:
    """Heads-up checked down to the river: four rounds, four completions in street order, one start per later street."""
    hand = started_hand({1: 1000, 2: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CHECK))
    for _ in range(3):
        deal_next_street(hand)
        start_betting_round(hand)
        play(hand, (2, CHECK), (1, CHECK))

    events = hand.history.events
    assert [event for event in events if isinstance(event, BettingRoundCompleted)] == [
        BettingRoundCompleted(Street.PREFLOP),
        BettingRoundCompleted(Street.FLOP),
        BettingRoundCompleted(Street.TURN),
        BettingRoundCompleted(Street.RIVER),
    ]
    assert [event for event in events if isinstance(event, BettingRoundStarted)] == [
        BettingRoundStarted(Street.FLOP),
        BettingRoundStarted(Street.TURN),
        BettingRoundStarted(Street.RIVER),
    ]
    assert not any(isinstance(event, ChipsReturned) for event in events)


def test_a_round_that_is_complete_as_it_starts_records_its_start_then_its_completion_in_one_call(
    started_hand: HandFactory, play: Play
) -> None:
    """After the button calls all-in and the small blind folds, the big blind alone can act, so the flop round starts
    complete: `BettingRoundStarted` then `BettingRoundCompleted`, no return (nothing was collected), and the same on
    the turn."""
    hand = started_hand({1: 10, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, FOLD))
    deal_next_street(hand)
    before = len(hand.history.events)

    start_betting_round(hand)

    assert hand.history.events[before:] == (BettingRoundStarted(Street.FLOP), BettingRoundCompleted(Street.FLOP))
    deal_next_street(hand)
    before = len(hand.history.events)
    start_betting_round(hand)
    assert hand.history.events[before:] == (BettingRoundStarted(Street.TURN), BettingRoundCompleted(Street.TURN))


def test_an_open_round_start_records_no_completion(started_hand: HandFactory, play: Play) -> None:
    """A round with players to act records its start only."""
    hand = started_hand({1: 1000, 2: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)

    assert not isinstance(hand.history.events[-1], BettingRoundCompleted)


# =============================================================================
# WHOLE HISTORIES
# =============================================================================


def test_an_all_in_and_a_short_call_record_a_return_and_the_completion_inside_the_calling_operation(
    started_hand: HandFactory, play: Play
) -> None:
    """Heads-up, the small blind shoves 100 and the big blind calls with its remaining 50: the call, the return of the
    shover's 40 uncalled chips and the completion are all recorded by the one `apply_action`."""
    hand = started_hand({1: 100, 2: 60}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, raise_to(100)))
    length = len(hand.history.events)
    assert hand.history.events[1:2] == (BlindsPosted(STAKES, (small_blind(1), big_blind(2))),)
    assert hand.history.events[3:] == (ActionTaken(1, raise_to(100), 95, True),)

    play(hand, (2, CALL))

    assert hand.history.events[length:] == (ActionTaken(2, CALL, 50, True), ChipsReturned(1, 40), PREFLOP_COMPLETED)
    assert len(hand.history.events) == 7


def test_a_three_handed_hand_has_this_event_order_across_operations(started_hand: HandFactory, play: Play) -> None:
    """Preflop raise, call and fold, then a flop bet and a fold: events follow the order of the successful calls (the
    dealt cards are checked in the Hold'em dealing events)."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, raise_to(30)), (2, CALL), (3, FOLD))
    deal_next_street(hand)
    start_betting_round(hand)
    play(hand, (2, bet(40)), (1, FOLD))

    events = hand.history.events
    assert events[3:7] == (
        ActionTaken(1, raise_to(30), 30, False),
        ActionTaken(2, CALL, 25, False),
        ActionTaken(3, FOLD, 0, False),
        PREFLOP_COMPLETED,
    )
    assert isinstance(events[7], StreetDealt) and events[7].street is Street.FLOP
    assert events[8:] == (
        BettingRoundStarted(Street.FLOP),
        ActionTaken(2, bet(40), 40, False),
        ActionTaken(1, FOLD, 0, False),
        ChipsReturned(2, 40),
        BettingRoundCompleted(Street.FLOP),
    )


# =============================================================================
# REJECTIONS AND READS
# =============================================================================


def completed_round_hand(started_hand: HandFactory, play: Play) -> PokerHand:
    """A hand whose preflop round is complete (the big blind won uncontested) and never started another."""
    hand = started_hand({1: 1000, 2: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, FOLD))
    return hand


def test_initialize_betting_rejections_leave_the_history_as_it_was(make_hand: HandFactory) -> None:
    """A second initialization, and one on a later street, are rejected and record nothing."""
    hand = make_hand(FOUR_HANDED, button_seat_number=5)
    initialize_betting(hand, STAKES)
    before = hand.history
    with pytest.raises(BettingAlreadyInitializedError):
        initialize_betting(hand, STAKES)
    assert hand.history == before

    later = make_hand(FOUR_HANDED, button_seat_number=5)
    deal_hole_cards(later)
    deal_next_street(later)
    before = later.history
    with pytest.raises(BettingNotPreflopError):
        initialize_betting(later, STAKES)
    assert later.history == before


def test_apply_action_rejections_leave_the_history_as_it_was(
    make_hand: HandFactory, started_hand: HandFactory, play: Play
) -> None:
    """Betting not initialized, the wrong seat, a complete round, and an illegal action each record nothing."""
    uninitialized = make_hand(FOUR_HANDED, button_seat_number=5)
    before = uninitialized.history
    with pytest.raises(BettingNotInitializedError):
        apply_action(uninitialized, 3, CALL)
    assert uninitialized.history == before

    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    before = hand.history
    with pytest.raises(NotPlayersTurnError):
        apply_action(hand, 5, CALL)
    with pytest.raises(IllegalActionError):
        apply_action(hand, 3, CHECK)
    with pytest.raises(IllegalActionError):
        apply_action(hand, 3, raise_to(11))
    assert hand.history == before

    complete = completed_round_hand(started_hand, play)
    before = complete.history
    with pytest.raises(NotPlayersTurnError):
        apply_action(complete, 2, CHECK)
    assert complete.history == before


def test_start_betting_round_rejections_leave_the_history_as_it_was(
    make_hand: HandFactory, started_hand: HandFactory, play: Play
) -> None:
    """No betting, an unfinished round, and a round already started each record nothing."""
    uninitialized = make_hand(FOUR_HANDED, button_seat_number=5)
    before = uninitialized.history
    with pytest.raises(BettingNotInitializedError):
        start_betting_round(uninitialized)
    assert uninitialized.history == before

    open_round = started_hand(FOUR_HANDED, button_seat_number=5)
    before = open_round.history
    with pytest.raises(BettingRoundNotCompleteError):
        start_betting_round(open_round)
    assert open_round.history == before

    same_street = completed_round_hand(started_hand, play)
    before = same_street.history
    with pytest.raises(BettingRoundAlreadyStartedError):
        start_betting_round(same_street)
    assert same_street.history == before


def test_derived_reads_record_nothing(started_hand: HandFactory, play: Play) -> None:
    """Legal actions, pots, the middle pot and the betting-closed check never change the history."""
    hand = started_hand({1: 1000, 2: 1000, 3: 60}, button_seat_number=1)
    deal_hole_cards(hand)
    for _ in range(2):
        before = hand.history
        legal_actions(hand)
        pots(hand)
        middle_pot(hand)
        is_betting_closed(hand)
        assert hand.betting is not None
        is_round_complete(hand.betting)
        assert hand.history == before
        assert hand.betting.current_actor is not None
        play(hand, (hand.betting.current_actor, CALL))

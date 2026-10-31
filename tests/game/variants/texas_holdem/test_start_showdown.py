"""Hold'em showdowns through the public `start_showdown`, and the showdown a direct `settle_hand` records.

Every hand reaches its state through the real dealing and betting operations, from a deck stacked by the shared
`stacked_hand` fixture. Unless a test says otherwise the three seats are the button (1), the small blind (2) and the big
blind (3); preflop seat 1 acts first and on every later street seat 2 does. With another button the seats keep their
numbers but the order moves: button 2 makes seat 3 the small blind and seat 1 the big blind, seat 2 acts first preflop
and seat 3 first on later streets. Seat 2 holds a set of kings on the default board, so it wins every showdown that is
not set up otherwise. `start_showdown` records seats, not cards, so most tests never look at the cards.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

import go_poker.game.variants.texas_holdem.showdown as showdown_module
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import HandAlreadySettledError
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    IncompleteBoardError,
    ShowdownAlreadyStartedError,
    ShowdownNotReadyError,
    ShowdownNotStartedError,
    UncontestedHandError,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
ROYAL_FLUSH_BOARD = "As Ks Qs Js Ts"
TYING_HOLES = {1: "2c 3d", 2: "4h 5c", 3: "6d 7h"}  # all three play the royal flush on the board

PREVIOUS_STREET = {Street.FLOP: Street.PREFLOP, Street.TURN: Street.FLOP, Street.RIVER: Street.TURN}

ALL_IN = ShowdownKind.ALL_IN
INTERACTIVE = ShowdownKind.INTERACTIVE

SHOW = ShowdownAction.SHOW

type NewHand = Callable[..., PokerHand]


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    for seat, action in actions:
        apply_action(hand, seat, action)


def next_street(hand: PokerHand) -> None:
    """Deal the next street, then start its betting round."""
    deal_next_street(hand)
    start_betting_round(hand)


def check_street(hand: PokerHand) -> None:
    """Everyone still to act checks, in turn."""
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


def call_preflop(hand: PokerHand) -> None:
    """Everyone calls the big blind and the big blind checks."""
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        apply_action(hand, actor, CHECK if hand.betting.pending_actors == {actor} else CALL)


def check_to(hand: PokerHand, street: Street) -> None:
    """From a hand that has just completed its preflop round, check every street up to and including `street`."""
    while hand.street is not street:
        next_street(hand)
        check_street(hand)


def snapshot(hand: PokerHand) -> dict[str, Any]:
    """Everything about the hand, for comparing before and after (the deck by its size: drawing is its only change)."""
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "showdown": hand.showdown,
        "players": [
            (
                state.seat_number,
                state.player.stack,
                state.folded,
                state.all_in,
                state.street_contribution,
                state.total_contribution,
                list(state.hole_cards),
            )
            for state in hand.players
        ],
        "pots": pots(hand),
        "middle_pot": middle_pot(hand),
    }


def started(hand: PokerHand) -> Showdown:
    assert hand.showdown is not None
    return hand.showdown


def start_and_check(hand: PokerHand) -> Showdown:
    """Start the showdown and check that only `hand.showdown` changed; return it."""
    before = snapshot(hand)

    start_showdown(hand)

    after = snapshot(hand)
    assert before["showdown"] is None
    assert {k: v for k, v in after.items() if k != "showdown"} == {k: v for k, v in before.items() if k != "showdown"}
    return started(hand)


def assert_start_rejected(hand: PokerHand, error: type[Exception]) -> None:
    """`start_showdown` raises `error` and leaves the hand exactly as it was, showdown included."""
    before = snapshot(hand)

    with pytest.raises(error):
        start_showdown(hand)

    assert snapshot(hand) == before
    assert hand.showdown is before["showdown"]


def assert_settle_rejected(hand: PokerHand, error: type[Exception]) -> None:
    """`settle_hand` raises `error` and leaves the hand exactly as it was, showdown included."""
    before = snapshot(hand)

    with pytest.raises(error):
        settle_hand(hand)

    assert snapshot(hand) == before
    assert hand.settlement is None
    assert hand.showdown is before["showdown"]


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    """A stacked hand with its blinds posted and hole cards dealt; takes optional stacks, holes, board and button."""

    def build(
        stacks: dict[int, int] | None = None,
        holes: dict[int, str] | None = None,
        board: str = BOARD,
        button: int = 1,
    ) -> PokerHand:
        hand = stacked_hand(holes or HOLES, board, button=button, stacks=stacks)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        return hand

    return build


ALL_IN_STACKS = {1: 100, 2: 100, 3: 100}


# -----------------------------------------------------------------------------
# ALL_IN showdowns: betting closed, every live hand tabled at once, in canonical order
# -----------------------------------------------------------------------------


def test_everyone_all_in_preflop_is_started_at_once_with_the_board_still_empty(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    assert hand.board == []

    showdown = start_and_check(hand)

    assert showdown == Showdown(ALL_IN, (2, 3, 1))


def test_the_all_in_showdown_lists_live_seats_in_canonical_order_whatever_the_betting_order(new_hand: NewHand) -> None:
    """Button 2: seat 3 is the first seat left of the button and seat 2 the button, so seats are listed 3, 1, 2 although
    seat 1 raised last and seat 2 acted first."""
    hand = new_hand(stacks=ALL_IN_STACKS, button=2)
    play(hand, (2, CALL), (3, CALL), (1, raise_to(100)), (2, CALL), (3, CALL))

    assert start_and_check(hand) == Showdown(ALL_IN, (3, 1, 2))


def test_a_folded_seat_never_appears_in_an_all_in_showdown(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, FOLD), (3, CALL))

    assert start_and_check(hand) == Showdown(ALL_IN, (3, 1))


def test_a_player_with_chips_facing_only_an_all_in_opponent_is_in_the_showdown_with_it(new_hand: NewHand) -> None:
    """Seat 2 covers the all-in seat 1 and calls, so seat 2 is not all-in itself; betting is closed all the same."""
    hand = new_hand(stacks={1: 100, 2: 1000, 3: 1000})
    play(hand, (1, raise_to(100)), (2, CALL), (3, FOLD))
    assert not next(state for state in hand.players if state.seat_number == 2).all_in

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 1))


@pytest.mark.parametrize("street", [Street.FLOP, Street.TURN])
def test_an_all_in_on_the_flop_or_turn_starts_with_the_board_incomplete(new_hand: NewHand, street: Street) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    call_preflop(hand)
    check_to(hand, PREVIOUS_STREET[street])
    next_street(hand)
    play(hand, (2, bet(90)), (3, CALL), (1, CALL))
    assert hand.street is street
    assert len(hand.board) < 5

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 3, 1))


def test_the_blinds_alone_closing_the_preflop_round_start_an_all_in_showdown_at_once(new_hand: NewHand) -> None:
    """Heads-up the small blind posts its whole 5 chips and is all-in; the big blind owes nothing, so the round is
    complete as soon as the blinds are posted."""
    hand = new_hand(stacks={1: 5, 2: 1000}, holes={1: "Ah Ad", 2: "Kd Kh"})
    assert hand.betting is not None
    assert hand.betting.current_actor is None

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 1))


def test_a_player_all_in_from_an_earlier_street_makes_the_river_showdown_all_in_in_canonical_order(
    new_hand: NewHand,
) -> None:
    """Seat 1 is all-in preflop; seats 2 and 3 play on and seat 3 raises last on the river. The aggressor is ignored:
    the order is canonical, not seat 3 first."""
    hand = new_hand(stacks={1: 50, 2: 1000, 3: 1000})
    play(hand, (1, raise_to(50)), (2, CALL), (3, CALL))
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, bet(20)), (3, raise_to(60)), (2, CALL))
    assert hand.betting is not None
    assert hand.betting.last_aggressor == 3

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 3, 1))


def test_a_river_all_in_call_makes_the_showdown_all_in(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, bet(90)), (3, CALL), (1, CALL))

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 3, 1))


def test_a_river_bet_partly_returned_by_a_short_all_in_call_is_an_all_in_showdown(new_hand: NewHand) -> None:
    """Seat 2 bets its whole 90 and seat 3, with 30 left, calls all-in; the 60 nobody matched goes back, so seat 2 is no
    longer all-in once the round is collected, but seat 3 is, and the showdown is ALL_IN with the aggressor ignored."""
    hand = new_hand(stacks={1: 1000, 2: 100, 3: 40})
    river_round(hand)
    play(hand, (2, bet(90)), (3, CALL), (1, FOLD))
    seat_2, seat_3 = (next(state for state in hand.players if state.seat_number == seat) for seat in (2, 3))
    assert (seat_2.all_in, seat_3.all_in, seat_2.player.stack) == (False, True, 60)

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 3))


# -----------------------------------------------------------------------------
# INTERACTIVE showdowns: the river round completed with nobody all-in, in the river decision order
# -----------------------------------------------------------------------------


def river_round(hand: PokerHand) -> None:
    """Call preflop and check down to the river, whose round is started."""
    call_preflop(hand)
    check_to(hand, Street.TURN)
    next_street(hand)


def test_with_no_river_bet_the_first_live_seat_left_of_the_button_decides_first(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    check_street(hand)

    assert start_and_check(hand) == Showdown(INTERACTIVE, (2, 3, 1))


def test_the_river_bettor_decides_first_and_the_order_wraps_past_the_button(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, CHECK), (3, bet(10)), (1, CALL), (2, CALL))

    assert start_and_check(hand) == Showdown(INTERACTIVE, (3, 1, 2))


def test_the_last_river_raiser_decides_first_not_the_first_bettor(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, bet(10)), (3, raise_to(30)), (1, CALL), (2, CALL))

    assert start_and_check(hand) == Showdown(INTERACTIVE, (3, 1, 2))


def test_a_folded_seat_is_skipped_in_the_decision_order(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, bet(10)), (3, FOLD), (1, CALL))

    assert start_and_check(hand) == Showdown(INTERACTIVE, (2, 1))


def test_the_button_can_decide_first(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, CHECK), (3, CHECK), (1, bet(10)), (2, CALL), (3, CALL))

    assert start_and_check(hand) == Showdown(INTERACTIVE, (1, 2, 3))


def test_an_earlier_streets_aggressor_does_not_carry_into_the_river(new_hand: NewHand) -> None:
    """Seat 3 bets the flop and is called; the river is checked down, so the first seat left of the button
    decides first, not seat 3."""
    hand = new_hand()
    call_preflop(hand)
    next_street(hand)
    play(hand, (2, CHECK), (3, bet(10)), (1, CALL), (2, CALL))
    check_to(hand, Street.TURN)
    next_street(hand)
    check_street(hand)

    assert start_and_check(hand) == Showdown(INTERACTIVE, (2, 3, 1))


def test_a_different_button_changes_the_river_order(new_hand: NewHand) -> None:
    """Button 2: the order is canonical 3, 1, 2 with no river bet."""
    hand = new_hand(button=2)
    river_round(hand)
    check_street(hand)

    assert start_and_check(hand) == Showdown(INTERACTIVE, (3, 1, 2))


def test_heads_up_the_big_blind_decides_first_with_no_river_bet(new_hand: NewHand) -> None:
    hand = new_hand(holes={1: "Ah Ad", 2: "Kd Kh"})
    river_round(hand)
    check_street(hand)

    assert start_and_check(hand) == Showdown(INTERACTIVE, (2, 1))


# -----------------------------------------------------------------------------
# Rejections
# -----------------------------------------------------------------------------


def test_a_hand_without_a_betting_state_is_rejected(stacked_hand: NewHand) -> None:
    hand = stacked_hand(HOLES, BOARD)

    assert_start_rejected(hand, BettingNotInitializedError)


def test_a_hand_whose_showdown_already_started_is_rejected_and_keeps_its_showdown(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    showdown = start_and_check(hand)

    assert_start_rejected(hand, ShowdownAlreadyStartedError)
    assert hand.showdown is showdown


def test_an_interactive_showdown_that_already_started_is_rejected_at_any_point_of_its_decisions(
    new_hand: NewHand,
) -> None:
    hand = new_hand()
    river_round(hand)
    check_street(hand)
    start_showdown(hand)

    assert_start_rejected(hand, ShowdownAlreadyStartedError)
    apply_showdown_action(hand, 2, SHOW)
    assert_start_rejected(hand, ShowdownAlreadyStartedError)
    apply_showdown_action(hand, 3, SHOW)
    apply_showdown_action(hand, 1, SHOW)
    assert_start_rejected(hand, ShowdownAlreadyStartedError)
    assert started(hand).is_complete


@pytest.mark.parametrize("street", [Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER])
def test_a_hand_won_uncontested_has_no_showdown_to_start(new_hand: NewHand, street: Street) -> None:
    hand = new_hand()
    if street is Street.PREFLOP:
        play(hand, (1, FOLD), (2, FOLD))
    else:
        call_preflop(hand)
        check_to(hand, PREVIOUS_STREET[street])
        next_street(hand)
        play(hand, (2, bet(20)), (3, FOLD), (1, FOLD))
    assert hand.street is street

    assert_start_rejected(hand, UncontestedHandError)


def test_a_preflop_round_in_progress_is_not_ready(new_hand: NewHand) -> None:
    assert_start_rejected(new_hand(), ShowdownNotReadyError)


def test_a_flop_round_in_progress_is_not_ready(new_hand: NewHand) -> None:
    hand = new_hand()
    call_preflop(hand)
    next_street(hand)
    play(hand, (2, CHECK))

    assert_start_rejected(hand, ShowdownNotReadyError)


def test_a_completed_flop_round_with_players_able_to_act_is_not_ready(new_hand: NewHand) -> None:
    hand = new_hand()
    call_preflop(hand)
    next_street(hand)
    check_street(hand)

    assert_start_rejected(hand, ShowdownNotReadyError)


def test_a_river_dealt_without_its_round_started_is_not_ready(new_hand: NewHand) -> None:
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.TURN)
    deal_next_street(hand)
    assert hand.street is Street.RIVER

    assert_start_rejected(hand, ShowdownNotReadyError)


def test_a_river_round_in_progress_is_not_ready(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, CHECK))

    assert_start_rejected(hand, ShowdownNotReadyError)


def test_a_river_bet_still_to_be_answered_is_not_ready(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, bet(10)), (3, CALL))

    assert_start_rejected(hand, ShowdownNotReadyError)


def test_start_showdown_does_not_check_the_board_or_the_hole_cards(stacked_hand: NewHand) -> None:
    """It records seats: betting closed before any card is dealt starts its showdown all the same."""
    hand = stacked_hand(HOLES, BOARD, stacks=ALL_IN_STACKS)
    initialize_betting(hand, STAKES)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    assert not any(state.hole_cards for state in hand.players)

    assert start_and_check(hand) == Showdown(ALL_IN, (2, 3, 1))


def test_an_interactive_showdown_starts_with_no_decisions_and_the_first_decider_to_act(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    check_street(hand)

    showdown = start_and_check(hand)

    assert (showdown.decisions, showdown.current_decider, showdown.is_complete) == ((), 2, False)
    assert (showdown.shown, showdown.mucked, showdown.contenders) == ((), (), (2, 3, 1))


def test_an_all_in_showdown_starts_complete_with_every_hand_shown(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))

    showdown = start_and_check(hand)

    assert (showdown.decisions, showdown.current_decider, showdown.is_complete) == ((), None, True)
    assert (showdown.shown, showdown.mucked, showdown.contenders) == ((2, 3, 1), (), (2, 3, 1))


# -----------------------------------------------------------------------------
# Rejection precedence: the reachable pairs
# -----------------------------------------------------------------------------


def settled_all_in_runout(new_hand: NewHand) -> PokerHand:
    hand = new_hand(stacks=ALL_IN_STACKS, holes=TYING_HOLES, board=ROYAL_FLUSH_BOARD)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    run_out(hand)
    settle_hand(hand)
    return hand


def test_a_settled_hand_is_reported_as_settled_before_it_is_reported_as_already_started(new_hand: NewHand) -> None:
    hand = settled_all_in_runout(new_hand)
    assert hand.showdown is not None

    assert_start_rejected(hand, HandAlreadySettledError)


def test_a_settled_hand_is_reported_as_settled_before_it_is_reported_as_not_ready(new_hand: NewHand) -> None:
    """Everyone was paid in the split, so none is all-in and betting looks open again; the settled error still wins."""
    hand = settled_all_in_runout(new_hand)
    assert not any(state.all_in for state in hand.players)

    assert_start_rejected(hand, HandAlreadySettledError)


def test_a_settled_hand_is_reported_as_settled_before_it_is_reported_as_uncontested(new_hand: NewHand) -> None:
    hand = new_hand()
    play(hand, (1, FOLD), (2, FOLD))
    settle_hand(hand)

    assert_start_rejected(hand, HandAlreadySettledError)


# -----------------------------------------------------------------------------
# Direct settlement and the showdown it records
# -----------------------------------------------------------------------------


def run_out(hand: PokerHand) -> None:
    while hand.street is not Street.RIVER:
        deal_next_street(hand)


def test_settling_an_all_in_runout_directly_records_an_all_in_showdown(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    run_out(hand)
    assert hand.showdown is None

    settle_hand(hand)

    assert hand.showdown == Showdown(ALL_IN, (2, 3, 1))


def test_settling_a_river_showdown_directly_without_starting_it_is_rejected(new_hand: NewHand) -> None:
    """An interactive showdown is never started or decided by the settlement."""
    hand = new_hand()
    river_round(hand)
    play(hand, (2, CHECK), (3, bet(10)), (1, CALL), (2, CALL))

    assert_settle_rejected(hand, ShowdownNotStartedError)
    assert hand.showdown is None


def test_a_river_all_in_that_ends_in_a_tie_still_records_all_in(new_hand: NewHand) -> None:
    """Everyone is paid and so no longer all-in after the payout, but the kind was read before it."""
    hand = new_hand(stacks=ALL_IN_STACKS, holes=TYING_HOLES, board=ROYAL_FLUSH_BOARD)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, bet(90)), (3, CALL), (1, CALL))

    settle_hand(hand)

    assert not any(state.all_in for state in hand.players)
    assert hand.showdown == Showdown(ALL_IN, (2, 3, 1))


def test_settling_an_uncontested_hand_records_no_showdown(new_hand: NewHand) -> None:
    hand = new_hand()
    play(hand, (1, FOLD), (2, FOLD))

    settle_hand(hand)

    assert hand.showdown is None


def test_settlement_keeps_an_existing_all_in_showdown_as_it_is(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    showdown = start_and_check(hand)
    run_out(hand)

    settle_hand(hand)

    assert hand.showdown is showdown


def test_a_completed_river_showdown_is_kept_by_settlement(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, bet(10)), (3, CALL), (1, CALL))
    start_showdown(hand)
    for seat in (2, 3, 1):
        apply_showdown_action(hand, seat, SHOW)
    showdown = started(hand)

    settle_hand(hand)

    assert hand.showdown is showdown
    assert showdown == Showdown(INTERACTIVE, (2, 3, 1), (SHOW, SHOW, SHOW))


def test_a_rejected_settlement_for_an_incomplete_board_records_no_showdown(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))

    assert_settle_rejected(hand, IncompleteBoardError)


def test_a_rejected_settlement_that_is_not_ready_records_no_showdown(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    play(hand, (2, bet(10)), (3, CALL))

    assert_settle_rejected(hand, ShowdownNotReadyError)


def test_the_all_in_showdown_is_recorded_only_after_the_settlement_succeeds(
    new_hand: NewHand, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every rejection `settle_hand` can make happens before the payout; this fails the payout itself, which no public
    sequence can do, to check that the candidate `ALL_IN` showdown waits for it."""
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    run_out(hand)

    def failing_settle(hand: PokerHand, ranks: object, contenders: object) -> None:
        raise RuntimeError("the settlement failed")

    monkeypatch.setattr(showdown_module, "_settle", failing_settle)

    assert_settle_rejected(hand, RuntimeError)
    assert hand.showdown is None


def test_a_rejected_settlement_keeps_an_existing_showdown(new_hand: NewHand) -> None:
    hand = new_hand(stacks=ALL_IN_STACKS)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    showdown = start_and_check(hand)

    assert_settle_rejected(hand, IncompleteBoardError)
    assert hand.showdown is showdown


def test_a_settled_hand_cannot_start_a_showdown(new_hand: NewHand) -> None:
    hand = new_hand()
    river_round(hand)
    check_street(hand)
    start_showdown(hand)
    for seat in (2, 3, 1):
        apply_showdown_action(hand, seat, SHOW)
    settle_hand(hand)
    showdown = started(hand)

    with pytest.raises(HandAlreadySettledError):
        start_showdown(hand)
    assert hand.showdown is showdown

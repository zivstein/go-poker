"""Hold'em showdown decisions through the public `apply_showdown_action`.

Every hand reaches its state through the real dealing, betting and `start_showdown` operations, from a deck stacked by
the shared `stacked_hand` fixture. Unless a test says otherwise the three seats are the button (1), the small blind (2)
and the big blind (3), the hand is checked down to the river, and the decision order is seat 2, 3, 1. A river bet moves
the order: it starts with the last bettor or raiser. A decision records seats and decisions, not cards, so these tests
never look at the cards.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import HandSettled, ShowdownDecided
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import HandAlreadySettledError
from go_poker.game.showdown import NotShowdownTurnError, Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    ShowdownNotStartedError,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"

INTERACTIVE = ShowdownKind.INTERACTIVE
ALL_IN = ShowdownKind.ALL_IN

type NewHand = Callable[..., PokerHand]


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    for seat, action in actions:
        apply_action(hand, seat, action)


def next_street(hand: PokerHand) -> None:
    deal_next_street(hand)
    start_betting_round(hand)


def check_street(hand: PokerHand) -> None:
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


def call_preflop(hand: PokerHand) -> None:
    """Everyone calls the big blind and the big blind checks."""
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        apply_action(hand, actor, CHECK if hand.betting.pending_actors == {actor} else CALL)


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
        "history": hand.history,
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
        "legal_actions": legal_actions(hand),
    }


def showdown_of(hand: PokerHand) -> Showdown:
    assert hand.showdown is not None
    return hand.showdown


def decide_and_check(hand: PokerHand, seat: int, action: ShowdownAction) -> Showdown:
    """Apply the decision and check that only `hand.showdown` and the history changed, by exactly that decision and
    exactly one `ShowdownDecided` for it; return the showdown."""
    before = snapshot(hand)
    before_showdown = showdown_of(hand)

    apply_showdown_action(hand, seat, action)

    after = snapshot(hand)
    changed = ("showdown", "history")
    assert {k: v for k, v in after.items() if k not in changed} == {k: v for k, v in before.items() if k not in changed}
    assert after["history"].events == (*before["history"].events, ShowdownDecided(seat, action))
    assert not after["history"].is_complete  # deciding does not settle the hand
    assert showdown_of(hand) == Showdown(
        before_showdown.kind, before_showdown.order, (*before_showdown.decisions, action)
    )
    assert showdown_of(hand) is not before_showdown
    return showdown_of(hand)


def assert_rejected(hand: PokerHand, seat: int, action: ShowdownAction, error: type[Exception]) -> None:
    """The decision raises `error` and leaves the hand exactly as it was, showdown included (the same object)."""
    before = snapshot(hand)

    with pytest.raises(error):
        apply_showdown_action(hand, seat, action)

    assert snapshot(hand) == before
    assert hand.showdown is before["showdown"]


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    """A stacked hand with its blinds posted and hole cards dealt, checked down to the river with its showdown started.

    `river_actions` are played in the river round first (the round is completed by the test's own actions, so they must
    end it); with none, the river is checked down. `stacks` and `holes` default to the usual ones.
    """

    def build(
        river_actions: tuple[tuple[int, Action], ...] = (),
        stacks: dict[int, int] | None = None,
        holes: dict[int, str] | None = None,
        start: bool = True,
    ) -> PokerHand:
        hand = stacked_hand(holes or HOLES, BOARD, stacks=stacks)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        call_preflop(hand)
        while hand.street is not Street.TURN:
            next_street(hand)
            check_street(hand)
        next_street(hand)
        if river_actions:
            play(hand, *river_actions)
        else:
            check_street(hand)
        if start:
            start_showdown(hand)
        return hand

    return build


# =============================================================================
# FIRST DECISION
# =============================================================================


def test_the_first_decider_shows_and_the_next_seat_is_to_decide(new_hand: NewHand) -> None:
    hand = new_hand()
    assert showdown_of(hand) == Showdown(INTERACTIVE, (2, 3, 1))

    showdown = decide_and_check(hand, 2, SHOW)

    assert (showdown.shown, showdown.mucked, showdown.contenders) == ((2,), (), (2, 3, 1))
    assert (showdown.current_decider, showdown.is_complete) == (3, False)


def test_the_first_decider_mucks_and_stays_unfolded_with_its_chips_in_the_pot(new_hand: NewHand) -> None:
    """A muck is showdown state only: seat 2 is not folded and its contributions and the betting state are untouched
    (decide_and_check compares every one of them)."""
    hand = new_hand()
    seat_two = next(state for state in hand.players if state.seat_number == 2)
    contribution = seat_two.total_contribution

    showdown = decide_and_check(hand, 2, MUCK)

    assert (showdown.shown, showdown.mucked, showdown.contenders) == ((), (2,), (3, 1))
    assert (showdown.current_decider, showdown.is_complete) == (3, False)
    assert (seat_two.folded, seat_two.total_contribution, seat_two.all_in) == (False, contribution, False)
    assert 2 in pots(hand)[0].eligible_seats


def test_a_decision_may_always_be_show_or_muck_whatever_has_been_shown(new_hand: NewHand) -> None:
    """The engine does not judge whether a shown hand already beats the decider's: seat 3 may muck or show after
    seat 2 showed a set of kings, and seat 2 may muck the best hand."""
    shown_then_muck = new_hand()
    decide_and_check(shown_then_muck, 2, SHOW)
    decide_and_check(shown_then_muck, 3, MUCK)

    muck_then_show = new_hand()
    decide_and_check(muck_then_show, 2, MUCK)
    decide_and_check(muck_then_show, 3, SHOW)

    assert showdown_of(shown_then_muck).decisions == (SHOW, MUCK)
    assert showdown_of(muck_then_show).decisions == (MUCK, SHOW)


def test_heads_up_a_first_muck_completes_the_showdown_and_the_other_seat_is_the_only_contender(
    new_hand: NewHand,
) -> None:
    hand = new_hand(holes={1: "Ah Ad", 2: "Kd Kh"})
    assert showdown_of(hand).order == (2, 1)

    showdown = decide_and_check(hand, 2, MUCK)

    assert (showdown.contenders, showdown.current_decider, showdown.is_complete) == ((1,), None, True)


def test_heads_up_a_first_show_leaves_the_other_seat_to_decide(new_hand: NewHand) -> None:
    hand = new_hand(holes={1: "Ah Ad", 2: "Kd Kh"})

    showdown = decide_and_check(hand, 2, SHOW)

    assert (showdown.shown, showdown.current_decider, showdown.is_complete) == ((2,), 1, False)


def test_the_river_aggressor_decides_first_and_the_order_wraps(new_hand: NewHand) -> None:
    hand = new_hand(river_actions=((2, CHECK), (3, bet(10)), (1, CALL), (2, CALL)))
    assert showdown_of(hand).order == (3, 1, 2)

    decide_and_check(hand, 3, SHOW)
    decide_and_check(hand, 1, MUCK)
    showdown = decide_and_check(hand, 2, SHOW)

    assert (showdown.shown, showdown.mucked, showdown.contenders, showdown.is_complete) == (
        (3, 2),
        (1,),
        (3, 2),
        True,
    )


# =============================================================================
# COMPLETION
# =============================================================================


def test_every_seat_deciding_completes_the_showdown_with_each_decision_recorded_in_order(new_hand: NewHand) -> None:
    hand = new_hand()

    decide_and_check(hand, 2, SHOW)
    decide_and_check(hand, 3, SHOW)
    showdown = decide_and_check(hand, 1, SHOW)

    assert showdown == Showdown(INTERACTIVE, (2, 3, 1), (SHOW, SHOW, SHOW))
    assert (showdown.current_decider, showdown.is_complete) == (None, True)


def test_a_muck_by_all_but_one_completes_the_showdown_and_the_last_seat_is_never_asked(new_hand: NewHand) -> None:
    hand = new_hand()

    decide_and_check(hand, 2, MUCK)
    showdown = decide_and_check(hand, 3, MUCK)

    assert (showdown.contenders, showdown.shown, showdown.current_decider, showdown.is_complete) == (
        (1,),
        (),
        None,
        True,
    )
    assert_rejected(hand, 1, SHOW, NotShowdownTurnError)
    assert_rejected(hand, 1, MUCK, NotShowdownTurnError)
    assert [event for event in hand.history.events if isinstance(event, ShowdownDecided)] == [
        ShowdownDecided(2, MUCK),
        ShowdownDecided(3, MUCK),
    ]  # the last contender is never asked, so it has no decision
    settle_hand(hand)
    assert hand.settlement is not None and hand.settlement.showdown_ranks == ()
    assert hand.history.events[-2:] == (ShowdownDecided(3, MUCK), HandSettled(hand.settlement))


def test_a_last_decider_may_muck_after_everyone_else_showed(new_hand: NewHand) -> None:
    hand = new_hand()
    decide_and_check(hand, 2, SHOW)
    decide_and_check(hand, 3, SHOW)

    showdown = decide_and_check(hand, 1, MUCK)

    assert (showdown.shown, showdown.mucked, showdown.contenders, showdown.is_complete) == ((2, 3), (1,), (2, 3), True)


def test_deciding_does_not_settle_the_hand_and_the_decided_hand_then_settles(new_hand: NewHand) -> None:
    hand = new_hand()
    for seat in (2, 3, 1):
        decide_and_check(hand, seat, SHOW)
    assert hand.settlement is None
    before = hand.history

    settle_hand(hand)

    assert hand.settlement is not None
    assert hand.history.events == (*before.events, HandSettled(hand.settlement))


# =============================================================================
# REJECTIONS
# =============================================================================


@pytest.mark.parametrize("seat", [3, 1], ids=["second-seat", "last-seat"])
def test_a_later_seat_cannot_decide_before_its_turn(new_hand: NewHand, seat: int) -> None:
    hand = new_hand()

    assert_rejected(hand, seat, SHOW, NotShowdownTurnError)
    assert_rejected(hand, seat, MUCK, NotShowdownTurnError)


@pytest.mark.parametrize("action", [SHOW, MUCK])
def test_a_seat_that_already_decided_cannot_decide_again(new_hand: NewHand, action: ShowdownAction) -> None:
    hand = new_hand()
    decide_and_check(hand, 2, SHOW)

    assert_rejected(hand, 2, action, NotShowdownTurnError)


def test_a_seat_that_mucked_cannot_decide_again(new_hand: NewHand) -> None:
    hand = new_hand()
    decide_and_check(hand, 2, MUCK)

    assert_rejected(hand, 2, SHOW, NotShowdownTurnError)


def test_a_folded_seat_cannot_decide(new_hand: NewHand) -> None:
    """Seat 3 folds on the river, so only seats 2 and 1 are in the showdown."""
    hand = new_hand(river_actions=((2, bet(10)), (3, FOLD), (1, CALL)))
    assert showdown_of(hand).order == (2, 1)

    assert_rejected(hand, 3, SHOW, NotShowdownTurnError)
    assert_rejected(hand, 3, MUCK, NotShowdownTurnError)
    decide_and_check(hand, 2, SHOW)
    assert_rejected(hand, 3, SHOW, NotShowdownTurnError)


@pytest.mark.parametrize("seat", [0, 4, 9, -1])
def test_an_unknown_seat_cannot_decide(new_hand: NewHand, seat: int) -> None:
    hand = new_hand()

    assert_rejected(hand, seat, SHOW, NotShowdownTurnError)
    decide_and_check(hand, 2, SHOW)
    assert_rejected(hand, seat, MUCK, NotShowdownTurnError)


def test_after_everyone_decided_every_seat_is_rejected(new_hand: NewHand) -> None:
    hand = new_hand()
    for seat in (2, 3, 1):
        decide_and_check(hand, seat, SHOW)

    for seat in (2, 3, 1, 9):
        for action in ShowdownAction:
            assert_rejected(hand, seat, action, NotShowdownTurnError)


def test_after_all_but_one_mucked_the_next_seat_in_order_and_the_unasked_contender_are_rejected(
    new_hand: NewHand,
) -> None:
    hand = new_hand()
    decide_and_check(hand, 2, MUCK)
    decide_and_check(hand, 3, MUCK)

    for seat in (1, 2, 3):
        for action in ShowdownAction:
            assert_rejected(hand, seat, action, NotShowdownTurnError)


@pytest.mark.parametrize("seat", [1, 2, 3, 9])
@pytest.mark.parametrize("action", ShowdownAction)
def test_an_all_in_showdown_accepts_no_decision(stacked_hand: NewHand, seat: int, action: ShowdownAction) -> None:
    """Every live hand is tabled at once: even the seat first in canonical order has nothing to decide."""
    hand = stacked_hand(HOLES, BOARD, stacks={1: 100, 2: 100, 3: 100})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    start_showdown(hand)
    assert showdown_of(hand) == Showdown(ALL_IN, (2, 3, 1))

    assert_rejected(hand, seat, action, NotShowdownTurnError)


def test_a_hand_whose_showdown_has_not_started_rejects_every_decision(new_hand: NewHand) -> None:
    hand = new_hand(start=False)
    assert hand.showdown is None

    for seat in (2, 3, 1, 9):
        assert_rejected(hand, seat, SHOW, ShowdownNotStartedError)


def test_a_hand_before_showdown_is_certain_has_no_showdown_to_decide_in(stacked_hand: NewHand) -> None:
    hand = stacked_hand(HOLES, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)

    assert_rejected(hand, 1, SHOW, ShowdownNotStartedError)


def test_a_rejected_decision_leaves_a_later_valid_decision_possible(new_hand: NewHand) -> None:
    hand = new_hand()
    assert_rejected(hand, 1, MUCK, NotShowdownTurnError)

    showdown = decide_and_check(hand, 2, MUCK)

    assert showdown.decisions == (MUCK,)


# =============================================================================
# UNSUPPORTED ACTION TYPES
# =============================================================================

BAD_ACTIONS: list[Any] = [Action(ActionType.CALL), ActionType.CALL, "show", None, 1]
BAD_ACTION_IDS = ["betting-action", "betting-action-type", "string", "none", "int"]


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_the_current_decider_cannot_decide_with_an_action_that_is_not_a_showdown_action(
    new_hand: NewHand, action: Any
) -> None:
    hand = new_hand()
    showdown = showdown_of(hand)
    assert showdown.current_decider == 2

    assert_rejected(hand, 2, action, TypeError)

    assert hand.showdown is showdown
    assert showdown.decisions == ()


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_a_rejected_unsupported_action_leaves_the_same_seat_able_to_decide_and_the_hand_settleable(
    new_hand: NewHand, action: Any
) -> None:
    hand = new_hand()
    assert_rejected(hand, 2, action, TypeError)

    decide_and_check(hand, 2, SHOW)
    assert_rejected(hand, 3, action, TypeError)
    decide_and_check(hand, 3, MUCK)
    decide_and_check(hand, 1, SHOW)
    settle_hand(hand)

    settlement = hand.settlement
    assert settlement is not None
    assert [seat for seat, _ in settlement.showdown_ranks] == [1, 2]
    assert settlement.payouts == {2: 30}


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_the_turn_is_reported_before_an_unsupported_action_type(new_hand: NewHand, action: Any) -> None:
    hand = new_hand()
    assert_rejected(hand, 3, action, NotShowdownTurnError)
    assert_rejected(hand, 9, action, NotShowdownTurnError)
    for seat in (2, 3, 1):
        decide_and_check(hand, seat, SHOW)

    for seat in (2, 3, 1):
        assert_rejected(hand, seat, action, NotShowdownTurnError)


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_not_started_is_reported_before_an_unsupported_action_type(new_hand: NewHand, action: Any) -> None:
    hand = new_hand(start=False)

    assert_rejected(hand, 2, action, ShowdownNotStartedError)


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_settled_is_reported_before_an_unsupported_action_type(new_hand: NewHand, action: Any) -> None:
    hand = new_hand()
    for seat in (2, 3, 1):
        decide_and_check(hand, seat, SHOW)
    settle_hand(hand)

    assert_rejected(hand, 2, action, HandAlreadySettledError)


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_an_all_in_showdown_reports_the_turn_before_an_unsupported_action_type(
    stacked_hand: NewHand, action: Any
) -> None:
    hand = stacked_hand(HOLES, BOARD, stacks={1: 100, 2: 100, 3: 100})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    start_showdown(hand)

    assert_rejected(hand, 2, action, NotShowdownTurnError)

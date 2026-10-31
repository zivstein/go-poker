"""The variant-agnostic showdown record, its turn rule and seat ordering, on plain seat sequences."""

import dataclasses
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.showdown import (
    NotShowdownTurnError,
    Showdown,
    ShowdownAction,
    ShowdownKind,
    canonical_seat_order,
    decision_order,
)

# Seats clockwise with the button first, as in `hand.players`: seat 4 is the button, 7 the small blind, 2 the big blind.
SEATS_FROM_BUTTON = (4, 7, 2, 9, 5)

SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK
ORDER = (2, 3, 1)


def interactive(*decisions: ShowdownAction, order: tuple[int, ...] = ORDER) -> Showdown:
    return Showdown(ShowdownKind.INTERACTIVE, order, decisions)


# =============================================================================
# SEAT ORDER
# =============================================================================


def test_canonical_order_starts_left_of_the_button_and_ends_with_the_button() -> None:
    assert canonical_seat_order(SEATS_FROM_BUTTON) == (7, 2, 9, 5, 4)


def test_canonical_order_heads_up_starts_with_the_big_blind() -> None:
    """Heads-up the button is the small blind, so the big blind is the first seat left of it."""
    assert canonical_seat_order((3, 8)) == (8, 3)


def test_decision_order_without_an_aggressor_is_the_live_seats_in_canonical_order() -> None:
    assert decision_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, None) == (7, 2, 9, 5, 4)


def test_decision_order_starts_with_the_aggressor_and_goes_clockwise() -> None:
    assert decision_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, 9) == (9, 5, 4, 7, 2)


def test_decision_order_wraps_past_the_button() -> None:
    """From seat 5 the order passes the button (4) and continues with the seats left of it."""
    assert decision_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, 5) == (5, 4, 7, 2, 9)


def test_decision_order_starting_at_the_first_seat_left_of_the_button_is_canonical() -> None:
    assert decision_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, 7) == (7, 2, 9, 5, 4)


def test_decision_order_skips_folded_seats() -> None:
    assert decision_order(SEATS_FROM_BUTTON, {4, 2, 5}, None) == (2, 5, 4)
    assert decision_order(SEATS_FROM_BUTTON, {4, 2, 5}, 5) == (5, 4, 2)


def test_decision_order_does_not_change_its_inputs() -> None:
    live = {4, 2}
    decision_order(SEATS_FROM_BUTTON, live, 4)

    assert SEATS_FROM_BUTTON == (4, 7, 2, 9, 5)
    assert live == {4, 2}


# =============================================================================
# DERIVED STATE
# =============================================================================


def derived(showdown: Showdown) -> tuple[object, ...]:
    return (
        showdown.shown,
        showdown.mucked,
        showdown.contenders,
        showdown.current_decider,
        showdown.is_complete,
    )


# (decisions, (shown, mucked, contenders, current decider, complete)) for every decision prefix of three seats.
PREFIX_CASES: list[tuple[tuple[ShowdownAction, ...], tuple[object, ...]]] = [
    ((), ((), (), (2, 3, 1), 2, False)),
    ((SHOW,), ((2,), (), (2, 3, 1), 3, False)),
    ((MUCK,), ((), (2,), (3, 1), 3, False)),
    ((SHOW, SHOW), ((2, 3), (), (2, 3, 1), 1, False)),
    ((SHOW, MUCK), ((2,), (3,), (2, 1), 1, False)),
    ((MUCK, SHOW), ((3,), (2,), (3, 1), 1, False)),
    ((MUCK, MUCK), ((), (2, 3), (1,), None, True)),
    ((SHOW, SHOW, SHOW), ((2, 3, 1), (), (2, 3, 1), None, True)),
    ((SHOW, SHOW, MUCK), ((2, 3), (1,), (2, 3), None, True)),
    ((SHOW, MUCK, SHOW), ((2, 1), (3,), (2, 1), None, True)),
    ((MUCK, SHOW, SHOW), ((3, 1), (2,), (3, 1), None, True)),
    ((MUCK, SHOW, MUCK), ((3,), (2, 1), (3,), None, True)),
    ((SHOW, MUCK, MUCK), ((2,), (3, 1), (2,), None, True)),
]


@pytest.mark.parametrize(
    ("decisions", "expected"),
    PREFIX_CASES,
    ids=["-".join(action.value for action in decisions) or "none" for decisions, _ in PREFIX_CASES],
)
def test_derived_state_after_every_decision_prefix(
    decisions: tuple[ShowdownAction, ...], expected: tuple[object, ...]
) -> None:
    assert derived(interactive(*decisions)) == expected


def test_a_showdown_where_everyone_but_one_mucks_is_complete_before_the_last_contender_decides() -> None:
    """Completion by one remaining contender: two decisions of three, and the last seat is never asked."""
    showdown = interactive(MUCK, MUCK)

    assert showdown.is_complete
    assert showdown.current_decider is None
    assert len(showdown.decisions) < len(showdown.order)


def test_a_showdown_where_everyone_decided_is_complete_with_several_contenders() -> None:
    """Completion by every seat having decided: three decisions of three, two contenders left."""
    showdown = interactive(SHOW, MUCK, SHOW)

    assert showdown.is_complete
    assert len(showdown.contenders) == 2


def test_heads_up_a_first_muck_completes_the_showdown() -> None:
    showdown = interactive(MUCK, order=(2, 1))

    assert derived(showdown) == ((), (2,), (1,), None, True)


def test_heads_up_a_first_show_leaves_the_second_seat_to_decide() -> None:
    showdown = interactive(SHOW, order=(2, 1))

    assert derived(showdown) == ((2,), (), (2, 1), 1, False)


def test_an_all_in_showdown_is_complete_with_every_seat_shown_and_nobody_to_decide() -> None:
    showdown = Showdown(ShowdownKind.ALL_IN, ORDER)

    assert derived(showdown) == (ORDER, (), ORDER, None, True)
    assert showdown.decisions == ()


def test_the_order_never_changes_as_decisions_are_made() -> None:
    assert interactive(SHOW, MUCK).order == ORDER


# =============================================================================
# DECIDING
# =============================================================================


def test_decide_appends_the_decision_and_returns_a_new_record() -> None:
    first = interactive()

    second = first.decide(2, SHOW)
    third = second.decide(3, MUCK)

    assert (first.decisions, second.decisions, third.decisions) == ((), (SHOW,), (SHOW, MUCK))
    assert third is not second is not first
    assert (third.kind, third.order) == (first.kind, first.order)


def test_decide_leaves_the_old_record_unchanged() -> None:
    first = interactive(SHOW)

    first.decide(3, MUCK)

    assert first == interactive(SHOW)
    assert derived(first) == derived(interactive(SHOW))


@pytest.mark.parametrize("seat", [3, 1, 9], ids=["a-later-seat", "the-last-seat", "an-unknown-seat"])
def test_decide_rejects_a_seat_that_is_not_the_current_decider(seat: int) -> None:
    showdown = interactive()

    with pytest.raises(NotShowdownTurnError):
        showdown.decide(seat, SHOW)

    assert showdown == interactive()


def test_decide_rejects_a_seat_that_already_decided() -> None:
    showdown = interactive(SHOW)

    with pytest.raises(NotShowdownTurnError):
        showdown.decide(2, MUCK)

    assert showdown == interactive(SHOW)


@pytest.mark.parametrize("decisions", [(SHOW, SHOW, SHOW), (MUCK, MUCK)], ids=["all-decided", "one-contender"])
@pytest.mark.parametrize("seat", [2, 3, 1], ids=["first", "second", "third"])
def test_decide_rejects_every_seat_once_complete(decisions: tuple[ShowdownAction, ...], seat: int) -> None:
    showdown = interactive(*decisions)

    with pytest.raises(NotShowdownTurnError):
        showdown.decide(seat, SHOW)

    assert showdown == interactive(*decisions)


@pytest.mark.parametrize("seat", [2, 3, 1, 9])
def test_decide_rejects_every_decision_on_an_all_in_showdown(seat: int) -> None:
    showdown = Showdown(ShowdownKind.ALL_IN, ORDER)

    for action in ShowdownAction:
        with pytest.raises(NotShowdownTurnError):
            showdown.decide(seat, action)

    assert showdown == Showdown(ShowdownKind.ALL_IN, ORDER)


BAD_ACTIONS: list[Any] = [Action(ActionType.CALL), ActionType.CALL, "show", None, 1]
BAD_ACTION_IDS = ["betting-action", "betting-action-type", "string", "none", "int"]


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_decide_rejects_an_action_that_is_not_a_showdown_action_and_stores_nothing(action: Any) -> None:
    showdown = interactive(SHOW)

    with pytest.raises(TypeError):
        showdown.decide(3, action)

    assert showdown == interactive(SHOW)
    assert showdown.decisions == (SHOW,)
    assert showdown.decide(3, MUCK).decisions == (SHOW, MUCK)


@pytest.mark.parametrize("action", BAD_ACTIONS, ids=BAD_ACTION_IDS)
def test_decide_reports_the_turn_before_the_action_type(action: Any) -> None:
    """A wrong seat, a complete showdown and any ALL_IN showdown are turn errors even with an unsupported action."""
    with pytest.raises(NotShowdownTurnError):
        interactive().decide(3, action)
    with pytest.raises(NotShowdownTurnError):
        interactive(SHOW, SHOW, SHOW).decide(2, action)
    with pytest.raises(NotShowdownTurnError):
        interactive(MUCK, MUCK).decide(1, action)
    with pytest.raises(NotShowdownTurnError):
        Showdown(ShowdownKind.ALL_IN, ORDER).decide(2, action)


def test_the_turn_error_is_a_runtime_error() -> None:
    assert issubclass(NotShowdownTurnError, RuntimeError)


# =============================================================================
# IMMUTABILITY
# =============================================================================


def test_a_showdown_is_immutable() -> None:
    showdown = interactive(SHOW)

    with pytest.raises(dataclasses.FrozenInstanceError):
        showdown.kind = ShowdownKind.ALL_IN  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        showdown.order = (1,)  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        showdown.decisions = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        showdown.contenders = ()  # type: ignore[misc]
    assert showdown == interactive(SHOW)
    assert showdown != Showdown(ShowdownKind.ALL_IN, ORDER)
    assert showdown != interactive(MUCK)


def test_the_kinds_and_actions_have_their_two_members() -> None:
    assert {kind.name for kind in ShowdownKind} == {"ALL_IN", "INTERACTIVE"}
    assert {action.name for action in ShowdownAction} == {"SHOW", "MUCK"}

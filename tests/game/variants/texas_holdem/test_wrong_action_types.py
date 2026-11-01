"""Values that are not the right kind of action, offered to the showdown and betting operations.

The ordinary wrong types and the rejection order of `apply_showdown_action` are covered in
`test_apply_showdown_action.py`. This module adds the wide set of look-alike values (a member's value or name string, a
str subclass, an object equal to a member, another enum, an int) that separates a real `isinstance` check from an
equality or truthiness one, and the betting operation's behavior when it is given a showdown action: during any street
and during a showdown in progress.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import NotPlayersTurnError, apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    apply_showdown_action,
    start_showdown,
)

STAKES = Stakes(small_blind=5, big_blind=10)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"

type NewHand = Callable[..., PokerHand]


class ShowString(str):
    """A str subclass with the value of SHOW."""


class EqualToShow:
    """An object that compares equal to SHOW."""

    def __eq__(self, other: object) -> bool:
        return other is ShowdownAction.SHOW or isinstance(other, EqualToShow)

    def __hash__(self) -> int:
        return 1


WRONG_SHOWDOWN_ACTIONS: list[Any] = [
    "show",
    "SHOW",
    ShowString("show"),
    ShowdownAction.SHOW.value,
    ShowdownAction.SHOW.name,
    ShowdownKind.ALL_IN,
    ActionType.CHECK,
    CHECK,
    EqualToShow(),
    None,
    0,
    1,
    True,
    (ShowdownAction.SHOW,),
    ShowdownAction,
]
WRONG_IDS = [
    "value-string",
    "name-string",
    "str-subclass",
    "value",
    "name",
    "other-enum",
    "betting-action-type",
    "betting-action",
    "equal-to-show",
    "none",
    "zero",
    "one",
    "true",
    "tuple",
    "the-enum-class",
]
WRONG_BETTING_ACTIONS: list[Any] = [ShowdownAction.SHOW, ShowdownAction.MUCK, "check", None]
WRONG_BETTING_IDS = ["show", "muck", "check-string", "none"]


def snapshot(hand: PokerHand) -> dict[str, Any]:
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
    }


def rejected(operation: Callable[[], None], hand: PokerHand, error: type[Exception]) -> None:
    before = snapshot(hand)
    with pytest.raises(error):
        operation()
    assert snapshot(hand) == before
    assert hand.showdown is before["showdown"]


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    def build(stacks: dict[int, int] | None = None) -> PokerHand:
        hand = stacked_hand(HOLES, BOARD, stacks=stacks)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        return hand

    return build


def to_river(hand: PokerHand) -> None:
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        apply_action(hand, actor, CHECK if hand.betting.pending_actors == {actor} else CALL)
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
        start_betting_round(hand)
        while hand.betting.current_actor is not None:
            apply_action(hand, hand.betting.current_actor, CHECK)


@pytest.fixture
def river_showdown(new_hand: NewHand) -> PokerHand:
    hand = new_hand()
    to_river(hand)
    start_showdown(hand)
    return hand


@pytest.mark.parametrize("action", WRONG_SHOWDOWN_ACTIONS, ids=WRONG_IDS)
def test_no_look_alike_value_is_ever_stored_as_a_showdown_decision(river_showdown: PokerHand, action: Any) -> None:
    hand = river_showdown
    for seat in (2, 3):
        rejected(lambda seat=seat: apply_showdown_action(hand, seat, action), hand, TypeError)
        apply_showdown_action(hand, seat, ShowdownAction.SHOW)
    assert hand.showdown is not None
    assert hand.showdown.decisions == (ShowdownAction.SHOW, ShowdownAction.SHOW)


@pytest.mark.parametrize("action", WRONG_BETTING_ACTIONS, ids=WRONG_BETTING_IDS)
def test_apply_action_rejects_a_non_betting_action_on_every_street_without_changes(
    new_hand: NewHand, action: Any
) -> None:
    hand = new_hand()
    assert hand.betting is not None
    while True:
        actor = hand.betting.current_actor
        assert actor is not None
        rejected(lambda actor=actor: apply_action(hand, actor, action), hand, AttributeError)
        other = next(seat for seat in (1, 2, 3) if seat != actor)
        rejected(lambda other=other: apply_action(hand, other, action), hand, NotPlayersTurnError)
        while hand.betting.current_actor is not None:
            current = hand.betting.current_actor
            preflop_call = hand.street is Street.PREFLOP and hand.betting.pending_actors != {current}
            apply_action(hand, current, CALL if preflop_call else CHECK)
        if hand.street is Street.RIVER:
            break
        deal_next_street(hand)
        start_betting_round(hand)


@pytest.mark.parametrize("action", WRONG_BETTING_ACTIONS, ids=WRONG_BETTING_IDS)
def test_apply_action_reports_a_completed_round_during_a_showdown_before_the_action_kind(
    river_showdown: PokerHand, action: Any
) -> None:
    hand = river_showdown
    for seat in (1, 2, 3):
        rejected(lambda seat=seat: apply_action(hand, seat, action), hand, NotPlayersTurnError)
    apply_showdown_action(hand, 2, ShowdownAction.MUCK)
    for seat in (1, 2, 3):
        rejected(lambda seat=seat: apply_action(hand, seat, action), hand, NotPlayersTurnError)

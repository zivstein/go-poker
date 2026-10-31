"""`hand_flow` entry points: dispatch, rejection orders, atomicity of rejections and the derived current actor.

Hands are built by the shared `stacked_hand` fixture and driven only through `begin_hand`, `act` and `current_actor`
(the settled and manually dealt cases are built with the low-level operations they are about). The three seats are
the button (1), the small blind (2) and the big blind (3); preflop seat 1 acts first and on every later street seat 2
does. Every rejection is compared with a full before and after snapshot of the hand. Whole-hand flows are in
`test_hand_flow_integration`.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.core.deck import DeckEmptyError
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, NotPlayersTurnError
from go_poker.game.betting.initialization import (
    BettingAlreadyInitializedError,
    BettingNotPreflopError,
    initialize_betting,
)
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.showdown import NotShowdownTurnError, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import (
    HoleCardsAlreadyDealtError,
    deal_hole_cards,
    deal_next_street,
)
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.showdown import ShowdownNotStartedError

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
GARBAGE: list[Any] = [None, ActionType.CHECK, "show", 7, object()]

type StackedHand = Callable[..., PokerHand]


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


def assert_rejected(hand: PokerHand, error: type[Exception], seat: int, action: Any) -> None:
    """`act` raises the error and leaves the whole hand as it was."""
    before = snapshot(hand)
    with pytest.raises(error):
        act(hand, seat, action)
    assert snapshot(hand) == before


def play(hand: PokerHand, *actions: tuple[int, Action | ShowdownAction]) -> None:
    for seat, action in actions:
        act(hand, seat, action)


def new_hand(stacked_hand: StackedHand, stacks: dict[int, int] | None = None) -> PokerHand:
    """A stacked hand that has not begun."""
    return stacked_hand(HOLES, BOARD, stacks=stacks)


def betting_hand(stacked_hand: StackedHand) -> PokerHand:
    """A begun hand waiting for seat 1 to act preflop."""
    hand = new_hand(stacked_hand)
    begin_hand(hand, STAKES)
    return hand


def showdown_hand(stacked_hand: StackedHand) -> PokerHand:
    """Everybody checks the hand down to an interactive river showdown, waiting for seat 2 to decide."""
    hand = betting_hand(stacked_hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    for _ in range(3):
        play(hand, (2, CHECK), (3, CHECK), (1, CHECK))
    return hand


def settled_hand(stacked_hand: StackedHand) -> PokerHand:
    hand = betting_hand(stacked_hand)
    play(hand, (1, FOLD), (2, FOLD))
    assert hand.settlement is not None
    return hand


# =============================================================================
# DISPATCH
# =============================================================================


def test_act_dispatches_a_betting_action_to_betting(stacked_hand: StackedHand) -> None:
    hand = betting_hand(stacked_hand)

    act(hand, 1, CALL)

    assert hand.players[0].street_contribution == 10
    assert current_actor(hand) == 2
    assert hand.showdown is None


def test_act_dispatches_a_showdown_action_to_the_showdown(stacked_hand: StackedHand) -> None:
    hand = showdown_hand(stacked_hand)
    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.INTERACTIVE

    act(hand, 2, SHOW)

    assert hand.showdown.decisions == (SHOW,)
    assert current_actor(hand) == 3


def test_act_returns_none(stacked_hand: StackedHand) -> None:
    hand = betting_hand(stacked_hand)

    assert act(hand, 1, CALL) is None  # type: ignore[func-returns-value]


# =============================================================================
# ACTIONS OF THE WRONG TYPE
# =============================================================================


@pytest.mark.parametrize("garbage", GARBAGE)
def test_garbage_action_raises_type_error_during_betting(stacked_hand: StackedHand, garbage: Any) -> None:
    assert_rejected(betting_hand(stacked_hand), TypeError, 1, garbage)


@pytest.mark.parametrize("garbage", GARBAGE)
def test_garbage_action_raises_type_error_during_a_showdown(stacked_hand: StackedHand, garbage: Any) -> None:
    assert_rejected(showdown_hand(stacked_hand), TypeError, 2, garbage)


@pytest.mark.parametrize("garbage", GARBAGE)
def test_garbage_action_raises_type_error_before_any_turn_check(stacked_hand: StackedHand, garbage: Any) -> None:
    """A wrong seat (and, in a showdown, a wrong decider) does not turn the type error into a turn error."""
    assert_rejected(betting_hand(stacked_hand), TypeError, 3, garbage)
    assert_rejected(showdown_hand(stacked_hand), TypeError, 1, garbage)
    assert_rejected(new_hand(stacked_hand), TypeError, 99, garbage)


@pytest.mark.parametrize("garbage", GARBAGE)
def test_settled_hand_error_wins_over_type_error(stacked_hand: StackedHand, garbage: Any) -> None:
    assert_rejected(settled_hand(stacked_hand), HandAlreadySettledError, 3, garbage)


# =============================================================================
# SETTLED HANDS
# =============================================================================


@pytest.mark.parametrize("action", [CHECK, FOLD, SHOW, MUCK])
@pytest.mark.parametrize("seat", [1, 2, 3, 99])
def test_act_on_a_settled_hand_is_rejected_as_settled(stacked_hand: StackedHand, seat: int, action: Any) -> None:
    assert_rejected(settled_hand(stacked_hand), HandAlreadySettledError, seat, action)


def test_begin_hand_on_a_settled_hand_is_rejected_as_settled_before_any_other_error(stacked_hand: StackedHand) -> None:
    """The settled hand already has betting and hole cards, so every other check would fail too."""
    hand = settled_hand(stacked_hand)
    before = snapshot(hand)

    with pytest.raises(HandAlreadySettledError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before


# =============================================================================
# WRONG ACTOR AND WRONG SUBSYSTEM
# =============================================================================


@pytest.mark.parametrize("seat", [2, 3, 99])
def test_wrong_betting_seat_is_rejected(stacked_hand: StackedHand, seat: int) -> None:
    assert_rejected(betting_hand(stacked_hand), NotPlayersTurnError, seat, CALL)


def test_illegal_betting_action_is_rejected(stacked_hand: StackedHand) -> None:
    hand = betting_hand(stacked_hand)

    assert_rejected(hand, IllegalActionError, 1, CHECK)
    assert_rejected(hand, IllegalActionError, 1, Action(ActionType.RAISE, 15))


@pytest.mark.parametrize("seat", [1, 3, 99])
def test_wrong_showdown_decider_is_rejected(stacked_hand: StackedHand, seat: int) -> None:
    assert_rejected(showdown_hand(stacked_hand), NotShowdownTurnError, seat, SHOW)


def test_wrong_decider_is_rejected_after_a_decision(stacked_hand: StackedHand) -> None:
    hand = showdown_hand(stacked_hand)
    act(hand, 2, SHOW)

    assert_rejected(hand, NotShowdownTurnError, 2, MUCK)
    assert_rejected(hand, NotShowdownTurnError, 1, MUCK)


@pytest.mark.parametrize("action", [SHOW, MUCK])
def test_showdown_action_during_betting_is_rejected(stacked_hand: StackedHand, action: ShowdownAction) -> None:
    hand = betting_hand(stacked_hand)

    assert_rejected(hand, ShowdownNotStartedError, 1, action)
    assert_rejected(hand, ShowdownNotStartedError, 3, action)


def test_showdown_action_before_the_hand_begins_is_rejected(stacked_hand: StackedHand) -> None:
    assert_rejected(new_hand(stacked_hand), ShowdownNotStartedError, 1, SHOW)


@pytest.mark.parametrize("action", [CHECK, FOLD, CALL])
def test_betting_action_during_a_showdown_is_rejected(stacked_hand: StackedHand, action: Action) -> None:
    hand = showdown_hand(stacked_hand)

    assert_rejected(hand, NotPlayersTurnError, 2, action)
    assert_rejected(hand, NotPlayersTurnError, 1, action)


# =============================================================================
# CURRENT ACTOR
# =============================================================================


def test_current_actor_is_none_before_the_hand_begins(stacked_hand: StackedHand) -> None:
    hand = new_hand(stacked_hand)

    assert hand.betting is None
    assert current_actor(hand) is None


def test_current_actor_is_the_betting_actor_during_betting(stacked_hand: StackedHand) -> None:
    hand = betting_hand(stacked_hand)
    assert current_actor(hand) == 1

    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    assert current_actor(hand) == 2


def test_current_actor_is_the_showdown_decider_during_an_interactive_showdown(stacked_hand: StackedHand) -> None:
    hand = showdown_hand(stacked_hand)
    assert hand.betting is not None and hand.betting.current_actor is None
    assert current_actor(hand) == 2

    act(hand, 2, SHOW)
    assert current_actor(hand) == 3
    act(hand, 3, SHOW)
    assert current_actor(hand) == 1


def test_current_actor_is_none_when_settled(stacked_hand: StackedHand) -> None:
    hand = showdown_hand(stacked_hand)
    play(hand, (2, SHOW), (3, MUCK), (1, SHOW))
    assert hand.settlement is not None

    assert current_actor(hand) is None


def test_current_actor_is_none_for_a_settled_hand_whatever_its_state(stacked_hand: StackedHand) -> None:
    assert current_actor(settled_hand(stacked_hand)) is None


def test_current_actor_is_a_read_that_changes_nothing(stacked_hand: StackedHand) -> None:
    hand = showdown_hand(stacked_hand)
    before = snapshot(hand)

    current_actor(hand)

    assert snapshot(hand) == before


# =============================================================================
# BEGIN HAND
# =============================================================================


def test_begin_hand_posts_blinds_deals_and_waits_for_the_first_actor(stacked_hand: StackedHand) -> None:
    hand = new_hand(stacked_hand)

    begin_hand(hand, STAKES)

    assert [state.street_contribution for state in hand.players] == [0, 5, 10]
    assert all(len(state.hole_cards) == 2 for state in hand.players)
    assert hand.street is Street.PREFLOP and hand.board == []
    assert current_actor(hand) == 1


def test_begin_hand_twice_is_rejected_without_a_change(stacked_hand: StackedHand) -> None:
    hand = betting_hand(stacked_hand)
    before = snapshot(hand)

    with pytest.raises(BettingAlreadyInitializedError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before


def test_begin_hand_after_the_hand_progressed_is_rejected_without_a_change(stacked_hand: StackedHand) -> None:
    """Betting exists, so the betting check comes before the street checks."""
    hand = showdown_hand(stacked_hand)
    before = snapshot(hand)

    with pytest.raises(BettingAlreadyInitializedError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before


def test_begin_hand_without_betting_past_preflop_is_rejected_as_not_preflop(stacked_hand: StackedHand) -> None:
    """With no betting, the betting-initialization street check precedes the hole-card street check."""
    hand = new_hand(stacked_hand)
    deal_hole_cards(hand)
    deal_next_street(hand)
    before = snapshot(hand)

    with pytest.raises(BettingNotPreflopError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before


def test_begin_hand_after_manually_dealt_hole_cards_is_rejected_before_any_blind_is_posted(
    stacked_hand: StackedHand,
) -> None:
    hand = new_hand(stacked_hand)
    deal_hole_cards(hand)
    before = snapshot(hand)

    with pytest.raises(HoleCardsAlreadyDealtError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before
    assert hand.betting is None
    assert [state.street_contribution for state in hand.players] == [0, 0, 0]


def test_begin_hand_with_too_few_cards_is_rejected_before_any_blind_is_posted(stacked_hand: StackedHand) -> None:
    hand = new_hand(stacked_hand)
    for _ in range(len(hand.deck) - 5):
        hand.deck.draw()
    before = snapshot(hand)

    with pytest.raises(DeckEmptyError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before
    assert hand.betting is None


def test_begin_hand_reports_dealt_hole_cards_before_a_short_deck(stacked_hand: StackedHand) -> None:
    hand = new_hand(stacked_hand)
    deal_hole_cards(hand)
    while len(hand.deck) > 0:
        hand.deck.draw()
    before = snapshot(hand)

    with pytest.raises(HoleCardsAlreadyDealtError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before


def test_begin_hand_after_manual_betting_initialization_is_rejected(stacked_hand: StackedHand) -> None:
    hand = new_hand(stacked_hand)
    initialize_betting(hand, STAKES)
    before = snapshot(hand)

    with pytest.raises(BettingAlreadyInitializedError):
        begin_hand(hand, STAKES)

    assert snapshot(hand) == before

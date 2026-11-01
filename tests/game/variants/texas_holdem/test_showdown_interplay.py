"""Other hand operations while a showdown is in progress, through the public operations.

A started showdown is hand state, not a phase: betting and dealing operations stay available or rejected by their own
rules, and none of them may disturb the showdown record. An interactive river showdown has nothing left to deal or bet,
so every one of them is rejected, unchanged, at each point of its decisions. An all-in showdown started before the
board is run out lets the runout proceed (with or without the betting rounds of the remaining streets) and the hand then
settles exactly as a hand settled directly.

Hands are reached through the real operations from a deck stacked by the shared `stacked_hand` fixture. Unless a test
says otherwise the three seats are the button (1), the small blind (2) and the big blind (3); seat 2 holds a set of
kings on the default board and seat 1 a pair of aces.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import NotPlayersTurnError, apply_action
from go_poker.game.betting.initialization import BettingAlreadyInitializedError, initialize_betting
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import BettingRoundAlreadyStartedError, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import Settlement
from go_poker.game.showdown import NotShowdownTurnError, Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import (
    HandPastPreflopError,
    NoNextStreetError,
    deal_hole_cards,
    deal_next_street,
)
from go_poker.game.variants.texas_holdem.showdown import (
    IncompleteBoardError,
    ShowdownAlreadyStartedError,
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

type NewHand = Callable[..., PokerHand]


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


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
    }


def next_street(hand: PokerHand) -> None:
    deal_next_street(hand)
    start_betting_round(hand)


def check_street(hand: PokerHand) -> None:
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


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


@pytest.fixture
def river_hand(new_hand: NewHand) -> PokerHand:
    """A checked-down river whose interactive showdown has started: the decision order is seats 2, 3, 1."""
    hand = new_hand()
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        apply_action(hand, actor, CHECK if hand.betting.pending_actors == {actor} else CALL)
    while hand.street is not Street.TURN:
        next_street(hand)
        check_street(hand)
    next_street(hand)
    check_street(hand)
    start_showdown(hand)
    return hand


def assert_every_other_operation_rejected(hand: PokerHand) -> None:
    """Every betting and dealing operation is rejected on a river showdown in progress, leaving the hand (showdown
    object included) exactly as it was."""
    before = snapshot(hand)
    attempts: list[tuple[Callable[[], None], type[Exception]]] = [
        (lambda: deal_next_street(hand), NoNextStreetError),
        (lambda: start_betting_round(hand), BettingRoundAlreadyStartedError),
        (lambda: initialize_betting(hand, STAKES), BettingAlreadyInitializedError),
        (lambda: deal_hole_cards(hand), HandPastPreflopError),
        (lambda: start_showdown(hand), ShowdownAlreadyStartedError),
    ]
    for seat in (state.seat_number for state in hand.players):
        for action in (CHECK, CALL, FOLD, Action(ActionType.BET, 20), raise_to(40)):
            attempts.append((lambda seat=seat, action=action: apply_action(hand, seat, action), NotPlayersTurnError))
    for attempt, error in attempts:
        with pytest.raises(error):
            attempt()
        assert snapshot(hand) == before
        assert hand.showdown is before["showdown"]


def test_a_river_showdown_rejects_every_betting_and_dealing_operation_before_any_decision(
    river_hand: PokerHand,
) -> None:
    assert_every_other_operation_rejected(river_hand)


@pytest.mark.parametrize(
    "decisions",
    [[(2, SHOW)], [(2, MUCK)], [(2, SHOW), (3, SHOW)], [(2, SHOW), (3, MUCK)], [(2, SHOW), (3, SHOW), (1, SHOW)]],
    ids=["after-show", "after-muck", "after-two-shows", "after-show-and-muck", "after-everyone-decided"],
)
def test_a_river_showdown_rejects_every_betting_and_dealing_operation_after_each_decision_prefix(
    river_hand: PokerHand, decisions: list[tuple[int, ShowdownAction]]
) -> None:
    for seat, action in decisions:
        apply_showdown_action(river_hand, seat, action)
        assert_every_other_operation_rejected(river_hand)


def test_a_showdown_survives_rejected_betting_and_dealing_and_still_settles(river_hand: PokerHand) -> None:
    """A rejected betting or dealing operation leaves later decisions and the settlement as they would have been."""
    apply_showdown_action(river_hand, 2, SHOW)
    assert_every_other_operation_rejected(river_hand)
    apply_showdown_action(river_hand, 3, MUCK)
    assert_every_other_operation_rejected(river_hand)
    apply_showdown_action(river_hand, 1, SHOW)
    assert_every_other_operation_rejected(river_hand)

    settle_hand(river_hand)

    settlement = river_hand.settlement
    assert settlement is not None
    assert settlement.payouts == {2: 30}
    assert river_hand.showdown == Showdown(ShowdownKind.INTERACTIVE, (2, 3, 1), (SHOW, MUCK, SHOW))


# -----------------------------------------------------------------------------
# An all-in showdown started before the runout
# -----------------------------------------------------------------------------

ALL_IN_STACKS = {1: 100, 2: 100, 3: 100}


def all_in_preflop(new_hand: NewHand, stacks: dict[int, int] = ALL_IN_STACKS) -> PokerHand:
    hand = new_hand(stacks=stacks)
    apply_action(hand, 1, raise_to(100))
    apply_action(hand, 2, CALL)
    apply_action(hand, 3, CALL)
    return hand


def run_out(hand: PokerHand, rounds_started: set[Street]) -> None:
    """Deal the remaining streets, starting the betting round of exactly the streets in `rounds_started`."""
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
        if hand.street in rounds_started:
            start_betting_round(hand)


def comparable(settlement: Settlement | None) -> Settlement:
    assert settlement is not None
    return settlement


RUNOUTS = [
    pytest.param(set(), id="no-rounds-started"),
    pytest.param({Street.FLOP, Street.TURN, Street.RIVER}, id="every-round-started"),
    pytest.param({Street.TURN}, id="only-the-turn-round-started"),
    pytest.param({Street.RIVER}, id="only-the-river-round-started"),
]


@pytest.mark.parametrize("rounds_started", RUNOUTS)
def test_an_all_in_showdown_started_before_the_runout_settles_like_a_direct_settlement(
    new_hand: NewHand, rounds_started: set[Street]
) -> None:
    """Whether or not the betting rounds of the remaining streets are started, the hand settles as a hand settled
    directly after the same runout, and keeps the showdown it started with."""
    direct = all_in_preflop(new_hand)
    started = all_in_preflop(new_hand)
    start_showdown(started)
    showdown = started.showdown
    assert showdown == Showdown(ShowdownKind.ALL_IN, (2, 3, 1))

    run_out(direct, rounds_started)
    run_out(started, rounds_started)
    assert started.showdown is showdown
    assert started.board == direct.board

    settle_hand(direct)
    settle_hand(started)

    assert comparable(started.settlement) == comparable(direct.settlement)
    assert started.showdown is showdown
    assert direct.showdown == showdown
    assert [(s.player.stack, s.all_in) for s in started.players] == [(s.player.stack, s.all_in) for s in direct.players]
    assert started.settlement.payouts == {2: 300}  # type: ignore[union-attr]


def test_an_all_in_showdown_rejects_betting_but_allows_the_runout_and_no_decision_at_any_point(
    new_hand: NewHand,
) -> None:
    hand = all_in_preflop(new_hand)
    start_showdown(hand)
    showdown = hand.showdown

    while True:
        before = snapshot(hand)
        for seat in (1, 2, 3, 99):
            with pytest.raises(NotPlayersTurnError):
                apply_action(hand, seat, CHECK)
            for action in ShowdownAction:
                with pytest.raises(NotShowdownTurnError):
                    apply_showdown_action(hand, seat, action)
        with pytest.raises(ShowdownAlreadyStartedError):
            start_showdown(hand)
        assert snapshot(hand) == before
        assert hand.showdown is showdown
        if hand.street is Street.RIVER:
            break
        deal_next_street(hand)

    with pytest.raises(NoNextStreetError):
        deal_next_street(hand)
    settle_hand(hand)
    assert hand.showdown is showdown


def test_an_all_in_showdown_started_before_the_runout_cannot_be_settled_until_the_board_is_complete(
    new_hand: NewHand,
) -> None:
    hand = all_in_preflop(new_hand)
    start_showdown(hand)
    showdown = hand.showdown

    for _ in range(3):
        before = snapshot(hand)
        with pytest.raises(IncompleteBoardError):
            settle_hand(hand)
        assert snapshot(hand) == before
        assert hand.showdown is showdown
        deal_next_street(hand)

    settle_hand(hand)
    assert hand.settlement is not None


def test_starting_the_betting_round_right_after_an_all_in_showdown_starts_is_rejected_until_a_street_is_dealt(
    new_hand: NewHand,
) -> None:
    hand = all_in_preflop(new_hand)
    start_showdown(hand)
    before = snapshot(hand)

    with pytest.raises(BettingRoundAlreadyStartedError):
        start_betting_round(hand)

    assert snapshot(hand) == before
    deal_next_street(hand)
    start_betting_round(hand)  # a completed round with nobody able to act, so the new round completes at once
    assert hand.betting is not None and hand.betting.current_actor is None and not hand.betting.pending_actors
    assert hand.showdown is before["showdown"]


@pytest.mark.parametrize("rounds_started", [set(), {Street.TURN, Street.RIVER}], ids=["no-rounds", "rounds-started"])
def test_an_all_in_showdown_started_on_the_flop_with_a_player_still_holding_chips_settles_after_the_runout(
    new_hand: NewHand, rounds_started: set[Street]
) -> None:
    """Seat 2 bets all-in on the flop, seat 3 folds and seat 1, who keeps chips, calls: the round closes with the turn
    and river undealt, the all-in showdown starts then and the hand settles like a directly settled one."""

    def build() -> PokerHand:
        hand = new_hand(stacks={1: 1000, 2: 100, 3: 1000})
        apply_action(hand, 1, CALL)
        apply_action(hand, 2, CALL)
        apply_action(hand, 3, CHECK)
        next_street(hand)
        apply_action(hand, 2, Action(ActionType.BET, 90))
        apply_action(hand, 3, FOLD)
        apply_action(hand, 1, CALL)
        assert hand.street is Street.FLOP and len(hand.board) == 3
        return hand

    direct, started = build(), build()
    start_showdown(started)
    showdown = started.showdown
    assert showdown == Showdown(ShowdownKind.ALL_IN, (2, 1))

    run_out(direct, rounds_started)
    run_out(started, rounds_started)
    settle_hand(direct)
    settle_hand(started)

    assert comparable(started.settlement) == comparable(direct.settlement)
    assert started.showdown is showdown
    assert direct.showdown == showdown
    assert started.settlement is not None and started.settlement.payouts == {2: 210}
    assert [seat for seat, _ in started.settlement.showdown_ranks] == [1, 2]

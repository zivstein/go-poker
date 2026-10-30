"""Milestone 2 betting scenarios driven through the public dealing and betting operations.

Hands are built the way hand setup builds them (the conftest `make_hand`); one scenario starts from a real game start.

Every step re-checks the betting invariants (see `CheckedHand.check` in the conftest), so each scenario also proves
that the invariants hold through the interactions it exercises.
"""

from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, NotPlayersTurnError, apply_action
from go_poker.game.betting.initialization import BettingAlreadyInitializedError, initialize_betting
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.rounds import (
    BettingRoundAlreadyStartedError,
    BettingRoundNotCompleteError,
    is_round_complete,
    start_betting_round,
)
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.game_lifecycle import start_game
from go_poker.game.player import Player
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street
from go_poker.game.table import Table

# The conftest `CheckedHand`, which test modules cannot import.
type CheckedHand = Any
type HandFactory = Callable[..., PokerHand]
type HandSnapshotter = Callable[[PokerHand], object]
type PlayerSnapshotter = Callable[[PokerHand], dict[int, tuple[int, int, int, bool, bool]]]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


FOUR_HANDED_BUTTON = 5  # seats 5 (button), 8 (small blind), 1 (big blind), 3 (UTG)


# =============================================================================
# MULTIWAY
# =============================================================================


def test_multiway_preflop_limp_raise_and_responses(
    checked: Callable[[PokerHand], CheckedHand], player_snapshot: PlayerSnapshotter, stakes: Stakes
) -> None:
    """Six-handed from a real game start: UTG limps, the hijack raises, which reopens the action for everyone,
    including the limper and the big blind; the cutoff and small blind fold, everyone else calls, and the round
    completes after the limper re-acts."""
    table = Table(9)
    for seat_number, stack in {1: 1000, 2: 1500, 4: 800, 5: 2000, 7: 1200, 9: 900}.items():
        table.sit_in(Player(f"P{seat_number}", stack=stack), seat_number)
    h = checked(start_game(table, lambda seats: 2))  # button 2, SB 4, BB 5, UTG 7, HJ 9, CO 1
    h.start(stakes)
    assert h.betting.current_actor == 7

    h.act((7, CALL), (9, raise_to(40)))
    assert h.betting.pending_actors == {1, 2, 4, 5, 7}
    h.act((1, FOLD), (2, CALL), (4, FOLD), (5, CALL))
    assert (h.betting.current_actor, h.betting.pending_actors) == (7, {7})
    h.act((7, CALL))

    assert player_snapshot(h.hand) == {
        2: (1460, 40, 40, False, False),
        4: (795, 5, 5, True, False),
        5: (1960, 40, 40, False, False),
        7: (1160, 40, 40, False, False),
        9: (860, 40, 40, False, False),
        1: (1000, 0, 0, True, False),
    }
    assert h.betting == BettingState(
        street=Street.PREFLOP,
        stakes=stakes,
        current_bet=40,
        last_full_raise_size=30,
        current_actor=None,
        pending_actors=set(),
        acted_at_bet={7: 40, 9: 40, 1: 40, 2: 40, 4: 40, 5: 40},
    )
    assert is_round_complete(h.betting)


def test_bet_after_checks_reopens_action_for_the_checkers(
    checked: Callable[[PokerHand], CheckedHand],
    make_hand: HandFactory,
    player_snapshot: PlayerSnapshotter,
    stakes: Stakes,
) -> None:
    """On a dealt flop, three players check and the button bets: all three checkers owe a response again, and the
    round completes once they have called or folded."""
    h = checked(make_hand({5: 1000, 8: 1000, 1: 1000, 3: 1000}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(stakes)
    h.act((3, CALL), (5, CALL), (8, CALL), (1, CHECK))
    h.next_street()

    h.act((8, CHECK), (1, CHECK), (3, CHECK), (5, bet(30)))
    assert (h.betting.current_actor, h.betting.pending_actors) == (8, {8, 1, 3})
    h.act((8, CALL), (1, FOLD), (3, CALL))

    assert player_snapshot(h.hand) == {
        5: (960, 30, 40, False, False),
        8: (960, 30, 40, False, False),
        1: (990, 0, 10, True, False),
        3: (960, 30, 40, False, False),
    }
    assert is_round_complete(h.betting)


def test_raise_reraise_and_four_bet_each_reset_the_minimum_and_reopen_action(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory, stakes: Stakes
) -> None:
    """Each full raise adds its target minus the raiser's street contribution, sets the last full raise size and the
    next minimum raise, and makes every other live player owe a response; calls then close the round."""
    h = checked(make_hand({5: 2000, 8: 2000, 1: 2000, 3: 2000}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(stakes)
    seats = h.seats

    def sizing() -> tuple[int, int, int | None, set[int]]:
        return (
            h.betting.current_bet,
            h.betting.last_full_raise_size,
            legal_actions(h.hand).min_full_target,
            h.betting.pending_actors,
        )

    h.act((3, raise_to(30)))  # UTG adds 30
    assert seats[3].player.stack == 1970
    assert sizing() == (30, 20, 50, {5, 8, 1})

    h.act((5, raise_to(90)))  # the button adds 90
    assert seats[5].player.stack == 1910
    assert sizing() == (90, 60, 150, {8, 1, 3})

    h.act((8, FOLD), (1, raise_to(250)))  # the big blind, with 10 in, adds 240
    assert seats[1].player.stack == 1750
    assert sizing() == (250, 160, 410, {3, 5})

    h.act((3, CALL), (5, CALL))  # UTG adds 220, the button 160
    assert {seat: hp.total_contribution for seat, hp in seats.items()} == {5: 250, 8: 5, 1: 250, 3: 250}
    assert is_round_complete(h.betting)


# =============================================================================
# HEADS-UP
# =============================================================================


def test_heads_up_button_acts_first_preflop_and_big_blind_first_after(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory, stakes: Stakes
) -> None:
    """Heads-up the button (small blind) acts first preflop and the big blind keeps its option; on every later
    street the big blind acts first."""
    h = checked(make_hand({3: 1000, 7: 1000}, button_seat_number=7))
    h.start(stakes)
    assert h.betting.current_actor == 7

    h.act((7, CALL))
    assert legal_actions(h.hand).can_check
    h.act((3, CHECK))
    assert is_round_complete(h.betting)

    h.next_street()
    assert h.betting.current_actor == 3
    h.act((3, bet(20)), (7, CALL))

    h.next_street()
    assert h.betting.current_actor == 3
    h.act((3, CHECK), (7, CHECK))
    assert is_round_complete(h.betting)
    assert {seat: hp.total_contribution for seat, hp in h.seats.items()} == {3: 30, 7: 30}


# =============================================================================
# ALL-INS THROUGH FULL ACTIONS
# =============================================================================


def test_full_raise_and_full_call_all_ins_are_skipped_on_later_streets(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory, stakes: Stakes
) -> None:
    """UTG raises all-in and the small blind calls all-in, both as full actions; neither is pending or to act again,
    the others finish the round, and on the flop only the button and big blind bet, the big blind first."""
    h = checked(make_hand({5: 1000, 8: 200, 1: 1000, 3: 200}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(stakes)
    seats = h.seats

    h.act((3, raise_to(200)), (5, CALL), (8, CALL))
    for all_in_seat in (3, 8):
        assert (seats[all_in_seat].player.stack, seats[all_in_seat].all_in) == (0, True)
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {1})
    h.act((1, CALL))
    assert is_round_complete(h.betting)

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {5, 1})
    h.act((1, bet(100)), (5, CALL))

    assert is_round_complete(h.betting)
    assert {seat: hp.player.stack for seat, hp in seats.items()} == {5: 700, 8: 0, 1: 700, 3: 0}


# =============================================================================
# EARLY ROUND ENDINGS
# =============================================================================


def test_everyone_folding_to_a_raise_ends_the_round_without_payout(
    checked: Callable[[PokerHand], CheckedHand],
    make_hand: HandFactory,
    player_snapshot: PlayerSnapshotter,
    hand_snapshot: HandSnapshotter,
    stakes: Stakes,
) -> None:
    """After UTG raises, everyone else folds: the round ends at once, the raiser's chips stay committed (no payout
    in Milestone 2), and any further action is rejected without changes."""
    h = checked(make_hand({5: 1000, 8: 1000, 1: 1000, 3: 1000}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(stakes)
    h.act((3, raise_to(30)), (5, FOLD), (8, FOLD), (1, FOLD))

    assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
    assert player_snapshot(h.hand) == {
        5: (1000, 0, 0, True, False),
        8: (995, 5, 5, True, False),
        1: (990, 10, 10, True, False),
        3: (970, 30, 30, False, False),
    }

    before = hand_snapshot(h.hand)
    with pytest.raises(NotPlayersTurnError):
        apply_action(h.hand, 3, CHECK)
    assert hand_snapshot(h.hand) == before


def test_last_player_calls_all_in_opponents_and_later_rounds_start_complete(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory, stakes: Stakes
) -> None:
    """Both halves of the all-opponents-all-in rule. The button raises all-in and the small blind calls all-in: the
    big blind still owes chips, so it can only call or fold, and its call closes the round. On every later street the
    big blind owes nothing and nobody could respond, so each round is complete as soon as it starts, without a check."""
    h = checked(make_hand({1: 300, 2: 300, 3: 2000}, button_seat_number=1))
    h.start(stakes)
    h.act((1, raise_to(300)), (2, CALL))

    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3})
    assert legal_actions(h.hand) == LegalActions(
        can_fold=True,
        can_check=False,
        can_call=True,
        amount_owed=290,
        call_amount=290,
        call_is_all_in=False,
        can_bet=False,
        can_raise=False,
        min_full_target=None,
        max_target=None,
        short_all_in_target=None,
    )
    h.act((3, CALL))
    assert is_round_complete(h.betting)

    for street in (Street.FLOP, Street.TURN, Street.RIVER):
        h.next_street()
        assert h.betting.street is street
        assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())


# =============================================================================
# LATER STREETS
# =============================================================================


def test_later_streets_reset_street_contributions_and_skip_folded_players(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory, stakes: Stakes
) -> None:
    """From preflop through the river, each new round resets street contributions, keeps totals, restores the
    big-blind minimum and starts with the first live player after the button, skipping players who folded."""
    h = checked(make_hand({5: 800, 8: 1200, 1: 1000, 3: 600}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(stakes)
    seats = h.seats

    def round_start() -> tuple[Street, dict[int, int], int, int, int | None, set[int]]:
        return (
            h.betting.street,
            {seat: hp.street_contribution for seat, hp in seats.items()},
            h.betting.current_bet,
            h.betting.last_full_raise_size,
            h.betting.current_actor,
            h.betting.pending_actors,
        )

    def totals() -> dict[int, int]:
        return {seat: hp.total_contribution for seat, hp in seats.items()}

    no_street_chips = {5: 0, 8: 0, 1: 0, 3: 0}

    h.act((3, raise_to(30)), (5, CALL), (8, FOLD), (1, CALL))
    h.next_street()  # the small blind folded, so the big blind acts first
    assert round_start() == (Street.FLOP, no_street_chips, 0, 10, 1, {5, 1, 3})
    assert totals() == {5: 30, 8: 5, 1: 30, 3: 30}

    h.act((1, CHECK), (3, bet(50)), (5, raise_to(150)), (1, FOLD), (3, CALL))
    h.next_street()  # both blinds folded, so UTG acts first
    assert round_start() == (Street.TURN, no_street_chips, 0, 10, 3, {5, 3})
    assert totals() == {5: 180, 8: 5, 1: 30, 3: 180}

    h.act((3, CHECK), (5, bet(100)), (3, CALL))
    h.next_street()
    assert round_start() == (Street.RIVER, no_street_chips, 0, 10, 3, {5, 3})

    h.act((3, CHECK), (5, CHECK))
    assert is_round_complete(h.betting)
    assert totals() == {5: 280, 8: 5, 1: 30, 3: 280}


# =============================================================================
# ATOMIC FAILURES MID-HAND
# =============================================================================


type Attempt = Callable[[PokerHand, Stakes], None]


@pytest.mark.parametrize(
    "actions_first, attempt, error",
    [
        pytest.param([], lambda hand, stakes: apply_action(hand, 2, CALL), NotPlayersTurnError, id="out-of-turn"),
        pytest.param(
            [],
            lambda hand, stakes: apply_action(hand, 1, raise_to(99)),
            IllegalActionError,
            id="raise-below-new-minimum",
        ),
        pytest.param(
            [],
            lambda hand, stakes: start_betting_round(hand),
            BettingRoundNotCompleteError,
            id="round-start-before-round-completes",
        ),
        pytest.param(
            [(1, CALL), (2, CALL)],
            lambda hand, stakes: start_betting_round(hand),
            BettingRoundAlreadyStartedError,
            id="second-round-start-on-same-street",
        ),
        pytest.param(
            [],
            lambda hand, stakes: initialize_betting(hand, stakes),
            BettingAlreadyInitializedError,
            id="repeated-initialization",
        ),
    ],
)
def test_rejected_operation_mid_hand_changes_nothing(
    actions_first: list[tuple[int, Action]],
    attempt: Attempt,
    error: type[Exception],
    checked: Callable[[PokerHand], CheckedHand],
    make_hand: HandFactory,
    hand_snapshot: HandSnapshotter,
    stakes: Stakes,
) -> None:
    """On the flop after a bet and a re-raise (current bet 60, next minimum raise 100, the button to act), a rejected
    operation leaves every stack, contribution, flag and the betting state exactly as they were."""
    h = checked(make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1))
    h.start(stakes)
    h.act((1, CALL), (2, CALL), (3, CHECK))
    h.next_street()
    h.act((2, bet(20)), (3, raise_to(60)))
    assert (h.betting.current_actor, legal_actions(h.hand).min_full_target) == (1, 100)
    h.act(*actions_first)
    before = hand_snapshot(h.hand)

    with pytest.raises(error):
        attempt(h.hand, stakes)

    assert hand_snapshot(h.hand) == before

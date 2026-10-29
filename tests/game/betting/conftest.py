"""Shared betting test helpers, exposed as fixtures because test modules cannot import each other."""

import copy
from collections.abc import Callable

import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.actions import Action
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.street import Street

STAKES = Stakes(small_blind=5, big_blind=10)

# stack, street contribution, total contribution, folded, all-in
type PlayerSnapshot = tuple[int, int, int, bool, bool]
type HandSnapshot = tuple[Street, dict[int, PlayerSnapshot], BettingState | None]


def _make_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """Build a hand clockwise from the button with an unshuffled deck, each seat's player holding the given stack."""
    assignments = assign_hand_seats(tuple(stacks), button_seat_number)
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=stacks[seat_number], status=PlayerStatus.READY),
            seat_number=seat_number,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat_number, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=Deck())


def _started_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """A hand with its blinds posted and preflop betting initialized at STAKES."""
    hand = _make_hand(stacks, button_seat_number)
    initialize_betting(hand, STAKES)
    return hand


def _by_seat(hand: PokerHand) -> dict[int, HandPlayerState]:
    return {hand_player.seat_number: hand_player for hand_player in hand.players}


def _betting(hand: PokerHand) -> BettingState:
    assert hand.betting is not None
    return hand.betting


def _player_snapshot(hand: PokerHand) -> dict[int, PlayerSnapshot]:
    return {
        hand_player.seat_number: (
            hand_player.player.stack,
            hand_player.street_contribution,
            hand_player.total_contribution,
            hand_player.folded,
            hand_player.all_in,
        )
        for hand_player in hand.players
    }


def _play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    """Apply each (seat number, action) in order."""
    for seat_number, action in actions:
        apply_action(hand, seat_number, action)


def _hand_snapshot(hand: PokerHand) -> HandSnapshot:
    """Everything betting may change: the street, each player's chips and flags, and a copy of the betting state."""
    return hand.street, _player_snapshot(hand), copy.deepcopy(hand.betting)


@pytest.fixture
def stakes() -> Stakes:
    return STAKES


@pytest.fixture
def make_hand() -> Callable[[dict[int, int], int], PokerHand]:
    return _make_hand


@pytest.fixture
def started_hand() -> Callable[[dict[int, int], int], PokerHand]:
    return _started_hand


@pytest.fixture
def by_seat() -> Callable[[PokerHand], dict[int, HandPlayerState]]:
    return _by_seat


@pytest.fixture
def betting() -> Callable[[PokerHand], BettingState]:
    return _betting


@pytest.fixture
def player_snapshot() -> Callable[[PokerHand], dict[int, PlayerSnapshot]]:
    return _player_snapshot


@pytest.fixture
def play() -> Callable[..., None]:
    return _play


@pytest.fixture
def hand_snapshot() -> Callable[[PokerHand], HandSnapshot]:
    return _hand_snapshot

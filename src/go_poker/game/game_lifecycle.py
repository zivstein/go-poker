from collections.abc import Callable

from .hand_setup import setup_hand
from .player import Player, PlayerStatus
from .poker_hand import PokerHand
from .position import validate_player_count
from .position_assignment import ButtonSeatNotInHandError, order_seats_from_button
from .table import ButtonUndefinedError, Table

type ButtonChooser = Callable[[tuple[int, ...]], int]


class GameAlreadyStartedError(RuntimeError):
    """Raised when starting a game while ready players are already seated."""


class GameNotStartedError(RuntimeError):
    """Raised when moving to the next hand without ready players; the game must be started again."""


def _seated_players_with_status(table: Table, status: PlayerStatus) -> dict[int, Player]:
    return {
        seat.number: seat.player
        for seat in table.occupied_seats
        if seat.player is not None and seat.player.status is status
    }


def _next_ready_seat(ready_seats: tuple[int, ...], anchor: int) -> int:
    # The previous button seat anchors the search even when it no longer holds a ready player.
    seats_from_anchor = order_seats_from_button(tuple({*ready_seats, anchor}), anchor)
    return seats_from_anchor[1] if len(seats_from_anchor) > 1 else seats_from_anchor[0]


def start_game(table: Table, choose_button: ButtonChooser) -> PokerHand:
    """Start a game with every waiting player, place the chosen button and return the first hand."""
    if _seated_players_with_status(table, PlayerStatus.READY):
        raise GameAlreadyStartedError("The game has already started")

    starters = _seated_players_with_status(table, PlayerStatus.WAITING)
    starter_seats = tuple(starters)
    validate_player_count(len(starter_seats))

    button_seat_number = choose_button(starter_seats)
    if button_seat_number not in starter_seats:
        raise ButtonSeatNotInHandError("Button seat must be one of the starting seats")

    previous_button_seat_number = table.button_seat_number
    try:
        for player in starters.values():
            player.status = PlayerStatus.READY
        table.set_button(button_seat_number)
        return PokerHand(players=setup_hand(table))
    except Exception:
        for player in starters.values():
            player.status = PlayerStatus.WAITING
        table.button_seat_number = previous_button_seat_number
        raise


def start_next_hand(table: Table) -> PokerHand:
    """Move the button to the next ready player and return the next hand."""
    ready_seats = tuple(_seated_players_with_status(table, PlayerStatus.READY))
    if not ready_seats:
        raise GameNotStartedError("No ready players are seated; start the game again")

    previous_button_seat_number = table.button_seat_number
    if previous_button_seat_number is None:
        raise ButtonUndefinedError("Button is not defined so it cannot be moved")

    try:
        table.set_button(_next_ready_seat(ready_seats, previous_button_seat_number))
        return PokerHand(players=setup_hand(table))
    except Exception:
        table.button_seat_number = previous_button_seat_number
        raise

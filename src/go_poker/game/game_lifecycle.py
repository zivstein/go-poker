from collections.abc import Callable

from go_poker.core.deck import Deck

from .hand_setup import has_chips_for_hand, setup_hand
from .player import Player, PlayerStatus
from .poker_hand import PokerHand, _require_valid_hand_number
from .position import validate_player_count
from .position_assignment import ButtonSeatNotInHandError, order_seats_from_button
from .table import ButtonUndefinedError, Table

type ButtonChooser = Callable[[tuple[int, ...]], int]


class GameAlreadyStartedError(RuntimeError):
    """Raised when starting a game while ready players are already seated."""


class GameNotStartedError(RuntimeError):
    """Raised when moving to the next hand without ready players who have chips."""


def _seated_players_with_status(table: Table, status: PlayerStatus) -> dict[int, Player]:
    return {
        seat.number: seat.player
        for seat in table.occupied_seats
        if seat.player is not None and seat.player.status is status
    }


def _players_with_chips_for_hand(table: Table, status: PlayerStatus) -> dict[int, Player]:
    # A player without chips may stay seated with any status, but cannot take part in or hold the button of a new hand.
    players = _seated_players_with_status(table, status)
    return {seat_number: player for seat_number, player in players.items() if has_chips_for_hand(player)}


def _next_ready_seat(ready_seats: tuple[int, ...], anchor: int) -> int:
    # The previous button seat anchors the search even when it no longer holds a ready player.
    seats_from_anchor = order_seats_from_button(tuple({*ready_seats, anchor}), anchor)
    return seats_from_anchor[1] if len(seats_from_anchor) > 1 else seats_from_anchor[0]


def _new_hand(table: Table, number: int) -> PokerHand:
    # Shuffle before setup_hand, which promotes entering players, so a shuffle failure happens before that change.
    deck = Deck()
    deck.shuffle()
    return PokerHand(players=setup_hand(table), deck=deck, number=number)


def start_game(table: Table, choose_button: ButtonChooser) -> PokerHand:
    """Start a game with every waiting player who has chips, place the chosen button and return hand number 1."""
    if _seated_players_with_status(table, PlayerStatus.READY):
        raise GameAlreadyStartedError("The game has already started")

    starters = _players_with_chips_for_hand(table, PlayerStatus.WAITING)
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
        return _new_hand(table, 1)
    except Exception:
        for player in starters.values():
            player.status = PlayerStatus.WAITING
        table.button_seat_number = previous_button_seat_number
        raise


def start_next_hand(table: Table, hand_number: int) -> PokerHand:
    """Move the button to the next ready player who has chips and return the next hand, numbered `hand_number`.

    The caller supplies the number (any positive integer; the lifecycle keeps no counter). It is validated first,
    before any other check or change, so a bad number never leaves a promoted entrant behind.
    """
    _require_valid_hand_number(hand_number)
    ready_seats = tuple(_players_with_chips_for_hand(table, PlayerStatus.READY))
    if not ready_seats:
        raise GameNotStartedError("No ready players with chips are seated")

    previous_button_seat_number = table.button_seat_number
    if previous_button_seat_number is None:
        raise ButtonUndefinedError("Button is not defined so it cannot be moved")

    try:
        table.set_button(_next_ready_seat(ready_seats, previous_button_seat_number))
        return _new_hand(table, hand_number)
    except Exception:
        table.button_seat_number = previous_button_seat_number
        raise

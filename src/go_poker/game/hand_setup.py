from .hand_state import HandPlayerState
from .player import Player, PlayerStatus
from .position import Position
from .position_assignment import HandSeatAssignment, assign_hand_seats
from .table import ButtonUndefinedError, Table

CANDIDATE_STATUSES = (PlayerStatus.READY, PlayerStatus.WAITING)
POSITIONS_CLOSED_TO_WAITING_PLAYERS = (Position.BTN, Position.SB)


def _candidate_players(table: Table) -> dict[int, Player]:
    return {
        seat.number: seat.player
        for seat in table.occupied_seats
        if seat.player is not None and seat.player.status in CANDIDATE_STATUSES
    }


def _assign_entering_seats(statuses: dict[int, PlayerStatus], button_seat_number: int) -> dict[int, HandSeatAssignment]:
    seat_numbers = tuple(statuses)

    # Dropping a waiting player shifts the positions behind them, so reassign until nobody else is dropped.
    while True:
        assignments = assign_hand_seats(seat_numbers, button_seat_number)
        blocked_seats = {
            seat_number
            for seat_number, assignment in assignments.items()
            if statuses[seat_number] is PlayerStatus.WAITING
            and assignment.position in POSITIONS_CLOSED_TO_WAITING_PLAYERS
        }
        if not blocked_seats:
            return assignments

        seat_numbers = tuple(seat_number for seat_number in seat_numbers if seat_number not in blocked_seats)


def setup_hand(table: Table) -> tuple[HandPlayerState, ...]:
    """Return the players of the next hand, ordered clockwise starting at the button."""
    button_seat_number = table.button_seat_number
    if button_seat_number is None:
        raise ButtonUndefinedError("Button is not defined so a hand cannot be set up")

    players = _candidate_players(table)
    statuses = {seat_number: player.status for seat_number, player in players.items()}
    assignments = _assign_entering_seats(statuses, button_seat_number)

    hand_players = tuple(
        HandPlayerState(
            player=players[seat_number],
            seat_number=seat_number,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat_number, assignment in assignments.items()
    )

    for hand_player in hand_players:
        hand_player.player.status = PlayerStatus.READY

    return hand_players

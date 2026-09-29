from dataclasses import dataclass

from .position import Blind, Position, positions_for_player_count


class ButtonSeatNotInHandError(ValueError):
    """Raised when the button seat is not part of the hand."""


class DuplicateSeatNumberError(ValueError):
    """Raised when the same seat appears more than once."""


@dataclass(frozen=True)
class HandSeatAssignment:
    position: Position
    blind: Blind


def order_seats_from_button(seat_numbers: tuple[int, ...], button_seat_number: int) -> tuple[int, ...]:
    if len(set(seat_numbers)) != len(seat_numbers):
        raise DuplicateSeatNumberError("Seat numbers in a hand must be unique")

    if button_seat_number not in seat_numbers:
        raise ButtonSeatNotInHandError("Button seat must be one of the participating seats")

    ordered_seats = sorted(seat_numbers)
    button_index = ordered_seats.index(button_seat_number)
    return tuple(ordered_seats[button_index:] + ordered_seats[:button_index])


def assign_positions(seat_numbers: tuple[int, ...], button_seat_number: int) -> dict[int, Position]:
    ordered_seats = order_seats_from_button(seat_numbers, button_seat_number)
    positions = positions_for_player_count(len(ordered_seats))
    return dict(zip(ordered_seats, positions, strict=True))


def assign_blinds(positions: dict[int, Position]) -> dict[int, Blind]:
    player_count = len(positions)
    blinds: dict[int, Blind] = {}

    for seat_number, position in positions.items():
        if position == Position.BB:
            blind = Blind.BIG
        elif position == Position.SB:
            blind = Blind.SMALL
        elif player_count == 2 and position == Position.BTN:
            blind = Blind.SMALL
        else:
            blind = Blind.NONE

        blinds[seat_number] = blind

    return blinds


def assign_hand_seats(seat_numbers: tuple[int, ...], button_seat_number: int) -> dict[int, HandSeatAssignment]:
    positions = assign_positions(seat_numbers, button_seat_number)
    blinds = assign_blinds(positions)

    return {
        seat_number: HandSeatAssignment(position=position, blind=blinds[seat_number])
        for seat_number, position in positions.items()
    }

from .player import Player
from .seat import Seat


class InvalidSeatNumber(IndexError): ...


class InvalidTableSize(ValueError): ...


class PlayerAlreadySeatedError(ValueError): ...


class EmptySeatError(ValueError): ...


class ButtonUndefinedError(RuntimeError): ...


class Table:
    def __init__(self, max_seats: int) -> None:
        if max_seats < 2 or max_seats > 9:
            raise InvalidTableSize("A table can only contain a max seats of 2-9 ")
        self.max_seats = max_seats
        self._seats: list[Seat] = self.create_new_empty_seats()
        self.button_seat_number: int | None = None

    def create_new_empty_seats(self) -> list[Seat]:
        return [Seat(number) for number in range(1, self.max_seats + 1)]

    def get_seat(self, seat_number: int) -> Seat:
        if not (1 <= seat_number <= self.max_seats):
            raise InvalidSeatNumber("You have requested to get a seat that does not exist.")
        return self._seats[seat_number - 1]

    def sit_in(self, player: Player, seat_number: int) -> None:
        seat = self.get_seat(seat_number)
        for check_seat in self._seats:
            seated_player = check_seat.player
            if seated_player is not None and seated_player.player_id == player.player_id:
                raise PlayerAlreadySeatedError(f"Player is already seated at seat {check_seat.number}")
        seat.sit_in(player)

    def stand_up(self, seat_number: int) -> None:
        self.get_seat(seat_number).stand_up()

    @property
    def player_count(self) -> int:
        return sum(seat.is_occupied for seat in self._seats)

    @property
    def occupied_seats(self) -> list[Seat]:
        return [seat for seat in self._seats if seat.is_occupied]

    def set_button(self, seat_number: int) -> None:
        seat = self.get_seat(seat_number)
        if seat.is_occupied is False:
            raise EmptySeatError("You have tried to set the button to an empty seat")
        self.button_seat_number = seat_number

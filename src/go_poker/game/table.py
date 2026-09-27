from .seat import Seat


class InvalidSeatNumber(IndexError):
    ...


class PlayerAlreadySeatedError(ValueError):
    ...


class EmptySeatError(ValueError):
    ...


class ButtonUndefinedError(TypeError):
    ...


class Table:
    def __init__(self, max_seats: int) -> None:
        if max_seats < 2 or max_seats > 9:
            raise InvalidSeatNumber("A table can only contain a max seats of 2-9 ")
        self.max_seats = max_seats
        self._seats: list[Seat] = self.create_new_empty_seats()
        self.button_seat_number: int | None = None

    def create_new_empty_seats(self) -> list[Seat]:
        return [Seat(number) for number in range(1, self.max_seats + 1)]

    def get_seat(self, seat_number: int) -> Seat:
        if not(1 <= seat_number <= self.max_seats):
            raise InvalidSeatNumber("You have requested to get a seat that does not exist.")
        return self._seats[seat_number-1]

    def sit_in(self, player_id: str, seat_number: int) -> None:
        seat = self.get_seat(seat_number)
        for check_seat in self._seats:
            if player_id == check_seat.player_id:
                raise PlayerAlreadySeatedError(f"Player is already seated at seat {check_seat.number}")
        seat.sit_in(player_id)

    def stand_up(self, seat_number: int) -> None:
        self.get_seat(seat_number).stand_up()

    @property
    def player_count(self) -> int:
        return sum(seat.is_occupied for seat in self._seats)
    @property
    def occupied_seats(self) -> list[Seat]:
        return [seat for seat in self._seats if seat.is_occupied]

    def get_next_occupied_seat(self, after_seat_number: int) -> Seat:
        self.get_seat(after_seat_number)

        for offset in range(1, self.max_seats + 1):
            seat_number = (
                (after_seat_number - 1 + offset) % self.max_seats
            ) + 1

            seat = self.get_seat(seat_number)

            if seat.is_occupied:
                return seat

        raise EmptySeatError("There are no occupied seats at the table")

    def set_button(self, seat_number: int) -> None:
        seat = self.get_seat(seat_number)
        if seat.is_occupied is False:
            raise EmptySeatError("You have tried to set the button to an empty seat")
        self.button_seat_number = seat_number

    def move_button(self) -> None:
        if self.button_seat_number is None:
            raise ButtonUndefinedError("Button is not defined so it cannot be moved")
        next_seat = self.get_next_occupied_seat(self.button_seat_number)
        self.button_seat_number = next_seat.number

        

    
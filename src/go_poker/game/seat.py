from dataclasses import dataclass


class SeatOccupiedError(ValueError):
    """Raised when trying to occupy an occupied seat."""


@dataclass
class Seat:
    number: int
    player_id: str | None = None

    @property
    def is_occupied(self) -> bool:
        return self.player_id is not None

    def sit_in(self, player_id: str) -> None:
        if self.is_occupied:
            raise SeatOccupiedError("This seat is already occupied")

        self.player_id = player_id

    def stand_up(self) -> None:
        self.player_id = None
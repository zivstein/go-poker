from dataclasses import dataclass

from .player import Player


class SeatOccupiedError(ValueError):
    """Raised when trying to occupy an occupied seat."""


@dataclass
class Seat:
    number: int
    player: Player | None = None

    @property
    def is_occupied(self) -> bool:
        return self.player is not None

    def sit_in(self, player: Player) -> None:
        if self.is_occupied:
            raise SeatOccupiedError("This seat is already occupied")

        self.player = player

    def stand_up(self) -> None:
        self.player = None

from dataclasses import dataclass
from enum import Enum


class InvalidStackError(ValueError):
    """Raised when a player is created with an invalid stack."""


class PlayerStatus(Enum):
    READY = "Ready"
    WAITING = "Waiting"
    SITTING_OUT = "Sitting out"


@dataclass
class Player:
    player_id: str
    stack: int
    status: PlayerStatus = PlayerStatus.WAITING

    def __post_init__(self) -> None:
        if self.stack < 0:
            raise InvalidStackError("Player stack cannot be negative")

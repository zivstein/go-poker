from dataclasses import dataclass
from enum import Enum
from typing import Any


class InvalidStackError(ValueError):
    """Raised when a player is created with an invalid stack."""


class InvalidPlayerIdError(ValueError):
    """Raised when a player is created with a `player_id` that is not a non-empty string."""


class PlayerStatus(Enum):
    READY = "Ready"
    WAITING = "Waiting"
    SITTING_OUT = "Sitting out"


@dataclass
class Player:
    """A participant of the engine.

    `player_id` is the stable logical identity of the participant (see ADR 0004 §6): an opaque, caller-assigned,
    non-empty string, read-only after creation. It is not a display name or an account identity. The engine enforces
    only that it is unique among the players currently seated at a table. `stack` and `status` stay mutable.
    """

    player_id: str
    stack: int
    status: PlayerStatus = PlayerStatus.WAITING

    def __post_init__(self) -> None:
        if not isinstance(self.player_id, str) or self.player_id == "":
            raise InvalidPlayerIdError("Player id must be a non-empty string")
        if self.stack < 0:
            raise InvalidStackError("Player stack cannot be negative")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "player_id" and "player_id" in self.__dict__:
            raise AttributeError("Player id cannot be changed after creation")
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        if name == "player_id":
            raise AttributeError("Player id cannot be deleted")
        super().__delattr__(name)

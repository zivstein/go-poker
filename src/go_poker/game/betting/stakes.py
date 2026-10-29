from dataclasses import dataclass


class InvalidStakesError(ValueError):
    """Raised when stakes are created with a non-positive blind or a small blind above the big blind."""


@dataclass(frozen=True)
class Stakes:
    """The blinds of a hand: both positive, the small blind never above the big blind (equal blinds are valid)."""

    small_blind: int
    big_blind: int

    def __post_init__(self) -> None:
        if self.small_blind <= 0 or self.big_blind <= 0:
            raise InvalidStakesError("Both blinds must be positive")
        if self.small_blind > self.big_blind:
            raise InvalidStakesError("The small blind cannot be larger than the big blind")

from enum import Enum


class Street(Enum):
    """The streets of a hand, in the order they are played."""

    PREFLOP = "Preflop"
    FLOP = "Flop"
    TURN = "Turn"
    RIVER = "River"

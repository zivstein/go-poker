from enum import Enum


class InvalidPlayerCount(ValueError):
    """ Raised when player count provided is not valid (2-9) """
    
class Blind(Enum):
    NONE = "NONE"
    SMALL = "SB"
    BIG = "BB"

    def __str__(self) -> str:
        return self.value


class Position(Enum):
    UTG = "UTG"
    UTG1 = "UTG+1"
    MP = "MP"
    LJ = "LJ"
    HJ = "HJ"
    CO = "CO"
    BTN = "BTN"
    SB = "SB"
    BB = "BB"

    def __str__(self) -> str:
        return self.value

POSITIONS_BY_PLAYER_COUNT: dict[int, tuple[Position, ...]] = {
    9: (
        Position.UTG,
        Position.UTG1,
        Position.MP,
        Position.LJ,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    8: (
        Position.UTG,
        Position.UTG1,
        Position.LJ,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    7: (
        Position.UTG,
        Position.LJ,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    6: (
        Position.UTG,
        Position.HJ,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    5: (
        Position.UTG,
        Position.CO,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    4: (
        Position.UTG,
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    3: (
        Position.BTN,
        Position.SB,
        Position.BB,
    ),
    2: (
        Position.BTN,
        Position.BB,
    )             
}

def positions_for_player_count(player_count: int) -> tuple[Position, ...]:
    if player_count < 2 or player_count > 9:
        raise InvalidPlayerCount("Player count must be between 2 and 9")
    return POSITIONS_BY_PLAYER_COUNT[player_count]
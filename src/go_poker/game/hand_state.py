from dataclasses import dataclass

from go_poker.game.player import Player
from go_poker.game.position import Blind, Position


@dataclass
class HandPlayerState:
    player: Player
    seat_number: int
    position: Position
    blind: Blind

    folded: bool = False
    all_in: bool = False

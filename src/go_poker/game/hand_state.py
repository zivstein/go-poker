from dataclasses import dataclass, field

from go_poker.core.card import Card
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
    # Private cards for this hand; empty until dealt. The variant's rules decide how many are dealt.
    hole_cards: list[Card] = field(default_factory=list)

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
    # Chips committed in the current betting round and in the whole hand; the player's stack holds the rest.
    street_contribution: int = 0
    total_contribution: int = 0
    # Private cards for this hand; empty until dealt. The variant's rules decide how many are dealt.
    hole_cards: list[Card] = field(default_factory=list)

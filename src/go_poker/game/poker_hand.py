from dataclasses import dataclass, field

from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState


@dataclass
class PokerHand:
    """One hand of poker: its participants, its own deck and the community board.

    Participants come from hand setup, clockwise from the button; participation rules are not re-checked here.
    """

    players: tuple[HandPlayerState, ...]
    deck: Deck = field(default_factory=Deck)
    board: list[Card] = field(default_factory=list)

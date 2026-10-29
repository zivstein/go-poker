from dataclasses import dataclass, field

from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.street import Street


@dataclass
class PokerHand:
    """One hand of poker: its participants, its own deck, the community board, the street and the burned cards.

    Participants come from hand setup, clockwise from the button; participation rules are not re-checked here.
    A hand starts on the preflop street with an empty board and no burned cards; variant rules deal the board,
    burn cards and advance the street.
    """

    players: tuple[HandPlayerState, ...]
    deck: Deck = field(default_factory=Deck)
    board: list[Card] = field(default_factory=list)
    street: Street = Street.PREFLOP
    # Cards burned before board cards; kept so every card drawn from the deck stays accounted for.
    burned_cards: list[Card] = field(default_factory=list)

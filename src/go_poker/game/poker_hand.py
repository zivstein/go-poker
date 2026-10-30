from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.street import Street

if TYPE_CHECKING:
    # Type-only: settlement reaches PokerHand through the pots it derives from a hand.
    from go_poker.game.settlement import Settlement


@dataclass
class PokerHand:
    """One hand of poker: its participants, its own deck, the community board, the street and the burned cards.

    Participants come from hand setup, clockwise from the button; participation rules are not re-checked here.
    The deck is required: the hand owns the deck's state for the hand, but not its shuffle policy, which belongs to
    the lifecycle that creates the hand. A hand starts on the preflop street with an empty board and no burned cards;
    variant rules deal the board, burn cards and advance the street. The hand has no betting state until the betting
    layer initializes it; betting rules live in that layer, not here. It has no settlement until the hand is settled;
    the stored settlement is immutable, and its presence marks the hand as settled.
    """

    players: tuple[HandPlayerState, ...]
    deck: Deck
    board: list[Card] = field(default_factory=list)
    street: Street = Street.PREFLOP
    # Cards burned before board cards; kept so every card drawn from the deck stays accounted for.
    burned_cards: list[Card] = field(default_factory=list)
    betting: BettingState | None = None
    settlement: Settlement | None = None

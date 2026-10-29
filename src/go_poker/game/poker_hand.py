from dataclasses import dataclass, field

from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.street import Street


class DuplicateCardError(ValueError):
    """Raised when a card appears more than once across a hand's hole cards, board, burned cards and deck."""


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


def ensure_unique_cards(hand: PokerHand) -> None:
    """Raise DuplicateCardError unless every card appears at most once across hole cards, board, burned cards and deck.

    Card uniqueness holds for every variant, so variant dealing rules check it before drawing.
    """
    dealt_cards = [card for state in hand.players for card in state.hole_cards] + hand.board + hand.burned_cards
    seen: set[Card] = set()
    for card in dealt_cards:
        if card in seen:
            raise DuplicateCardError(f"The {card} appears more than once in the hand")
        if card in hand.deck:
            raise DuplicateCardError(f"The {card} has been dealt but is still in the deck")
        seen.add(card)

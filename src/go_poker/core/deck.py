from random import shuffle

from .card import Card, Rank, Suit

class DeckEmptyError(IndexError):
    """Raised when drawing from an empty deck."""

class Deck:
    def __init__(self) -> None:
        self.cards: list[Card] = self.create_new_deck()

    @staticmethod
    def create_new_deck() -> list[Card]:
        new_deck: list[Card] = []
        for rank in Rank:
            for suit in Suit:
                new_deck.append(Card(rank, suit))
        return new_deck

    def shuffle(self) -> None:
        shuffle(self._deck)

    def draw(self) -> Card:
        if len(self._deck) == 0:
            raise DeckEmptyError("The deck is empty")
        return self._deck.pop()

    def __len__(self) -> int:
        return len(self._deck)

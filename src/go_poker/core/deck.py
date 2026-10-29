import random

from .card import Card, Rank, Suit

# Engine shuffles use the OS CSPRNG, which cannot be seeded, so production deck orders are unpredictable.
_SYSTEM_RANDOM = random.SystemRandom()


class DeckEmptyError(IndexError):
    """Raised when drawing from an empty deck."""


class Deck:
    def __init__(self) -> None:
        self._deck: list[Card] = self.create_new_deck()

    @staticmethod
    def create_new_deck() -> list[Card]:
        new_deck: list[Card] = []
        for rank in Rank:
            for suit in Suit:
                new_deck.append(Card(rank, suit))
        return new_deck

    def shuffle(self, *, _rng: random.Random | None = None) -> None:
        """Shuffle the remaining cards with the OS CSPRNG.

        ``_rng`` is test-only: tests pass a seeded generator for a reproducible order. Engine code must never pass it.
        """
        (_SYSTEM_RANDOM if _rng is None else _rng).shuffle(self._deck)

    def draw(self) -> Card:
        if len(self._deck) == 0:
            raise DeckEmptyError("The deck is empty")
        return self._deck.pop()

    def __len__(self) -> int:
        return len(self._deck)

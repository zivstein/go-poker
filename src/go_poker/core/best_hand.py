from collections.abc import Sequence
from dataclasses import dataclass

from .card import Card, Rank
from .hand_rank import HandCategory, HandRank

# Each rank's English name and its plural.
_NAMES = {
    Rank.TWO: ("Two", "Twos"),
    Rank.THREE: ("Three", "Threes"),
    Rank.FOUR: ("Four", "Fours"),
    Rank.FIVE: ("Five", "Fives"),
    Rank.SIX: ("Six", "Sixes"),
    Rank.SEVEN: ("Seven", "Sevens"),
    Rank.EIGHT: ("Eight", "Eights"),
    Rank.NINE: ("Nine", "Nines"),
    Rank.TEN: ("Ten", "Tens"),
    Rank.JACK: ("Jack", "Jacks"),
    Rank.QUEEN: ("Queen", "Queens"),
    Rank.KING: ("King", "Kings"),
    Rank.ACE: ("Ace", "Aces"),
}
_WHEEL = (Rank.FIVE,)


def _name(value: int) -> str:
    return _NAMES[Rank(value)][0]


def _plural(value: int) -> str:
    return _NAMES[Rank(value)][1]


def _is_wheel(rank: HandRank) -> bool:
    return rank.category in (HandCategory.STRAIGHT, HandCategory.STRAIGHT_FLUSH) and rank.tiebreakers == _WHEEL


def _describe(rank: HandRank) -> str:
    """The English description of a rank, from its category and tiebreakers only (no kickers)."""
    high = rank.tiebreakers[0]
    match rank.category:
        case HandCategory.HIGH_CARD:
            return f"{_name(high)} high"
        case HandCategory.ONE_PAIR:
            return f"Pair of {_plural(high)}"
        case HandCategory.TWO_PAIR:
            return f"Two pair, {_plural(high)} and {_plural(rank.tiebreakers[1])}"
        case HandCategory.THREE_OF_A_KIND:
            return f"Three of a kind, {_plural(high)}"
        case HandCategory.STRAIGHT:
            return f"{_name(high)}-high straight"
        case HandCategory.FLUSH:
            return f"{_name(high)}-high flush"
        case HandCategory.FULL_HOUSE:
            return f"{_plural(high)} full of {_plural(rank.tiebreakers[1])}"
        case HandCategory.FOUR_OF_A_KIND:
            return f"Four of a kind, {_plural(high)}"
        case HandCategory.STRAIGHT_FLUSH:
            return "Royal flush" if high == Rank.ACE else f"{_name(high)}-high straight flush"


@dataclass(frozen=True)
class BestHand:
    """A player's best five-card hand: its `HandRank` (not a `Card.rank`), the exact five cards in order of
    significance, and a description derived from the rank.

    The cards are the quads then the kicker, the trips then the pair, and so on, high to low; the wheel is 5-4-3-2-A.
    The description names the category and its ranks, never kickers. A `BestHand` is built by the engine and not
    validated on construction, and it has no ordering: compare strengths through `rank`.
    """

    rank: HandRank
    cards: tuple[Card, Card, Card, Card, Card]

    @property
    def description(self) -> str:
        return _describe(self.rank)


def _best_hand(rank: HandRank, cards_in_deal_order: Sequence[Card]) -> BestHand:
    """Put the five cards of a rank in order of significance. Engine-internal.

    Cards with the same rank keep the order they are given in, so a caller passing deal order gets deal order. Cards are
    ordered by how many of their rank the hand holds, then by rank, with the Ace low in the wheel.
    """
    counts: dict[Rank, int] = {}
    for card in cards_in_deal_order:
        counts[card.rank] = counts.get(card.rank, 0) + 1
    wheel = _is_wheel(rank)

    def significance(card: Card) -> tuple[int, int]:
        effective = 1 if wheel and card.rank is Rank.ACE else card.rank
        return -counts[card.rank], -effective

    first, second, third, fourth, fifth = sorted(cards_in_deal_order, key=significance)
    return BestHand(rank, (first, second, third, fourth, fifth))

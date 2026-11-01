import dataclasses

import pytest

from go_poker.core.best_hand import BestHand
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.hand_rank import HandCategory, HandRank

# BestHand is engine-built and never validated, so these tests only need its derived description. Its card order and
# selection come from Hold'em hand strength and are tested with it.

FIVE_CARDS = tuple(Card(Rank(value), Suit.CLUBS) for value in (2, 4, 6, 8, 10))


def described(category: HandCategory, *tiebreakers: int) -> str:
    return BestHand(HandRank(category, tiebreakers), FIVE_CARDS).description


@pytest.mark.parametrize(
    "category, tiebreakers, expected",
    [
        pytest.param(HandCategory.HIGH_CARD, (14, 11, 9, 6, 2), "Ace high", id="high-card-ace"),
        pytest.param(HandCategory.HIGH_CARD, (7, 5, 4, 3, 2), "Seven high", id="high-card-seven"),
        pytest.param(HandCategory.ONE_PAIR, (8, 14, 9, 3), "Pair of Eights", id="pair"),
        pytest.param(HandCategory.ONE_PAIR, (6, 14, 9, 3), "Pair of Sixes", id="pair-plural-es"),
        pytest.param(HandCategory.TWO_PAIR, (13, 4, 9), "Two pair, Kings and Fours", id="two-pair"),
        pytest.param(HandCategory.TWO_PAIR, (6, 3, 2), "Two pair, Sixes and Threes", id="two-pair-plurals"),
        pytest.param(HandCategory.THREE_OF_A_KIND, (7, 14, 2), "Three of a kind, Sevens", id="trips"),
        pytest.param(HandCategory.STRAIGHT, (9,), "Nine-high straight", id="straight"),
        pytest.param(HandCategory.STRAIGHT, (14,), "Ace-high straight", id="broadway"),
        pytest.param(HandCategory.STRAIGHT, (5,), "Five-high straight", id="wheel"),
        pytest.param(HandCategory.FLUSH, (14, 11, 9, 6, 2), "Ace-high flush", id="flush"),
        pytest.param(HandCategory.FLUSH, (10, 8, 6, 4, 2), "Ten-high flush", id="flush-ten"),
        pytest.param(HandCategory.FULL_HOUSE, (8, 14), "Eights full of Aces", id="full-house"),
        pytest.param(HandCategory.FULL_HOUSE, (2, 3), "Twos full of Threes", id="full-house-twos"),
        pytest.param(HandCategory.FOUR_OF_A_KIND, (12, 2), "Four of a kind, Queens", id="quads"),
        pytest.param(HandCategory.STRAIGHT_FLUSH, (9,), "Nine-high straight flush", id="straight-flush"),
        pytest.param(HandCategory.STRAIGHT_FLUSH, (5,), "Five-high straight flush", id="wheel-straight-flush"),
        pytest.param(HandCategory.STRAIGHT_FLUSH, (13,), "King-high straight flush", id="king-high-straight-flush"),
        pytest.param(HandCategory.STRAIGHT_FLUSH, (14,), "Royal flush", id="royal-flush"),
    ],
)
def test_description(category: HandCategory, tiebreakers: tuple[int, ...], expected: str) -> None:
    assert described(category, *tiebreakers) == expected


@pytest.mark.parametrize(
    "value, singular, plural",
    [
        (2, "Two", "Twos"),
        (3, "Three", "Threes"),
        (4, "Four", "Fours"),
        (5, "Five", "Fives"),
        (6, "Six", "Sixes"),
        (7, "Seven", "Sevens"),
        (8, "Eight", "Eights"),
        (9, "Nine", "Nines"),
        (10, "Ten", "Tens"),
        (11, "Jack", "Jacks"),
        (12, "Queen", "Queens"),
        (13, "King", "Kings"),
        (14, "Ace", "Aces"),
    ],
)
def test_every_rank_is_named_singular_and_plural(value: int, singular: str, plural: str) -> None:
    assert described(HandCategory.HIGH_CARD, value) == f"{singular} high"
    assert described(HandCategory.THREE_OF_A_KIND, value) == f"Three of a kind, {plural}"


def test_description_follows_the_rank_and_cannot_disagree() -> None:
    first = BestHand(HandRank(HandCategory.FLUSH, (14, 11, 9, 6, 2)), FIVE_CARDS)
    second = dataclasses.replace(first, rank=HandRank(HandCategory.FOUR_OF_A_KIND, (12, 2)))
    assert first.description == "Ace-high flush"
    assert second.description == "Four of a kind, Queens"


def test_description_is_read_only() -> None:
    best = BestHand(HandRank(HandCategory.HIGH_CARD, (14, 11, 9, 6, 2)), FIVE_CARDS)
    with pytest.raises(AttributeError):
        best.description = "Something else"  # type: ignore[misc]
    assert "description" not in {field.name for field in dataclasses.fields(best)}


def test_best_hand_is_frozen_and_unordered() -> None:
    best = BestHand(HandRank(HandCategory.HIGH_CARD, (14, 11, 9, 6, 2)), FIVE_CARDS)
    with pytest.raises(dataclasses.FrozenInstanceError):
        best.rank = HandRank(HandCategory.FLUSH, (14, 11, 9, 6, 2))  # type: ignore[misc]
    with pytest.raises(TypeError):
        best < best  # type: ignore[operator]  # noqa: B015
    assert best == BestHand(HandRank(HandCategory.HIGH_CARD, (14, 11, 9, 6, 2)), FIVE_CARDS)

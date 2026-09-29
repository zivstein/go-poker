import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.evaluator import DuplicateCardsError, WrongCardAmountError, evaluate_best, evaluate_five
from go_poker.core.hand_rank import HandCategory, HandRank


@pytest.mark.parametrize("suit", list(Suit))
@pytest.mark.parametrize(
    "ranks, expected_tiebreakers",
    [
        pytest.param((9, 2, 14, 6, 11), (14, 11, 9, 6, 2), id="unsorted-ace-high-flush"),
        pytest.param((2, 3, 4, 5, 7), (7, 5, 4, 3, 2), id="gap-at-end-is-not-straight-flush"),
        pytest.param((2, 3, 4, 6, 14), (14, 6, 4, 3, 2), id="ace-with-gap-is-not-wheel"),
        pytest.param((12, 13, 14, 2, 3), (14, 13, 12, 3, 2), id="straight-cannot-wrap-through-ace"),
    ],
)
def test_flush(ranks: tuple[int, ...], expected_tiebreakers: tuple[int, ...], suit: Suit) -> None:
    """A nonconsecutive flush keeps all five ranks as descending tiebreakers."""
    cards = tuple(Card(Rank(rank), suit) for rank in ranks)
    result = evaluate_five(cards)
    assert result == HandRank(HandCategory.FLUSH, expected_tiebreakers)


@pytest.mark.parametrize("high_card", range(5, 15))
def test_straight(high_card: int) -> None:
    """Recognize every straight, with the wheel using five as its high card."""
    ranks = (14, 2, 3, 4, 5) if high_card == 5 else tuple(range(high_card - 4, high_card + 1))
    suits = (Suit.CLUBS, Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS)
    cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(ranks, suits, strict=True))
    result = evaluate_five(cards)
    assert result == HandRank(HandCategory.STRAIGHT, (high_card,))


@pytest.mark.parametrize("suit", list(Suit))
@pytest.mark.parametrize("high_card", range(5, 15))
def test_straight_flush(high_card: int, suit: Suit) -> None:
    """A suited straight outranks a flush, including wheel and ace-high straights."""
    ranks = (14, 2, 3, 4, 5) if high_card == 5 else tuple(range(high_card - 4, high_card + 1))
    cards = tuple(Card(Rank(rank), suit) for rank in ranks)
    result = evaluate_five(cards)
    assert result == HandRank(HandCategory.STRAIGHT_FLUSH, (high_card,))


@pytest.mark.parametrize(
    "ranks",
    [
        pytest.param((8, 9, 10, 11, 12), id="ascending"),
        pytest.param((12, 11, 10, 9, 8), id="descending"),
        pytest.param((10, 8, 12, 9, 11), id="shuffled"),
    ],
)
def test_straight_does_not_depend_on_input_order(ranks: tuple[int, ...]) -> None:
    """The same straight is recognized regardless of the order of the cards."""
    suits = (Suit.CLUBS, Suit.HEARTS, Suit.SPADES, Suit.DIAMONDS, Suit.CLUBS)
    cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(ranks, suits, strict=True))
    assert evaluate_five(cards) == HandRank(HandCategory.STRAIGHT, (12,))


# =============================================================================
# FOUR OF A KIND (QUADS)
# =============================================================================


@pytest.mark.parametrize(
    "quad_rank, kicker_rank",
    [
        pytest.param(Rank.ACE, Rank.KING, id="ace-quads-lower-kicker"),
        pytest.param(Rank.TWO, Rank.ACE, id="two-quads-higher-kicker"),
        pytest.param(Rank.TEN, Rank.SEVEN, id="ten-quads"),
    ],
)
@pytest.mark.parametrize("kicker_index", [0, 2, 4], ids=["kicker-first", "kicker-middle", "kicker-last"])
def test_four_of_a_kind(quad_rank: Rank, kicker_rank: Rank, kicker_index: int) -> None:
    """Return the quad rank before the kicker, regardless of card order or rank values."""
    cards = [Card(quad_rank, suit) for suit in Suit]
    cards.insert(kicker_index, Card(kicker_rank, Suit.CLUBS))
    result = evaluate_five(tuple(cards))
    assert result == HandRank(HandCategory.FOUR_OF_A_KIND, (quad_rank, kicker_rank))


@pytest.mark.parametrize(
    "trips_rank, pair_rank",
    [
        pytest.param(Rank.ACE, Rank.KING, id="higher-trips"),
        pytest.param(Rank.TWO, Rank.ACE, id="higher-pair"),
    ],
)
def test_full_house(trips_rank: Rank, pair_rank: Rank) -> None:
    """A full house puts the trips rank before the pair, regardless of their values."""
    cards = (
        Card(trips_rank, Suit.CLUBS),
        Card(trips_rank, Suit.DIAMONDS),
        Card(trips_rank, Suit.HEARTS),
        Card(pair_rank, Suit.CLUBS),
        Card(pair_rank, Suit.SPADES),
    )
    result = evaluate_five(cards)
    assert result == HandRank(HandCategory.FULL_HOUSE, (trips_rank, pair_rank))


# =============================================================================
# TRIPS, TWO PAIR, ONE PAIR AND HIGH CARD
# =============================================================================


@pytest.mark.parametrize(
    "ranks, category, expected_tiebreakers",
    [
        pytest.param((2, 2, 2, 14, 13), HandCategory.THREE_OF_A_KIND, (2, 14, 13), id="low-trips-high-kickers"),
        pytest.param((14, 14, 14, 2, 13), HandCategory.THREE_OF_A_KIND, (14, 13, 2), id="ace-trips-sort-kickers"),
        pytest.param((2, 2, 13, 13, 14), HandCategory.TWO_PAIR, (13, 2, 14), id="two-pair-high-kicker"),
        pytest.param((14, 14, 13, 13, 2), HandCategory.TWO_PAIR, (14, 13, 2), id="two-pair-low-kicker"),
        pytest.param((2, 2, 14, 10, 13), HandCategory.ONE_PAIR, (2, 14, 13, 10), id="low-pair-high-kickers"),
        pytest.param((14, 14, 3, 2, 13), HandCategory.ONE_PAIR, (14, 13, 3, 2), id="ace-pair-sort-kickers"),
        pytest.param((2, 2, 3, 4, 5), HandCategory.ONE_PAIR, (2, 5, 4, 3), id="duplicate-rank-is-not-straight"),
        pytest.param((9, 2, 14, 6, 11), HandCategory.HIGH_CARD, (14, 11, 9, 6, 2), id="high-card-descending"),
        pytest.param((2, 3, 4, 5, 7), HandCategory.HIGH_CARD, (7, 5, 4, 3, 2), id="gap-at-end"),
        pytest.param((2, 3, 4, 6, 14), HandCategory.HIGH_CARD, (14, 6, 4, 3, 2), id="ace-with-gap-is-not-wheel"),
        pytest.param((12, 13, 14, 2, 3), HandCategory.HIGH_CARD, (14, 13, 12, 3, 2), id="no-wrap-through-ace"),
    ],
)
@pytest.mark.parametrize(
    "order", [(0, 1, 2, 3, 4), (4, 3, 2, 1, 0), (2, 4, 0, 3, 1)], ids=["original", "reversed", "shuffled"]
)
def test_remaining_hand_categories(
    ranks: tuple[int, ...],
    category: HandCategory,
    expected_tiebreakers: tuple[int, ...],
    order: tuple[int, ...],
) -> None:
    """Recognize rank groups and return every tiebreaker in priority order."""
    suits = (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES, Suit.CLUBS)
    cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(ranks, suits, strict=True))
    shuffled_cards = tuple(cards[index] for index in order)
    assert evaluate_five(shuffled_cards) == HandRank(category, expected_tiebreakers)


# =============================================================================
# TIEBREAKERS AND HAND COMPARISONS
# =============================================================================


@pytest.mark.parametrize(
    "stronger_ranks, weaker_ranks",
    [
        pytest.param((13, 13, 13, 13, 2), (12, 12, 12, 12, 14), id="quads-rank-before-kicker"),
        pytest.param((10, 10, 10, 10, 14), (10, 10, 10, 10, 13), id="quads-kicker"),
        pytest.param((10, 10, 10, 2, 2), (9, 9, 9, 14, 14), id="full-house-trips-before-pair"),
        pytest.param((10, 10, 10, 8, 8), (10, 10, 10, 7, 7), id="full-house-pair"),
        pytest.param((10, 10, 10, 3, 2), (9, 9, 9, 14, 13), id="trips-before-kickers"),
        pytest.param((10, 10, 10, 14, 2), (10, 10, 10, 13, 12), id="trips-first-kicker"),
        pytest.param((10, 10, 10, 14, 8), (10, 10, 10, 14, 7), id="trips-second-kicker"),
        pytest.param((13, 13, 2, 2, 3), (12, 12, 11, 11, 14), id="two-pair-high-pair"),
        pytest.param((13, 13, 10, 10, 2), (13, 13, 9, 9, 14), id="two-pair-low-pair"),
        pytest.param((13, 13, 10, 10, 8), (13, 13, 10, 10, 7), id="two-pair-kicker"),
        pytest.param((13, 13, 5, 4, 3), (12, 12, 14, 11, 10), id="pair-before-kickers"),
        pytest.param((10, 10, 14, 7, 2), (10, 10, 13, 12, 11), id="pair-first-kicker"),
        pytest.param((10, 10, 14, 8, 2), (10, 10, 14, 7, 6), id="pair-second-kicker"),
        pytest.param((10, 10, 14, 8, 4), (10, 10, 14, 8, 3), id="pair-third-kicker"),
        pytest.param((2, 3, 4, 5, 6), (14, 2, 3, 4, 5), id="six-high-straight-beats-wheel"),
    ],
)
def test_evaluated_hand_tiebreakers(stronger_ranks: tuple[int, ...], weaker_ranks: tuple[int, ...]) -> None:
    """Compare evaluated hands so incorrect tiebreaker order changes the winner."""
    suits = (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES, Suit.CLUBS)
    stronger_cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(stronger_ranks, suits, strict=True))
    weaker_cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(weaker_ranks, suits, strict=True))
    assert evaluate_five(stronger_cards) > evaluate_five(weaker_cards)


@pytest.mark.parametrize("is_flush", [False, True], ids=["high-card", "flush"])
@pytest.mark.parametrize(
    "stronger_ranks, weaker_ranks",
    [
        pytest.param((14, 10, 8, 5, 2), (13, 12, 9, 6, 3), id="first-card"),
        pytest.param((14, 12, 8, 5, 2), (14, 11, 9, 6, 3), id="second-card"),
        pytest.param((14, 12, 10, 5, 2), (14, 12, 9, 6, 3), id="third-card"),
        pytest.param((14, 12, 10, 7, 2), (14, 12, 10, 6, 3), id="fourth-card"),
        pytest.param((14, 12, 10, 7, 4), (14, 12, 10, 7, 3), id="fifth-card"),
    ],
)
def test_flush_and_high_card_tiebreakers(
    stronger_ranks: tuple[int, ...],
    weaker_ranks: tuple[int, ...],
    is_flush: bool,
) -> None:
    """Every card can decide a flush or high-card tie, including the lowest card."""
    suits = (Suit.CLUBS,) * 5 if is_flush else (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES, Suit.CLUBS)
    stronger_cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(stronger_ranks, suits, strict=True))
    weaker_cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(weaker_ranks, suits, strict=True))
    assert evaluate_five(stronger_cards) > evaluate_five(weaker_cards)


@pytest.mark.parametrize(
    "ranks, suit_indices",
    [
        pytest.param((14, 11, 9, 6, 2), (0, 1, 2, 3, 0), id="high-card"),
        pytest.param((10, 10, 14, 8, 3), (0, 1, 2, 3, 0), id="pair"),
        pytest.param((13, 13, 10, 10, 2), (0, 1, 2, 3, 0), id="two-pair"),
        pytest.param((10, 10, 10, 14, 2), (0, 1, 2, 3, 0), id="trips"),
        pytest.param((2, 3, 4, 5, 6), (0, 1, 2, 3, 0), id="straight"),
        pytest.param((14, 11, 9, 6, 2), (0, 0, 0, 0, 0), id="flush"),
        pytest.param((10, 10, 10, 2, 2), (0, 1, 2, 3, 0), id="full-house"),
        pytest.param((10, 10, 10, 10, 2), (0, 1, 2, 3, 0), id="quads"),
        pytest.param((2, 3, 4, 5, 6), (0, 0, 0, 0, 0), id="straight-flush"),
    ],
)
def test_suits_do_not_break_ties(ranks: tuple[int, ...], suit_indices: tuple[int, ...]) -> None:
    """Changing suit names preserves the rank of every hand category."""
    suits = list(Suit)
    first = tuple(Card(Rank(rank), suits[index]) for rank, index in zip(ranks, suit_indices, strict=True))
    second = tuple(Card(Rank(rank), suits[(index + 1) % 4]) for rank, index in zip(ranks, suit_indices, strict=True))
    assert evaluate_five(first) == evaluate_five(second)


# =============================================================================
# INPUT VALIDATION
# =============================================================================


@pytest.mark.parametrize("card_count", [0, 1, 2, 3, 4, 6, 7])
def test_wrong_card_amount_raises_error(card_count: int) -> None:
    """Only exactly five cards can be evaluated."""
    cards = tuple(Card(Rank(rank), Suit.CLUBS) for rank in range(2, 2 + card_count))
    with pytest.raises(WrongCardAmountError):
        evaluate_five(cards)


@pytest.mark.parametrize(
    "ranks",
    [
        pytest.param((2, 3, 4, 5, 2), id="duplicate-separated"),
        pytest.param((2, 2, 3, 4, 5), id="duplicate-adjacent"),
        pytest.param((14, 14, 14, 14, 14), id="all-identical"),
    ],
)
def test_duplicate_cards_raise_error(ranks: tuple[int, ...]) -> None:
    """Separate Card objects with the same rank and suit are still duplicate cards."""
    cards = tuple(Card(Rank(rank), Suit.CLUBS) for rank in ranks)
    with pytest.raises(DuplicateCardsError):
        evaluate_five(cards)


# =============================================================================
# CATEGORY PRIORITY
# =============================================================================


@pytest.fixture
def hands_by_category() -> tuple[tuple[Card, ...], ...]:
    """Provide one concrete hand per category, ordered from weakest to strongest."""
    mixed_suits = (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES, Suit.CLUBS)
    flush_suits = (Suit.HEARTS,) * 5
    hands = (
        ((14, 13, 11, 8, 3), mixed_suits),
        ((2, 2, 7, 5, 3), mixed_suits),
        ((3, 3, 2, 2, 4), mixed_suits),
        ((2, 2, 2, 4, 3), mixed_suits),
        ((14, 2, 3, 4, 5), mixed_suits),
        ((7, 5, 4, 3, 2), flush_suits),
        ((2, 2, 2, 3, 3), mixed_suits),
        ((2, 2, 2, 2, 3), mixed_suits),
        ((14, 2, 3, 4, 5), flush_suits),
    )
    return tuple(
        tuple(Card(Rank(rank), suit) for rank, suit in zip(ranks, suits, strict=True)) for ranks, suits in hands
    )


@pytest.mark.parametrize("category", list(HandCategory)[1:], ids=lambda category: category.name.lower())
def test_higher_category_beats_previous_category(
    hands_by_category: tuple[tuple[Card, ...], ...],
    category: HandCategory,
) -> None:
    """Every category outranks the category immediately below it."""
    stronger = evaluate_five(hands_by_category[category])
    weaker = evaluate_five(hands_by_category[category - 1])
    assert stronger > weaker


# =============================================================================
# EVALUATE BEST - FIVE TO SEVEN CARDS
# =============================================================================


@pytest.mark.parametrize("category", list(HandCategory), ids=lambda category: category.name.lower())
def test_evaluate_best_with_exactly_five_cards(
    hands_by_category: tuple[tuple[Card, ...], ...],
    category: HandCategory,
) -> None:
    """Five-card input keeps the same complete rank as evaluate_five."""
    cards = hands_by_category[category]
    assert evaluate_best(cards) == evaluate_five(cards)
    assert evaluate_best(cards).category == category


@pytest.mark.parametrize(
    "ranks, category, expected_tiebreakers",
    [
        pytest.param(
            (2, 2, 4, 7, 10, 13, 14), HandCategory.ONE_PAIR, (2, 14, 13, 10), id="pair-with-best-three-kickers"
        ),
        pytest.param((2, 2, 10, 10, 13, 13, 14), HandCategory.TWO_PAIR, (13, 10, 14), id="best-two-of-three-pairs"),
        pytest.param(
            (2, 2, 13, 13, 14, 14, 3), HandCategory.TWO_PAIR, (14, 13, 3), id="discarded-pair-can-provide-kicker"
        ),
        pytest.param((2, 2, 2, 13, 13, 13, 14), HandCategory.FULL_HOUSE, (13, 2), id="higher-of-two-trips"),
        pytest.param(
            (10, 10, 10, 2, 2, 14, 14), HandCategory.FULL_HOUSE, (10, 14), id="trips-with-higher-of-two-pairs"
        ),
        pytest.param((13, 14, 2, 3, 4, 5, 9), HandCategory.STRAIGHT, (5,), id="wheel-from-seven-cards"),
    ],
)
@pytest.mark.parametrize("reverse_order", [False, True], ids=["original", "reversed"])
def test_evaluate_best_rank_groups_and_wheel(
    ranks: tuple[int, ...],
    category: HandCategory,
    expected_tiebreakers: tuple[int, ...],
    reverse_order: bool,
) -> None:
    """Select the best five cards, including the correct groups and remaining kickers."""
    suits = (Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS, Suit.SPADES, Suit.CLUBS, Suit.DIAMONDS, Suit.HEARTS)
    cards = tuple(Card(Rank(rank), suit) for rank, suit in zip(ranks, suits, strict=True))
    if reverse_order:
        cards = tuple(reversed(cards))
    assert evaluate_best(cards) == HandRank(category, expected_tiebreakers)


@pytest.mark.parametrize("suit", list(Suit))
@pytest.mark.parametrize(
    "ranks, category, expected_tiebreakers",
    [
        pytest.param(
            (2, 5, 7, 9, 11, 13, 14), HandCategory.FLUSH, (14, 13, 11, 9, 7), id="highest-five-of-seven-suited-cards"
        ),
        pytest.param(
            (2, 3, 4, 5, 6, 7, 8), HandCategory.STRAIGHT_FLUSH, (8,), id="highest-of-multiple-straight-flushes"
        ),
    ],
)
def test_evaluate_best_seven_suited_cards(
    ranks: tuple[int, ...],
    category: HandCategory,
    expected_tiebreakers: tuple[int, ...],
    suit: Suit,
) -> None:
    """Choose the strongest five suited cards rather than the first five."""
    cards = tuple(Card(Rank(rank), suit) for rank in ranks)
    assert evaluate_best(cards) == HandRank(category, expected_tiebreakers)


def test_evaluate_best_straight_flush_with_off_suit_cards() -> None:
    """Ignore off-suit high cards when a lower straight flush is available."""
    cards = (
        Card(Rank.ACE, Suit.CLUBS),
        Card(Rank.SEVEN, Suit.HEARTS),
        Card(Rank.KING, Suit.SPADES),
        Card(Rank.FIVE, Suit.HEARTS),
        Card(Rank.NINE, Suit.HEARTS),
        Card(Rank.SIX, Suit.HEARTS),
        Card(Rank.EIGHT, Suit.HEARTS),
    )
    assert evaluate_best(cards) == HandRank(HandCategory.STRAIGHT_FLUSH, (9,))


@pytest.mark.parametrize("card_count", [4, 8])
def test_evaluate_best_rejects_wrong_card_amount(card_count: int) -> None:
    """Reject inputs outside the five-to-seven-card range."""
    cards = tuple(Card(Rank(rank), Suit.CLUBS) for rank in range(2, 2 + card_count))
    with pytest.raises(WrongCardAmountError):
        evaluate_best(cards)


@pytest.mark.parametrize("card_count", [5, 6, 7])
def test_evaluate_best_rejects_duplicate_cards(card_count: int) -> None:
    """Reject a duplicate even if a valid five-card subset could be selected."""
    cards = tuple(Card(Rank(rank), Suit.CLUBS) for rank in range(2, card_count + 1))
    cards += (Card(Rank.TWO, Suit.CLUBS),)
    with pytest.raises(DuplicateCardsError):
        evaluate_best(cards)

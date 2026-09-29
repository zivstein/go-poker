from collections import Counter
from collections.abc import Sequence
from itertools import combinations

from .card import Card
from .hand_rank import HandCategory, HandRank


class WrongCardAmountError(ValueError): ...


class DuplicateCardsError(ValueError): ...


def evaluate_best(cards: Sequence[Card]) -> HandRank:
    cards_tuple = tuple(cards)

    if not 5 <= len(cards_tuple) <= 7:
        raise WrongCardAmountError("Best-hand evaluation requires between 5 and 7 cards")

    if len(cards_tuple) != len(set(cards_tuple)):
        raise DuplicateCardsError("Hand contains duplicate cards")

    if len(cards_tuple) == 5:
        return evaluate_five(cards_tuple)

    return max(evaluate_five(combo) for combo in combinations(cards_tuple, 5))


def evaluate_five(cards: tuple[Card, ...]) -> HandRank:
    if len(cards) != 5:
        raise WrongCardAmountError(f"Expected 5 cards, received {len(cards)}")
    if len(set(cards)) != 5:
        raise DuplicateCardsError("A hand cannot contain duplicate cards")

    rank_counts = Counter(card.rank for card in cards)

    if len(rank_counts) == 5:
        sorted_ranks = sorted(rank_counts)
        is_flush = len({card.suit for card in cards}) == 1
        straight_high: int | None = None

        if sorted_ranks[-1] - sorted_ranks[0] == 4:
            straight_high = sorted_ranks[-1]
        elif sorted_ranks == [2, 3, 4, 5, 14]:
            # Ace counts as low only in A-2-3-4-5.
            straight_high = 5

        if straight_high is not None:
            category = HandCategory.STRAIGHT_FLUSH if is_flush else HandCategory.STRAIGHT
            return HandRank(category, (straight_high,))

        tiebreakers = tuple(reversed(sorted_ranks))
        category = HandCategory.FLUSH if is_flush else HandCategory.HIGH_CARD
        return HandRank(category, tiebreakers)

    rank_groups = sorted(rank_counts.items(), key=lambda item: (item[1], item[0]), reverse=True)
    counts = tuple(count for rank, count in rank_groups)
    ordered_ranks = tuple(rank for rank, count in rank_groups)

    if counts == (4, 1):
        return HandRank(HandCategory.FOUR_OF_A_KIND, ordered_ranks)
    if counts == (3, 2):
        return HandRank(HandCategory.FULL_HOUSE, ordered_ranks)
    if counts == (3, 1, 1):
        return HandRank(HandCategory.THREE_OF_A_KIND, ordered_ranks)
    if counts == (2, 2, 1):
        return HandRank(HandCategory.TWO_PAIR, ordered_ranks)

    # The only remaining pattern is (2, 1, 1, 1).
    return HandRank(HandCategory.ONE_PAIR, ordered_ranks)

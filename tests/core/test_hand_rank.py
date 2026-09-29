import pytest

from go_poker.core.hand_rank import HandCategory, HandRank


@pytest.mark.parametrize(
    "stronger, weaker",
    [
        pytest.param(
            HandRank(HandCategory.STRAIGHT_FLUSH, (5,)),
            HandRank(HandCategory.FOUR_OF_A_KIND, (14, 13)),
            id="straight-flush-beats-four-of-a-kind",
        ),
        pytest.param(
            HandRank(HandCategory.ONE_PAIR, (2, 5, 4, 3)),
            HandRank(HandCategory.HIGH_CARD, (14, 13, 12, 11, 9)),
            id="pair-beats-high-card",
        ),
    ],
)
def test_higher_category_beats_lower_category(stronger: HandRank, weaker: HandRank) -> None:
    """The category takes priority even when the weaker hand has higher card ranks."""
    assert stronger > weaker
    assert weaker < stronger


@pytest.mark.parametrize(
    "category, stronger_tiebreakers, weaker_tiebreakers",
    [
        pytest.param(HandCategory.ONE_PAIR, (13, 5, 4, 3), (12, 14, 11, 10), id="higher-pair-wins"),
        pytest.param(HandCategory.ONE_PAIR, (10, 14, 7, 2), (10, 13, 12, 11), id="same-pair-higher-kicker-wins"),
        pytest.param(HandCategory.TWO_PAIR, (13, 2, 3), (12, 11, 14), id="higher-two-pair-wins"),
        pytest.param(HandCategory.TWO_PAIR, (13, 10, 2), (13, 9, 14), id="same-high-pair-lower-pair-decides"),
        pytest.param(HandCategory.TWO_PAIR, (13, 10, 14), (13, 10, 2), id="same-two-pair-kicker-decides"),
        pytest.param(HandCategory.FULL_HOUSE, (10, 2), (9, 14), id="full-house-higher-trips-wins"),
    ],
)
def test_tiebreakers_decide_same_category(
    category: HandCategory,
    stronger_tiebreakers: tuple[int, ...],
    weaker_tiebreakers: tuple[int, ...],
) -> None:
    """Compare tiebreakers in order, with earlier ranks taking priority."""
    stronger = HandRank(category, stronger_tiebreakers)
    weaker = HandRank(category, weaker_tiebreakers)
    assert stronger > weaker
    assert weaker < stronger


def test_identical_hand_ranks_are_equal() -> None:
    """Separate HandRank objects with the same category and tiebreakers are equal."""
    first = HandRank(HandCategory.ONE_PAIR, (10, 14, 8, 3))
    second = HandRank(HandCategory.ONE_PAIR, (10, 14, 8, 3))
    assert first == second
    assert not first > second
    assert not first < second

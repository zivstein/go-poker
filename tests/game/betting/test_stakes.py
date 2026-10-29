import pytest

from go_poker.game.betting.stakes import InvalidStakesError, Stakes


def test_equal_blinds_are_valid() -> None:
    """A small blind equal to the big blind is allowed."""
    stakes = Stakes(small_blind=1, big_blind=1)
    assert (stakes.small_blind, stakes.big_blind) == (1, 1)


@pytest.mark.parametrize(
    "small_blind, big_blind",
    [
        pytest.param(0, 2, id="zero-small-blind"),
        pytest.param(-1, 2, id="negative-small-blind"),
        pytest.param(1, 0, id="zero-big-blind"),
        pytest.param(3, 2, id="small-blind-above-big-blind"),
    ],
)
def test_invalid_stakes_are_rejected(small_blind: int, big_blind: int) -> None:
    """Both blinds must be positive and the small blind may not exceed the big blind."""
    with pytest.raises(InvalidStakesError):
        Stakes(small_blind=small_blind, big_blind=big_blind)

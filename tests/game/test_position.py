import pytest

from go_poker.game.position import InvalidPlayerCount, Position, positions_for_player_count, validate_player_count


def test_six_player_positions():
    positions = positions_for_player_count(6)

    assert positions == (Position.BTN, Position.SB, Position.BB, Position.UTG, Position.HJ, Position.CO)


def test_heads_up_positions():
    positions = positions_for_player_count(2)

    assert positions == (
        Position.BTN,
        Position.BB,
    )


def test_too_many_players_raises_error():
    with pytest.raises(InvalidPlayerCount):
        positions_for_player_count(10)


def test_too_few_players_raises_error():
    with pytest.raises(InvalidPlayerCount):
        positions_for_player_count(1)


@pytest.mark.parametrize("player_count", [2, 9])
def test_validate_player_count_accepts_two_to_nine(player_count: int) -> None:
    """Player counts at both ends of the 2-9 range are valid."""
    validate_player_count(player_count)


@pytest.mark.parametrize("player_count", [0, 1, 10])
def test_validate_player_count_rejects_counts_outside_two_to_nine(player_count: int) -> None:
    """Player counts outside 2-9 raise InvalidPlayerCount."""
    with pytest.raises(InvalidPlayerCount):
        validate_player_count(player_count)

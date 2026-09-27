import pytest

from go_poker.game.position import InvalidPlayerCount, Position, positions_for_player_count


def test_six_player_positions():
    positions = positions_for_player_count(6)

    assert positions == (
        Position.BTN,
        Position.SB,
        Position.BB,
        Position.UTG,
        Position.HJ,
        Position.CO
    )

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
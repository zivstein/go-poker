import pytest

from go_poker.game.player import InvalidStackError, Player, PlayerStatus


@pytest.mark.parametrize("stack", [0, 1, 1000])
def test_player_can_be_created_with_nonnegative_stack(stack: int) -> None:
    """A player can have chips or a zero stack and starts waiting by default."""
    player = Player("Ziv", stack=stack)
    assert player.player_id == "Ziv"
    assert player.stack == stack
    assert player.status == PlayerStatus.WAITING


@pytest.mark.parametrize("stack", [-1, -1000])
def test_player_rejects_negative_starting_stack(stack: int) -> None:
    """A negative initial stack is invalid."""
    with pytest.raises(InvalidStackError):
        Player("Ziv", stack=stack)


@pytest.mark.parametrize("status", list(PlayerStatus), ids=lambda status: status.name.lower())
def test_player_can_be_created_with_explicit_status(status: PlayerStatus) -> None:
    """The caller can select a status instead of using the default."""
    player = Player("Ziv", stack=1000, status=status)
    assert player.status == status


@pytest.mark.parametrize("status", [PlayerStatus.READY, PlayerStatus.SITTING_OUT])
def test_player_status_can_change(status: PlayerStatus) -> None:
    """Changing status preserves the player's identity and stack."""
    player = Player("Ziv", stack=1000)
    player.status = status
    assert player.status == status
    assert player.player_id == "Ziv"
    assert player.stack == 1000



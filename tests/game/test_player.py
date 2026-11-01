import copy
from typing import Any

import pytest

from go_poker.game.player import InvalidPlayerIdError, InvalidStackError, Player, PlayerStatus


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


# =============================================================================
# PLAYER ID
# =============================================================================


def test_player_rejects_empty_player_id() -> None:
    """An empty player id is invalid."""
    with pytest.raises(InvalidPlayerIdError):
        Player("", stack=1000)


@pytest.mark.parametrize("player_id", [None, 1, 1.5, b"Ziv", ("Ziv",)], ids=repr)
def test_player_rejects_non_string_player_id(player_id: Any) -> None:
    """A player id must be a string."""
    with pytest.raises(InvalidPlayerIdError):
        Player(player_id, stack=1000)


def test_invalid_player_id_is_reported_before_invalid_stack() -> None:
    """The id is validated first, so a player that is wrong in both ways reports the id."""
    with pytest.raises(InvalidPlayerIdError):
        Player("", stack=-1)
    with pytest.raises(InvalidStackError):
        Player("Ziv", stack=-1)


@pytest.mark.parametrize("player_id", [" ", "  ", "\t", " Ziv ", "a b"])
def test_player_id_is_opaque_so_whitespace_is_accepted(player_id: str) -> None:
    """Ids are opaque strings: only the empty string is rejected, and the id is kept exactly as given."""
    assert Player(player_id, stack=1000).player_id == player_id


def test_player_id_cannot_be_reassigned() -> None:
    """The id is read-only after creation, even when the new value is equal."""
    player = Player("Ziv", stack=1000)
    with pytest.raises(AttributeError):
        player.player_id = "Other"
    with pytest.raises(AttributeError):
        player.player_id = "Ziv"
    assert player.player_id == "Ziv"


def test_player_id_cannot_be_deleted() -> None:
    """The id cannot be deleted either."""
    player = Player("Ziv", stack=1000)
    with pytest.raises(AttributeError):
        del player.player_id
    assert player.player_id == "Ziv"


def test_stack_and_status_stay_mutable_when_player_id_is_read_only() -> None:
    """Making the id read-only does not freeze the rest of the player."""
    player = Player("Ziv", stack=1000)
    player.stack = 5
    player.status = PlayerStatus.READY
    assert (player.player_id, player.stack, player.status) == ("Ziv", 5, PlayerStatus.READY)


def test_player_equality_and_copies_are_unchanged_by_the_read_only_id() -> None:
    """Players still compare by value and can still be copied."""
    assert Player("Ziv", stack=1000) == Player("Ziv", stack=1000)
    assert Player("Ziv", stack=1000) != Player("Ziv", stack=999)
    assert copy.deepcopy(Player("Ziv", stack=1000)) == Player("Ziv", stack=1000)
    assert (
        repr(Player("Ziv", stack=1000))
        == "Player(player_id='Ziv', stack=1000, status=<PlayerStatus.WAITING: 'Waiting'>)"
    )

import pytest

from go_poker.game.betting.chips import InsufficientChipsError, InvalidChipAmountError, commit_chips
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player
from go_poker.game.position import Blind, Position


def test_committed_chips_move_from_stack_to_both_contributions_until_all_in() -> None:
    """Each commitment adds to both contributions; the commitment that empties the stack marks the player all-in."""
    hand_player = HandPlayerState(Player("Ziv", stack=100), 1, Position.BTN, Blind.NONE)

    commit_chips(hand_player, 30)
    assert hand_player.player.stack == 70
    assert (hand_player.street_contribution, hand_player.total_contribution) == (30, 30)
    assert hand_player.all_in is False

    commit_chips(hand_player, 70)
    assert hand_player.player.stack == 0
    assert (hand_player.street_contribution, hand_player.total_contribution) == (100, 100)
    assert hand_player.all_in is True


@pytest.mark.parametrize(
    "amount, error",
    [
        pytest.param(0, InvalidChipAmountError, id="zero"),
        pytest.param(-5, InvalidChipAmountError, id="negative"),
        pytest.param(101, InsufficientChipsError, id="above-stack"),
    ],
)
def test_invalid_commitment_is_rejected_without_changes(amount: int, error: type[Exception]) -> None:
    """Only a positive amount the stack can cover is committed; anything else changes nothing."""
    hand_player = HandPlayerState(Player("Ziv", stack=100), 1, Position.BTN, Blind.NONE)

    with pytest.raises(error):
        commit_chips(hand_player, amount)

    assert hand_player.player.stack == 100
    assert (hand_player.street_contribution, hand_player.total_contribution) == (0, 0)
    assert hand_player.all_in is False

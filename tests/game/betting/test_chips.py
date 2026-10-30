import pytest

from go_poker.game.betting.chips import (
    InsufficientChipsError,
    InsufficientChipsInFrontError,
    InvalidChipAmountError,
    commit_chips,
    return_chips,
)
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


def all_in_with_chips_in_front() -> HandPlayerState:
    """A player all-in with 80 committed to the hand: 50 already collected and 30 still in front."""
    return HandPlayerState(
        Player("Ziv", stack=0), 1, Position.BTN, Blind.NONE, all_in=True, street_contribution=30, total_contribution=80
    )


def test_returned_chips_move_from_in_front_back_to_the_stack_and_clear_all_in() -> None:
    """Returning chips lowers both contributions by the amount and raises the stack, so the player is no longer
    all-in; the collected chips stay committed."""
    hand_player = all_in_with_chips_in_front()

    return_chips(hand_player, 30)

    assert hand_player.player.stack == 30
    assert (hand_player.street_contribution, hand_player.total_contribution) == (0, 50)
    assert hand_player.all_in is False


@pytest.mark.parametrize(
    "amount, error",
    [
        pytest.param(0, InvalidChipAmountError, id="zero"),
        pytest.param(-5, InvalidChipAmountError, id="negative"),
        pytest.param(31, InsufficientChipsInFrontError, id="above-chips-in-front"),
    ],
)
def test_invalid_return_is_rejected_without_changes(amount: int, error: type[Exception]) -> None:
    """Only a positive amount of the chips still in front can be returned, never collected chips; anything else
    changes nothing."""
    hand_player = all_in_with_chips_in_front()

    with pytest.raises(error):
        return_chips(hand_player, amount)

    assert hand_player.player.stack == 0
    assert (hand_player.street_contribution, hand_player.total_contribution) == (30, 80)
    assert hand_player.all_in is True

from collections.abc import Callable

import pytest

from go_poker.game.position import Blind, InvalidPlayerCount, Position
from go_poker.game.position_assignment import (
    ButtonSeatNotInHandError,
    DuplicateSeatNumberError,
    HandSeatAssignment,
    assign_blinds,
    assign_hand_seats,
    assign_positions,
    order_seats_from_button,
)


def test_six_players_in_contiguous_seats() -> None:
    """Assign the correct positions to six players in consecutive seats."""
    positions = assign_positions((1, 2, 3, 4, 5, 6), 1)
    assert positions == {
        1: Position.BTN,
        2: Position.SB,
        3: Position.BB,
        4: Position.UTG,
        5: Position.HJ,
        6: Position.CO,
    }


def test_six_players_with_empty_gaps_between_seats() -> None:
    """Assign positions in seat order while skipping empty seats."""
    positions = assign_positions((1, 3, 4, 6, 8, 9), 1)
    assert positions == {
        1: Position.BTN,
        3: Position.SB,
        4: Position.BB,
        6: Position.UTG,
        8: Position.HJ,
        9: Position.CO,
    }


def test_position_assignment_wraps_around_table() -> None:
    """Continue assigning positions from the first seat after reaching seat nine."""
    positions = assign_positions((1, 3, 4, 6, 8, 9), 9)
    assert positions == {
        9: Position.BTN,
        1: Position.SB,
        3: Position.BB,
        4: Position.UTG,
        6: Position.HJ,
        8: Position.CO,
    }
    assert list(positions) == [9, 1, 3, 4, 6, 8]


def test_nine_player_positions() -> None:
    """Assign all nine positions starting from the button."""
    positions = assign_positions((1, 2, 3, 4, 5, 6, 7, 8, 9), 1)
    assert positions == {
        1: Position.BTN,
        2: Position.SB,
        3: Position.BB,
        4: Position.UTG,
        5: Position.UTG1,
        6: Position.MP,
        7: Position.LJ,
        8: Position.HJ,
        9: Position.CO,
    }


def test_three_player_positions() -> None:
    """Assign BTN, SB, and BB to three players in circular seat order."""
    positions = assign_positions((2, 5, 8), 5)
    assert positions == {5: Position.BTN, 8: Position.SB, 2: Position.BB}


def test_heads_up_positions_are_button_and_big_blind() -> None:
    """Assign BTN to the button player and BB to the other player."""
    positions = assign_positions((2, 7), 7)
    assert positions == {7: Position.BTN, 2: Position.BB}


def test_heads_up_button_gets_small_blind() -> None:
    """Assign the SMALL blind to the button player in heads-up play."""
    blinds = assign_blinds({7: Position.BTN, 2: Position.BB})
    assert blinds[7] == Blind.SMALL


def test_heads_up_big_blind_position_gets_big_blind() -> None:
    """Assign the BIG blind to the player in the BB position in heads-up play."""
    blinds = assign_blinds({7: Position.BTN, 2: Position.BB})
    assert blinds[2] == Blind.BIG


def test_order_seats_sorts_unsorted_input_and_starts_from_button() -> None:
    """Use seat numbers rather than input order to determine the circular order."""
    ordered_seats = order_seats_from_button((8, 2, 9, 5), 8)
    assert ordered_seats == (8, 9, 2, 5)


def test_assign_positions_works_with_unsorted_seats() -> None:
    """Assign the same positions regardless of the input seat order."""
    positions = assign_positions((8, 2, 5), 5)
    assert positions == {5: Position.BTN, 8: Position.SB, 2: Position.BB}


@pytest.mark.parametrize("assign", [order_seats_from_button, assign_positions, assign_hand_seats])
def test_duplicate_seat_numbers_raise_error(assign: Callable[[tuple[int, ...], int], object]) -> None:
    """Reject duplicate seats before producing assignments."""
    with pytest.raises(DuplicateSeatNumberError):
        assign((1, 2, 2), 1)


@pytest.mark.parametrize("assign", [order_seats_from_button, assign_positions, assign_hand_seats])
def test_button_not_in_hand_raises_error(assign: Callable[[tuple[int, ...], int], object]) -> None:
    """The button must belong to a participating seat."""
    with pytest.raises(ButtonSeatNotInHandError):
        assign((1, 3, 5), 2)


@pytest.mark.parametrize("seat_numbers", [(1,), tuple(range(1, 11))])
@pytest.mark.parametrize("assign", [assign_positions, assign_hand_seats])
def test_invalid_player_count_raises_error(
    assign: Callable[[tuple[int, ...], int], object], seat_numbers: tuple[int, ...],
) -> None:
    """Reject hands with fewer than two or more than nine players."""
    with pytest.raises(InvalidPlayerCount):
        assign(seat_numbers, 1)


def test_blinds_follow_positions_instead_of_dictionary_order() -> None:
    """Assign blinds by position even when the dictionary does not start with BTN."""
    positions = {4: Position.UTG, 3: Position.BB, 1: Position.BTN, 6: Position.CO, 2: Position.SB, 5: Position.HJ}
    blinds = assign_blinds(positions)
    assert blinds == {
        1: Blind.NONE,
        2: Blind.SMALL,
        3: Blind.BIG,
        4: Blind.NONE,
        5: Blind.NONE,
        6: Blind.NONE,
    }


def test_three_player_button_has_no_blind() -> None:
    """The button has no blind when three players participate."""
    blinds = assign_blinds({5: Position.BTN, 8: Position.SB, 2: Position.BB})
    assert blinds == {5: Blind.NONE, 8: Blind.SMALL, 2: Blind.BIG}


def test_assign_hand_seats_combines_positions_and_blinds() -> None:
    """Return the position and blind for every participating seat, including wrap-around."""
    assignments = assign_hand_seats((2, 5, 8), 8)
    assert assignments == {
        8: HandSeatAssignment(position=Position.BTN, blind=Blind.NONE),
        2: HandSeatAssignment(position=Position.SB, blind=Blind.SMALL),
        5: HandSeatAssignment(position=Position.BB, blind=Blind.BIG),
    }
    assert list(assignments) == [8, 2, 5]


def test_assign_hand_seats_heads_up() -> None:
    """Combine heads-up positions with the button's small blind."""
    assignments = assign_hand_seats((2, 7), 7)
    assert assignments == {
        7: HandSeatAssignment(position=Position.BTN, blind=Blind.SMALL),
        2: HandSeatAssignment(position=Position.BB, blind=Blind.BIG),
    }

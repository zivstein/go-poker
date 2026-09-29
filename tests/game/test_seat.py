import pytest

from go_poker.game.seat import Seat, SeatOccupiedError


def test_new_seat_is_empty() -> None:
    seat = Seat(1)
    assert seat.is_occupied is False


def test_player_can_sit_in_empty_seat() -> None:
    seat = Seat(1)
    seat.sit_in("Ziv")
    assert seat.is_occupied is True
    assert seat.player_id == "Ziv"


def test_player_cannot_sit_in_occupied_seat() -> None:
    seat = Seat(1)
    seat.sit_in("Ziv")
    assert seat.is_occupied is True
    assert seat.player_id == "Ziv"
    with pytest.raises(SeatOccupiedError):
        seat.sit_in("Player 2")
    assert seat.is_occupied is True
    assert seat.player_id == "Ziv"


def test_seat_is_empty_after_stand_up() -> None:
    seat = Seat(1)
    seat.sit_in("Ziv")
    assert seat.is_occupied is True
    assert seat.player_id == "Ziv"
    seat.stand_up()
    assert seat.is_occupied is False
    assert seat.player_id is None


def test_new_player_can_sit_after_old_player_left() -> None:
    seat = Seat(1)
    seat.sit_in("Ziv")
    assert seat.is_occupied is True
    assert seat.player_id == "Ziv"
    with pytest.raises(SeatOccupiedError):
        seat.sit_in("Player 2")
    assert seat.is_occupied is True
    assert seat.player_id == "Ziv"
    seat.stand_up()
    assert seat.player_id is None
    assert seat.is_occupied is False
    seat.sit_in("Player 2")
    assert seat.is_occupied is True
    assert seat.player_id == "Player 2"


def test_stand_up_on_empty_seat_does_not_cause_error() -> None:
    seat = Seat(1)
    assert seat.player_id is None
    seat.stand_up()
    assert seat.player_id is None
    assert seat.is_occupied is False

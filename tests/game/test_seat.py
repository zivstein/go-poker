import pytest

from go_poker.game.player import Player
from go_poker.game.seat import Seat, SeatOccupiedError


def test_new_seat_is_empty() -> None:
    seat = Seat(1)
    assert seat.is_occupied is False


def test_player_can_sit_in_empty_seat() -> None:
    seat = Seat(1)
    player = Player("Ziv", stack=1000)
    seat.sit_in(player)
    assert seat.is_occupied is True
    assert seat.player is player


def test_player_cannot_sit_in_occupied_seat() -> None:
    seat = Seat(1)
    player = Player("Ziv", stack=1000)
    other_player = Player("Player 2", stack=1000)
    seat.sit_in(player)
    assert seat.is_occupied is True
    assert seat.player is player
    with pytest.raises(SeatOccupiedError):
        seat.sit_in(other_player)
    assert seat.is_occupied is True
    assert seat.player is player


def test_seat_is_empty_after_stand_up() -> None:
    seat = Seat(1)
    player = Player("Ziv", stack=1000)
    seat.sit_in(player)
    assert seat.is_occupied is True
    assert seat.player is player
    seat.stand_up()
    assert seat.is_occupied is False
    assert seat.player is None


def test_new_player_can_sit_after_old_player_left() -> None:
    seat = Seat(1)
    player = Player("Ziv", stack=1000)
    other_player = Player("Player 2", stack=1000)
    seat.sit_in(player)
    assert seat.is_occupied is True
    assert seat.player is player
    with pytest.raises(SeatOccupiedError):
        seat.sit_in(other_player)
    assert seat.is_occupied is True
    assert seat.player is player
    seat.stand_up()
    assert seat.player is None
    assert seat.is_occupied is False
    seat.sit_in(other_player)
    assert seat.is_occupied is True
    assert seat.player is other_player


def test_stand_up_on_empty_seat_does_not_cause_error() -> None:
    seat = Seat(1)
    assert seat.player is None
    seat.stand_up()
    assert seat.player is None
    assert seat.is_occupied is False

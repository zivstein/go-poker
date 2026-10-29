import pytest

from go_poker.game.player import Player
from go_poker.game.seat import Seat, SeatOccupiedError
from go_poker.game.table import (
    EmptySeatError,
    InvalidSeatNumber,
    InvalidTableSize,
    PlayerAlreadySeatedError,
    Table,
)


@pytest.fixture
def empty_table_max_9() -> Table:
    return Table(9)


def test_table_can_be_created_with_two_seats() -> None:
    """A table accepts the minimum size of two seats."""
    table = Table(2)
    assert table.max_seats == 2


def test_table_can_be_created_with_nine_seats(empty_table_max_9: Table) -> None:
    """A table accepts the maximum size of nine seats."""
    assert empty_table_max_9.max_seats == 9


def test_table_rejects_less_than_two_seats() -> None:
    """Fewer than two seats raises InvalidTableSize."""
    with pytest.raises(InvalidTableSize):
        Table(1)


def test_table_rejects_more_than_nine_seats() -> None:
    """More than nine seats raises InvalidTableSize."""
    with pytest.raises(InvalidTableSize):
        Table(10)


def test_table_creates_correct_seat_numbers(empty_table_max_9: Table) -> None:
    """Seats are numbered consecutively from one through the table size."""
    assert [seat.number for seat in empty_table_max_9._seats] == list(range(1, 10))


@pytest.mark.parametrize("seat_number", [1, 2, 4, 9])
def test_get_existing_seat(empty_table_max_9: Table, seat_number: int) -> None:
    """Looking up a valid seat number returns the corresponding Seat."""
    assert empty_table_max_9.get_seat(seat_number).number == seat_number


@pytest.mark.parametrize("seat_number", [0, -1])
def test_get_seat_below_one_raises_error(empty_table_max_9: Table, seat_number: int) -> None:
    """Seat number zero or below raises InvalidSeatNumber."""
    with pytest.raises(InvalidSeatNumber):
        empty_table_max_9.get_seat(seat_number)


@pytest.mark.parametrize("max_seats", [2, 8, 9])
def test_get_seat_above_max_raises_error(max_seats: int) -> None:
    table = Table(max_seats)

    with pytest.raises(InvalidSeatNumber):
        table.get_seat(max_seats + 1)


def test_player_can_sit_at_table() -> None:
    """A player can occupy an empty seat at the table."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    table.sit_in(player, 2)
    assert table.get_seat(2).player is player


def test_two_players_can_sit_at_different_seats() -> None:
    """Different players can occupy separate seats at the same time."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    other_player = Player("Player 2", stack=1000)
    table.sit_in(player, 2)
    table.sit_in(other_player, 3)
    assert table.get_seat(2).player is player
    assert table.get_seat(3).player is other_player


def test_same_player_cannot_sit_twice() -> None:
    """Seating an already seated player raises PlayerAlreadySeatedError."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    table.sit_in(player, 2)
    assert table.get_seat(2).player is player
    with pytest.raises(PlayerAlreadySeatedError):
        table.sit_in(player, 3)
    assert table.get_seat(2).player is player
    assert table.get_seat(3).player is None
    assert table.player_count == 1


def test_cannot_sit_in_occupied_seat() -> None:
    """Seating another player in an occupied seat raises SeatOccupiedError."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    other_player = Player("Player 2", stack=1000)
    table.sit_in(player, 2)
    assert table.get_seat(2).player is player
    with pytest.raises(SeatOccupiedError):
        table.sit_in(other_player, 2)
    assert table.get_seat(2).player is player
    assert table.player_count == 1


def test_player_can_leave_table() -> None:
    """Standing up removes the player and leaves their seat empty."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    table.sit_in(player, 2)
    assert table.get_seat(2).player is player
    table.stand_up(2)
    assert table.get_seat(2).is_occupied is False
    assert table.get_seat(2).player is None


def test_player_count_starts_at_zero() -> None:
    """A newly created table has no seated players."""
    table = Table(9)
    assert table.player_count == 0


def test_player_count_changes_after_sit_in_and_stand_up() -> None:
    """The player count increases on seating and decreases on leaving."""
    table = Table(9)
    assert table.player_count == 0
    player = Player("Ziv", stack=1000)
    other_player = Player("P2", stack=1000)
    table.sit_in(player, 2)
    assert table.player_count == 1
    table.sit_in(other_player, 5)
    assert table.player_count == 2
    table.stand_up(2)
    assert table.player_count == 1
    table.stand_up(5)
    assert table.player_count == 0


def test_occupied_seats_contains_only_occupied_seats() -> None:
    """The occupied seats collection includes seated players and excludes empty seats."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    table.sit_in(player, 2)
    assert [Seat(number=2, player=player)] == table.occupied_seats


def test_occupied_seats_are_in_seat_order() -> None:
    """Occupied seats follow seat-number order regardless of seating order."""
    table = Table(9)
    player = Player("Player 1", stack=1000)
    other_player = Player("Player 2", stack=1000)
    table.sit_in(player, 3)
    table.sit_in(other_player, 2)
    assert table.occupied_seats[0] == Seat(number=2, player=other_player)
    assert table.occupied_seats[1] == Seat(number=3, player=player)


def test_button_can_be_set_on_occupied_seat() -> None:
    """Setting the button to an occupied seat stores its seat number."""
    table = Table(9)
    player = Player("Ziv", stack=1000)
    table.sit_in(player, 2)
    table.set_button(2)
    assert table.button_seat_number == 2


def test_button_cannot_be_set_on_empty_seat(empty_table_max_9: Table) -> None:
    """Setting the button to an empty seat raises EmptySeatError."""
    with pytest.raises(EmptySeatError):
        empty_table_max_9.set_button(2)


# =============================================================================
# PLAYER IDENTITY AFTER THE REFACTOR
# =============================================================================


def test_different_player_objects_with_same_id_cannot_sit_twice() -> None:
    table = Table(9)
    player = Player("Ziv", stack=1000)
    same_id_player = Player("Ziv", stack=500)
    table.sit_in(player, 2)

    with pytest.raises(PlayerAlreadySeatedError):
        table.sit_in(same_id_player, 3)

    assert table.get_seat(2).player is player
    assert table.get_seat(3).player is None
    assert table.player_count == 1

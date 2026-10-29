import pytest

from go_poker.game.hand_setup import setup_hand
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.position import Blind, InvalidPlayerCount, Position
from go_poker.game.position_assignment import ButtonSeatNotInHandError
from go_poker.game.table import ButtonUndefinedError, Table

READY = PlayerStatus.READY
WAITING = PlayerStatus.WAITING
SITTING_OUT = PlayerStatus.SITTING_OUT


def seat_players(table: Table, statuses: dict[int, PlayerStatus]) -> dict[int, Player]:
    players = {}
    for seat_number, status in statuses.items():
        player = Player(f"P{seat_number}", stack=1000, status=status)
        table.sit_in(player, seat_number)
        players[seat_number] = player
    return players


def summarize(hand_players: tuple[HandPlayerState, ...]) -> list[tuple[int, Position, Blind]]:
    return [(state.seat_number, state.position, state.blind) for state in hand_players]


def test_ready_players_are_ordered_from_button() -> None:
    """Build one hand state per ready player, starting at the button and wrapping around."""
    table = Table(9)
    players = seat_players(table, {2: READY, 5: READY, 8: READY})
    table.set_button(5)
    hand_players = setup_hand(table)
    assert summarize(hand_players) == [
        (5, Position.BTN, Blind.NONE),
        (8, Position.SB, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
    ]
    assert [state.player for state in hand_players] == [players[5], players[8], players[2]]
    assert all(state.player is players[state.seat_number] for state in hand_players)
    assert all(state.folded is False and state.all_in is False for state in hand_players)


def test_two_players_can_play_on_nine_seat_table() -> None:
    """A hand needs two participants, not a full table."""
    table = Table(9)
    seat_players(table, {2: READY, 7: READY})
    table.set_button(7)
    assert summarize(setup_hand(table)) == [
        (7, Position.BTN, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
    ]


def test_player_without_chips_is_excluded_but_short_stack_plays() -> None:
    """A player with no chips gets no hand state and keeps their status; one chip, below any blind, is enough."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: READY, 3: WAITING, 4: READY})
    players[2].stack = 0
    players[3].stack = 0
    players[4].stack = 1
    table.set_button(1)
    assert summarize(setup_hand(table)) == [
        (1, Position.BTN, Blind.SMALL),
        (4, Position.BB, Blind.BIG),
    ]
    assert {seat: player.status for seat, player in players.items()} == {1: READY, 2: READY, 3: WAITING, 4: READY}


def test_sitting_out_player_is_excluded() -> None:
    """A sitting-out player keeps their seat and status but gets no hand state."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: SITTING_OUT, 3: READY, 4: READY})
    table.set_button(1)
    assert summarize(setup_hand(table)) == [
        (1, Position.BTN, Blind.NONE),
        (3, Position.SB, Blind.SMALL),
        (4, Position.BB, Blind.BIG),
    ]
    assert players[2].status == SITTING_OUT


@pytest.mark.parametrize(
    "waiting_seat, expected",
    [
        pytest.param(
            3,
            [
                (1, Position.BTN, Blind.NONE),
                (2, Position.SB, Blind.SMALL),
                (3, Position.BB, Blind.BIG),
                (4, Position.UTG, Blind.NONE),
            ],
            id="big-blind",
        ),
        pytest.param(
            6,
            [
                (1, Position.BTN, Blind.NONE),
                (2, Position.SB, Blind.SMALL),
                (4, Position.BB, Blind.BIG),
                (6, Position.UTG, Blind.NONE),
            ],
            id="non-blind",
        ),
    ],
)
def test_waiting_player_enters_and_becomes_ready(
    waiting_seat: int, expected: list[tuple[int, Position, Blind]]
) -> None:
    """A waiting player joins as BB or in a non-blind position and is ready from then on."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: READY, 4: READY, waiting_seat: WAITING})
    table.set_button(1)
    assert summarize(setup_hand(table)) == expected
    assert players[waiting_seat].status == READY


def test_waiting_player_who_would_be_small_blind_stays_out() -> None:
    """The small blind passes to the next ready player and the waiting player keeps waiting."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: WAITING, 4: READY, 6: READY})
    table.set_button(1)
    assert summarize(setup_hand(table)) == [
        (1, Position.BTN, Blind.NONE),
        (4, Position.SB, Blind.SMALL),
        (6, Position.BB, Blind.BIG),
    ]
    assert players[2].status == WAITING


@pytest.mark.parametrize(
    "button_seat, waiting_seats, ready_seats",
    [
        pytest.param(1, (2, 3), (5, 7), id="consecutive-seats"),
        pytest.param(8, (9, 1), (3, 5), id="wrapping-around-table"),
    ],
)
def test_every_waiting_player_between_button_and_next_ready_player_stays_out(
    button_seat: int, waiting_seats: tuple[int, int], ready_seats: tuple[int, int]
) -> None:
    """Dropping the first waiting player does not let the next one take the small blind."""
    table = Table(9)
    statuses = {button_seat: READY} | dict.fromkeys(waiting_seats, WAITING) | dict.fromkeys(ready_seats, READY)
    players = seat_players(table, statuses)
    table.set_button(button_seat)
    assert summarize(setup_hand(table)) == [
        (button_seat, Position.BTN, Blind.NONE),
        (ready_seats[0], Position.SB, Blind.SMALL),
        (ready_seats[1], Position.BB, Blind.BIG),
    ]
    assert all(players[seat_number].status == WAITING for seat_number in waiting_seats)


def test_second_waiting_player_enters_heads_up_as_big_blind() -> None:
    """With one ready player, the first waiting player stays out and the second joins as BB."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: WAITING, 3: WAITING})
    table.set_button(1)
    assert summarize(setup_hand(table)) == [
        (1, Position.BTN, Blind.SMALL),
        (3, Position.BB, Blind.BIG),
    ]
    assert players[2].status == WAITING
    assert players[3].status == READY


@pytest.mark.parametrize("button_status", [WAITING, SITTING_OUT], ids=["waiting", "sitting-out"])
def test_button_on_non_participating_player_raises_error(button_status: PlayerStatus) -> None:
    """A failed setup rejects the button and leaves every player status unchanged."""
    table = Table(9)
    players = seat_players(table, {1: button_status, 2: READY, 3: READY, 4: WAITING})
    table.set_button(1)
    with pytest.raises(ButtonSeatNotInHandError):
        setup_hand(table)
    assert players[1].status == button_status
    assert players[4].status == WAITING


def test_button_on_empty_seat_raises_error() -> None:
    """A button left behind by a player who stood up is not a valid button."""
    table = Table(9)
    seat_players(table, {1: READY, 2: READY, 3: READY})
    table.set_button(1)
    table.stand_up(1)
    with pytest.raises(ButtonSeatNotInHandError):
        setup_hand(table)


def test_undefined_button_raises_error() -> None:
    """A hand cannot be set up before the table has a button."""
    table = Table(9)
    seat_players(table, {1: READY, 2: READY})
    with pytest.raises(ButtonUndefinedError):
        setup_hand(table)


@pytest.mark.parametrize(
    "statuses",
    [
        pytest.param({1: READY}, id="one-player"),
        pytest.param({1: READY, 2: SITTING_OUT, 3: SITTING_OUT}, id="others-sitting-out"),
    ],
)
def test_fewer_than_two_participants_raises_error(statuses: dict[int, PlayerStatus]) -> None:
    """A hand requires at least two participating players."""
    table = Table(9)
    seat_players(table, statuses)
    table.set_button(1)
    with pytest.raises(InvalidPlayerCount):
        setup_hand(table)


def test_setup_does_not_change_button_or_stacks() -> None:
    """Setup reads the button and never touches chips."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: READY, 3: WAITING})
    table.set_button(1)
    setup_hand(table)
    assert table.button_seat_number == 1
    assert all(player.stack == 1000 for player in players.values())


def test_each_setup_returns_new_hand_states() -> None:
    """Per-hand flags from one hand do not carry over to the next setup."""
    table = Table(9)
    seat_players(table, {1: READY, 2: READY})
    table.set_button(1)
    first_hand = setup_hand(table)
    first_hand[0].folded = True
    first_hand[1].all_in = True
    second_hand = setup_hand(table)
    assert all(state.folded is False and state.all_in is False for state in second_hand)
    assert all(new.player is old.player for new, old in zip(second_hand, first_hand, strict=True))

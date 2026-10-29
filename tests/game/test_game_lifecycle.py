from collections.abc import MutableSequence
from random import Random
from typing import Any

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.game_lifecycle import (
    GameAlreadyStartedError,
    GameNotStartedError,
    start_game,
    start_next_hand,
)
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, InvalidPlayerCount, Position
from go_poker.game.position_assignment import ButtonSeatNotInHandError
from go_poker.game.street import Street
from go_poker.game.table import ButtonUndefinedError, Table

READY = PlayerStatus.READY
WAITING = PlayerStatus.WAITING
SITTING_OUT = PlayerStatus.SITTING_OUT

SETUP_HAND_PATH = "go_poker.game.game_lifecycle.setup_hand"

FULL_DECK = {Card(rank, suit) for rank in Rank for suit in Suit}


def seat_players(table: Table, statuses: dict[int, PlayerStatus]) -> dict[int, Player]:
    players = {}
    for seat_number, status in statuses.items():
        player = Player(f"P{seat_number}", stack=1000, status=status)
        table.sit_in(player, seat_number)
        players[seat_number] = player
    return players


def summarize(hand: PokerHand) -> list[tuple[int, Position, Blind]]:
    return [(state.seat_number, state.position, state.blind) for state in hand.players]


def assert_fresh_hand(hand: PokerHand) -> None:
    assert isinstance(hand, PokerHand)
    assert isinstance(hand.deck, Deck)
    assert len(hand.deck) == 52
    assert {hand.deck.draw() for _ in range(52)} == FULL_DECK
    assert hand.board == []
    assert hand.street is Street.PREFLOP
    assert hand.burned_cards == []
    assert all(state.hole_cards == [] for state in hand.players)


def statuses_of(players: dict[int, Player]) -> dict[int, PlayerStatus]:
    return {seat_number: player.status for seat_number, player in players.items()}


class RecordingChooser:
    """Button chooser that returns a fixed seat and records the seats it was offered."""

    def __init__(self, button_seat_number: int) -> None:
        self.button_seat_number = button_seat_number
        self.calls: list[tuple[int, ...]] = []

    def __call__(self, seat_numbers: tuple[int, ...]) -> int:
        self.calls.append(seat_numbers)
        return self.button_seat_number


class SetupFailure(Exception):
    """Sentinel raised by a patched setup_hand."""


class ShuffleFailure(Exception):
    """Sentinel raised by FailingRandom."""


class FailingRandom(Random):
    """Test generator whose shuffle always fails."""

    def shuffle(self, x: MutableSequence[Any]) -> None:
        raise ShuffleFailure


def deck_order(hand: PokerHand) -> list[Card]:
    return [hand.deck.draw() for _ in range(len(hand.deck))]


def expected_deck_order(seed: int) -> list[Card]:
    """The draw order of a fresh deck shuffled once with Random(seed)."""
    cards = Deck.create_new_deck()
    Random(seed).shuffle(cards)
    return list(reversed(cards))


# =============================================================================
# START GAME
# =============================================================================


def test_seating_players_does_not_start_a_game() -> None:
    """Sitting down leaves players waiting and the button unset until the game is started."""
    table = Table(9)
    players = [Player(f"P{seat_number}", stack=1000) for seat_number in (1, 2, 3)]
    for seat_number, player in enumerate(players, start=1):
        table.sit_in(player, seat_number)
    assert all(player.status == WAITING for player in players)
    assert table.button_seat_number is None


@pytest.mark.parametrize(
    "max_seats, button_seat, expected",
    [
        pytest.param(
            2,
            2,
            [
                (2, Position.BTN, Blind.SMALL),
                (1, Position.BB, Blind.BIG),
            ],
            id="heads-up-on-two-seat-table",
        ),
        pytest.param(
            9,
            7,
            [
                (7, Position.BTN, Blind.SMALL),
                (3, Position.BB, Blind.BIG),
            ],
            id="heads-up-on-nine-seat-table",
        ),
        pytest.param(
            9,
            3,
            [
                (3, Position.BTN, Blind.NONE),
                (4, Position.SB, Blind.SMALL),
                (6, Position.BB, Blind.BIG),
                (8, Position.UTG, Blind.NONE),
                (1, Position.CO, Blind.NONE),
            ],
            id="multi-player",
        ),
        pytest.param(
            9,
            5,
            [
                (5, Position.BTN, Blind.NONE),
                (6, Position.SB, Blind.SMALL),
                (7, Position.BB, Blind.BIG),
                (8, Position.UTG, Blind.NONE),
                (9, Position.UTG1, Blind.NONE),
                (1, Position.MP, Blind.NONE),
                (2, Position.LJ, Blind.NONE),
                (3, Position.HJ, Blind.NONE),
                (4, Position.CO, Blind.NONE),
            ],
            id="nine-players",
        ),
    ],
)
def test_start_game_readies_every_waiting_player_and_sets_up_first_hand(
    max_seats: int, button_seat: int, expected: list[tuple[int, Position, Blind]]
) -> None:
    """Every waiting player starts the game as ready, with the chosen seat on the button."""
    table = Table(max_seats)
    starter_seats = tuple(sorted(seat_number for seat_number, _, _ in expected))
    players = seat_players(table, dict.fromkeys(starter_seats, WAITING))
    chooser = RecordingChooser(button_seat)
    assert summarize(start_game(table, chooser)) == expected
    assert chooser.calls == [starter_seats]
    assert all(player.status == READY for player in players.values())
    assert table.button_seat_number == button_seat


def test_start_game_returns_hand_with_fresh_deck_and_empty_board() -> None:
    """The first hand is a PokerHand with its own full deck and no community cards yet."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
    assert_fresh_hand(start_game(table, RecordingChooser(1)))


def test_sitting_out_players_are_not_starters() -> None:
    """Sitting-out players are not offered to the chooser, not dealt in, and keep sitting out."""
    table = Table(9)
    players = seat_players(table, {1: WAITING, 2: SITTING_OUT, 4: WAITING, 6: SITTING_OUT, 7: WAITING})
    chooser = RecordingChooser(1)
    assert summarize(start_game(table, chooser)) == [
        (1, Position.BTN, Blind.NONE),
        (4, Position.SB, Blind.SMALL),
        (7, Position.BB, Blind.BIG),
    ]
    assert chooser.calls == [(1, 4, 7)]
    assert statuses_of(players) == {1: READY, 2: SITTING_OUT, 4: READY, 6: SITTING_OUT, 7: READY}


def test_chooser_receives_starter_seats_in_seat_order() -> None:
    """The chooser is called once with the starter seats in seat order, not seating order."""
    table = Table(9)
    seat_players(table, {7: WAITING, 2: WAITING, 5: WAITING})
    chooser = RecordingChooser(5)
    start_game(table, chooser)
    assert chooser.calls == [(2, 5, 7)]


def test_start_game_replaces_stale_button() -> None:
    """A button left over from an earlier game is replaced by the chosen seat."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3, 4), WAITING))
    table.set_button(1)
    table.stand_up(1)
    hand = start_game(table, RecordingChooser(3))
    assert table.button_seat_number == 3
    assert summarize(hand) == [
        (3, Position.BTN, Blind.NONE),
        (4, Position.SB, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
    ]


def test_start_game_with_ready_player_raises_error() -> None:
    """A game that already has ready players cannot be started again."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: WAITING, 3: WAITING})
    table.set_button(1)
    chooser = RecordingChooser(2)
    with pytest.raises(GameAlreadyStartedError):
        start_game(table, chooser)
    assert chooser.calls == []
    assert statuses_of(players) == {1: READY, 2: WAITING, 3: WAITING}
    assert table.button_seat_number == 1


@pytest.mark.parametrize(
    "statuses",
    [
        pytest.param({}, id="no-players"),
        pytest.param({1: WAITING}, id="one-player"),
        pytest.param({1: WAITING, 2: SITTING_OUT, 3: SITTING_OUT}, id="others-sitting-out"),
    ],
)
def test_start_game_with_fewer_than_two_starters_raises_error(statuses: dict[int, PlayerStatus]) -> None:
    """A game needs at least two waiting players, and nothing changes when it cannot start."""
    table = Table(9)
    players = seat_players(table, statuses)
    chooser = RecordingChooser(1)
    with pytest.raises(InvalidPlayerCount):
        start_game(table, chooser)
    assert chooser.calls == []
    assert statuses_of(players) == statuses
    assert table.button_seat_number is None


@pytest.mark.parametrize(
    "chosen_seat",
    [
        pytest.param(2, id="sitting-out-seat"),
        pytest.param(5, id="empty-seat"),
        pytest.param(42, id="nonexistent-seat"),
    ],
)
def test_chooser_result_outside_starters_raises_error(chosen_seat: int) -> None:
    """The chosen button must be a starter seat, and nothing changes when it is not."""
    table = Table(9)
    players = seat_players(table, {1: WAITING, 2: SITTING_OUT, 3: WAITING, 4: WAITING})
    with pytest.raises(ButtonSeatNotInHandError):
        start_game(table, RecordingChooser(chosen_seat))
    assert statuses_of(players) == {1: WAITING, 2: SITTING_OUT, 3: WAITING, 4: WAITING}
    assert table.button_seat_number is None


@pytest.mark.parametrize("previous_button", [None, 4], ids=["no-button", "stale-button"])
def test_start_game_failure_restores_statuses_and_button(
    monkeypatch: pytest.MonkeyPatch, previous_button: int | None
) -> None:
    """A failure after starters are readied undoes the start and re-raises the original error."""
    table = Table(9)
    players = seat_players(table, {1: WAITING, 2: WAITING, 3: WAITING, 4: SITTING_OUT})
    if previous_button is not None:
        table.set_button(previous_button)
    error = SetupFailure()
    observed: list[tuple[dict[int, PlayerStatus], int | None]] = []

    def failing_setup_hand(table: Table) -> tuple[HandPlayerState, ...]:
        observed.append((statuses_of(players), table.button_seat_number))
        raise error

    monkeypatch.setattr(SETUP_HAND_PATH, failing_setup_hand)
    with pytest.raises(SetupFailure) as excinfo:
        start_game(table, RecordingChooser(2))
    assert excinfo.value is error
    assert observed == [({1: READY, 2: READY, 3: READY, 4: SITTING_OUT}, 2)]
    assert statuses_of(players) == {1: WAITING, 2: WAITING, 3: WAITING, 4: SITTING_OUT}
    assert table.button_seat_number == previous_button


# =============================================================================
# START NEXT HAND
# =============================================================================


@pytest.mark.parametrize(
    "statuses, previous_button, expected",
    [
        pytest.param(
            {1: READY, 2: READY, 3: READY},
            1,
            [
                (2, Position.BTN, Blind.NONE),
                (3, Position.SB, Blind.SMALL),
                (1, Position.BB, Blind.BIG),
            ],
            id="next-adjacent-player",
        ),
        pytest.param(
            {1: READY, 4: READY, 6: READY},
            1,
            [
                (4, Position.BTN, Blind.NONE),
                (6, Position.SB, Blind.SMALL),
                (1, Position.BB, Blind.BIG),
            ],
            id="skips-empty-seats",
        ),
        pytest.param(
            {2: READY, 5: READY, 9: READY},
            9,
            [
                (2, Position.BTN, Blind.NONE),
                (5, Position.SB, Blind.SMALL),
                (9, Position.BB, Blind.BIG),
            ],
            id="wraps-around-table",
        ),
        pytest.param(
            {1: READY, 2: SITTING_OUT, 3: READY, 4: READY},
            1,
            [
                (3, Position.BTN, Blind.NONE),
                (4, Position.SB, Blind.SMALL),
                (1, Position.BB, Blind.BIG),
            ],
            id="skips-sitting-out-player",
        ),
    ],
)
def test_button_moves_to_next_ready_player(
    statuses: dict[int, PlayerStatus], previous_button: int, expected: list[tuple[int, Position, Blind]]
) -> None:
    """The button moves clockwise to the next ready player and the hand is set up from there."""
    table = Table(9)
    seat_players(table, statuses)
    table.set_button(previous_button)
    assert summarize(start_next_hand(table)) == expected
    assert table.button_seat_number == expected[0][0]


def test_start_next_hand_returns_hand_with_fresh_deck_and_empty_board() -> None:
    """Each next hand is a PokerHand with its own full deck and no community cards yet."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), READY))
    table.set_button(1)
    assert_fresh_hand(start_next_hand(table))


def test_new_hands_start_preflop_without_burned_cards() -> None:
    """Both the first hand and each next hand start on the preflop street with nothing burned."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
    for hand in (start_game(table, RecordingChooser(1)), start_next_hand(table)):
        assert hand.street is Street.PREFLOP
        assert hand.burned_cards == []


def test_consecutive_hands_get_distinct_decks_and_boards() -> None:
    """A new hand never reuses the previous hand's deck or board."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
    first_hand = start_game(table, RecordingChooser(1))
    first_hand.board.append(first_hand.deck.draw())
    second_hand = start_next_hand(table)
    assert second_hand.deck is not first_hand.deck
    assert second_hand.board is not first_hand.board
    assert_fresh_hand(second_hand)


def test_button_skips_waiting_player() -> None:
    """A waiting player cannot receive the button, though hand setup may still deal them in."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: WAITING, 3: READY, 4: READY})
    table.set_button(1)
    assert summarize(start_next_hand(table)) == [
        (3, Position.BTN, Blind.NONE),
        (4, Position.SB, Blind.SMALL),
        (1, Position.BB, Blind.BIG),
        (2, Position.UTG, Blind.NONE),
    ]
    assert table.button_seat_number == 3
    assert players[2].status == READY


def test_button_moves_on_from_seat_of_player_who_stood_up() -> None:
    """The previous button seat still anchors the move after its player leaves the table."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 3, 5, 7), READY))
    table.set_button(5)
    table.stand_up(5)
    assert summarize(start_next_hand(table)) == [
        (7, Position.BTN, Blind.NONE),
        (1, Position.SB, Blind.SMALL),
        (3, Position.BB, Blind.BIG),
    ]
    assert table.button_seat_number == 7


@pytest.mark.parametrize(
    "new_status, expected",
    [
        pytest.param(
            WAITING,
            [
                (7, Position.BTN, Blind.NONE),
                (1, Position.SB, Blind.SMALL),
                (3, Position.BB, Blind.BIG),
                (5, Position.UTG, Blind.NONE),
            ],
            id="waiting",
        ),
        pytest.param(
            SITTING_OUT,
            [
                (7, Position.BTN, Blind.NONE),
                (1, Position.SB, Blind.SMALL),
                (3, Position.BB, Blind.BIG),
            ],
            id="sitting-out",
        ),
    ],
)
def test_button_moves_on_from_player_who_is_no_longer_ready(
    new_status: PlayerStatus, expected: list[tuple[int, Position, Blind]]
) -> None:
    """The previous button seat still anchors the move after its player stops being ready."""
    table = Table(9)
    players = seat_players(table, dict.fromkeys((1, 3, 5, 7), READY))
    table.set_button(5)
    players[5].status = new_status
    assert summarize(start_next_hand(table)) == expected
    assert table.button_seat_number == 7


def test_single_ready_player_keeps_button_and_plays_heads_up_with_waiting_player() -> None:
    """With one ready player the button stays with them and a waiting player joins as BB."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: WAITING})
    table.set_button(1)
    assert summarize(start_next_hand(table)) == [
        (1, Position.BTN, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
    ]
    assert table.button_seat_number == 1
    assert players[2].status == READY


def test_single_ready_player_without_opponent_raises_error_and_restores_button() -> None:
    """Hand setup's player-count error propagates and the previous button is restored."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: SITTING_OUT, 3: SITTING_OUT})
    table.set_button(3)
    with pytest.raises(InvalidPlayerCount):
        start_next_hand(table)
    assert table.button_seat_number == 3
    assert statuses_of(players) == {1: READY, 2: SITTING_OUT, 3: SITTING_OUT}


@pytest.mark.parametrize(
    "statuses",
    [
        pytest.param({1: WAITING, 2: WAITING}, id="all-waiting"),
        pytest.param({1: SITTING_OUT, 2: SITTING_OUT}, id="all-sitting-out"),
        pytest.param({1: WAITING, 2: SITTING_OUT, 3: WAITING}, id="mixed"),
    ],
)
def test_next_hand_without_ready_players_requires_restart(statuses: dict[int, PlayerStatus]) -> None:
    """Without ready players the game must be started again, and nothing changes."""
    table = Table(9)
    players = seat_players(table, statuses)
    table.set_button(1)
    with pytest.raises(GameNotStartedError):
        start_next_hand(table)
    assert statuses_of(players) == statuses
    assert table.button_seat_number == 1


def test_missing_ready_players_is_reported_before_missing_button() -> None:
    """A table that never started reports that the game is not started, not that the button is missing."""
    table = Table(9)
    seat_players(table, {1: WAITING, 2: WAITING})
    with pytest.raises(GameNotStartedError):
        start_next_hand(table)
    assert table.button_seat_number is None


def test_next_hand_without_button_raises_error() -> None:
    """Ready players cannot move on to a next hand when no button was ever placed."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: READY})
    with pytest.raises(ButtonUndefinedError):
        start_next_hand(table)
    assert table.button_seat_number is None
    assert statuses_of(players) == {1: READY, 2: READY}


def test_button_rotates_across_hands() -> None:
    """After the game starts, each next hand moves the button one ready player clockwise."""
    table = Table(9)
    seat_players(table, dict.fromkeys((2, 4, 7), WAITING))
    first_hand = start_game(table, RecordingChooser(4))
    later_hands = [start_next_hand(table) for _ in range(3)]
    hands = [first_hand, *later_hands]
    assert [hand.players[0].seat_number for hand in hands] == [4, 7, 2, 4]
    assert all(hand.players[0].position is Position.BTN for hand in hands)
    assert summarize(later_hands[0]) == [
        (7, Position.BTN, Blind.NONE),
        (2, Position.SB, Blind.SMALL),
        (4, Position.BB, Blind.BIG),
    ]
    assert table.button_seat_number == 4


def test_player_who_entered_a_later_hand_can_receive_the_button() -> None:
    """A waiting player promoted by hand setup becomes a button candidate on later hands."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
    start_game(table, RecordingChooser(1))
    newcomer = seat_players(table, {4: WAITING})[4]

    entry_hand = start_next_hand(table)
    assert summarize(entry_hand) == [
        (2, Position.BTN, Blind.NONE),
        (3, Position.SB, Blind.SMALL),
        (4, Position.BB, Blind.BIG),
        (1, Position.UTG, Blind.NONE),
    ]
    assert newcomer.status == READY

    start_next_hand(table)
    assert table.button_seat_number == 3

    assert summarize(start_next_hand(table)) == [
        (4, Position.BTN, Blind.NONE),
        (1, Position.SB, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
        (3, Position.UTG, Blind.NONE),
    ]
    assert table.button_seat_number == 4


def test_next_hand_failure_restores_button(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failure after the button moves puts it back and re-raises the original error."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: READY, 3: READY})
    table.set_button(1)
    error = SetupFailure()
    observed_buttons: list[int | None] = []

    def failing_setup_hand(table: Table) -> tuple[HandPlayerState, ...]:
        observed_buttons.append(table.button_seat_number)
        raise error

    monkeypatch.setattr(SETUP_HAND_PATH, failing_setup_hand)
    with pytest.raises(SetupFailure) as excinfo:
        start_next_hand(table)
    assert excinfo.value is error
    assert observed_buttons == [2]
    assert table.button_seat_number == 1
    assert statuses_of(players) == {1: READY, 2: READY, 3: READY}


# =============================================================================
# DECK SHUFFLING
# =============================================================================


def test_every_new_hand_is_shuffled_without_a_test_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a test rng, game start and every next hand shuffle a fresh full deck with the default generator."""
    shuffles: list[tuple[int, Random | None]] = []

    def recording_shuffle(deck: Deck, *, _rng: Random | None = None) -> None:
        shuffles.append((len(deck), _rng))

    monkeypatch.setattr(Deck, "shuffle", recording_shuffle)
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
    start_game(table, RecordingChooser(1))
    start_next_hand(table)
    start_next_hand(table)
    assert shuffles == [(52, None)] * 3


def test_start_game_shuffles_the_deck_with_the_test_rng() -> None:
    """Equal seeds give the first hand the same deck order, and the order comes from the given rng."""
    orders = []
    for _ in range(2):
        table = Table(9)
        seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
        orders.append(deck_order(start_game(table, RecordingChooser(1), _rng=Random(11))))
    assert orders[0] == orders[1] == expected_deck_order(11)


def test_start_next_hand_shuffles_the_deck_with_the_test_rng() -> None:
    """Equal seeds give the next hand the same deck order, and the order comes from the given rng."""
    orders = []
    for _ in range(2):
        table = Table(9)
        seat_players(table, dict.fromkeys((1, 2, 3), READY))
        table.set_button(1)
        orders.append(deck_order(start_next_hand(table, _rng=Random(23))))
    assert orders[0] == orders[1] == expected_deck_order(23)


def test_shared_test_rng_reproduces_a_sequence_of_hands() -> None:
    """Replaying a game with the same seeded generator reproduces every hand's deck order."""
    games = []
    for _ in range(2):
        table = Table(9)
        seat_players(table, dict.fromkeys((2, 4, 7), WAITING))
        rng = Random(5)
        hands = [start_game(table, RecordingChooser(4), _rng=rng)]
        hands += [start_next_hand(table, _rng=rng) for _ in range(3)]
        games.append([deck_order(hand) for hand in hands])
    assert games[0] == games[1]
    assert len({tuple(order) for order in games[0]}) == 4


@pytest.mark.parametrize("seed", [0, 99])
def test_seeded_hands_have_full_deck_and_no_dealt_cards(seed: int) -> None:
    """A seeded shuffle still gives each hand all 52 cards, and starting a hand deals nothing."""
    table = Table(9)
    seat_players(table, dict.fromkeys((1, 2, 3), WAITING))
    assert_fresh_hand(start_game(table, RecordingChooser(1), _rng=Random(seed)))
    assert_fresh_hand(start_next_hand(table, _rng=Random(seed)))


def test_start_game_shuffle_failure_restores_statuses_and_button() -> None:
    """A failing shuffle undoes the start like any other failure while the hand is being created."""
    table = Table(9)
    players = seat_players(table, {1: WAITING, 2: WAITING, 3: SITTING_OUT})
    with pytest.raises(ShuffleFailure):
        start_game(table, RecordingChooser(2), _rng=FailingRandom())
    assert statuses_of(players) == {1: WAITING, 2: WAITING, 3: SITTING_OUT}
    assert table.button_seat_number is None


def test_start_next_hand_shuffle_failure_restores_button_and_keeps_entrant_waiting() -> None:
    """A failing shuffle restores the button and leaves a would-be entrant waiting."""
    table = Table(9)
    players = seat_players(table, {1: READY, 2: READY, 3: READY, 4: WAITING})
    table.set_button(1)
    with pytest.raises(ShuffleFailure):
        start_next_hand(table, _rng=FailingRandom())
    assert table.button_seat_number == 1
    assert statuses_of(players) == {1: READY, 2: READY, 3: READY, 4: WAITING}

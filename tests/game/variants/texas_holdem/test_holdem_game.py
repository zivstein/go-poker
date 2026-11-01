"""The continuous `HoldemGame`: one representative test per rule of its orchestration contract.

The lifecycle and `hand_flow` own the button, participation, turn and settlement rules and have their own matrices, so
these tests only check that the game wires them together and rejects what the contract says it rejects, each rejection
leaving the table, the players, `game.hand` and the hand unchanged.

Decks are stacked through the lifecycle's own shuffle (the `queue_decks` fixture): one queued draw order per hand, in
the order the hands start. Blinds are 5/10. Hole cards come from `HOLES` (AA beats KK, which beats 3s 4s) on `BOARD`,
which holds no pair, no possible flush and no possible straight for them.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import NotPlayersTurnError
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.game_lifecycle import GameAlreadyStartedError, GameNotStartedError
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BlindPost,
    BlindsPosted,
    ChipsReturned,
    HandHistory,
    HandParticipant,
    HandStarted,
    HoleCardsDealt,
    SeatHoleCards,
)
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.position import Blind, InvalidPlayerCount, Position
from go_poker.game.position_assignment import ButtonSeatNotInHandError
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem import hand_flow
from go_poker.game.variants.texas_holdem.game import HandInProgressError, HoldemGame
from go_poker.game.variants.texas_holdem.hand_flow import current_actor

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK
READY = PlayerStatus.READY
WAITING = PlayerStatus.WAITING
SITTING_OUT = PlayerStatus.SITTING_OUT

BOARD = "2c 4d 7h 9s Jc"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s", 4: "Qh Qd", 5: "5s 6s"}

type DrawOrder = Callable[..., list[Card]]
type QueueDecks = Callable[..., Any]
type Setup = tuple[HoldemGame, Table, dict[int, Player]]


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def order(draw_order: DrawOrder, seats: tuple[int, ...], button: int, winner: int | None = None) -> list[Card]:
    """The deck for a hand of these seats; `winner`, when given, gets the best hole cards (AA) and seat 1's go to it."""
    holes = {seat: HOLES[seat] for seat in seats}
    if winner is not None and winner != 1 and 1 in holes:
        holes[winner], holes[1] = holes[1], holes[winner]
    return draw_order(holes, BOARD, button)


def make_game(stacks: dict[int, int], max_seats: int = 9) -> Setup:
    table = Table(max_seats)
    players = {seat: Player(f"P{seat}", stack=stack) for seat, stack in stacks.items()}
    for seat, player in players.items():
        table.sit_in(player, seat)
    return HoldemGame(table, STAKES), table, players


def button_at(seat: int) -> Callable[[tuple[int, ...]], int]:
    return lambda _seats: seat


def hand_state(hand: PokerHand, *, with_stacks: bool = True) -> dict[str, Any]:
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "showdown": hand.showdown,
        "history": hand.history,
        "players": [
            (
                state.seat_number,
                state.position,
                state.player.stack if with_stacks else None,
                state.folded,
                state.all_in,
                state.street_contribution,
                state.total_contribution,
                list(state.hole_cards),
            )
            for state in hand.players
        ],
        "pots": pots(hand),
    }


def world(game: HoldemGame, table: Table) -> tuple[Any, ...]:
    """Everything a rejected call must leave alone: the button, every seated player and the hand."""
    seated = [
        (seat.number, seat.player, seat.player.stack, seat.player.status)
        for seat in table.occupied_seats
        if seat.player
    ]
    hand = game.hand
    return table.button_seat_number, seated, hand, None if hand is None else hand_state(hand)


def fold_out(game: HoldemGame) -> None:
    """Fold every actor until the hand is settled uncontested."""
    while game.hand is not None and game.hand.settlement is None:
        seat = current_actor(game.hand)
        assert seat is not None
        game.act(seat, FOLD)


def check_down_to_showdown(game: HoldemGame) -> None:
    """Check or call every betting decision until the interactive river showdown waits for its first decider."""
    hand = game.hand
    assert hand is not None
    while hand.showdown is None:
        seat = current_actor(hand)
        assert seat is not None
        game.act(seat, CHECK if legal_actions(hand).can_check else CALL)
    assert hand.settlement is None and not hand.showdown.is_complete


def assert_settled_hand_rejects_flow(hand: PokerHand) -> None:
    before = hand_state(hand, with_stacks=False)
    with pytest.raises(HandAlreadySettledError):
        hand_flow.act(hand, 1, FOLD)
    assert hand_state(hand, with_stacks=False) == before


# =============================================================================
# START
# =============================================================================


def test_start_uses_the_chosen_button_readies_the_starters_and_awaits_a_decision(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=2))
    offered: list[tuple[int, ...]] = []

    def choose(seats: tuple[int, ...]) -> int:
        offered.append(seats)
        return 2

    assert game.hand is None
    hand = game.start(choose)

    assert offered == [(1, 2, 3)]
    assert hand is game.hand
    assert table.button_seat_number == 2
    assert [player.status for player in players.values()] == [READY, READY, READY]
    assert [state.seat_number for state in hand.players] == [2, 3, 1]
    assert hand.settlement is None
    assert current_actor(hand) == 2  # three-handed, the button acts first preflop
    assert hand.betting is not None and hand.betting.stakes == STAKES
    assert [state.player.stack for state in hand.players] == [1000, 995, 990]


def test_start_and_next_hand_return_a_hand_the_blinds_alone_settled(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    """Heads-up with stacks that the blinds put all-in: the hand is settled at once, and the next hand still begins."""
    game, table, players = make_game({1: 5, 2: 10})
    queue_decks(order(draw_order, (1, 2), button=1), order(draw_order, (1, 2), button=2, winner=2))

    first = game.start(button_at(1))

    assert first is game.hand and first.settlement is not None
    assert current_actor(first) is None
    assert (players[1].stack, players[2].stack) == (10, 5)  # seat 1 won the 10 that both could contest

    second = game.next_hand()

    assert second is game.hand and second is not first
    assert table.button_seat_number == 2
    assert second.settlement is not None
    assert (players[1].stack, players[2].stack) == (5, 10)


# =============================================================================
# PLAYING HANDS
# =============================================================================


def test_a_whole_hand_is_driven_only_through_game_act_including_show_and_muck(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1))
    hand = game.start(button_at(1))

    moves: list[tuple[int, Action | ShowdownAction]] = [
        (1, CALL), (2, CALL), (3, CHECK),  # preflop
        *[(seat, CHECK) for seat in (2, 3, 1)] * 3,  # flop, turn, river
        (2, SHOW), (3, MUCK), (1, SHOW),  # interactive showdown, first left of the button first
    ]  # fmt: skip
    for seat, move in moves:
        assert hand.settlement is None
        assert current_actor(hand) == seat
        game.act(seat, move)

    assert hand is game.hand
    assert hand.settlement is not None and current_actor(hand) is None
    assert [seat for seat, _ in hand.settlement.showdown_ranks] == [1, 2]  # the muck is not ranked
    assert [players[seat].stack for seat in (1, 2, 3)] == [1020, 990, 990]


# =============================================================================
# NEXT HAND
# =============================================================================


def test_next_hand_moves_the_button_starts_a_new_hand_and_leaves_the_settled_one_alone(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3), button=2))
    first = game.start(button_at(1))
    fold_out(game)
    assert first.settlement is not None
    settled = hand_state(first, with_stacks=False)
    settlement = first.settlement

    second = game.next_hand()

    assert second is game.hand and second is not first
    assert table.button_seat_number == 2
    assert [state.seat_number for state in second.players] == [2, 3, 1]
    assert second.settlement is None and current_actor(second) == 2
    assert hand_state(first, with_stacks=False) == settled and first.settlement is settlement
    assert_settled_hand_rejects_flow(first)

    before_second = hand_state(second)
    game.act(2, FOLD)

    assert hand_state(second) != before_second and second.players[0].folded
    assert hand_state(first, with_stacks=False) == settled


def test_a_busted_player_stays_seated_but_is_skipped(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    """Seat 3 posts its last 10 as the big blind and loses it to seat 1's all-in; it takes no further part."""
    game, table, players = make_game({1: 1000, 2: 1000, 3: 10})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2), button=2))
    game.start(button_at(1))
    game.act(1, raise_to(1000))
    game.act(2, FOLD)
    assert players[3].stack == 0 and game.hand is not None and game.hand.settlement is not None

    second = game.next_hand()

    assert table.button_seat_number == 2
    assert [state.seat_number for state in second.players] == [2, 1]
    assert table.get_seat(3).player is players[3]
    assert players[3].stack == 0 and players[3].status is READY


def test_a_busted_button_still_anchors_the_search_for_the_next_button(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    """The button holder (seat 3) calls its last 10 all-in and loses; the button goes on to seat 4, the next seat
    clockwise from seat 3, and does not wrap to the lowest ready seat (1)."""
    game, table, players = make_game({1: 1000, 2: 1000, 3: 10, 4: 1000})
    queue_decks(order(draw_order, (1, 2, 3, 4), button=3), order(draw_order, (1, 2, 4), button=4))
    game.start(button_at(3))
    game.act(2, FOLD)
    game.act(3, CALL)
    game.act(4, FOLD)  # the big blind (seat 1) has nothing left to decide against an all-in
    assert players[3].stack == 0 and game.hand is not None and game.hand.settlement is not None

    second = game.next_hand()

    assert table.button_seat_number == 4
    assert [state.seat_number for state in second.players] == [4, 1, 2]
    assert players[3].stack == 0 and table.get_seat(3).player is players[3]


def test_a_waiting_player_seated_between_hands_enters_as_big_blind(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3, 4), button=2))
    game.start(button_at(1))
    fold_out(game)
    newcomer = Player("P4", stack=1000)
    table.sit_in(newcomer, 4)

    second = game.next_hand()

    assert [(state.seat_number, state.position.value) for state in second.players] == [
        (2, "BTN"),
        (3, "SB"),
        (4, "BB"),
        (1, "UTG"),
    ]
    assert newcomer.status is READY and players[1].status is READY


def test_a_waiting_player_who_would_be_small_blind_keeps_waiting(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, _ = make_game({1: 1000, 2: 1000, 4: 1000})
    queue_decks(order(draw_order, (1, 2, 4), button=1), order(draw_order, (1, 2, 4), button=2))
    game.start(button_at(1))
    fold_out(game)
    newcomer = Player("P3", stack=1000)
    table.sit_in(newcomer, 3)  # clockwise from the new button 2, seat 3 would be the small blind

    second = game.next_hand()

    assert [state.seat_number for state in second.players] == [2, 4, 1]
    assert newcomer.status is WAITING


# =============================================================================
# REJECTIONS
# =============================================================================


def test_next_hand_is_rejected_while_betting_or_a_showdown_decision_is_pending(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1))
    game.start(button_at(1))

    before = world(game, table)
    with pytest.raises(HandInProgressError):
        game.next_hand()
    assert world(game, table) == before

    check_down_to_showdown(game)
    game.act(2, SHOW)
    assert game.hand is not None and game.hand.showdown is not None and not game.hand.showdown.is_complete

    before = world(game, table)
    with pytest.raises(HandInProgressError):
        game.next_hand()
    assert world(game, table) == before


def test_start_is_rejected_once_a_hand_exists_and_is_never_a_restart(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1))
    offered: list[tuple[int, ...]] = []

    def choose(seats: tuple[int, ...]) -> int:
        offered.append(seats)
        return seats[0]

    game.start(button_at(1))

    before = world(game, table)
    with pytest.raises(GameAlreadyStartedError):
        game.start(choose)
    assert world(game, table) == before

    fold_out(game)
    before = world(game, table)
    with pytest.raises(GameAlreadyStartedError):
        game.start(choose)
    assert world(game, table) == before

    # Even with no READY player seated, where the lifecycle alone would start a new game, start never restarts.
    for player in players.values():
        player.status = WAITING
    before = world(game, table)
    with pytest.raises(GameAlreadyStartedError):
        game.start(choose)
    assert world(game, table) == before
    assert offered == []


def test_act_and_next_hand_before_start_are_rejected() -> None:
    game, table, players = make_game({1: 1000, 2: 1000})
    before = world(game, table)

    with pytest.raises(GameNotStartedError):
        game.act(1, CALL)
    with pytest.raises(GameNotStartedError):
        game.next_hand()

    assert world(game, table) == before
    assert game.hand is None and table.button_seat_number is None
    assert [player.status for player in players.values()] == [WAITING, WAITING]


def test_heads_up_bust_rejects_next_hand_until_another_player_is_seated(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 10})
    # The lifecycle shuffles before it rejects the missing second player, so the rejected call also uses up a deck.
    queue_decks(
        order(draw_order, (1, 2), button=1), order(draw_order, (1, 2), button=1), order(draw_order, (1, 3), button=1)
    )
    game.start(button_at(1))
    game.act(1, CALL)  # seat 2 is all-in with its big blind, and loses
    assert players[2].stack == 0 and game.hand is not None and game.hand.settlement is not None

    before = world(game, table)
    with pytest.raises(InvalidPlayerCount):
        game.next_hand()
    assert world(game, table) == before

    newcomer = Player("P3", stack=1000)
    table.sit_in(newcomer, 3)
    second = game.next_hand()

    assert second is game.hand
    assert [state.seat_number for state in second.players] == [1, 3]
    assert newcomer.status is READY


@pytest.mark.parametrize("fault", ["too_few_starters", "invalid_button"])
def test_a_lifecycle_rejection_on_start_propagates_and_the_game_can_still_start(
    fault: str, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000} if fault == "too_few_starters" else {1: 1000, 2: 1000})
    queue_decks(order(draw_order, (1, 2), button=1))
    error = InvalidPlayerCount if fault == "too_few_starters" else ButtonSeatNotInHandError

    before = world(game, table)
    with pytest.raises(error):
        game.start(button_at(5))  # only reached by the invalid-button case; a single starter is rejected first
    assert world(game, table) == before
    assert game.hand is None and table.button_seat_number is None

    if fault == "too_few_starters":
        players[2] = Player("P2", stack=1000)
        table.sit_in(players[2], 2)
    hand = game.start(button_at(1))

    assert hand is game.hand and table.button_seat_number == 1
    assert [player.status for player in players.values()] == [READY, READY]


@pytest.mark.parametrize(
    "seat, action, error",
    [(1, "garbage", TypeError), (2, CALL, NotPlayersTurnError)],
    ids=["garbage_action", "wrong_seat"],
)
def test_act_rejections_pass_through_unchanged(
    seat: int, action: Any, error: type[Exception], queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1))
    game.start(button_at(1))
    before = world(game, table)

    with pytest.raises(error):
        game.act(seat, action)

    assert world(game, table) == before


def test_game_hand_is_replaced_only_after_the_hand_has_begun(
    monkeypatch: pytest.MonkeyPatch, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    """An engine defect while beginning a hand propagates and leaves `game.hand` alone; the table is not rolled back."""

    class EngineDefect(Exception):
        pass

    def failing_begin_hand(hand: PokerHand, stakes: Stakes) -> None:
        raise EngineDefect

    deck = order(draw_order, (1, 2, 3), button=1)
    queue_decks(deck, deck, deck)  # the failed start, then a start and a next hand
    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})

    with monkeypatch.context() as patch:
        patch.setattr(hand_flow, "begin_hand", failing_begin_hand)
        with pytest.raises(EngineDefect):
            game.start(button_at(1))
    assert game.hand is None

    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    first = game.start(button_at(1))
    fold_out(game)
    with monkeypatch.context() as patch:
        patch.setattr(hand_flow, "begin_hand", failing_begin_hand)
        with pytest.raises(EngineDefect):
            game.next_hand()
    assert game.hand is first


def test_start_passes_through_the_lifecycle_error_for_seated_ready_players_and_stays_unstarted() -> None:
    """Seated READY players with no hand of this game: the lifecycle's own rule rejects, the game stays unstarted."""
    game, table, players = make_game({1: 1000, 2: 1000})
    players[1].status = READY
    before = world(game, table)

    with pytest.raises(GameAlreadyStartedError):
        game.start(button_at(1))

    assert world(game, table) == before and game.hand is None and table.button_seat_number is None
    assert players[2].status is WAITING


# =============================================================================
# CROSS-HAND REJECTIONS AND STATE
# =============================================================================


class ShuffleDefect(Exception):
    pass


def failing_shuffle(deck: Any, *, _rng: Any = None) -> None:
    raise ShuffleDefect


def test_a_failing_shuffle_on_start_restores_the_table_and_the_game_can_still_start(
    monkeypatch: pytest.MonkeyPatch, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=2))
    before = world(game, table)

    with monkeypatch.context() as patch:
        patch.setattr("go_poker.core.deck.Deck.shuffle", failing_shuffle)
        with pytest.raises(ShuffleDefect):
            game.start(button_at(2))

    assert world(game, table) == before and game.hand is None and table.button_seat_number is None
    assert [player.status for player in players.values()] == [WAITING, WAITING, WAITING]

    hand = game.start(button_at(2))

    assert hand is game.hand and table.button_seat_number == 2
    assert [player.status for player in players.values()] == [READY, READY, READY]


def test_a_failing_shuffle_on_next_hand_keeps_the_button_the_hand_and_waiting_players_then_a_retry_succeeds(
    monkeypatch: pytest.MonkeyPatch, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3, 4), button=2))
    first = game.start(button_at(1))
    fold_out(game)
    newcomer = Player("P4", stack=1000)
    table.sit_in(newcomer, 4)
    before = world(game, table)

    with monkeypatch.context() as patch:
        patch.setattr("go_poker.core.deck.Deck.shuffle", failing_shuffle)
        with pytest.raises(ShuffleDefect):
            game.next_hand()

    assert world(game, table) == before and game.hand is first
    assert table.button_seat_number == 1 and newcomer.status is WAITING

    second = game.next_hand()

    assert second is game.hand and table.button_seat_number == 2
    assert [state.seat_number for state in second.players] == [2, 3, 4, 1]
    assert newcomer.status is READY


def test_an_unsettled_hand_outranks_lifecycle_errors_and_status_changes_only_affect_later_hands(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    """Everyone sits out mid-hand: the hand still plays on and pays, next_hand says "in progress" until it is settled,
    then the lifecycle reports that nobody is ready; nothing changes until a player is made READY again."""
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2), button=2))
    first = game.start(button_at(1))
    for player in players.values():
        player.status = SITTING_OUT

    before = world(game, table)
    with pytest.raises(HandInProgressError):
        game.next_hand()
    assert world(game, table) == before

    fold_out(game)  # the hand's own turn order and payout ignore the new statuses
    assert first.settlement is not None and [players[seat].stack for seat in (1, 2, 3)] == [1000, 995, 1005]

    before = world(game, table)
    with pytest.raises(GameNotStartedError):
        game.next_hand()
    assert world(game, table) == before and game.hand is first

    players[1].status = players[2].status = READY
    second = game.next_hand()

    assert [state.seat_number for state in second.players] == [2, 1]  # the button moves on from seat 1
    assert players[3].status is SITTING_OUT

    before = world(game, table)
    with pytest.raises(HandInProgressError):
        game.next_hand()  # a second call never skips the new hand
    assert world(game, table) == before and game.hand is second


@pytest.mark.parametrize("stacks", [{1: 5, 2: 10}, {1: 1000, 2: 1000, 3: 1000}], ids=["blinds_settled", "folded_out"])
def test_a_settled_hand_rejects_game_act_and_start_whatever_is_passed(
    stacks: dict[int, int], queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, _ = make_game(stacks)
    queue_decks(order(draw_order, tuple(stacks), button=1))
    hand = game.start(button_at(1))
    fold_out(game)
    assert hand.settlement is not None
    before = world(game, table)

    for seat, move in [(1, FOLD), (2, CHECK), (99, SHOW), (1, "garbage")]:
        with pytest.raises(HandAlreadySettledError):
            game.act(seat, move)  # type: ignore[arg-type]
    with pytest.raises(GameAlreadyStartedError):
        game.start(button_at(2))

    assert world(game, table) == before and game.hand is hand


def test_three_hands_keep_the_stakes_the_chips_and_every_earlier_hand_intact(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(*[order(draw_order, (1, 2, 3), button=button) for button in (1, 2, 3)])
    hands: list[PokerHand] = []
    snapshots: list[dict[str, Any]] = []

    hand = game.start(button_at(1))
    for button in (1, 2, 3):
        assert hand is game.hand and table.button_seat_number == button
        assert hand.betting is not None and hand.betting.stakes == STAKES
        assert sum(state.street_contribution for state in hand.players) == STAKES.small_blind + STAKES.big_blind
        hands.append(hand)
        fold_out(game)
        snapshots.append(hand_state(hand, with_stacks=False))
        assert sum(player.stack for player in players.values()) == 3000
        if button != 3:
            hand = game.next_hand()

    assert len({id(hand.deck) for hand in hands}) == 3 and len({id(hand.betting) for hand in hands}) == 3
    for hand, snapshot in zip(hands, snapshots, strict=True):
        assert hand_state(hand, with_stacks=False) == snapshot
        assert_settled_hand_rejects_flow(hand)
    assert game.hand is hands[-1]


def test_an_interactive_showdown_settles_and_the_next_hand_follows_conserving_chips(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3), button=2))
    first = game.start(button_at(1))
    check_down_to_showdown(game)
    for seat, decision in [(2, SHOW), (3, MUCK), (1, SHOW)]:
        game.act(seat, decision)
    assert first.settlement is not None
    assert sum(player.stack for player in players.values()) == 3000

    second = game.next_hand()

    assert second is game.hand and table.button_seat_number == 2 and second.settlement is None
    assert (
        sum(player.stack for player in players.values()) + sum(state.street_contribution for state in second.players)
        == 3000
    )


def test_the_public_surface_is_exactly_start_next_hand_act_and_a_read_only_hand() -> None:
    game, _, _ = make_game({1: 1000, 2: 1000})

    assert {name for name in dir(HoldemGame) if not name.startswith("_")} == {"start", "next_hand", "act", "hand"}
    with pytest.raises(AttributeError):
        setattr(game, "hand", None)  # noqa: B010


# =============================================================================
# HAND NUMBERS AND HISTORY
# =============================================================================


def test_hands_are_numbered_consecutively_from_one(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(*[order(draw_order, (1, 2, 3), button=button) for button in (1, 2, 3, 1, 2)])
    numbers = [game.start(button_at(1)).number]
    for _ in range(4):
        fold_out(game)
        numbers.append(game.next_hand().number)
    assert numbers == [1, 2, 3, 4, 5]
    assert game.hand is not None and game.hand.history.number == 5


def test_a_hand_rejected_for_being_in_progress_consumes_no_number(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3), button=2))
    game.start(button_at(1))
    for _ in range(2):
        with pytest.raises(HandInProgressError):
            game.next_hand()
    fold_out(game)
    assert game.next_hand().number == 2


def test_a_hand_rejected_by_the_lifecycle_consumes_no_number(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, table, players = make_game({1: 1000, 2: 10})
    # As in the bust test above, the rejected call still shuffles a deck.
    queue_decks(
        order(draw_order, (1, 2), button=1), order(draw_order, (1, 2), button=1), order(draw_order, (1, 3), button=1)
    )
    game.start(button_at(1))
    game.act(1, CALL)
    assert players[2].stack == 0 and game.hand is not None and game.hand.settlement is not None

    with pytest.raises(InvalidPlayerCount):
        game.next_hand()
    assert game.hand.number == 1

    table.sit_in(Player("P3", stack=1000), 3)
    assert game.next_hand().number == 2


def test_the_game_keeps_no_counter_and_no_past_histories(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3), button=2))
    assert vars(game).keys() == {"_table", "_stakes", "_hand"}
    game.start(button_at(1))
    fold_out(game)
    game.next_hand()
    assert vars(game).keys() == {"_table", "_stakes", "_hand"}


def test_histories_survive_later_hands_by_value(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Callable[[str], list[Card]]
) -> None:
    """Hand 1's history still equals an independent literal copy after hand 2 changes the same Player objects."""
    game, _, players = make_game({1: 1000, 2: 1000, 3: 1000})
    queue_decks(order(draw_order, (1, 2, 3), button=1), order(draw_order, (1, 2, 3), button=2))
    first = game.start(button_at(1))
    first_history = first.history
    expected_started = HandStarted(
        number=1,
        participants=(
            HandParticipant(1, "P1", Position.BTN, Blind.NONE, 1000),
            HandParticipant(2, "P2", Position.SB, Blind.SMALL, 1000),
            HandParticipant(3, "P3", Position.BB, Blind.BIG, 1000),
        ),
    )
    expected_start = (
        expected_started,
        BlindsPosted(STAKES, (BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 10, False))),
        HoleCardsDealt(
            (
                SeatHoleCards(1, tuple(cards("Ah Ad"))),
                SeatHoleCards(2, tuple(cards("Kd Kh"))),
                SeatHoleCards(3, tuple(cards("3s 4s"))),
            )
        ),
    )
    assert first_history == HandHistory(expected_start)

    fold_out(game)
    expected_first = HandHistory(
        (
            *expected_start,
            ActionTaken(1, FOLD, 0, False),
            ActionTaken(2, FOLD, 0, False),
            ChipsReturned(3, 5),
            BettingRoundCompleted(Street.PREFLOP),
        )
    )
    assert first.history == expected_first
    second = game.next_hand()
    game.act(2, FOLD)
    players[3].status = SITTING_OUT

    assert first.history == expected_first
    assert first_history == HandHistory(expected_start)
    assert second.history.events == (
        HandStarted(
            number=2,
            participants=(
                HandParticipant(2, "P2", Position.BTN, Blind.NONE, 995),
                HandParticipant(3, "P3", Position.SB, Blind.SMALL, 1005),
                HandParticipant(1, "P1", Position.BB, Blind.BIG, 1000),
            ),
        ),
        BlindsPosted(STAKES, (BlindPost(3, Blind.SMALL, 5, False), BlindPost(1, Blind.BIG, 10, False))),
        HoleCardsDealt(
            (
                SeatHoleCards(2, tuple(cards("Kd Kh"))),
                SeatHoleCards(3, tuple(cards("3s 4s"))),
                SeatHoleCards(1, tuple(cards("Ah Ad"))),
            )
        ),
        ActionTaken(2, FOLD, 0, False),
    )


def test_rejected_starts_leave_no_hand_and_the_game_that_does_start_is_hand_one() -> None:
    """Every `start` rejection path (too few players, a bad button, a failing chooser) creates no hand and no number."""
    game, table, _ = make_game({1: 1000})
    with pytest.raises(InvalidPlayerCount):
        game.start(button_at(1))
    assert game.hand is None

    table.sit_in(Player("P2", stack=1000), 2)
    with pytest.raises(ButtonSeatNotInHandError):
        game.start(button_at(9))
    assert game.hand is None

    def failing_chooser(_seats: tuple[int, ...]) -> int:
        raise RuntimeError("chooser failed")

    with pytest.raises(RuntimeError):
        game.start(failing_chooser)
    assert game.hand is None

    hand = game.start(button_at(2))
    assert hand.number == hand.history.number == 1
    with pytest.raises(GameAlreadyStartedError):
        game.start(button_at(1))
    assert game.hand is hand and hand.number == 1


def test_next_hand_before_start_and_every_rejection_leave_the_current_number_alone() -> None:
    """A mix of rejected `next_hand` calls between two successful ones never skips or repeats a number."""
    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    with pytest.raises(GameNotStartedError):
        game.next_hand()
    first = game.start(button_at(1))
    for _ in range(3):
        with pytest.raises(HandInProgressError):
            game.next_hand()
        with pytest.raises(GameAlreadyStartedError):
            game.start(button_at(1))
        assert game.hand is first and first.number == 1
    fold_out(game)
    second = game.next_hand()
    with pytest.raises(HandInProgressError):
        game.next_hand()
    fold_out(game)
    third = game.next_hand()
    assert [first.number, second.number, third.number] == [1, 2, 3]
    assert [first.history.number, second.history.number, third.history.number] == [1, 2, 3]


def test_a_next_hand_that_fails_after_the_lifecycle_does_not_replace_the_hand_or_consume_a_number(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If beginning the new hand fails, `game.hand` stays the settled hand, and the retry gets the very next number."""
    game, _, _ = make_game({1: 1000, 2: 1000, 3: 1000})
    first = game.start(button_at(1))
    fold_out(game)
    first_history = first.history
    original_begin = hand_flow.begin_hand

    def failing_begin(_hand: PokerHand, _stakes: Stakes) -> None:
        raise RuntimeError("begin failed")

    monkeypatch.setattr(hand_flow, "begin_hand", failing_begin)
    with pytest.raises(RuntimeError):
        game.next_hand()
    assert game.hand is first and first.number == 1 and first.history == first_history

    monkeypatch.setattr(hand_flow, "begin_hand", original_begin)
    second = game.next_hand()
    assert second.number == 2 and second.history.number == 2
    assert first.history == first_history


def test_every_hand_of_a_long_game_carries_its_own_history(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    """Hand objects kept by the caller each hold their own number and participants after the game has moved on."""
    game, _, players = make_game({1: 1000, 2: 1000, 3: 1000, 4: 1000})
    queue_decks(*[order(draw_order, (1, 2, 3, 4), button=button) for button in (1, 2, 3, 4, 1, 2)])
    hands = [game.start(button_at(1))]
    for _ in range(5):
        fold_out(game)
        hands.append(game.next_hand())
    assert [hand.number for hand in hands] == [1, 2, 3, 4, 5, 6]
    assert [hand.history.participants[0].seat for hand in hands] == [1, 2, 3, 4, 1, 2]  # the button moved each time
    assert len({id(hand.history) for hand in hands}) == 6
    assert [p.starting_stack for p in hands[0].history.participants] == [1000, 1000, 1000, 1000]
    assert sum(p.starting_stack for p in hands[-1].history.participants) == 4000  # chips are only moved around
    # Hand 1: seat 2 posted the small blind and folded, seat 3 won it from the big blind; hand 2 starts from there.
    assert [(p.seat, p.starting_stack) for p in hands[1].history.participants] == [
        (2, 995),
        (3, 1005),
        (4, 1000),
        (1, 1000),
    ]
    for hand in hands:
        assert [p.player_id for p in hand.history.participants] == [
            players[state.seat_number].player_id for state in hand.players
        ]
    players[1].stack = 1
    players[1].status = SITTING_OUT
    assert [p.starting_stack for p in hands[0].history.participants] == [1000, 1000, 1000, 1000]

"""The Hold'em player view: each visibility row, the seats, the turn, and the errors (ADR 0005 §2-4).

Hands are played through the real `HoldemGame` from decks stacked with the shared `queue_decks` and `draw_order`
fixtures. Blinds are 5/10 and the seats are the button (1), the small blind (2) and the big blind (3). Seat 1 holds a
pair of aces, seat 2 a set of kings and seat 3 king high on the board 2c 7d 9h Jc Ks. Preflop the button (seat 1) acts
first; after the flop the small blind acts first, so a check-down decides in the order 2, 3, 1 and the interactive
showdown starts with seat 2. Seat 6 is empty and seat 7 is seated after the hand started (a non-participant).
"""

from collections.abc import Callable, Iterator
from dataclasses import FrozenInstanceError, dataclass, fields, is_dataclass
from typing import Any

import pytest

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.settlement import Settlement
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street
from go_poker.game.table import InvalidSeatNumber, Table
from go_poker.game.variants.texas_holdem.game import HoldemGame
from go_poker.game.variants.texas_holdem.hand_strength import hand_strength
from go_poker.game.variants.texas_holdem.view import (
    HandView,
    HoldemView,
    OccupantStatus,
    OccupantView,
    ParticipantView,
    SeatView,
    Turn,
    TurnKind,
    holdem_view,
)
from go_poker.game.visibility import HandSettledView, settlement_view

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
EMPTY_SEAT = 6
NON_PARTICIPANT_SEAT = 7
VIEWERS = [None, 1, 2, 3, EMPTY_SEAT, NON_PARTICIPANT_SEAT]

type DrawOrder = Callable[..., list[Card]]
type QueueDecks = Callable[..., Any]
type Cards = Callable[[str], list[Card]]
type Play = tuple[int, Action | ShowdownAction]

LIMP: tuple[Play, ...] = ((1, CALL), (2, CALL), (3, CHECK))
STREET_CHECKS: tuple[Play, ...] = ((2, CHECK), (3, CHECK), (1, CHECK))
TO_SHOWDOWN: tuple[Play, ...] = (*LIMP, *STREET_CHECKS, *STREET_CHECKS, *STREET_CHECKS)


@dataclass
class Setup:
    game: HoldemGame
    table: Table

    @property
    def hand(self) -> PokerHand:
        assert self.game.hand is not None
        return self.game.hand

    def play(self, *plays: Play) -> None:
        for seat, action in plays:
            self.game.act(seat, action)

    def view(self, viewer: int | None) -> HandView:
        return _hand_view(self.table, self.game.hand, viewer)


def new_game(queue_decks: QueueDecks, draw_order: DrawOrder, *plays: Play) -> Setup:
    table = Table(9)
    for seat in HOLES:
        table.sit_in(Player(f"P{seat}", stack=1000), seat)
    queue_decks(draw_order(HOLES, BOARD, 1))
    game = HoldemGame(table, STAKES)
    game.start(lambda _seats: 1)
    table.sit_in(Player("LATE", stack=500), NON_PARTICIPANT_SEAT)
    setup = Setup(game, table)
    setup.play(*plays)
    return setup


def _hand_view(table: Table, hand: PokerHand | None, viewer: int | None) -> HandView:
    hand_view = holdem_view(table, hand, viewer).hand
    assert hand_view is not None
    return hand_view


def participant(view: HandView, seat: int) -> ParticipantView:
    return next(entry for entry in view.participants if entry.seat == seat)


def reachable(value: object) -> Iterator[object]:
    """Every value reachable from `value` through dataclass fields and containers."""
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from reachable(getattr(value, field.name))
    elif isinstance(value, tuple | list | set | frozenset):
        for item in value:
            yield from reachable(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from reachable(key)
            yield from reachable(item)


def cards_in(view: HoldemView) -> set[Card]:
    return {item for item in reachable(view) if isinstance(item, Card)}


# =============================================================================
# VISIBILITY MATRIX
# =============================================================================


@pytest.mark.parametrize("viewer", VIEWERS)
def test_each_viewer_sees_only_its_own_hole_cards(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards, viewer: int | None
) -> None:
    setup = new_game(queue_decks, draw_order)

    view = setup.view(viewer)

    assert [entry.seat for entry in view.participants] == [1, 2, 3]
    for entry in view.participants:
        expected = tuple(cards(HOLES[entry.seat])) if entry.seat == viewer else None
        assert entry.hole_cards == expected


@pytest.mark.parametrize("viewer", VIEWERS)
def test_the_board_the_pots_and_the_hand_facts_are_the_same_for_every_viewer(
    queue_decks: QueueDecks, draw_order: DrawOrder, viewer: int | None
) -> None:
    setup = new_game(queue_decks, draw_order, *LIMP)
    hand = setup.hand

    view = setup.view(viewer)

    assert view.board == tuple(hand.board) and len(view.board) == 3
    assert view.pots == pots(hand)
    assert (view.number, view.stakes, view.street) == (1, STAKES, Street.FLOP)
    assert view.turn == Turn(2, TurnKind.BETTING)


def test_a_folded_seat_keeps_its_own_cards_for_its_owner_only(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, (1, FOLD))

    assert participant(setup.view(1), 1).hole_cards == tuple(cards(HOLES[1]))
    for viewer in (None, 2, 3, EMPTY_SEAT, NON_PARTICIPANT_SEAT):
        assert participant(setup.view(viewer), 1).hole_cards is None
    assert participant(setup.view(2), 1).folded


def test_hidden_cards_are_absent_not_masked(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order)

    hidden = participant(setup.view(None), 2)

    assert hidden.hole_cards is None and hidden.strength is None
    assert hidden.has_live_cards


# =============================================================================
# STRENGTH
# =============================================================================


def test_strength_is_none_preflop_even_for_the_owner(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order)

    owner = participant(setup.view(1), 1)

    assert owner.hole_cards is not None and owner.strength is None
    assert owner.strength == hand_strength(setup.hand, 1)


@pytest.mark.parametrize("plays", [LIMP, (*LIMP, *STREET_CHECKS), (*LIMP, *STREET_CHECKS, *STREET_CHECKS)])
def test_strength_from_the_flop_on_equals_the_engines_hand_strength_for_the_owner(
    queue_decks: QueueDecks, draw_order: DrawOrder, plays: tuple[Play, ...]
) -> None:
    setup = new_game(queue_decks, draw_order, *plays)

    for seat in (1, 2, 3):
        strength = participant(setup.view(seat), seat).strength
        assert strength is not None
        assert strength == hand_strength(setup.hand, seat)


def test_an_opponents_strength_is_hidden(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *LIMP)

    for viewer in (None, 1, 3, EMPTY_SEAT, NON_PARTICIPANT_SEAT):
        assert participant(setup.view(viewer), 2).strength is None
        assert participant(setup.view(viewer), 2).hole_cards is None


# =============================================================================
# TURN, LEGAL ACTIONS, SHOWDOWN OPTIONS
# =============================================================================


def test_legal_actions_are_only_in_the_betting_actors_view(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order)
    assert setup.hand.betting is not None and setup.hand.betting.current_actor == 1

    assert setup.view(1).legal_actions == legal_actions(setup.hand)
    assert setup.view(1).legal_actions is not None and setup.view(1).legal_actions.can_raise
    for viewer in (None, 2, 3, EMPTY_SEAT, NON_PARTICIPANT_SEAT):
        assert setup.view(viewer).legal_actions is None
    assert all(setup.view(viewer).showdown_actions is None for viewer in VIEWERS)


def test_a_new_occupant_of_the_actors_seat_gets_no_legal_actions(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order)
    setup.table.stand_up(1)
    setup.table.sit_in(Player("NEW", stack=500), 1)

    view = setup.view(1)

    assert view.legal_actions is None
    assert participant(view, 1).hole_cards is None
    assert view.turn == Turn(1, TurnKind.BETTING)


def test_the_showdown_options_are_only_in_the_current_deciders_view(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN)

    assert setup.view(2).showdown_actions == (SHOW, MUCK)
    assert setup.view(2).legal_actions is None
    for viewer in (None, 1, 3, EMPTY_SEAT, NON_PARTICIPANT_SEAT):
        assert setup.view(viewer).showdown_actions is None
        assert setup.view(viewer).legal_actions is None


def test_the_showdown_options_move_to_the_next_decider(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW))

    assert setup.view(2).showdown_actions is None
    assert setup.view(3).showdown_actions == (SHOW, MUCK)
    assert setup.view(1).showdown_actions is None


def test_the_turn_kind_is_betting_during_betting(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order)

    assert setup.view(None).turn == Turn(1, TurnKind.BETTING)


def test_the_turn_kind_is_showdown_during_the_showdown(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN)

    assert setup.view(None).turn == Turn(2, TurnKind.SHOWDOWN)
    assert setup.view(3).turn == Turn(2, TurnKind.SHOWDOWN)
    assert setup.view(None).showdown == setup.hand.showdown


def test_a_settled_hand_has_no_turn_and_no_actions(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, (1, FOLD), (2, FOLD))

    for viewer in VIEWERS:
        view = setup.view(viewer)
        assert view.turn is None and view.legal_actions is None and view.showdown_actions is None
        assert view.settlement is not None


# =============================================================================
# LIVE CARDS
# =============================================================================


def test_every_participant_has_live_cards_once_dealt(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order)

    assert all(entry.has_live_cards for entry in setup.view(None).participants)


@pytest.mark.parametrize("viewer", VIEWERS)
def test_a_folded_seat_has_no_live_cards_for_any_viewer(
    queue_decks: QueueDecks, draw_order: DrawOrder, viewer: int | None
) -> None:
    setup = new_game(queue_decks, draw_order, (1, FOLD))

    view = setup.view(viewer)

    assert [participant(view, seat).has_live_cards for seat in (1, 2, 3)] == [False, True, True]


@pytest.mark.parametrize("viewer", VIEWERS)
def test_a_mucked_seat_has_no_live_cards_for_any_viewer(
    queue_decks: QueueDecks, draw_order: DrawOrder, viewer: int | None
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, MUCK))

    view = setup.view(viewer)

    assert [participant(view, seat).has_live_cards for seat in (1, 2, 3)] == [True, False, True]
    assert not participant(view, 2).folded


def test_a_participant_without_dealt_cards_has_no_live_cards_and_no_strength(stacked_hand: Callable[..., Any]) -> None:
    table = Table(9)
    hand = stacked_hand(HOLES, BOARD)
    for state in hand.players:
        table.sit_in(Player(state.player.player_id, stack=1000), state.seat_number)
    initialize_betting(hand, STAKES)

    entry = participant(_hand_view(table, hand, 1), 1)

    assert hand.players[0].hole_cards == []
    assert entry.has_live_cards is False
    assert entry.hole_cards == () and entry.strength is None


# =============================================================================
# SEATS AND PARTICIPANTS
# =============================================================================


def test_the_seats_project_every_table_seat_with_stack_and_status(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order)

    seats = holdem_view(setup.table, setup.game.hand, None).seats

    assert [seat.number for seat in seats] == list(range(1, 10))
    assert seats[0] == SeatView(1, OccupantView(stack=1000, status=None))
    assert seats[1] == SeatView(2, OccupantView(stack=995, status=None))
    assert seats[2] == SeatView(3, OccupantView(stack=990, status=None))
    assert seats[EMPTY_SEAT - 1] == SeatView(EMPTY_SEAT, None)
    assert seats[NON_PARTICIPANT_SEAT - 1] == SeatView(
        NON_PARTICIPANT_SEAT, OccupantView(stack=500, status=OccupantStatus.WAITING_TO_JOIN)
    )


def test_a_ready_occupant_has_no_status() -> None:
    table = Table(6)
    table.sit_in(Player("A", stack=100, status=PlayerStatus.READY), 2)

    assert holdem_view(table, None, None).seats[1].occupant == OccupantView(100, None)


def test_a_waiting_occupant_is_waiting_to_join() -> None:
    table = Table(6)
    table.sit_in(Player("A", stack=100, status=PlayerStatus.WAITING), 2)

    occupant = holdem_view(table, None, None).seats[1].occupant

    assert occupant is not None and occupant.status is OccupantStatus.WAITING_TO_JOIN


def test_a_sitting_out_occupant_is_sitting_out() -> None:
    table = Table(6)
    table.sit_in(Player("A", stack=100, status=PlayerStatus.SITTING_OUT), 2)

    occupant = holdem_view(table, None, None).seats[1].occupant

    assert occupant is not None and occupant.status is OccupantStatus.SITTING_OUT


def test_the_occupant_statuses_are_exactly_the_user_relevant_ones() -> None:
    assert {status.name for status in OccupantStatus} == {"WAITING_TO_JOIN", "SITTING_OUT"}


def test_no_engine_player_status_is_reachable_from_any_view() -> None:
    table = Table(6)
    for seat, status in enumerate(PlayerStatus, start=1):
        table.sit_in(Player(f"P{seat}", stack=100, status=status), seat)
    view = holdem_view(table, None, None)

    assert [seat.occupant.status for seat in view.seats[:3] if seat.occupant] == [
        None,
        OccupantStatus.WAITING_TO_JOIN,
        OccupantStatus.SITTING_OUT,
    ]
    assert not any(isinstance(item, PlayerStatus) for item in reachable(view))


def test_the_seats_are_the_same_for_every_viewer(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order)

    assert {holdem_view(setup.table, setup.game.hand, viewer).seats for viewer in VIEWERS} == {
        holdem_view(setup.table, setup.game.hand, None).seats
    }


def test_the_participants_join_the_seats_in_hand_order_with_public_betting_facts(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order)
    seats = {seat.number: seat for seat in holdem_view(setup.table, setup.game.hand, None).seats}

    participants = setup.view(None).participants

    assert [(entry.seat, entry.position, entry.blind, entry.in_front) for entry in participants] == [
        (1, Position.BTN, Blind.NONE, 0),
        (2, Position.SB, Blind.SMALL, 5),
        (3, Position.BB, Blind.BIG, 10),
    ]
    assert all(seats[entry.seat].occupant is not None for entry in participants)
    assert not any(entry.folded or entry.all_in for entry in participants)


def test_the_participants_follow_the_button_first_hand_order(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    table = Table(9)
    for seat in HOLES:
        table.sit_in(Player(f"P{seat}", stack=1000), seat)
    queue_decks(draw_order(HOLES, BOARD, 2))
    game = HoldemGame(table, STAKES)
    game.start(lambda _seats: 2)

    view = holdem_view(table, game.hand, None).hand

    assert view is not None and [entry.seat for entry in view.participants] == [2, 3, 1]


def test_chips_in_front_all_in_and_folded_follow_the_hand(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, (1, Action(ActionType.RAISE, 1000)), (2, FOLD))

    view = setup.view(None)

    assert [(entry.seat, entry.in_front, entry.folded, entry.all_in) for entry in view.participants] == [
        (1, 1000, False, True),
        (2, 5, True, False),  # a folded blind keeps its chips in front until the round is collected
        (3, 10, False, False),
    ]


# =============================================================================
# NO HAND, ERRORS
# =============================================================================


def test_without_a_hand_the_view_has_the_seats_only() -> None:
    table = Table(6)
    table.sit_in(Player("A", stack=100), 2)

    view = holdem_view(table, None, 2)

    assert view == HoldemView(
        seats=tuple(
            SeatView(number, OccupantView(100, OccupantStatus.WAITING_TO_JOIN) if number == 2 else None)
            for number in range(1, 7)
        ),
        hand=None,
    )
    assert holdem_view(table, None, None) == view


@pytest.mark.parametrize("seat", [0, 10, -1])
def test_a_viewer_seat_outside_the_table_is_rejected_with_or_without_a_hand(
    queue_decks: QueueDecks, draw_order: DrawOrder, seat: int
) -> None:
    setup = new_game(queue_decks, draw_order)

    with pytest.raises(InvalidSeatNumber):
        holdem_view(setup.table, None, seat)
    with pytest.raises(InvalidSeatNumber):
        holdem_view(setup.table, setup.game.hand, seat)


def test_a_hand_without_betting_is_rejected_for_every_viewer(stacked_hand: Callable[..., Any]) -> None:
    table = Table(9)
    hand = stacked_hand(HOLES, BOARD)
    assert hand.betting is None

    for viewer in (None, 1, EMPTY_SEAT):
        with pytest.raises(BettingNotInitializedError):
            holdem_view(table, hand, viewer)


def test_a_bad_viewer_seat_is_reported_before_an_uninitialized_hand(stacked_hand: Callable[..., Any]) -> None:
    with pytest.raises(InvalidSeatNumber):
        holdem_view(Table(9), stacked_hand(HOLES, BOARD), 12)


# =============================================================================
# SETTLED HAND AND A RE-OCCUPIED SEAT
# =============================================================================


def test_a_settled_hand_stays_projected_with_its_settlement_in_the_view_and_the_log(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order, (1, FOLD), (2, FOLD))
    assert setup.hand.settlement is not None

    view = setup.view(None)

    assert view.settlement == settlement_view(setup.hand.settlement)
    assert isinstance(view.log[-1], HandSettledView) and view.log[-1].settlement == view.settlement
    assert not any(isinstance(item, Settlement) for item in reachable(view))


def test_a_new_occupant_of_a_participant_seat_sees_the_public_view_of_the_settled_hand(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, (1, FOLD), (2, FOLD))
    setup.table.stand_up(3)
    setup.table.sit_in(Player("NEW", stack=700), 3)

    newcomer = holdem_view(setup.table, setup.game.hand, 3)
    public = holdem_view(setup.table, setup.game.hand, None)

    assert newcomer == public
    assert newcomer.seats[2] == SeatView(3, OccupantView(700, OccupantStatus.WAITING_TO_JOIN))
    assert holdem_view(setup.table, setup.game.hand, 2).hand is not None
    assert participant(setup.view(2), 2).hole_cards == tuple(cards(HOLES[2]))


# =============================================================================
# LEAKS, STRUCTURE
# =============================================================================


@pytest.mark.parametrize("viewer", VIEWERS)
@pytest.mark.parametrize("street_plays", [(), LIMP, (*LIMP, *STREET_CHECKS), TO_SHOWDOWN])
def test_burned_cards_the_deck_and_other_hole_cards_are_in_no_view(
    queue_decks: QueueDecks,
    draw_order: DrawOrder,
    cards: Cards,
    street_plays: tuple[Play, ...],
    viewer: int | None,
) -> None:
    setup = new_game(queue_decks, draw_order, *street_plays)
    hand = setup.hand
    allowed = set(hand.board) | (set(cards(HOLES[viewer])) if viewer in HOLES else set())

    found = cards_in(holdem_view(setup.table, hand, viewer))

    assert (
        found <= allowed
    )  # nothing outside the board and the viewer's own cards: no burned card, deck card or other hole
    assert not found & set(hand.burned_cards)


def test_a_view_holds_no_player_id_and_no_engine_object(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW))
    forbidden = (Table, Player, PokerHand, HandPlayerState)

    for viewer in VIEWERS:
        items = list(reachable(holdem_view(setup.table, setup.hand, viewer)))
        assert not any(isinstance(item, forbidden) for item in items)
        assert not any(isinstance(item, PlayerStatus) for item in items)
        assert not {item for item in items if isinstance(item, str)} & {"P1", "P2", "P3", "LATE"}
        assert not any(type(item).__name__ in {"Deck", "BettingState", "HandHistory", "Seat"} for item in items)


def test_every_view_value_is_frozen_and_every_collection_is_immutable(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW))

    for viewer in (None, 2, 3):
        for item in reachable(holdem_view(setup.table, setup.hand, viewer)):
            assert not isinstance(item, list | dict | set | bytearray)
            if is_dataclass(item) and not isinstance(item, type):
                first_field = fields(item)[0].name
                with pytest.raises(FrozenInstanceError):
                    setattr(item, first_field, None)


def test_the_view_fields_exclude_the_button_the_middle_pot_and_the_betting_internals() -> None:
    assert {field.name for field in fields(HoldemView)} == {"seats", "hand"}
    assert {field.name for field in fields(HandView)} == {
        "number",
        "stakes",
        "street",
        "board",
        "participants",
        "pots",
        "turn",
        "legal_actions",
        "showdown_actions",
        "showdown",
        "settlement",
        "log",
    }
    assert {field.name for field in fields(ParticipantView)} == {
        "seat",
        "position",
        "blind",
        "in_front",
        "folded",
        "all_in",
        "has_live_cards",
        "hole_cards",
        "strength",
    }
    assert {field.name for field in fields(OccupantView)} == {"stack", "status"}


def test_a_view_is_a_snapshot_that_later_play_does_not_change(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *LIMP)
    before = holdem_view(setup.table, setup.hand, 2)
    copy_of_before = holdem_view(setup.table, setup.hand, 2)

    setup.play((2, CHECK))

    assert before == copy_of_before
    assert before != holdem_view(setup.table, setup.hand, 2)
    assert before.hand is not None and before.hand.board == tuple(setup.hand.board)
    assert before.hand.board is not setup.hand.board


def test_projecting_a_view_changes_nothing(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW))
    hand = setup.hand

    def state() -> tuple[object, ...]:
        return (
            hand.street,
            list(hand.board),
            list(hand.burned_cards),
            len(hand.deck),
            hand.history,
            hand.showdown,
            hand.settlement,
            [
                (s.folded, s.all_in, s.street_contribution, s.total_contribution, list(s.hole_cards))
                for s in hand.players
            ],
            [
                (seat.number, seat.player and (seat.player.stack, seat.player.status))
                for seat in setup.table.occupied_seats
            ],
            setup.table.button_seat_number,
        )

    before = state()
    for viewer in VIEWERS:
        holdem_view(setup.table, hand, viewer)

    assert state() == before

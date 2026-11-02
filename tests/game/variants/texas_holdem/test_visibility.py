"""The variant-agnostic visibility rule and the redacted hand log (ADR 0005 §2-5).

Hands are played through the real `HoldemGame` from decks stacked with the shared `queue_decks` and `draw_order`
fixtures. Blinds are 5/10 and the seats are the button (1), the small blind (2) and the big blind (3). Seat 1 holds a
pair of aces, seat 2 a set of kings and seat 3 king high on the board 2c 7d 9h Jc Ks.

`INTERACTIVE_HAND` is a three-way hand that ends in an interactive showdown: seat 2 shows, seat 3 mucks. `ALL_IN_HAND`
has seat 3 all-in on the flop against a bigger bet, so it holds the returned chips and an `ALL_IN` showdown.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

import pytest

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.pots import Pot
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindPost,
    BlindsPosted,
    ChipsReturned,
    HandEvent,
    HandHistory,
    HandParticipant,
    HandSettled,
    HandStarted,
    HoleCardsDealt,
    SeatHoleCards,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.player import Player
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import PotAward, Settlement
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.table import InvalidSeatNumber, Table
from go_poker.game.variants.texas_holdem.game import HoldemGame
from go_poker.game.visibility import (
    ActionTakenView,
    BettingRoundCompletedView,
    BettingRoundStartedView,
    BlindsPostedView,
    ChipsReturnedView,
    HandSettledView,
    HandStartedView,
    HoleCardsDealtView,
    PotAwardView,
    SettlementView,
    ShowdownDecidedView,
    ShowdownStartedView,
    StreetDealtView,
    project_event,
    project_log,
    settlement_view,
    viewer_participant_seat,
    visible_hole_card_seats,
)

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"

type DrawOrder = Callable[..., list[Card]]
type QueueDecks = Callable[..., Any]
type Play = tuple[int, Action | ShowdownAction]

# Preflop everyone limps, the flop is bet, raised and folded to the raiser's caller, then it checks down.
INTERACTIVE_PLAYS: tuple[Play, ...] = (
    (1, CALL),
    (2, CALL),
    (3, CHECK),
    (2, Action(ActionType.BET, 20)),
    (3, Action(ActionType.RAISE, 60)),
    (1, FOLD),
    (2, CALL),
    (2, CHECK),
    (3, CHECK),
    (2, CHECK),
    (3, CHECK),
    (2, SHOW),
    (3, MUCK),
)
# Preflop everyone limps; on the flop seat 2 bets 200, seat 3 (90 behind) calls all-in and seat 1 folds.
ALL_IN_PLAYS: tuple[Play, ...] = (
    (1, CALL),
    (2, CALL),
    (3, CHECK),
    (2, Action(ActionType.BET, 200)),
    (3, CALL),
    (1, FOLD),
)


@dataclass(frozen=True)
class Scenario:
    plays: tuple[Play, ...]
    stacks: dict[int, int] | None = None


INTERACTIVE_HAND = Scenario(INTERACTIVE_PLAYS)
ALL_IN_HAND = Scenario(ALL_IN_PLAYS, {3: 100})


def build_game(stacks: dict[int, int] | None = None) -> tuple[HoldemGame, Table]:
    table = Table(9)
    for seat in HOLES:
        table.sit_in(Player(f"P{seat}", stack=(stacks or {}).get(seat, 1000)), seat)
    return HoldemGame(table, STAKES), table


def new_game(
    queue_decks: QueueDecks, draw_order: DrawOrder, stacks: dict[int, int] | None = None
) -> tuple[HoldemGame, Table]:
    queue_decks(draw_order(HOLES, BOARD, 1))
    game, table = build_game(stacks)
    game.start(lambda _seats: 1)
    return game, table


def played(queue_decks: QueueDecks, draw_order: DrawOrder, scenario: Scenario) -> tuple[HoldemGame, Table]:
    game, table = new_game(queue_decks, draw_order, scenario.stacks)
    for seat, action in scenario.plays:
        game.act(seat, action)
    return game, table


def settled_hand(hand: PokerHand | None) -> PokerHand:
    assert hand is not None and hand.settlement is not None
    return hand


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


# =============================================================================
# VIEWER RESOLUTION
# =============================================================================


def test_a_viewer_resolves_to_its_own_participant_seat(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None

    assert [viewer_participant_seat(table, game.hand, seat) for seat in (1, 2, 3)] == [1, 2, 3]


def test_the_public_viewer_has_no_participant_seat(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None

    assert viewer_participant_seat(table, game.hand, None) is None


def test_an_empty_seat_has_no_participant_seat(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None

    assert viewer_participant_seat(table, game.hand, 6) is None


def test_a_seated_non_participant_has_no_participant_seat(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None
    table.sit_in(Player("LATE", stack=500), 6)

    assert viewer_participant_seat(table, game.hand, 6) is None


def test_a_new_occupant_of_a_participant_seat_after_settlement_has_no_participant_seat(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table = played(queue_decks, draw_order, Scenario(((1, FOLD), (2, FOLD))))
    hand = settled_hand(game.hand)
    table.stand_up(2)
    table.sit_in(Player("NEW", stack=500), 2)

    assert viewer_participant_seat(table, hand, 2) is None
    assert viewer_participant_seat(table, hand, 3) == 3


def test_viewers_are_matched_by_player_id_not_by_object_identity(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None
    table.stand_up(2)
    table.sit_in(Player("P2", stack=1), 2)  # a different object, the same logical participant

    assert viewer_participant_seat(table, game.hand, 2) == 2


def test_a_participant_who_moved_seats_has_no_participant_seat_at_either(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None
    moved = table.get_seat(2).player
    assert moved is not None
    table.stand_up(2)
    table.sit_in(moved, 6)

    assert viewer_participant_seat(table, game.hand, 2) is None
    assert viewer_participant_seat(table, game.hand, 6) is None


@pytest.mark.parametrize("seat", [0, 10, -1])
def test_a_viewer_seat_outside_the_table_is_rejected(queue_decks: QueueDecks, draw_order: DrawOrder, seat: int) -> None:
    game, table = new_game(queue_decks, draw_order)
    assert game.hand is not None

    with pytest.raises(InvalidSeatNumber):
        viewer_participant_seat(table, game.hand, seat)


# =============================================================================
# VISIBLE SEATS
# =============================================================================


def test_without_a_showdown_a_viewer_sees_only_its_own_seat(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _ = new_game(queue_decks, draw_order)
    assert game.hand is not None and game.hand.showdown is None

    assert visible_hole_card_seats(game.hand, None) == frozenset()
    assert visible_hole_card_seats(game.hand, 2) == frozenset({2})


def test_visible_seats_add_the_shown_seats_of_an_interactive_showdown(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _ = new_game(queue_decks, draw_order)
    hand = game.hand
    assert hand is not None
    hand.showdown = Showdown(ShowdownKind.INTERACTIVE, (2, 3, 1), (SHOW, MUCK))

    assert visible_hole_card_seats(hand, None) == frozenset({2})
    assert visible_hole_card_seats(hand, 3) == frozenset({2, 3})  # own muck stays visible to its owner
    assert visible_hole_card_seats(hand, 2) == frozenset({2})


def test_visible_seats_include_every_live_seat_of_an_all_in_showdown(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _ = new_game(queue_decks, draw_order)
    hand = game.hand
    assert hand is not None
    hand.showdown = Showdown(ShowdownKind.ALL_IN, (2, 3))

    assert visible_hole_card_seats(hand, None) == frozenset({2, 3})
    assert visible_hole_card_seats(hand, 1) == frozenset({1, 2, 3})  # the folded owner keeps its own cards


def test_visible_seats_are_an_immutable_set(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _ = new_game(queue_decks, draw_order)
    assert game.hand is not None

    assert isinstance(visible_hole_card_seats(game.hand, 1), frozenset)


# =============================================================================
# EVENT PROJECTION
# =============================================================================


def test_hole_cards_dealt_carries_only_the_viewers_own_cards(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Callable[[str], list[Card]]
) -> None:
    game, _ = new_game(queue_decks, draw_order)
    assert game.hand is not None
    event = next(event for event in game.hand.history.events if isinstance(event, HoleCardsDealt))

    own = project_event(event, 1)
    opponent = project_event(event, 2)

    assert own == HoleCardsDealtView(own_cards=tuple(cards(HOLES[1])))
    assert opponent == HoleCardsDealtView(own_cards=tuple(cards(HOLES[2])))
    assert {card for card in reachable(own) if isinstance(card, Card)} == set(cards(HOLES[1]))


@pytest.mark.parametrize("participant_seat", [None, 6])
def test_hole_cards_dealt_carries_no_cards_for_the_public_or_a_non_participant(
    queue_decks: QueueDecks, draw_order: DrawOrder, participant_seat: int | None
) -> None:
    game, _ = new_game(queue_decks, draw_order)
    assert game.hand is not None
    event = next(event for event in game.hand.history.events if isinstance(event, HoleCardsDealt))

    view = project_event(event, participant_seat)

    assert view == HoleCardsDealtView(own_cards=None)
    assert not any(isinstance(card, Card) for card in reachable(view))


def test_street_dealt_drops_the_burned_cards(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _ = played(queue_decks, draw_order, INTERACTIVE_HAND)
    hand = settled_hand(game.hand)
    streets = [event for event in hand.history.events if isinstance(event, StreetDealt)]
    assert len(streets) == 3 and all(event.burned for event in streets)

    for event in streets:
        view = project_event(event, 1)
        assert view == StreetDealtView(street=event.street, cards=event.cards)
        assert "burned" not in {field.name for field in fields(StreetDealtView)}
        assert not set(event.burned) & {card for card in reachable(view) if isinstance(card, Card)}


def test_hand_started_drops_every_player_id(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _ = new_game(queue_decks, draw_order)
    assert game.hand is not None
    event = game.hand.history.events[0]
    assert isinstance(event, HandStarted)

    view = project_event(event, None)

    assert isinstance(view, HandStartedView)
    assert view.number == event.number
    assert [
        (participant.seat, participant.position, participant.blind, participant.starting_stack)
        for participant in view.participants
    ] == [
        (participant.seat, participant.position, participant.blind, participant.starting_stack)
        for participant in event.participants
    ]
    assert not any(isinstance(item, HandParticipant) for item in reachable(view))
    assert not {item for item in reachable(view) if isinstance(item, str)} & {"P1", "P2", "P3"}
    assert all("player_id" not in {field.name for field in fields(item)} for item in view.participants)


def test_hand_settled_projects_the_settlement_through_the_settlement_view(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _ = played(queue_decks, draw_order, INTERACTIVE_HAND)
    hand = settled_hand(game.hand)
    event = hand.history.events[-1]
    assert isinstance(event, HandSettled)

    view = project_event(event, None)

    assert hand.settlement is not None
    assert view == HandSettledView(settlement=settlement_view(hand.settlement))
    assert not any(isinstance(item, Settlement | PotAward) for item in reachable(view))


def test_settlement_view_is_built_field_by_field_from_tuples(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _ = played(queue_decks, draw_order, INTERACTIVE_HAND)
    settlement = settled_hand(game.hand).settlement
    assert settlement is not None

    view = settlement_view(settlement)

    assert isinstance(view, SettlementView)
    assert view.pot_awards == tuple(PotAwardView(award.pot, award.shares) for award in settlement.pot_awards)
    assert view.showdown_ranks == settlement.showdown_ranks != ()
    assert all(isinstance(award.pot, Pot) and isinstance(award.shares, tuple) for award in view.pot_awards)


def test_every_public_event_projects_to_values_equal_to_its_source_fields(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    """Counter test: the events whose facts are all public project to views with exactly their fields' values."""
    direct = {
        BettingRoundStarted: BettingRoundStartedView,
        ActionTaken: ActionTakenView,
        ChipsReturned: ChipsReturnedView,
        BettingRoundCompleted: BettingRoundCompletedView,
        ShowdownStarted: ShowdownStartedView,
        ShowdownDecided: ShowdownDecidedView,
    }
    counted: set[type] = set()
    scenarios = (INTERACTIVE_HAND, ALL_IN_HAND)
    queue_decks(*(draw_order(HOLES, BOARD, 1) for _ in scenarios))
    for scenario in scenarios:
        game, _ = build_game(scenario.stacks)
        game.start(lambda _seats: 1)
        for seat, action in scenario.plays:
            game.act(seat, action)
        assert game.hand is not None
        for event in game.hand.history.events:
            if type(event) not in direct:
                continue
            view = project_event(event, 1)
            assert type(view) is direct[type(event)]
            assert [field.name for field in fields(view)] == [field.name for field in fields(event)]
            for field in fields(event):
                assert getattr(view, field.name) == getattr(event, field.name)
            counted.add(type(event))

    assert counted == set(direct)


def test_blinds_posted_projects_the_stakes_and_each_post(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    game, _ = new_game(queue_decks, draw_order)
    assert game.hand is not None
    event = next(event for event in game.hand.history.events if isinstance(event, BlindsPosted))

    view = project_event(event, None)

    assert isinstance(view, BlindsPostedView)
    assert view.stakes == event.stakes
    assert [(post.seat, post.blind, post.chips, post.all_in) for post in view.posts] == [
        (post.seat, post.blind, post.chips, post.all_in) for post in event.posts
    ]
    assert not any(isinstance(item, BlindPost) for item in reachable(view))


def test_an_unclassified_event_is_rejected() -> None:
    with pytest.raises(AssertionError):
        project_event(object(), None)  # type: ignore[arg-type]


# =============================================================================
# LOG PROJECTION
# =============================================================================


@pytest.mark.parametrize("viewer", [None, 1, 2, 3, 6])
@pytest.mark.parametrize("scenario", [INTERACTIVE_HAND, ALL_IN_HAND])
def test_the_log_keeps_one_projected_event_per_event_in_order(
    queue_decks: QueueDecks, draw_order: DrawOrder, scenario: Scenario, viewer: int | None
) -> None:
    game, _ = played(queue_decks, draw_order, scenario)
    assert game.hand is not None
    history = game.hand.history

    log = project_log(history, viewer)

    assert [type(view).__name__ for view in log] == [f"{type(event).__name__}View" for event in history.events]
    assert log == tuple(project_event(event, viewer) for event in history.events)


def test_the_log_is_a_tuple_and_projecting_does_not_change_the_history(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _ = played(queue_decks, draw_order, INTERACTIVE_HAND)
    assert game.hand is not None
    history = game.hand.history

    log = project_log(history, 2)

    assert isinstance(log, tuple)
    assert history == game.hand.history and history.is_complete


@pytest.mark.parametrize("viewer", [None, 1, 2, 3, 6])
@pytest.mark.parametrize("scenario", [INTERACTIVE_HAND, ALL_IN_HAND])
def test_no_authoritative_history_value_is_reachable_from_the_log(
    queue_decks: QueueDecks, draw_order: DrawOrder, scenario: Scenario, viewer: int | None
) -> None:
    game, _ = played(queue_decks, draw_order, scenario)
    assert game.hand is not None
    authoritative = (HandHistory, HandParticipant, BlindPost, SeatHoleCards, Settlement, PotAward)

    log = project_log(game.hand.history, viewer)

    for item in reachable(log):
        assert not isinstance(item, authoritative)
        assert not any(isinstance(item, event_type) for event_type in HandEvent.__value__.__args__)


@pytest.mark.parametrize("scenario", [INTERACTIVE_HAND, ALL_IN_HAND])
def test_the_public_log_never_carries_a_hole_card_or_a_burned_card(
    queue_decks: QueueDecks, draw_order: DrawOrder, scenario: Scenario
) -> None:
    """Shown cards are not added to the log either: a showdown's hole cards are not in any event."""
    game, _ = played(queue_decks, draw_order, scenario)
    hand = settled_hand(game.hand)
    assert hand.showdown is not None and hand.showdown.shown

    in_log = {item for item in reachable(project_log(hand.history, None)) if isinstance(item, Card)}

    assert in_log == set(hand.board)
    assert not in_log & set(hand.burned_cards)


def test_a_viewers_log_holds_its_own_cards_and_the_board_only(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Callable[[str], list[Card]]
) -> None:
    game, _ = played(queue_decks, draw_order, INTERACTIVE_HAND)
    hand = settled_hand(game.hand)

    in_log = {item for item in reachable(project_log(hand.history, 3)) if isinstance(item, Card)}

    assert in_log == set(hand.board) | set(cards(HOLES[3]))


def test_the_returned_chips_and_the_all_in_showdown_are_in_the_log(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    game, _ = played(queue_decks, draw_order, ALL_IN_HAND)
    hand = settled_hand(game.hand)

    log = project_log(hand.history, None)

    assert ChipsReturnedView(seat=2, chips=110) in log
    assert any(isinstance(view, ShowdownStartedView) and view.kind is ShowdownKind.ALL_IN for view in log)
    assert hand.street is Street.RIVER

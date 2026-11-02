"""Seeded whole games checked, at every state and for every viewer, against an independent visibility oracle.

The safety invariant under test: no card, and no rank derived from hidden cards, appears in a viewer's `holdem_view`
unless ADR 0004 or ADR 0005 makes it visible to that specific viewer at that moment.

The games are driven only through `HoldemGame.start`, `act` and `next_hand` with random legal betting, random SHOW/MUCK
and table churn between hands. The churn includes a solvent participant who sits out (so a sitting-out seat is checked,
also in the next hand) and the re-occupied-seat window: a participant of the settled hand stands up and a new player (a
new `player_id`) sits at that seat before `next_hand`; also a participant who comes back with the same `player_id`, and
one who moves seat. After every successful `start`, `act`, `next_hand` and churn step,
`holdem_view` is built for the public viewer and for every seat `1..max_seats` and checked.

The oracle reads nothing from `game/visibility.py` (no viewer rule, no projection function), nor `Showdown.shown` or
`Showdown.mucked`. It works from the hand's history alone:

- the shown seats are every seat of `ShowdownStarted.order` when its kind is `ALL_IN`, plus the seat of each
  `ShowdownDecided(SHOW)`;
- the own seat of viewer V is the hand's participant at V whose `player_id` (from `HandStarted`) is the id of the
  table's current occupant of V;
- permitted(V) is the board plus the hole cards of the own seat and of the shown seats, all read from the events.

A structural walker reaches every value in a view through dataclass fields, tuples and frozensets only, and fails on a
list, dict, set, string, the engine `PlayerStatus` or any object that is not an expected frozen view or leaf value. A
view is then checked for:

- safety: the Cards reached are exactly permitted(V), so no burned or undealt card is reachable and nothing visible is
  missing (an empty view fails); every `BestHand` and `HandRank` belongs to a visible seat and equals the rank evaluated
  independently from the cards;
- completeness: the visible hole cards and `HoleCardsDealtView.own_cards` are exactly the oracle's;
- no `player_id`: any string is a failure;
- the checkpoint: with its private fields stripped (own cards and strength unless shown, legal actions, showdown actions
  and `HoleCardsDealtView.own_cards`), a participant's view equals the public view, and a viewer without private facts
  gets exactly the public view;
- legal actions exactly for the betting actor's own viewer, equal to `legal_actions(hand)`; showdown actions exactly for
  the decider's own viewer;
- the public hand facts, the log and the settlement against the hand and its history.

Views are also kept and must not change by later play, churn or a rejected operation. The seeds are fixed, a failure
names its seed, and the counters keep the seed set honest. The oracle checker is itself checked on tampered views.
"""

import random
from collections import Counter
from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from functools import cache
from typing import Any

import pytest

from go_poker.core.best_hand import BestHand
from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandRank
from go_poker.game import visibility as visibility_module
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import NotPlayersTurnError, apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.pots import Pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindsPosted,
    ChipsReturned,
    HandEvent,
    HandSettled,
    HandStarted,
    HoleCardsDealt,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import InvalidPlayerCount
from go_poker.game.settlement import Settlement
from go_poker.game.showdown import NotShowdownTurnError, Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.table import InvalidSeatNumber, Table
from go_poker.game.variants.texas_holdem import view as view_module
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.game import HoldemGame
from go_poker.game.variants.texas_holdem.hand_flow import current_actor
from go_poker.game.variants.texas_holdem.showdown import settle_hand, start_showdown
from go_poker.game.variants.texas_holdem.view import (
    HandView,
    HoldemView,
    OccupantStatus,
    OccupantView,
    SeatView,
    Turn,
    TurnKind,
    holdem_view,
)
from go_poker.game.visibility import (
    ActionTakenView,
    BettingRoundCompletedView,
    BettingRoundStartedView,
    BlindPostView,
    BlindsPostedView,
    ChipsReturnedView,
    HandParticipantView,
    HandSettledView,
    HandStartedView,
    HoleCardsDealtView,
    PotAwardView,
    SettlementView,
    ShowdownDecidedView,
    ShowdownStartedView,
    StreetDealtView,
)

STAKES = Stakes(small_blind=5, big_blind=10)
SEEDS = range(30)
MAX_HANDS = 12
MAX_STEPS = 300  # far more calls than any generated hand needs
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
READY = PlayerStatus.READY
WAITING = PlayerStatus.WAITING
SITTING_OUT = PlayerStatus.SITTING_OUT
# The oracle's own statement of the seat status contract: only exceptional states are shown, a ready player has none.
EXPECTED_OCCUPANT_STATUS: dict[PlayerStatus, OccupantStatus | None] = {
    READY: None,
    WAITING: OccupantStatus.WAITING_TO_JOIN,
    SITTING_OUT: OccupantStatus.SITTING_OUT,
}
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

# =============================================================================
# THE ORACLE
# =============================================================================


@cache
def rank_of(cards: tuple[Card, ...]) -> HandRank:
    """The independent evaluation of seven cards, cached because every viewer's view repeats it."""
    return evaluate_best(cards)


def _module_dataclasses(module: Any) -> set[type]:
    return {
        value
        for value in vars(module).values()
        if isinstance(value, type) and is_dataclass(value) and value.__module__ == module.__name__
    }


# Frozen values a view may reach: the view and projection values, and the safe engine leaves the contract reuses.
ALLOWED_TYPES: frozenset[type] = frozenset(
    _module_dataclasses(view_module)
    | _module_dataclasses(visibility_module)
    | {Card, HandRank, BestHand, LegalActions, Pot, Showdown, Stakes, Action}
)


@dataclass
class Reached:
    """Everything a walk of one view reached."""

    cards: dict[Card, str]
    best_hands: list[BestHand]
    ranks: list[HandRank]


def walk(value: object, path: str, reached: Reached) -> None:
    """Visit every value through dataclass fields, tuples and frozensets only; fail on anything else."""
    if isinstance(value, PlayerStatus):
        raise AssertionError(f"{path}: the engine PlayerStatus is reachable ({value})")
    if value is None or isinstance(value, bool | int | Enum):
        return
    if isinstance(value, str):
        raise AssertionError(f"{path}: a string is reachable ({value!r}), possibly a player_id")
    kind = type(value)
    if kind is tuple or kind is frozenset:
        assert isinstance(value, tuple | frozenset)
        for index, item in enumerate(value):
            walk(item, f"{path}[{index}]", reached)
        return
    if kind in ALLOWED_TYPES:
        params = kind.__dataclass_params__
        assert is_dataclass(value) and params.frozen, f"{path}: {kind.__name__} is not frozen"
        if isinstance(value, Card):
            reached.cards.setdefault(value, path)
            return
        if isinstance(value, BestHand):
            reached.best_hands.append(value)
        if isinstance(value, HandRank):
            reached.ranks.append(value)
        for field in fields(value):
            walk(getattr(value, field.name), f"{path}.{field.name}", reached)
        return
    raise AssertionError(f"{path}: {kind.__name__} is reachable from a view")


@dataclass(frozen=True)
class Facts:
    """What the hand's history says, the only source the oracle reads about cards and showdown."""

    started: HandStarted
    events: tuple[HandEvent, ...]
    hole: dict[int, tuple[Card, ...]]
    board: tuple[Card, ...]
    burned: tuple[Card, ...]
    shown: frozenset[int]
    mucked: frozenset[int]


def facts_of(hand: PokerHand) -> Facts:
    events = hand.history.events
    first = events[0]
    assert isinstance(first, HandStarted)
    hole: dict[int, tuple[Card, ...]] = {}
    board: list[Card] = []
    burned: list[Card] = []
    shown: set[int] = set()
    mucked: set[int] = set()
    for event in events:
        if isinstance(event, HoleCardsDealt):
            hole = {dealt.seat: tuple(dealt.cards) for dealt in event.hole_cards}
        elif isinstance(event, StreetDealt):
            board.extend(event.cards)
            burned.extend(event.burned)
        elif isinstance(event, ShowdownStarted) and event.kind is ShowdownKind.ALL_IN:
            shown.update(event.order)
        elif isinstance(event, ShowdownDecided):
            (shown if event.action is SHOW else mucked).add(event.seat)
    return Facts(first, events, hole, tuple(board), tuple(burned), frozenset(shown), frozenset(mucked))


def own_seat(table: Table, facts: Facts, viewer: int | None) -> int | None:
    """The viewer seat if the hand's participant there has the id of the seat's current occupant, else None."""
    if viewer is None:
        return None
    occupant = table.get_seat(viewer).player
    if occupant is None:
        return None
    for participant in facts.started.participants:
        if participant.seat == viewer and participant.player_id == occupant.player_id:
            return viewer
    return None


def permitted(facts: Facts, own: int | None) -> set[Card]:
    visible = set(facts.shown) | ({own} if own is not None else set())
    return set(facts.board) | {card for seat in visible for card in facts.hole.get(seat, ())}


def expected_event(event: HandEvent, own_cards: tuple[Card, ...] | None) -> object:
    """The projection of one event, written out from its fields."""
    match event:
        case HandStarted():
            return HandStartedView(
                event.number,
                tuple(HandParticipantView(p.seat, p.position, p.blind, p.starting_stack) for p in event.participants),
            )
        case BlindsPosted():
            return BlindsPostedView(
                event.stakes, tuple(BlindPostView(p.seat, p.blind, p.chips, p.all_in) for p in event.posts)
            )
        case HoleCardsDealt():
            return HoleCardsDealtView(own_cards)
        case StreetDealt():
            return StreetDealtView(event.street, tuple(event.cards))
        case BettingRoundStarted():
            return BettingRoundStartedView(event.street)
        case ActionTaken():
            return ActionTakenView(event.seat, event.action, event.chips, event.all_in)
        case ChipsReturned():
            return ChipsReturnedView(event.seat, event.chips)
        case BettingRoundCompleted():
            return BettingRoundCompletedView(event.street)
        case ShowdownStarted():
            return ShowdownStartedView(event.kind, tuple(event.order))
        case ShowdownDecided():
            return ShowdownDecidedView(event.seat, event.action)
        case HandSettled():
            return HandSettledView(expected_settlement(event.settlement))
    raise AssertionError(f"unclassified event {event!r}")


def expected_settlement(settlement: Settlement) -> SettlementView:
    return SettlementView(
        tuple(PotAwardView(award.pot, tuple(award.shares)) for award in settlement.pot_awards),
        tuple(settlement.showdown_ranks),
    )


def strip_private(view: HoldemView, own: int | None, shown: frozenset[int]) -> HoldemView:
    """The view of a participant without its private fields; a viewer without private facts is returned as it is."""
    hand_view = view.hand
    if hand_view is None or own is None:
        return view
    participants = tuple(
        replace(entry, hole_cards=None, strength=None) if entry.seat == own and own not in shown else entry
        for entry in hand_view.participants
    )
    log = tuple(
        replace(item, own_cards=None) if isinstance(item, HoleCardsDealtView) else item for item in hand_view.log
    )
    return replace(
        view,
        hand=replace(hand_view, participants=participants, legal_actions=None, showdown_actions=None, log=log),
    )


def check_seats(table: Table, view: HoldemView) -> None:
    expected = tuple(
        SeatView(
            number,
            None
            if table.get_seat(number).player is None
            else OccupantView(
                table.get_seat(number).player.stack,  # type: ignore[union-attr]
                EXPECTED_OCCUPANT_STATUS[table.get_seat(number).player.status],  # type: ignore[union-attr]
            ),
        )
        for number in range(1, table.max_seats + 1)
    )
    assert view.seats == expected, "the seats do not follow the table"


def check_view(table: Table, hand: PokerHand, facts: Facts, viewer: int | None, view: HoldemView) -> None:
    """The full oracle for one view of the hand's current state; raises AssertionError on any violation."""
    assert type(view) is HoldemView
    check_seats(table, view)
    hand_view = view.hand
    assert hand_view is not None and type(hand_view) is HandView
    own = own_seat(table, facts, viewer)
    allowed = permitted(facts, own)

    reached = Reached({}, [], [])
    walk(view, "view", reached)

    # Safety and completeness: exactly the permitted cards are reachable.
    leaked = {card: path for card, path in reached.cards.items() if card not in allowed}
    assert not leaked, f"viewer {viewer} reaches cards it must not see: {leaked}"
    burned = set(facts.burned) & set(reached.cards)
    assert not burned, f"viewer {viewer} reaches burned cards {burned}"
    missing = allowed - set(reached.cards)
    assert not missing, f"viewer {viewer} is missing visible cards {missing}"

    # The public hand facts, from the hand itself.
    assert hand_view.number == hand.number
    assert hand_view.street is hand.street
    assert hand_view.stakes == STAKES
    assert hand_view.board == facts.board == tuple(hand.board)
    assert hand_view.pots == pots(hand)
    assert hand_view.showdown == hand.showdown
    settled = hand.settlement is not None
    assert hand_view.settlement == (None if hand.settlement is None else expected_settlement(hand.settlement))

    # Participants: public facts, visible cards and strength.
    visible = set(facts.shown) | ({own} if own is not None else set())
    live = {state.seat_number: state for state in hand.players}
    assert tuple(entry.seat for entry in hand_view.participants) == tuple(
        participant.seat for participant in facts.started.participants
    )
    strengths: list[BestHand] = []
    for entry, participant in zip(hand_view.participants, facts.started.participants, strict=True):
        state = live[entry.seat]
        assert (entry.position, entry.blind) == (participant.position, participant.blind)
        assert (entry.in_front, entry.folded, entry.all_in) == (
            state.street_contribution,
            state.folded,
            state.all_in,
        )
        assert entry.has_live_cards == (not state.folded and entry.seat not in facts.mucked)
        cards = facts.hole[entry.seat]
        assert len(cards) == 2
        if entry.seat in visible:
            assert entry.hole_cards == cards, f"viewer {viewer}: seat {entry.seat} cards are wrong or missing"
            if facts.board:
                assert entry.strength is not None
                assert entry.strength.rank == rank_of((*cards, *facts.board))
                assert set(entry.strength.cards) <= {*cards, *facts.board}
                assert len(set(entry.strength.cards)) == 5
                strengths.append(entry.strength)
            else:
                assert entry.strength is None
        else:
            assert entry.hole_cards is None and entry.strength is None, f"viewer {viewer}: seat {entry.seat} leaks"

    # Ranks: a BestHand only for a visible participant, a settlement rank only for a shown seat.
    assert reached.best_hands == strengths, f"viewer {viewer}: a BestHand is reachable outside a visible participant"
    ranks_expected = [best.rank for best in strengths]
    if hand.settlement is not None:
        settlement_view = hand_view.settlement
        assert settlement_view is not None
        assert {seat for seat, _ in settlement_view.showdown_ranks} == set(facts.shown), "ranks of unshown seats"
        for seat, rank in settlement_view.showdown_ranks:
            assert rank == rank_of((*facts.hole[seat], *facts.board))
        ranks_expected += [rank for _, rank in settlement_view.showdown_ranks] * 2  # the view and its log event
    assert sorted(map(repr, reached.ranks)) == sorted(map(repr, ranks_expected)), f"viewer {viewer}: stray HandRank"

    # The turn, legal actions and showdown options.
    betting = hand.betting
    assert betting is not None
    decider = None if hand.showdown is None else hand.showdown.current_decider
    if settled:
        expected_turn = None
    elif betting.current_actor is not None:
        expected_turn = Turn(betting.current_actor, TurnKind.BETTING)
    elif decider is not None:
        expected_turn = Turn(decider, TurnKind.SHOWDOWN)
    else:
        expected_turn = None
    assert hand_view.turn == expected_turn
    assert (current_actor(hand) is None) == (expected_turn is None)
    betting_turn = expected_turn is not None and expected_turn.kind is TurnKind.BETTING
    showdown_turn = expected_turn is not None and expected_turn.kind is TurnKind.SHOWDOWN
    expect_legal = own is not None and betting_turn and expected_turn is not None and expected_turn.seat == own
    expect_options = own is not None and showdown_turn and expected_turn is not None and expected_turn.seat == own
    assert hand_view.legal_actions == (legal_actions(hand) if expect_legal else None), f"viewer {viewer}: legal actions"
    assert hand_view.showdown_actions == ((SHOW, MUCK) if expect_options else None), f"viewer {viewer}: options"

    # The log: one projected event per event, own cards only in the hole-cards deal, no burned cards.
    own_cards = None if own is None else facts.hole[own]
    assert len(hand_view.log) == len(facts.events)
    for item, event in zip(hand_view.log, facts.events, strict=True):
        assert item == expected_event(event, own_cards), f"viewer {viewer}: log event {event!r}"


def engine_state(table: Table, hand: PokerHand) -> tuple[object, ...]:
    """The authoritative state a projection must leave untouched."""
    betting = hand.betting
    return (
        hand.history,
        hand.showdown,
        hand.settlement,
        hand.street,
        tuple(hand.board),
        tuple(hand.burned_cards),
        len(hand.deck),
        None if betting is None else (betting.current_actor, betting.current_bet),
        [
            (s.folded, s.all_in, s.street_contribution, s.total_contribution, tuple(s.hole_cards), s.player.stack)
            for s in hand.players
        ],
        [
            (seat.number, seat.player and (seat.player.player_id, seat.player.stack, seat.player.status))
            for seat in table.occupied_seats
        ],
        table.button_seat_number,
    )


def check_all_viewers(table: Table, hand: PokerHand, counters: Counter[str]) -> dict[int | None, HoldemView]:
    """Build and check the view of every viewer, with the checkpoint against the public view."""
    facts = facts_of(hand)
    state = engine_state(table, hand)
    views: dict[int | None, HoldemView] = {}
    for viewer in (None, *range(1, table.max_seats + 1)):
        views[viewer] = holdem_view(table, hand, viewer)
    assert engine_state(table, hand) == state, "building the views changed the engine state"
    public = views[None]
    check_view(table, hand, facts, None, public)
    for viewer in range(1, table.max_seats + 1):
        own = own_seat(table, facts, viewer)
        view = views[viewer]
        assert strip_private(view, own, facts.shown) == public, f"viewer {viewer}: differs from the public view"
        if own is None:
            # Equal to the public view, so its safety is the public view's; the seat still counts for coverage.
            participant = next((p for p in facts.started.participants if p.seat == viewer), None)
            occupant = table.get_seat(viewer).player
            if participant is not None and occupant is not None:
                counters["reoccupied_views"] += 1
            elif participant is not None:
                counters["vacated_views"] += 1
            elif occupant is not None:
                counters["seated_non_participant_views"] += 1
            else:
                counters["empty_seat_views"] += 1
        else:
            check_view(table, hand, facts, viewer, view)
            counters["participant_views"] += 1
    counters["checks"] += 1
    counters["sitting_out_seat_checks"] += sum(
        seat.player is not None and seat.player.status is SITTING_OUT for seat in table.occupied_seats
    )
    return views


# =============================================================================
# THE DRIVER
# =============================================================================


def betting_action(rng: random.Random, legal: LegalActions, aggression: int, *, passive: bool) -> Action:
    """A random legal action. Passive play rarely folds and never bets big, so hands reach the interactive river."""
    options: list[tuple[Action, int]] = [(FOLD, 1 if passive else (2 if legal.can_check else 3))]
    if legal.can_check:
        options.append((CHECK, 10 if passive else 6))
    if legal.can_call:
        options.append((CALL, 10 if passive else 6))
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        options.append((Action(kind, legal.short_all_in_target), 1 if passive else aggression))
    elif legal.min_full_target is not None and legal.max_target is not None:
        low, high = legal.min_full_target, legal.max_target
        if passive:
            options.append((Action(kind, min(high, low + rng.randint(0, 2 * low))), 1))
        else:
            options.append((Action(kind, low), aggression))
            options.append((Action(kind, rng.randint(low, high)), aggression))
            options.append((Action(kind, high), max(1, aggression // 2)))
    return rng.choices([action for action, _ in options], [weight for _, weight in options])[0]


class Game:
    """One seeded game of a few hands, with every state checked."""

    def __init__(self, seed: int, counters: Counter[str]) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.counters = counters
        self.table = Table(self.rng.choice([2, 3, 4, 5, 6, 6, 6]))
        self.game = HoldemGame(self.table, STAKES)
        self.aggression = self.rng.choice([1, 3, 8])
        self.passive = self.rng.random() < 0.5
        self.target_players = self.rng.randint(2, min(6, self.table.max_seats))
        self.show_probability = self.rng.choice([0.2, 0.5, 0.85])
        self.next_id = 0
        self.kept: list[tuple[HoldemView, str]] = []  # views and their repr when taken, which must never change
        count = self.rng.randint(2, min(6, self.table.max_seats))
        for seat in self.rng.sample(range(1, self.table.max_seats + 1), count):
            self.sit_new(seat)

    # --- seats -------------------------------------------------------------------------------------------------

    def stack(self) -> int:
        roll = self.rng.random()
        if self.passive:
            return self.rng.randint(300, 1500) if roll < 0.8 else self.rng.randint(1, 120)
        if roll < 0.25:
            return self.rng.randint(1, 14)  # often a short blind or a short all-in
        if roll < 0.6:
            return self.rng.randint(15, 120)
        return self.rng.randint(120, 800)

    def sit_new(self, seat: int) -> None:
        self.next_id += 1
        self.table.sit_in(Player(f"player-{self.seed}-{self.next_id}", stack=self.stack()), seat)

    def occupied(self) -> dict[int, Player]:
        return {seat.number: seat.player for seat in self.table.occupied_seats if seat.player is not None}

    def empty_seats(self) -> list[int]:
        return [n for n in range(1, self.table.max_seats + 1) if self.table.get_seat(n).player is None]

    # --- checks ------------------------------------------------------------------------------------------------

    def check(self) -> None:
        hand = self.game.hand
        assert hand is not None
        views = check_all_viewers(self.table, hand, self.counters)
        viewer = self.rng.choice(list(views))
        if self.rng.random() < 0.25:
            self.kept.append((views[viewer], repr(views[viewer])))
        # A view of a state before the latest change keeps its value.
        for view, text in self.kept[-3:]:
            assert repr(view) == text, f"seed {self.seed}: a kept view changed"

    def assert_kept_views_unchanged(self) -> None:
        for view, text in self.kept:
            assert repr(view) == text, f"seed {self.seed}: a kept view changed by later play"
            self.counters["kept_views_rechecked"] += 1

    def probe_rejection(self, hand: PokerHand) -> None:
        """A rejected act changes no view."""
        actor = current_actor(hand)
        wrong = next(state.seat_number for state in hand.players if state.seat_number != actor)
        before = {viewer: repr(holdem_view(self.table, hand, viewer)) for viewer in (None, 1, 2)}
        with pytest.raises((NotPlayersTurnError, NotShowdownTurnError)):
            self.game.act(wrong, FOLD if hand.showdown is None else SHOW)
        assert before == {viewer: repr(holdem_view(self.table, hand, viewer)) for viewer in (None, 1, 2)}
        self.counters["rejections"] += 1

    # --- play --------------------------------------------------------------------------------------------------

    def play_hand(self, hand: PokerHand) -> None:
        steps = 0
        while hand.settlement is None:
            steps += 1
            assert steps < MAX_STEPS, f"seed {self.seed}: the hand did not end"
            betting = hand.betting
            assert betting is not None
            seat = current_actor(hand)
            assert seat is not None
            if self.rng.random() < 0.1:
                self.probe_rejection(hand)
            if betting.current_actor is not None:
                self.game.act(
                    seat, betting_action(self.rng, legal_actions(hand), self.aggression, passive=self.passive)
                )
            else:
                self.game.act(seat, SHOW if self.rng.random() < self.show_probability else MUCK)
            self.check()
        self.count_settled(hand)
        self.assert_kept_views_unchanged()

    def count_settled(self, hand: PokerHand) -> None:
        counters = self.counters
        events = hand.history.events
        settlement = hand.settlement
        assert settlement is not None
        started = [event for event in events if isinstance(event, ShowdownStarted)]
        decisions = [event.action for event in events if isinstance(event, ShowdownDecided)]
        counters["hands"] += 1
        counters["all_in_showdown"] += any(event.kind is ShowdownKind.ALL_IN for event in started)
        counters["interactive_showdown"] += any(event.kind is ShowdownKind.INTERACTIVE for event in started)
        counters["interactive_show"] += SHOW in decisions
        counters["muck"] += MUCK in decisions
        counters["uncontested"] += not started
        counters["last_contender_unshown"] += bool(started) and not settlement.showdown_ranks
        counters["side_pots"] += len(settlement.pot_awards) > 1
        counters["short_blind_all_in"] += any(
            isinstance(event, BlindsPosted) and any(post.all_in for post in event.posts) for event in events
        )
        counters["heads_up"] += len(hand.players) == 2

    def after_new_hand(self, hand: PokerHand) -> None:
        assert hand is self.game.hand
        self.check()
        self.counters["settled_at_start"] += hand.settlement is not None

    # --- churn -------------------------------------------------------------------------------------------------

    def churn(self, hand: PokerHand) -> None:
        """Between hands, with the settled hand still current. Every step is checked."""
        rng = self.rng
        participants = [(p.seat, p.player_id) for p in facts_of(hand).started.participants]
        order = list(participants)
        rng.shuffle(order)
        for seat, player_id in order:
            roll = rng.random()
            current = self.table.get_seat(seat).player
            if current is None or current.player_id != player_id:
                continue
            if roll < 0.4:
                # The re-occupied-seat window: a new player (a new player_id) takes the seat before the next hand.
                self.table.stand_up(seat)
                self.check()
                self.counters["vacated"] += 1
                self.sit_new(seat)
                self.check()
                self.counters["reoccupied"] += 1
            elif roll < 0.5:
                # The same player_id comes back to the same seat as a new Player object.
                self.table.stand_up(seat)
                self.table.sit_in(Player(player_id, stack=current.stack, status=current.status), seat)
                self.check()
                self.counters["same_id_returned"] += 1
            elif roll < 0.6 and self.empty_seats():
                # The same player_id moves to another seat.
                other = rng.choice(self.empty_seats())
                self.table.stand_up(seat)
                self.table.sit_in(Player(player_id, stack=current.stack, status=current.status), other)
                self.check()
                self.counters["moved_seat"] += 1
            elif roll < 0.7:
                # Two participants swap seats: each seat now holds the other's player_id.
                partner = next(
                    (
                        other
                        for other, other_id in order
                        if other != seat
                        and (seated := self.table.get_seat(other).player) is not None
                        and seated.player_id == other_id
                    ),
                    None,
                )
                if partner is not None:
                    partner_player = self.table.get_seat(partner).player
                    assert partner_player is not None
                    self.table.stand_up(seat)
                    self.table.stand_up(partner)
                    self.table.sit_in(Player(player_id, current.stack, current.status), partner)
                    self.table.sit_in(
                        Player(partner_player.player_id, partner_player.stack, partner_player.status), seat
                    )
                    self.check()
                    self.counters["swapped"] += 1
            elif roll < 0.8 and current.stack > 0:
                # A solvent participant sits out; it stays out until the repair brings it back, so the seat is
                # projected as sitting out in the checks below and in the next hand.
                current.status = SITTING_OUT
                self.check()
                self.counters["sat_out"] += 1
        for number, player in self.occupied().items():
            if player.stack == 0 and rng.random() < 0.7:
                self.table.stand_up(number)
        while len(self.playable()) < self.target_players and self.empty_seats():
            self.sit_new(rng.choice(self.empty_seats()))
            self.counters["newcomers"] += 1
        self.check()
        self.repair_table()

    def playable(self) -> list[int]:
        return [n for n, p in self.occupied().items() if p.status is not SITTING_OUT and p.stack > 0]

    def repair_table(self) -> bool:
        """Make the next hand possible: two players who can play and one of them ready. False when it cannot be."""
        for player in self.occupied().values():
            if player.status is SITTING_OUT and player.stack > 0 and len(self.playable()) < 2:
                player.status = READY
        while len(self.playable()) < 2:
            empty = self.empty_seats()
            if not empty:
                busted = [n for n, p in self.occupied().items() if p.stack == 0]
                if not busted:
                    return False
                self.table.stand_up(busted[0])
                continue
            self.sit_new(self.rng.choice(empty))
            self.counters["topped_up"] += 1
        if not any(p.status is READY and p.stack > 0 for p in self.occupied().values()):
            self.occupied()[self.playable()[0]].status = READY
        return True

    # --- the game ----------------------------------------------------------------------------------------------

    def next_hand(self) -> PokerHand | None:
        """The next hand, or None when no hand can be made. A rejected call leaves every view as it was."""
        for _attempt in range(2):
            if not self.repair_table():
                return None
            hand = self.game.hand
            assert hand is not None
            before = repr(holdem_view(self.table, hand, None))
            try:
                return self.game.next_hand()
            except InvalidPlayerCount:
                assert repr(holdem_view(self.table, hand, None)) == before
                self.check()
                self.counters["next_hand_rejected"] += 1
                for player in self.occupied().values():
                    if player.status is WAITING and player.stack > 0:
                        player.status = READY
        return None

    def play(self) -> None:
        assert self.game.hand is None
        before = holdem_view(self.table, None, None)
        assert before.hand is None and len(before.seats) == self.table.max_seats
        hand: PokerHand | None = self.game.start(lambda seats: self.rng.choice(seats))
        for number in range(MAX_HANDS):
            assert hand is not None
            self.after_new_hand(hand)
            self.play_hand(hand)
            if number == MAX_HANDS - 1:
                break
            self.churn(hand)
            hand = self.next_hand()
            if hand is None:
                break
            self.counters["next_hands"] += 1
        self.assert_kept_views_unchanged()


def play_seed(seed: int, counters: Counter[str]) -> None:
    with pytest.MonkeyPatch.context() as patch:
        deck_rng = random.Random(f"leak-decks-{seed}")
        original = Deck.shuffle
        patch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=deck_rng))
        try:
            Game(seed, counters).play()
        except AssertionError as error:
            error.add_note(f"reproduce with seed {seed}")
            raise


def test_no_viewer_ever_sees_a_card_or_rank_it_may_not_across_seeded_games() -> None:
    counters: Counter[str] = Counter()
    for seed in SEEDS:
        play_seed(seed, counters)

    required: dict[str, int] = {
        "hands": 250,
        "checks": 2500,
        "all_in_showdown": 100,
        "interactive_showdown": 40,
        "interactive_show": 18,
        "muck": 35,
        "uncontested": 80,
        "last_contender_unshown": 25,
        "side_pots": 60,
        "short_blind_all_in": 30,
        "settled_at_start": 10,
        "heads_up": 100,
        "reoccupied": 250,
        "reoccupied_views": 700,
        "vacated_views": 250,
        "same_id_returned": 50,
        "moved_seat": 20,
        "swapped": 10,
        "sat_out": 30,
        "sitting_out_seat_checks": 1500,
        "seated_non_participant_views": 1500,
        "empty_seat_views": 1500,
        "participant_views": 7000,
        "rejections": 150,
        "kept_views_rechecked": 4000,
    }
    missing = {key: (counters[key], need) for key, need in required.items() if counters[key] < need}
    assert not missing, f"the seed set no longer reaches enough of: {missing} (got {dict(counters)})"


# =============================================================================
# THE ORACLE CHECKS ITSELF: A TAMPERED VIEW MUST BE REJECTED
# =============================================================================


def flop_hand() -> tuple[Table, PokerHand]:
    """Three players on a five-seat table (seats 1, 2 and 4), checked and called to the flop, nobody settled."""
    table = Table(5)
    for seat in (1, 2, 4):
        table.sit_in(Player(f"tamper-{seat}", stack=1000), seat)
    with pytest.MonkeyPatch.context() as patch:
        deck_rng = random.Random("tamper")
        original = Deck.shuffle
        patch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=deck_rng))
        game = HoldemGame(table, STAKES)
        hand = game.start(lambda seats: seats[0])
    while hand.street is Street.PREFLOP:
        actor = current_actor(hand)
        assert actor is not None
        game.act(actor, CALL if legal_actions(hand).can_call else CHECK)
    assert hand.settlement is None and len(hand.board) == 3
    return table, hand


def hand_view_of(table: Table, hand: PokerHand, viewer: int | None) -> tuple[HoldemView, HandView]:
    view = holdem_view(table, hand, viewer)
    assert view.hand is not None
    return view, view.hand


def tampered_views(table: Table, hand: PokerHand) -> Iterator[tuple[str, int | None, HoldemView]]:
    """Real views with one leak or defect injected each, as (what was injected, the viewer, the view)."""
    actor = current_actor(hand)
    assert actor is not None
    others = [state.seat_number for state in hand.players if state.seat_number != actor]
    watcher, victim = others
    spectator = 3  # an empty seat
    victim_cards = tuple(next(s for s in hand.players if s.seat_number == victim).hole_cards)
    burned = tuple(hand.burned_cards)
    actor_view, actor_hand = hand_view_of(table, hand, actor)
    watcher_view, watcher_hand = hand_view_of(table, hand, watcher)
    public_view, public_hand = hand_view_of(table, hand, None)
    spectator_view, spectator_hand = hand_view_of(table, hand, spectator)
    victim_strength = next(e for e in hand_view_of(table, hand, victim)[1].participants if e.seat == victim).strength
    assert victim_strength is not None

    def show_victim(hand_view: HandView, **extra: Any) -> HandView:
        entries = tuple(
            replace(entry, hole_cards=victim_cards, **extra) if entry.seat == victim else entry
            for entry in hand_view.participants
        )
        return replace(hand_view, participants=entries)

    def hide(hand_view: HandView, seat: int) -> HandView:
        entries = tuple(
            replace(entry, hole_cards=None, strength=None) if entry.seat == seat else entry
            for entry in hand_view.participants
        )
        return replace(hand_view, participants=entries)

    yield "an opponent's hole cards", watcher, replace(watcher_view, hand=show_victim(watcher_hand))
    yield "an opponent's hole cards to the public", None, replace(public_view, hand=show_victim(public_hand))
    yield (
        "an opponent's strength",
        watcher,
        replace(watcher_view, hand=show_victim(watcher_hand, strength=victim_strength)),
    )
    yield "a seated outsider seeing an opponent", spectator, replace(spectator_view, hand=show_victim(spectator_hand))
    street_log = tuple(
        replace(item, cards=(*item.cards, burned[0])) if isinstance(item, StreetDealtView) else item
        for item in public_hand.log
    )
    yield "a burned card in the log", None, replace(public_view, hand=replace(public_hand, log=street_log))
    yield (
        "a list instead of a tuple",
        None,
        replace(public_view, hand=replace(public_hand, board=list(public_hand.board))),
    )  # type: ignore[arg-type]
    yield (
        "a live engine object",
        None,
        replace(public_view, hand=replace(public_hand, participants=tuple(hand.players))),
    )  # type: ignore[arg-type]
    yield "a player_id string", None, replace(public_view, seats=(SeatView(1, OccupantView("tamper-1", None)),))  # type: ignore[arg-type]
    yield "an own hand that went missing", actor, replace(actor_view, hand=hide(actor_hand, actor))
    no_own_deal = tuple(
        replace(item, own_cards=None) if isinstance(item, HoleCardsDealtView) else item for item in actor_hand.log
    )
    yield "a missing own deal in the log", actor, replace(actor_view, hand=replace(actor_hand, log=no_own_deal))
    assert actor_hand.legal_actions is not None
    yield (
        "legal actions for a viewer who is not the actor",
        watcher,
        replace(watcher_view, hand=replace(watcher_hand, legal_actions=actor_hand.legal_actions)),
    )
    yield "no legal actions for the actor", actor, replace(actor_view, hand=replace(actor_hand, legal_actions=None))
    yield (
        "showdown options during betting",
        actor,
        replace(actor_view, hand=replace(actor_hand, showdown_actions=(SHOW, MUCK))),
    )


def test_the_walker_rejects_an_engine_player_status() -> None:
    for status in PlayerStatus:
        with pytest.raises(AssertionError, match="PlayerStatus"):
            walk(SeatView(1, OccupantView(100, status)), "view", Reached({}, [], []))  # type: ignore[arg-type]
    for status in (None, *OccupantStatus):
        walk(SeatView(1, OccupantView(100, status)), "view", Reached({}, [], []))


def test_the_oracle_accepts_the_real_views_and_rejects_every_tampered_view() -> None:
    table, hand = flop_hand()
    check_all_viewers(table, hand, Counter())  # every real view passes, so each rejection below is the injected defect

    rejected = 0
    for name, viewer, view in tampered_views(table, hand):
        with pytest.raises(AssertionError):
            check_view(table, hand, facts_of(hand), viewer, view)
        rejected += 1
        if viewer is not None:
            own = own_seat(table, facts_of(hand), viewer)
            if own is None:
                assert strip_private(view, own, facts_of(hand).shown) != holdem_view(table, hand, None), name
    assert rejected == 13


# =============================================================================
# ADVERSARIAL SCENARIOS, EACH CHECKED AT EVERY STATE BY THE ORACLE
# =============================================================================

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
RAISE = ActionType.RAISE
LIMP: tuple[tuple[int, Action | ShowdownAction], ...] = ((1, CALL), (2, CALL), (3, CHECK))
STREET_CHECKS: tuple[tuple[int, Action | ShowdownAction], ...] = ((2, CHECK), (3, CHECK), (1, CHECK))

type Play = tuple[int, Action | ShowdownAction]
type Deal = Callable[..., list[Card]]
type Queue = Callable[..., Any]


@dataclass
class Scene:
    """A real `HoldemGame` on stacked decks whose every state is checked for every viewer, outside seat included."""

    table: Table
    game: HoldemGame

    @property
    def hand(self) -> PokerHand:
        assert self.game.hand is not None
        return self.game.hand

    def check(self) -> dict[int | None, HoldemView]:
        return check_all_viewers(self.table, self.hand, Counter())

    def play(self, *plays: Play) -> None:
        for seat, action in plays:
            self.game.act(seat, action)
            self.check()


def new_scene(
    queue_decks: Queue,
    draw_order: Deal,
    holes: dict[int, str],
    *,
    stacks: dict[int, int] | None = None,
    button: int = 1,
    max_seats: int = 9,
    outsider: int | None = 7,
) -> Scene:
    """The seats in `holes` play; seat `outsider`, when given, sits down after the hand started and never plays."""
    table = Table(max_seats)
    for seat in holes:
        table.sit_in(Player(f"P{seat}", stack=(stacks or {}).get(seat, 1000)), seat)
    queue_decks(draw_order(holes, BOARD, button))
    game = HoldemGame(table, STAKES)
    game.start(lambda _seats: button)
    if outsider is not None:
        table.sit_in(Player("LATE", stack=500), outsider)
    scene = Scene(table, game)
    scene.check()
    return scene


def test_a_non_participant_and_an_empty_seat_see_exactly_the_public_view_through_a_whole_hand(
    queue_decks: Queue, draw_order: Deal
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES)
    plays: tuple[Play, ...] = (*LIMP, *STREET_CHECKS, *STREET_CHECKS, *STREET_CHECKS, (2, SHOW), (3, MUCK), (1, SHOW))

    for step in range(len(plays) + 1):
        for outsider in (7, 6, 4, 9):  # the late player, then empty seats
            assert holdem_view(scene.table, scene.hand, outsider) == holdem_view(scene.table, scene.hand, None), step
        if step < len(plays):
            scene.play(plays[step])
    assert scene.hand.settlement is not None


def test_a_viewer_outside_a_small_table_is_rejected_for_every_hand_state_and_changes_nothing() -> None:
    table = Table(2)
    table.sit_in(Player("A", stack=100), 1)
    table.sit_in(Player("B", stack=100), 2)
    before = repr(holdem_view(table, None, None))
    for seat in (0, -1, 3, 9, 10):
        with pytest.raises(InvalidSeatNumber):
            holdem_view(table, None, seat)
    assert repr(holdem_view(table, None, None)) == before


@pytest.mark.parametrize(
    ("small_blind_stack", "big_blind_stack", "returned"),
    [(3, 7, 4), (4, 1000, 6), (5, 10, 5), (10, 5, 0)],
    ids=["both-blinds-short", "short-small-blind", "both-exactly-all-in", "short-big-blind-matched"],
)
def test_blinds_alone_can_decide_a_heads_up_hand_and_the_all_in_showdown_shows_both_seats(
    queue_decks: Queue,
    draw_order: Deal,
    cards: Callable[[str], list[Card]],
    small_blind_stack: int,
    big_blind_stack: int,
    returned: int,
) -> None:
    """Heads-up the button is the small blind. No player ever acts, yet both live cards are tabled."""
    holes = {2: "Ah Ad", 5: "Kd Kh"}
    scene = new_scene(
        queue_decks,
        draw_order,
        holes,
        stacks={2: small_blind_stack, 5: big_blind_stack},
        button=2,
        max_seats=6,
        outsider=None,
    )
    hand = scene.hand
    assert hand.settlement is not None and hand.showdown is not None and hand.showdown.kind is ShowdownKind.ALL_IN
    assert [state.blind.value for state in hand.players] == ["SB", "BB"]

    views = scene.check()
    for viewer in (None, 1, 2, 3, 5, 6):
        view = views[viewer].hand
        assert view is not None and view.turn is None and view.legal_actions is None and view.showdown_actions is None
        assert [entry.hole_cards for entry in view.participants] == [tuple(cards(holes[2])), tuple(cards(holes[5]))]
        assert view.board == tuple(cards(BOARD))
        assert view.settlement is not None and [seat for seat, _ in view.settlement.showdown_ranks] == [2, 5]
    log = views[None].hand.log  # type: ignore[union-attr]
    assert sum(item.chips for item in log if isinstance(item, ChipsReturnedView)) == returned
    assert isinstance(log[-1], HandSettledView)
    assert sum(isinstance(item, ShowdownStartedView) for item in log) == 1


def test_a_heads_up_hand_with_an_interactive_showdown_is_checked_at_every_state(
    queue_decks: Queue, draw_order: Deal
) -> None:
    holes = {2: "Ah Ad", 5: "Kd Kh"}
    scene = new_scene(queue_decks, draw_order, holes, button=2, max_seats=6, outsider=3)
    # Preflop the small blind (button, seat 2) acts first, afterwards the big blind (seat 5) acts first.
    scene.play((2, CALL), (5, CHECK), *[(5, CHECK), (2, CHECK)] * 3)
    assert scene.hand.showdown is not None and scene.hand.showdown.kind is ShowdownKind.INTERACTIVE
    scene.play((5, MUCK))
    assert scene.hand.settlement is not None
    only = holdem_view(scene.table, scene.hand, 2).hand
    assert only is not None and only.settlement is not None and only.settlement.showdown_ranks == ()


def test_a_big_blind_all_in_by_its_blind_stays_hidden_until_the_all_in_showdown_starts(
    queue_decks: Queue, draw_order: Deal, cards: Callable[[str], list[Card]]
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES, stacks={3: 6})
    hand = scene.hand
    blind_state = next(state for state in hand.players if state.seat_number == 3)
    assert blind_state.all_in and hand.showdown is None

    scene.play((1, CALL), (2, CALL))  # the round closes with the short big blind all-in; the others can still bet
    for street in range(3):
        assert hand.showdown is None and hand.settlement is None
        for viewer in (None, 1, 2, 7):
            entry = holdem_view(scene.table, hand, viewer).hand.participants[2]  # type: ignore[union-attr]
            assert entry.seat == 3 and entry.all_in and entry.hole_cards is None and entry.strength is None, street
        assert holdem_view(scene.table, hand, 3).hand.participants[2].hole_cards == tuple(cards(HOLES[3]))  # type: ignore[union-attr]
        scene.play((2, CHECK), (1, CHECK))

    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.ALL_IN and hand.settlement is not None
    for viewer in (None, 1, 2, 7):
        entries = holdem_view(scene.table, hand, viewer).hand.participants  # type: ignore[union-attr]
        assert [entry.hole_cards for entry in entries] == [tuple(cards(HOLES[seat])) for seat in (1, 2, 3)]


def test_a_raw_all_in_hand_reveals_its_cards_only_when_settle_hand_builds_the_showdown(
    stacked_hand: Callable[..., PokerHand],
) -> None:
    hand = stacked_hand(HOLES, BOARD, stacks={1: 300, 2: 100, 3: 300})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    table = Table(9)
    for state in hand.players:
        table.sit_in(state.player, state.seat_number)
    apply_action(hand, 1, Action(RAISE, 300))
    apply_action(hand, 2, CALL)
    apply_action(hand, 3, CALL)
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    assert hand.showdown is None and len(hand.board) == 5 and hand.settlement is None

    before = check_all_viewers(table, hand, Counter())
    assert before[None].hand is not None
    assert all(entry.hole_cards is None for entry in before[None].hand.participants)  # nothing shown yet
    for seat in (1, 2, 3):
        own_hand = before[seat].hand
        assert own_hand is not None
        assert [entry.hole_cards is not None for entry in own_hand.participants] == [s == seat for s in (1, 2, 3)]

    settle_hand(hand)

    after = check_all_viewers(table, hand, Counter())
    for viewer in (None, 1, 2, 3, 6):
        view = after[viewer].hand
        assert view is not None and all(entry.hole_cards is not None for entry in view.participants)
        assert view.settlement is not None and [seat for seat, _ in view.settlement.showdown_ranks] == [1, 2, 3]
    assert [type(item) for item in after[None].hand.log[-2:]] == [ShowdownStartedView, HandSettledView]  # type: ignore[union-attr]


def test_a_mucked_seat_keeps_its_own_strength_and_loses_it_for_everyone_else_at_every_state(
    queue_decks: Queue, draw_order: Deal
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES)
    scene.play(*LIMP, *STREET_CHECKS, *STREET_CHECKS, *STREET_CHECKS)
    scene.play((2, MUCK))
    for viewer in (None, 1, 3, 7):
        entry = holdem_view(scene.table, scene.hand, viewer).hand.participants[1]  # type: ignore[union-attr]
        assert entry.seat == 2 and entry.hole_cards is None and entry.strength is None and not entry.has_live_cards
    own = holdem_view(scene.table, scene.hand, 2).hand
    assert own is not None and own.participants[1].strength is not None and own.participants[1].hole_cards is not None
    scene.play((3, SHOW), (1, MUCK))
    assert scene.hand.settlement is not None


def test_a_last_contender_who_wins_unshown_keeps_its_cards_private_to_everyone_else(
    queue_decks: Queue, draw_order: Deal
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES)
    scene.play(*LIMP, *STREET_CHECKS, *STREET_CHECKS, *STREET_CHECKS, (2, MUCK), (3, MUCK))
    hand = scene.hand
    assert hand.settlement is not None and hand.settlement.showdown_ranks == ()
    public = holdem_view(scene.table, hand, None).hand
    assert public is not None and all(entry.hole_cards is None for entry in public.participants)
    assert public.settlement is not None and public.settlement.showdown_ranks == ()
    winner = holdem_view(scene.table, hand, 1).hand
    assert winner is not None and winner.participants[0].hole_cards is not None


def test_the_views_of_a_re_occupied_seat_never_carry_the_old_occupants_cards_or_any_player_id(
    queue_decks: Queue, draw_order: Deal
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES)
    scene.play((1, FOLD), (2, FOLD))
    hand = scene.hand
    old_cards = set(next(s for s in hand.players if s.seat_number == 3).hole_cards)
    scene.table.stand_up(3)
    scene.check()
    scene.table.sit_in(Player("NEWCOMER", stack=700), 3)
    views = scene.check()

    newcomer = views[3]
    assert newcomer == views[None]
    assert newcomer.hand is not None and newcomer.hand.board == ()
    assert old_cards.isdisjoint(card for item in newcomer.hand.log for card in getattr(item, "own_cards", None) or ())
    assert [
        getattr(item, "own_cards", "n/a") for item in newcomer.hand.log if isinstance(item, HoleCardsDealtView)
    ] == [None]
    for view in views.values():
        text = repr(view)
        assert all(name not in text for name in ("P1", "P2", "P3", "NEWCOMER", "LATE"))


def test_two_players_who_swap_seats_between_hands_get_no_private_facts_of_the_other_seat(
    queue_decks: Queue, draw_order: Deal
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES)
    scene.play((1, FOLD), (2, FOLD))
    first, second = scene.table.get_seat(1).player, scene.table.get_seat(2).player
    assert first is not None and second is not None
    scene.table.stand_up(1)
    scene.table.stand_up(2)
    scene.table.sit_in(Player(second.player_id, second.stack), 1)
    scene.table.sit_in(Player(first.player_id, first.stack), 2)

    views = scene.check()

    assert views[1] == views[2] == views[None]
    assert all(entry.hole_cards is None for entry in views[1].hand.participants)  # type: ignore[union-attr]


def test_a_view_is_unchanged_by_later_play_the_next_hand_and_changes_to_the_players_it_was_built_from(
    queue_decks: Queue, draw_order: Deal, cards: Callable[[str], list[Card]]
) -> None:
    holes = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
    queue_decks(draw_order(holes, BOARD, 1), draw_order(holes, BOARD, 2))
    table = Table(9)
    for seat in holes:
        table.sit_in(Player(f"P{seat}", stack=1000), seat)
    game = HoldemGame(table, STAKES)
    game.start(lambda _seats: 1)
    hand = game.hand
    assert hand is not None

    kept: list[tuple[HoldemView, str]] = []
    plays: tuple[Play, ...] = (*LIMP, *STREET_CHECKS, *STREET_CHECKS, *STREET_CHECKS, (2, SHOW), (3, MUCK), (1, MUCK))
    for step in range(len(plays) + 1):
        for viewer in (None, 1, 2, 3, 7):
            view = holdem_view(table, hand, viewer)
            kept.append((view, repr(view)))
        if step < len(plays):
            game.act(*plays[step])
    assert hand.settlement is not None

    for player in (table.get_seat(seat).player for seat in holes):
        assert player is not None
        player.stack += 321
        player.status = PlayerStatus.SITTING_OUT if player.stack % 2 else PlayerStatus.READY
    table.stand_up(2)
    table.sit_in(Player("NEWCOMER", stack=5), 2)
    for status_player in (table.get_seat(1).player, table.get_seat(3).player):
        assert status_player is not None
        status_player.status = PlayerStatus.READY
    second = game.next_hand()
    assert second is not hand
    for seat in (1, 2, 3):
        holdem_view(table, second, seat)

    assert all(repr(view) == text for view, text in kept)
    assert len({text for _, text in kept}) > 20


def test_a_hand_view_of_the_settled_hand_is_stable_while_the_table_is_churned(
    queue_decks: Queue, draw_order: Deal
) -> None:
    scene = new_scene(queue_decks, draw_order, HOLES)
    scene.play((1, FOLD), (2, FOLD))
    before = {viewer: holdem_view(scene.table, scene.hand, viewer) for viewer in (None, 1, 2, 3)}
    snapshot = {viewer: repr(view) for viewer, view in before.items()}
    seat_two = scene.table.get_seat(2).player
    assert seat_two is not None
    seat_two.stack = 0
    scene.table.get_seat(3).player.status = PlayerStatus.SITTING_OUT  # type: ignore[union-attr]
    assert {viewer: repr(view) for viewer, view in before.items()} == snapshot
    assert holdem_view(scene.table, scene.hand, None).seats != before[None].seats


def test_an_all_in_showdown_started_before_the_board_is_dealt_reveals_cards_and_strength_follows_the_board(
    stacked_hand: Callable[..., PokerHand],
) -> None:
    hand = stacked_hand(HOLES, BOARD, stacks={1: 300, 2: 100, 3: 300})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    table = Table(9)
    for state in hand.players:
        table.sit_in(state.player, state.seat_number)
    apply_action(hand, 1, Action(RAISE, 300))
    apply_action(hand, 2, CALL)
    apply_action(hand, 3, CALL)
    assert hand.board == [] and hand.showdown is None
    check_all_viewers(table, hand, Counter())  # nothing is shown before the showdown starts

    start_showdown(hand)
    expected_board_sizes = [0, 3, 4, 5]
    for size in expected_board_sizes:
        while len(hand.board) < size:
            deal_next_street(hand)
        views = check_all_viewers(table, hand, Counter())
        for viewer in (None, 1, 2, 3, 6):
            entries = views[viewer].hand.participants  # type: ignore[union-attr]
            assert all(entry.hole_cards is not None for entry in entries)
            assert all((entry.strength is None) == (size == 0) for entry in entries)

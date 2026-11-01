"""Game-level test helpers shared by several modules, exposed as fixtures because test modules cannot import each other.

`replay_facts` folds a hand's history into the facts ADR 0004 promises it can reconstruct and asserts that they equal
the live hand. It is written independently of the engine's recording code and reads nothing but the history: the
`HandStarted` participants and the events, showdown and settlement included.

`fold_history` replays a history alone and checks the facts a completed history promises by itself (chip conservation,
the pots, who may be paid, the showdown ranks). `assert_orchestrated_order` checks the presentation order that the
`begin_hand`/`act` orchestration guarantees, which the low-level operations do not.
"""

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from itertools import pairwise

import pytest

from go_poker.core.card import Card
from go_poker.core.evaluator import evaluate_best
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.rounds import is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindsPosted,
    ChipsReturned,
    HandHistory,
    HandSettled,
    HandStarted,
    HoleCardsDealt,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import Settlement
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street


@dataclass
class SeatFacts:
    hole_cards: list[Card]
    total_contribution: int
    street_contribution: int
    folded: bool
    all_in: bool
    # The starting stack less the total contribution, plus the settlement's shares once the hand is settled.
    stack: int


@dataclass
class ReplayedFacts:
    seats: dict[int, SeatFacts]
    board: list[Card] = field(default_factory=list)
    burned: list[Card] = field(default_factory=list)
    street: Street = Street.PREFLOP
    stakes: Stakes | None = None
    # None until the blinds are posted; then the street of the current or last betting round.
    betting_street: Street | None = None
    round_open: bool | None = None
    actions: list[tuple[int, Action]] = field(default_factory=list)
    # None until a showdown starts; then the started showdown with the decisions made so far.
    showdown: Showdown | None = None
    # None until HandSettled.
    settlement: Settlement | None = None


def _fold(history_events: tuple[object, ...]) -> ReplayedFacts:
    started = history_events[0]
    assert isinstance(started, HandStarted)
    facts = ReplayedFacts({p.seat: SeatFacts([], 0, 0, False, False, p.starting_stack) for p in started.participants})
    for event in history_events[1:]:
        match event:
            case BlindsPosted(stakes=stakes, posts=posts):
                facts.stakes = stakes
                facts.betting_street = Street.PREFLOP
                facts.round_open = True
                for post in posts:
                    seat = facts.seats[post.seat]
                    seat.street_contribution += post.chips
                    seat.total_contribution += post.chips
                    seat.stack -= post.chips
                    seat.all_in = post.all_in
            case HoleCardsDealt(hole_cards=dealt):
                for seat_cards in dealt:
                    facts.seats[seat_cards.seat].hole_cards = list(seat_cards.cards)
            case StreetDealt(street=street, burned=burned, cards=cards):
                facts.street = street
                facts.burned += burned
                facts.board += cards
            case BettingRoundStarted(street=street):
                facts.betting_street = street
                facts.round_open = True
            case ActionTaken(seat=seat_number, action=action, chips=chips, all_in=all_in):
                seat = facts.seats[seat_number]
                seat.street_contribution += chips
                seat.total_contribution += chips
                seat.stack -= chips
                seat.folded = seat.folded or action.type is ActionType.FOLD
                seat.all_in = all_in
                facts.actions.append((seat_number, action))
            case ChipsReturned(seat=seat_number, chips=chips):
                seat = facts.seats[seat_number]
                seat.street_contribution -= chips
                seat.total_contribution -= chips
                seat.stack += chips
                seat.all_in = False
            case BettingRoundCompleted():
                for seat in facts.seats.values():
                    seat.street_contribution = 0
                facts.round_open = False
            case ShowdownStarted(kind=kind, order=order):
                assert facts.showdown is None, "a showdown starts at most once"
                facts.showdown = Showdown(kind, order)
            case ShowdownDecided(seat=seat_number, action=decision):
                assert facts.showdown is not None, "a decision needs a started showdown"
                assert facts.showdown.kind is ShowdownKind.INTERACTIVE, "only an interactive showdown has decisions"
                decided = len(facts.showdown.decisions)
                assert decided < len(facts.showdown.order), "every seat has decided"
                assert seat_number == facts.showdown.order[decided], "the deciding seat is the next in the order"
                facts.showdown = replace(facts.showdown, decisions=(*facts.showdown.decisions, decision))
            case HandSettled(settlement=settlement):
                assert facts.settlement is None, "a hand settles once"
                facts.settlement = settlement
                for pot_award in settlement.pot_awards:
                    for seat_number, chips in pot_award.shares:
                        facts.seats[seat_number].stack += chips
                        facts.seats[seat_number].all_in = False
            case _:
                raise AssertionError(f"unexpected event: {event!r}")
    return facts


def _replay_facts(hand: PokerHand) -> ReplayedFacts:
    """Fold the hand's history and assert that the facts equal the live hand, stacks, all-in, showdown and settlement
    included; return them. The settlement facts of a completed history are also checked by `fold_history`."""
    facts = _fold_history(hand.history)
    assert hand.history.settlement == hand.settlement
    assert hand.history.is_complete == (hand.settlement is not None)
    assert facts.showdown == hand.showdown
    assert facts.settlement == hand.settlement
    assert list(facts.seats) == [state.seat_number for state in hand.players]
    for state in hand.players:
        seat = facts.seats[state.seat_number]
        assert seat.hole_cards == state.hole_cards, f"seat {state.seat_number} hole cards"
        assert seat.total_contribution == state.total_contribution, f"seat {state.seat_number} total contribution"
        assert seat.street_contribution == state.street_contribution, f"seat {state.seat_number} street contribution"
        assert seat.folded == state.folded, f"seat {state.seat_number} folded"
        assert seat.all_in == state.all_in, f"seat {state.seat_number} all-in"
        assert seat.stack == state.player.stack, f"seat {state.seat_number} stack"
    assert facts.board == hand.board
    assert facts.burned == hand.burned_cards
    assert facts.street is hand.street
    betting = hand.betting
    if betting is None:
        assert (facts.stakes, facts.betting_street, facts.round_open) == (None, None, None)
    else:
        assert facts.stakes == betting.stakes
        assert facts.betting_street is betting.street
        assert facts.round_open == (not is_round_complete(betting))
    return facts


def _layers(facts: ReplayedFacts) -> list[tuple[int, frozenset[int]]]:
    """The pots as layered from the replayed contributions alone: one (amount, eligible seats) per distinct positive
    contribution, folded players' dead money included and adjacent layers not merged."""
    contributions = {seat: seat_facts.total_contribution for seat, seat_facts in facts.seats.items()}
    levels = sorted({chips for chips in contributions.values() if chips > 0})
    return [
        (
            sum(min(chips, level) - min(chips, previous) for chips in contributions.values()),
            frozenset(seat for seat, chips in contributions.items() if chips >= level and not facts.seats[seat].folded),
        )
        for previous, level in pairwise((0, *levels))
    ]


def _assert_settlement_facts(history: HandHistory, facts: ReplayedFacts) -> None:
    """The facts a completed history promises by itself, from its replay alone."""
    settlement = facts.settlement
    assert settlement is not None
    started = history.events[0]
    assert isinstance(started, HandStarted)
    seats = list(facts.seats)
    assert sum(seat.stack for seat in facts.seats.values()) == sum(p.starting_stack for p in started.participants)

    assert [(award.pot.amount, award.pot.eligible_seats) for award in settlement.pot_awards] == _layers(facts)
    assert sum(award.pot.amount for award in settlement.pot_awards) == sum(
        seat.total_contribution for seat in facts.seats.values()
    )
    live = {seat for seat, seat_facts in facts.seats.items() if not seat_facts.folded}
    for award in settlement.pot_awards:
        assert award.pot.eligible_seats <= live
        assert sum(chips for _, chips in award.shares) == award.pot.amount

    if facts.showdown is None:
        assert len(live) == 1, "only an uncontested hand settles without a showdown"
        contenders, shown = live, set[int]()
    else:
        assert live == set(facts.showdown.order)
        mucked = {
            seat
            for seat, action in zip(facts.showdown.order, facts.showdown.decisions, strict=False)
            if action is ShowdownAction.MUCK
        }
        contenders = live - mucked
        if facts.showdown.kind is ShowdownKind.ALL_IN:
            assert facts.showdown.decisions == ()
            shown = live
        else:
            assert len(facts.showdown.decisions) == len(facts.showdown.order) or len(contenders) == 1
            shown = {
                seat
                for seat, action in zip(facts.showdown.order, facts.showdown.decisions, strict=False)
                if action is ShowdownAction.SHOW
            }
    assert set(settlement.payouts) <= contenders
    assert [seat for seat, _ in settlement.showdown_ranks] == [seat for seat in seats if seat in shown]
    for seat, rank in settlement.showdown_ranks:
        assert rank == evaluate_best([*facts.seats[seat].hole_cards, *facts.board])

    # Every pot goes to the best replayed hand among its eligible contenders, split evenly with the odd chips first to
    # the seats clockwise from the button: the award itself, not only who may be paid, is checked from the history.
    clockwise = [*seats[1:], *seats[:1]]
    for award in settlement.pot_awards:
        candidates = [seat for seat in clockwise if seat in award.pot.eligible_seats and seat in contenders]
        if len(candidates) > 1:
            assert set(candidates) <= shown, "a contested pot needs every contender shown"
            strength = {seat: evaluate_best([*facts.seats[seat].hole_cards, *facts.board]) for seat in candidates}
            candidates = [seat for seat in candidates if strength[seat] == max(strength.values())]
        share, odd_chips = divmod(award.pot.amount, len(candidates))
        assert list(award.shares) == [(seat, share + (index < odd_chips)) for index, seat in enumerate(candidates)]


def _fold_history(history: HandHistory) -> ReplayedFacts:
    """Replay a history alone and return its facts; a completed history's settlement facts are also checked."""
    facts = _fold(history.events)
    if history.is_complete:
        _assert_settlement_facts(history, facts)
    return facts


def _assert_orchestrated_order(history: HandHistory) -> None:
    """The presentation order `begin_hand`/`act` guarantee, which low-level calls need not follow. `HandStarted` is
    first and only once and `HandSettled` is last, at most once. An `INTERACTIVE` showdown starts right after the river
    round completes and only decisions follow it, in decision order. An `ALL_IN` showdown starts right after the
    betting that closed the hand and only the remaining streets follow, each without a betting round. A hand without a
    showdown has neither showdown event."""
    events = history.events
    assert isinstance(events[0], HandStarted) and not any(isinstance(e, HandStarted) for e in events[1:])
    settled = [index for index, event in enumerate(events) if isinstance(event, HandSettled)]
    assert settled in ([], [len(events) - 1]), "HandSettled is recorded at most once, and last"
    starts = [index for index, event in enumerate(events) if isinstance(event, ShowdownStarted)]
    assert len(starts) <= 1
    if not starts:
        assert not any(isinstance(event, ShowdownDecided) for event in events)
        return

    index = starts[0]
    started = events[index]
    assert isinstance(started, ShowdownStarted)
    before, after = events[:index], events[index + 1 :]
    dealt = [event.street for event in before if isinstance(event, StreetDealt)]
    if started.kind is ShowdownKind.INTERACTIVE:
        assert before[-1] == BettingRoundCompleted(Street.RIVER)
        assert all(isinstance(event, ShowdownDecided) for event in after[: len(after) - bool(settled)])
        decided = [event.seat for event in after if isinstance(event, ShowdownDecided)]
        assert decided == list(started.order[: len(decided)])
    else:
        assert isinstance(before[-1], BettingRoundCompleted | HoleCardsDealt)
        assert not any(isinstance(event, ShowdownDecided | BettingRoundStarted) for event in after)
        if settled:
            streets = list(Street)
            last = dealt[-1] if dealt else Street.PREFLOP
            runout = [event.street for event in after if isinstance(event, StreetDealt)]
            assert runout == streets[streets.index(last) + 1 : streets.index(Street.RIVER) + 1]
            assert all(isinstance(event, StreetDealt) for event in after[:-1])


@pytest.fixture
def replay_facts() -> Callable[[PokerHand], ReplayedFacts]:
    return _replay_facts


@pytest.fixture
def fold_history() -> Callable[[HandHistory], ReplayedFacts]:
    return _fold_history


@pytest.fixture
def assert_orchestrated_order() -> Callable[[HandHistory], None]:
    return _assert_orchestrated_order

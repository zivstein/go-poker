"""Game-level test helpers shared by several modules, exposed as fixtures because test modules cannot import each other.

`replay_facts` folds a hand's history into the facts ADR 0004 promises it can reconstruct and asserts that they equal
the live hand. It is written independently of the engine's recording code and never reads anything but the history, the
`HandStarted` participants and the Cycle 3 events (showdown and settlement events are recorded later).
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import pytest

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.rounds import is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindsPosted,
    ChipsReturned,
    HandStarted,
    HoleCardsDealt,
    StreetDealt,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street


@dataclass
class SeatFacts:
    hole_cards: list[Card]
    total_contribution: int
    street_contribution: int
    folded: bool
    all_in: bool
    # The starting stack less the total contribution: the stack before any payout.
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
            case _:
                raise AssertionError(f"unexpected event in a Cycle 3 history: {event!r}")
    return facts


def _replay_facts(hand: PokerHand, *, settled: bool = False) -> ReplayedFacts:
    """Fold the hand's history and assert that the facts equal the live hand; return them.

    For a settled hand the payout (not recorded yet) has changed stacks and all-in, so pass `settled=True` to skip those
    two comparisons.
    """
    facts = _fold(hand.history.events)
    assert list(facts.seats) == [state.seat_number for state in hand.players]
    for state in hand.players:
        seat = facts.seats[state.seat_number]
        assert seat.hole_cards == state.hole_cards, f"seat {state.seat_number} hole cards"
        assert seat.total_contribution == state.total_contribution, f"seat {state.seat_number} total contribution"
        assert seat.street_contribution == state.street_contribution, f"seat {state.seat_number} street contribution"
        assert seat.folded == state.folded, f"seat {state.seat_number} folded"
        if not settled:
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


@pytest.fixture
def replay_facts() -> Callable[..., ReplayedFacts]:
    return _replay_facts

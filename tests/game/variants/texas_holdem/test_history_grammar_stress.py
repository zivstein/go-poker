"""Deterministic stress of the structure of recorded histories (ADR 0004 §3, §4, §8).

Random hands are played to settlement through `begin_hand` and `act` only, deciding every showdown with random SHOW and
MUCK. After every call the history must extend the previous one (the earlier value never changes) and, after the hand,
an independent single-pass check walks the whole history with its own chip accounting. It never reads engine state to
decide what an event should be, except the live hand's actor before each action: the recorded blinds, amounts, all-in
flags, returns, round starts and completions, street deals, showdown kind and order, decisions and the settlement's
payers and ranked seats must follow from the stakes, starting stacks and requested actions and decisions alone. The
history ends with exactly one `HandSettled`, and the orchestrated order (a showdown starts right after the betting that
decided it, before any runout street) is checked here and by the shared `assert_orchestrated_order`. The seeds are
fixed, so a failure names the seed that reproduces it, and counters keep the seed set honest.
"""

import random
from collections import Counter
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindPost,
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
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor

STAKES = Stakes(small_blind=5, big_blind=10)
SEEDS = range(400)
STREETS = (Street.FLOP, Street.TURN, Street.RIVER)
CARDS_PER_STREET = {Street.FLOP: 3, Street.TURN: 1, Street.RIVER: 1}


def random_hand(rng: random.Random) -> PokerHand:
    seats = tuple(sorted(rng.sample(range(1, 10), rng.randint(2, 6))))
    assignments = assign_hand_seats(seats, rng.choice(seats))
    stack_range = rng.choice([(1, 40), (10, 300), (500, 1500)])
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat}", stack=rng.randint(*stack_range), status=PlayerStatus.READY),
            seat_number=seat,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat, assignment in assignments.items()
    )
    deck = Deck()
    deck.shuffle(_rng=random.Random(f"deck-{rng.random()}"))
    return PokerHand(players=players, deck=deck, number=1)


def random_action(rng: random.Random, hand: PokerHand, raise_chance: float) -> Action:
    """A random legal action; a bet or raise is offered only with probability `raise_chance`, so passive seeds reach
    river showdowns that nobody is all-in for."""
    legal = legal_actions(hand)
    options = [Action(ActionType.FOLD)]
    if legal.can_check:
        options += [Action(ActionType.CHECK)] * 3
    if legal.can_call:
        options += [Action(ActionType.CALL)] * 3
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    offer_raise = rng.random() < raise_chance
    if offer_raise and legal.short_all_in_target is not None:
        options.append(Action(kind, legal.short_all_in_target))
    elif offer_raise and legal.min_full_target is not None and legal.max_target is not None:
        options.append(Action(kind, legal.min_full_target))
        options.append(Action(kind, rng.randint(legal.min_full_target, legal.max_target)))
        options.append(Action(kind, legal.max_target))
    return rng.choice(options)


class Walk:
    """A single-pass reading of a history with its own accounting. Each seat's chips are tracked from the starting
    stacks, and the grammar of the events is checked as they are read."""

    def __init__(self, history: HandHistory, counters: Counter[str]) -> None:
        started = history.events[0]
        assert isinstance(started, HandStarted)
        self.counters = counters
        self.seats = [participant.seat for participant in started.participants]
        self.stack = {p.seat: p.starting_stack for p in started.participants}
        self.starting_total = sum(self.stack.values())
        self.in_front = dict.fromkeys(self.seats, 0)
        self.total = dict.fromkeys(self.seats, 0)
        self.folded: set[int] = set()
        self.all_in: set[int] = set()
        self.blind_of = {p.seat: p.blind for p in started.participants}
        self.current_bet = 0
        self.open = False
        self.betting_street: Street | None = None
        self.dealt_street = Street.PREFLOP
        self.completed: list[Street] = []
        self.hole_dealt = False
        self.last_aggressor: int | None = None
        self.showdown_kind: ShowdownKind | None = None
        self.showdown_order: tuple[int, ...] = ()
        self.decisions: list[tuple[int, ShowdownAction]] = []
        self.runout: list[Street] = []  # the streets dealt after the showdown started
        self.dealt_at_showdown = Street.PREFLOP
        self.completed_at_showdown = Street.PREFLOP
        self.settled = False
        events = history.events[1:]
        self.read(events)

    def commit(self, seat: int, chips: int) -> None:
        assert 0 < chips <= self.stack[seat]
        self.stack[seat] -= chips
        self.in_front[seat] += chips
        self.total[seat] += chips
        if self.stack[seat] == 0:
            self.all_in.add(seat)

    def read(self, events: tuple[object, ...]) -> None:
        blinds = events[0]
        assert isinstance(blinds, BlindsPosted) and blinds.stakes == STAKES
        self.read_blinds(blinds)
        self.open = True
        self.betting_street = Street.PREFLOP
        for index, event in enumerate(events[1:], start=1):
            previous = events[index - 1]
            following = events[index + 1] if index + 1 < len(events) else None
            self.read_event(event, previous, following)

    def read_blinds(self, blinds: BlindsPosted) -> None:
        assert [post.blind for post in blinds.posts] == [Blind.SMALL, Blind.BIG]
        for post, amount in zip(blinds.posts, (STAKES.small_blind, STAKES.big_blind), strict=True):
            assert isinstance(post, BlindPost) and self.blind_of[post.seat] is post.blind
            assert post.chips == min(amount, self.stack[post.seat])
            self.commit(post.seat, post.chips)
            assert post.all_in == (post.seat in self.all_in)
        self.current_bet = STAKES.big_blind

    def read_event(self, event: object, previous: object, following: object) -> None:
        match event:
            case HoleCardsDealt(hole_cards=dealt):
                assert not self.hole_dealt
                self.hole_dealt = True
                assert [held.seat for held in dealt] == self.seats
                assert all(len(held.cards) == 2 for held in dealt)
                assert not isinstance(previous, StreetDealt)
            case StreetDealt(street=street, burned=burned, cards=cards):
                assert not self.open, "a street is dealt only once its round completed"
                assert self.hole_dealt and not self.settled
                if self.showdown_kind is not None:
                    assert self.showdown_kind is ShowdownKind.ALL_IN and not self.decisions, "only a runout follows"
                    assert isinstance(previous, ShowdownStarted | StreetDealt)
                expected = (
                    STREETS[STREETS.index(self.dealt_street) + 1] if self.dealt_street in STREETS else Street.FLOP
                )
                assert street is expected
                assert len(burned) == 1 and len(cards) == CARDS_PER_STREET[street]
                self.dealt_street = street
                if self.showdown_kind is not None:
                    self.runout.append(street)
            case BettingRoundStarted(street=street):
                assert not self.open and isinstance(previous, StreetDealt) and previous.street is street
                self.open = True
                self.betting_street = street
                self.current_bet = 0
                self.last_aggressor = None
            case ActionTaken(seat=seat, action=action, chips=chips, all_in=all_in):
                assert self.open and seat not in self.folded and seat not in self.all_in
                self.read_action(seat, action, chips, all_in)
                self.counters["actions"] += 1
            case ChipsReturned(seat=seat, chips=chips):
                assert self.open and isinstance(previous, ActionTaken | BlindsPosted)
                assert isinstance(following, BettingRoundCompleted)
                assert 0 < chips <= self.in_front[seat]
                top = max(self.total.values())
                assert self.total[seat] == top and sorted(self.total.values())[-2] == top - chips
                self.stack[seat] += chips
                self.in_front[seat] -= chips
                self.total[seat] -= chips
                self.all_in.discard(seat)
                self.counters["returns"] += 1
            case BettingRoundCompleted(street=street):
                assert self.open and street is self.betting_street
                assert street not in self.completed
                self.completed.append(street)
                self.open = False
                self.in_front = dict.fromkeys(self.seats, 0)
                self.counters["completions"] += 1
            case ShowdownStarted(kind=kind, order=order):
                self.read_showdown_start(kind, order, previous)
            case ShowdownDecided(seat=seat, action=action):
                assert self.showdown_kind is ShowdownKind.INTERACTIVE and not self.settled
                assert not self.showdown_complete() and seat == self.showdown_order[len(self.decisions)]
                assert isinstance(action, ShowdownAction)
                self.decisions.append((seat, action))
                self.counters["decisions"] += 1
            case HandSettled(settlement=settlement):
                assert following is None and not self.settled
                self.read_settlement(settlement)
            case _:
                raise AssertionError(f"unexpected event {event!r}")

    def live(self) -> list[int]:
        """The live seats in canonical order: clockwise from the first seat left of the button, the button last."""
        canonical = [*self.seats[1:], *self.seats[:1]]
        return [seat for seat in canonical if seat not in self.folded]

    def showdown_complete(self) -> bool:
        if self.showdown_kind is ShowdownKind.ALL_IN:
            return True
        return len(self.decisions) == len(self.showdown_order) or len(self.contenders()) == 1

    def contenders(self) -> set[int]:
        mucked = {seat for seat, action in self.decisions if action is ShowdownAction.MUCK}
        return set(self.showdown_order) - mucked

    def read_showdown_start(self, kind: ShowdownKind, order: tuple[int, ...], previous: object) -> None:
        live = self.live()
        assert self.showdown_kind is None and len(live) >= 2 and not self.open
        assert (kind is ShowdownKind.ALL_IN) == bool(set(live) & self.all_in), "the kind follows the live all-ins"
        if kind is ShowdownKind.ALL_IN:
            assert isinstance(previous, BettingRoundCompleted | HoleCardsDealt)
            assert order == tuple(live), "an all-in showdown stores every live seat in canonical order"
            self.counters["all_in_showdown"] += 1
        else:
            assert previous == BettingRoundCompleted(Street.RIVER) and self.dealt_street is Street.RIVER
            start = live.index(self.last_aggressor) if self.last_aggressor is not None else 0
            assert order == (*live[start:], *live[:start]), "decisions start with the river's last aggressor"
            self.counters["interactive_showdown"] += 1
        self.showdown_kind, self.showdown_order = kind, order
        self.dealt_at_showdown, self.completed_at_showdown = self.dealt_street, self.completed[-1]

    def read_settlement(self, settlement: Any) -> None:
        """The settlement's payers and ranked seats follow from the walk alone, and it conserves the chips."""
        live = self.live()
        if self.showdown_kind is None:
            assert len(live) == 1, "only an uncontested hand settles without a showdown"
            contenders, shown = set(live), set[int]()
            self.counters["uncontested"] += 1
        else:
            assert self.showdown_complete() and self.dealt_street is Street.RIVER
            contenders = self.contenders()
            if self.showdown_kind is ShowdownKind.ALL_IN:
                shown = set(live)
                streets = list(Street)
                remaining = streets[streets.index(self.dealt_at_showdown) + 1 :]
                assert self.runout == remaining, "the runout deals every remaining street, after the showdown start"
                assert not self.decisions
                self.counters["river_all_in"] += not remaining
                if remaining:
                    self.counters[f"runout_after_{self.completed_at_showdown.name.lower()}"] += 1
            else:
                shown = {seat for seat, action in self.decisions if action is ShowdownAction.SHOW}
                self.counters["interactive_with_show"] += bool(shown)
                self.counters["one_contender_finish"] += len(self.decisions) < len(self.showdown_order)
                self.counters["all_muck_but_one"] += len(contenders) == 1 and not shown
        payouts = settlement.payouts
        assert set(payouts) <= contenders and payouts
        assert [seat for seat, _ in settlement.showdown_ranks] == [seat for seat in self.seats if seat in shown]
        assert sum(award.pot.amount for award in settlement.pot_awards) == sum(self.total.values())
        for seat, chips in payouts.items():
            self.stack[seat] += chips
            self.all_in.discard(seat)
        assert sum(self.stack.values()) == self.starting_total
        self.settled = True
        self.counters["side_pots"] += len(settlement.pot_awards) > 1
        self.counters["odd_chip_split"] += any(
            len({chips for _, chips in award.shares}) > 1 for award in settlement.pot_awards
        )

    def read_action(self, seat: int, action: Action, chips: int, all_in: bool) -> None:
        match action.type:
            case ActionType.FOLD:
                assert chips == 0 and not all_in
                self.folded.add(seat)
            case ActionType.CHECK:
                assert chips == 0 and not all_in
            case ActionType.CALL:
                # At most the nominal bet less what is in front: opponents' stacks can cap what a call is owed.
                assert 0 < chips <= min(self.current_bet - self.in_front[seat], self.stack[seat])
                self.commit(seat, chips)
            case ActionType.BET | ActionType.RAISE:
                assert action.amount is not None
                assert chips == action.amount - self.in_front[seat], "a bet or raise adds to what is in front"
                self.commit(seat, chips)
                self.current_bet = max(self.current_bet, action.amount)
                self.last_aggressor = seat
                self.counters["bets" if action.type is ActionType.BET else "raises"] += 1
                self.counters["aggressive_all_ins"] += all_in
        assert all_in == (seat in self.all_in)

    def finish(self) -> None:
        """Every round that began ended exactly once and nothing is owed back."""
        assert self.open or self.completed
        if not self.open:
            assert self.completed[-1] is self.betting_street
        assert len(set(self.completed)) == len(self.completed)


def play_seed(
    seed: int,
    counters: Counter[str],
    fold_history: Callable[[HandHistory], Any],
    assert_orchestrated_order: Callable[[HandHistory], None],
) -> None:
    rng = random.Random(seed)
    hand = random_hand(rng)
    show_chance = rng.choice([0.1, 0.5, 0.9])
    raise_chance = rng.choice([0.03, 0.3, 1.0])
    begin_hand(hand, STAKES)
    taken = hand.history
    assert taken.is_complete == (hand.settlement is not None)  # blinds alone can settle a hand
    for _ in range(500):
        seat = current_actor(hand)
        if seat is None:
            break
        if hand.showdown is not None:
            act(hand, seat, ShowdownAction.SHOW if rng.random() < show_chance else ShowdownAction.MUCK)
        else:
            act(hand, seat, random_action(rng, hand, raise_chance))
        later = hand.history
        assert later.events[: len(taken.events)] == taken.events, f"seed {seed}: an earlier event changed"
        assert len(later.events) > len(taken.events)
        assert later.is_complete == (hand.settlement is not None)
        taken = later
    assert hand.settlement is not None, f"seed {seed}: the hand did not settle"
    history = hand.history
    assert history.is_complete and history.settlement == hand.settlement
    assert isinstance(history.events[-1], HandSettled)
    assert sum(isinstance(event, HandSettled) for event in history.events) == 1
    counters["hands"] += 1
    walk = Walk(history, counters)
    walk.finish()
    assert walk.settled
    assert_orchestrated_order(history)
    assert fold_history(history).settlement == hand.settlement
    counters["streets_completed"] += len(walk.completed)
    counters["blinds_complete_round"] += isinstance(history.events[2], ChipsReturned | BettingRoundCompleted)
    assert walk.seats == [state.seat_number for state in hand.players]
    for state in hand.players:  # the independent accounting equals the live stacks, contributions and folds
        assert walk.stack[state.seat_number] == state.player.stack, f"seed {seed}: seat {state.seat_number} stack"
        assert walk.total[state.seat_number] == state.total_contribution
        assert (state.seat_number in walk.folded) == state.folded


@pytest.mark.parametrize("seed", SEEDS)
def test_histories_of_random_hands_follow_their_grammar(
    seed: int, fold_history: Callable[..., Any], assert_orchestrated_order: Callable[[HandHistory], None]
) -> None:
    play_seed(seed, Counter(), fold_history, assert_orchestrated_order)


def test_the_seeds_reach_every_event_shape(
    fold_history: Callable[..., Any], assert_orchestrated_order: Callable[[HandHistory], None]
) -> None:
    counters: Counter[str] = Counter()
    for seed in SEEDS:
        play_seed(seed, counters, fold_history, assert_orchestrated_order)
    required = {
        "hands": 400,
        "actions": 1000,
        "returns": 100,
        "completions": 600,
        "blinds_complete_round": 5,
        "all_in_showdown": 100,
        "runout_after_preflop": 50,
        "runout_after_flop": 25,
        "runout_after_turn": 10,
        "river_all_in": 10,
        "interactive_showdown": 20,
        "decisions": 40,
        "interactive_with_show": 15,
        "one_contender_finish": 8,
        "all_muck_but_one": 8,
        "uncontested": 60,
        "side_pots": 100,
        "odd_chip_split": 3,
        "bets": 60,
        "raises": 130,
        "aggressive_all_ins": 80,
    }
    shortfalls = {key: (counters[key], need) for key, need in required.items() if counters[key] < need}
    assert not shortfalls, f"the seed set no longer reaches enough of: {shortfalls} (got {dict(counters)})"

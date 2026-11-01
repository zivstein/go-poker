"""Deterministic stress of the structure of recorded histories (ADR 0004 §3, §4, §8).

Random hands are played to the end of their betting through `begin_hand` and `act` only. After every call the history
must extend the previous one (the earlier value never changes) and, after the hand, an independent single-pass check
walks the whole history with its own chip accounting. It never reads engine state to decide what an event should be,
except the live hand's actor before each action: the recorded blinds, amounts, all-in flags, returns, round starts and
completions, and street deals must follow from the stakes, starting stacks and requested actions alone. The seeds are
fixed, so a failure names the seed that reproduces it, and counters keep the seed set honest.
"""

import random
from collections import Counter

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
    HandStarted,
    HoleCardsDealt,
    StreetDealt,
)
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.position_assignment import assign_hand_seats
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


def random_action(rng: random.Random, hand: PokerHand) -> Action:
    legal = legal_actions(hand)
    options = [Action(ActionType.FOLD)]
    if legal.can_check:
        options += [Action(ActionType.CHECK)] * 3
    if legal.can_call:
        options += [Action(ActionType.CALL)] * 3
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        options.append(Action(kind, legal.short_all_in_target))
    elif legal.min_full_target is not None and legal.max_target is not None:
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
                assert self.hole_dealt
                expected = (
                    STREETS[STREETS.index(self.dealt_street) + 1] if self.dealt_street in STREETS else Street.FLOP
                )
                assert street is expected
                assert len(burned) == 1 and len(cards) == CARDS_PER_STREET[street]
                self.dealt_street = street
            case BettingRoundStarted(street=street):
                assert not self.open and isinstance(previous, StreetDealt) and previous.street is street
                self.open = True
                self.betting_street = street
                self.current_bet = 0
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
            case _:
                raise AssertionError(f"unexpected event {event!r}")

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
        assert all_in == (seat in self.all_in)

    def finish(self) -> None:
        """Every round that began ended exactly once and nothing is owed back."""
        assert self.open or self.completed
        if not self.open:
            assert self.completed[-1] is self.betting_street
        assert len(set(self.completed)) == len(self.completed)


def play_seed(seed: int, counters: Counter[str]) -> None:
    rng = random.Random(seed)
    hand = random_hand(rng)
    begin_hand(hand, STAKES)
    taken = hand.history
    for _ in range(500):
        seat = current_actor(hand)
        if seat is None or hand.showdown is not None:
            break
        act(hand, seat, random_action(rng, hand))
        later = hand.history
        assert later.events[: len(taken.events)] == taken.events, f"seed {seed}: an earlier event changed"
        assert len(later.events) > len(taken.events)
        taken = later
    counters["hands"] += 1
    walk = Walk(hand.history, counters)
    walk.finish()
    counters["streets_completed"] += len(walk.completed)
    counters["runout"] += (
        any(isinstance(e, StreetDealt) for e in hand.history.events) and walk.completed[-1] is not Street.RIVER
    )
    counters["blinds_complete_round"] += isinstance(hand.history.events[2], ChipsReturned | BettingRoundCompleted)
    assert walk.seats == [state.seat_number for state in hand.players]
    for state in hand.players:  # the independent accounting equals the live stacks, contributions and folds
        if hand.settlement is None:  # a settled hand's stacks also hold the payout, which is not recorded yet
            assert walk.stack[state.seat_number] == state.player.stack, f"seed {seed}: seat {state.seat_number} stack"
        assert walk.total[state.seat_number] == state.total_contribution
        assert (state.seat_number in walk.folded) == state.folded


@pytest.mark.parametrize("seed", SEEDS)
def test_histories_of_random_hands_follow_their_grammar(seed: int) -> None:
    play_seed(seed, Counter())


def test_the_seeds_reach_every_event_shape() -> None:
    counters: Counter[str] = Counter()
    for seed in SEEDS:
        play_seed(seed, counters)
    required = {
        "hands": 400,
        "actions": 1000,
        "returns": 100,
        "completions": 600,
        "runout": 20,
        "blinds_complete_round": 5,
    }
    for key, minimum in required.items():
        assert counters[key] >= minimum, f"{key}: {counters[key]} < {minimum}"

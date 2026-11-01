"""Shared betting test helpers, exposed as fixtures because test modules cannot import each other."""

import copy
from collections.abc import Callable
from itertools import pairwise
from typing import Any

import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.actions import AMOUNT_ACTION_TYPES, Action
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import is_round_complete, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_history import HandHistory
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

STAKES = Stakes(small_blind=5, big_blind=10)

# stack, street contribution, total contribution, folded, all-in
type PlayerSnapshot = tuple[int, int, int, bool, bool]
type HandSnapshot = tuple[Street, dict[int, PlayerSnapshot], BettingState | None, HandHistory]


def _make_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """Build a hand clockwise from the button with an unshuffled deck, each seat's player holding the given stack."""
    assignments = assign_hand_seats(tuple(stacks), button_seat_number)
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=stacks[seat_number], status=PlayerStatus.READY),
            seat_number=seat_number,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat_number, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=Deck(), number=1)


def _started_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """A hand with its blinds posted and preflop betting initialized at STAKES."""
    hand = _make_hand(stacks, button_seat_number)
    initialize_betting(hand, STAKES)
    return hand


def _by_seat(hand: PokerHand) -> dict[int, HandPlayerState]:
    return {hand_player.seat_number: hand_player for hand_player in hand.players}


def _betting(hand: PokerHand) -> BettingState:
    assert hand.betting is not None
    return hand.betting


def _player_snapshot(hand: PokerHand) -> dict[int, PlayerSnapshot]:
    return {
        hand_player.seat_number: (
            hand_player.player.stack,
            hand_player.street_contribution,
            hand_player.total_contribution,
            hand_player.folded,
            hand_player.all_in,
        )
        for hand_player in hand.players
    }


def _play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    """Apply each (seat number, action) in order."""
    for seat_number, action in actions:
        apply_action(hand, seat_number, action)


def _hand_snapshot(hand: PokerHand) -> HandSnapshot:
    """Everything betting may change: the street, each player's chips and flags, a copy of the betting state and the
    history."""
    return hand.street, _player_snapshot(hand), copy.deepcopy(hand.betting), hand.history


class CheckedHand:
    """Drives one hand through real betting and dealing operations, asserting the betting invariants after each step,
    and that the facts replayed from the hand's history equal the live hand."""

    def __init__(self, hand: PokerHand, replay_facts: Callable[..., Any]) -> None:
        self.hand = hand
        self.replay_facts = replay_facts
        # Every action requested so far, in order; the history must replay exactly these.
        self.actions: list[tuple[int, Action]] = []
        # Recorded before betting starts: every player's chips at the start of the hand.
        self.starting_chips = {hand_player.seat_number: hand_player.player.stack for hand_player in hand.players}
        # The seats that have acted in the current betting round; posting a blind is not an action.
        self.acted: set[int] = set()

    @property
    def betting(self) -> BettingState:
        assert self.hand.betting is not None
        return self.hand.betting

    @property
    def seats(self) -> dict[int, HandPlayerState]:
        return {hand_player.seat_number: hand_player for hand_player in self.hand.players}

    def start(self, stakes: Stakes) -> None:
        """The intended hand start: initialize betting (post the blinds), then deal the hole cards."""
        initialize_betting(self.hand, stakes)
        deal_hole_cards(self.hand)
        self.acted = set()
        # The preflop round starts at the full big blind, whatever the blinds actually posted.
        assert (self.betting.current_bet, self.betting.last_full_raise_size) == (stakes.big_blind, stakes.big_blind)
        assert self.betting.last_aggressor is None
        self.check()

    def act(self, *actions: tuple[int, Action]) -> None:
        for seat_number, action in actions:
            legal = legal_actions(self.hand)
            bet_before = self.betting.current_bet
            full_raise_before = self.betting.last_full_raise_size
            aggressor_before = self.betting.last_aggressor
            apply_action(self.hand, seat_number, action)
            self.actions.append((seat_number, action))
            self.acted.add(seat_number)
            self._check_betting_context(action, legal, bet_before, full_raise_before)
            # Only a bet or raise, a short all-in one included, makes its actor the round's last aggressor.
            assert self.betting.last_aggressor == (
                seat_number if action.type in AMOUNT_ACTION_TYPES else aggressor_before
            )
            self.check()

    def next_street(self) -> None:
        """Deal the next street, then start its betting round."""
        deal_next_street(self.hand)
        start_betting_round(self.hand)
        self.acted = set()
        # A later round starts unopened, with the big-blind minimum restored.
        assert (self.betting.current_bet, self.betting.last_full_raise_size) == (0, self.betting.stakes.big_blind)
        assert self.betting.last_aggressor is None
        self.check()

    def _check_betting_context(
        self, action: Action, legal: LegalActions, bet_before: int, full_raise_before: int
    ) -> None:
        """Only a bet or raise moves the current bet, and only a full one changes the last full raise size, which
        never shrinks within a round."""
        betting = self.betting
        if action.type in AMOUNT_ACTION_TYPES:
            assert betting.current_bet == action.amount
            if action.amount == legal.short_all_in_target:
                assert betting.last_full_raise_size == full_raise_before
            else:
                assert betting.last_full_raise_size >= full_raise_before
        else:
            assert (betting.current_bet, betting.last_full_raise_size) == (bet_before, full_raise_before)

    def check(self) -> None:
        players = self.hand.players
        betting = self.betting
        assert {hp.seat_number: hp.player.stack + hp.total_contribution for hp in players} == self.starting_chips
        assert all(hp.all_in == (hp.player.stack == 0) for hp in players)
        assert all(hp.street_contribution <= hp.total_contribution for hp in players)
        assert max(hp.street_contribution for hp in players) <= betting.current_bet
        assert betting.acted_at_bet.keys() == self.acted  # exactly the seats that have acted in this round
        assert all(acted_at <= betting.current_bet for acted_at in betting.acted_at_bet.values())
        assert not {hp.seat_number for hp in players if hp.folded or hp.all_in} & betting.pending_actors
        assert betting.current_actor is None or betting.current_actor in betting.pending_actors
        assert (betting.current_actor is None) == (not betting.pending_actors)
        self._check_accounting()
        assert self.replay_facts(self.hand).actions == self.actions

        before = _hand_snapshot(self.hand)
        legal_actions(self.hand)
        middle_pot(self.hand)
        pots(self.hand)
        assert _hand_snapshot(self.hand) == before  # legal actions and pots are derived, never stored

    def _check_accounting(self) -> None:
        """Every committed chip is either in front of a player or in the middle, and the pots layer the middle."""
        players = self.hand.players
        middle = middle_pot(self.hand)
        assert middle + sum(hp.street_contribution for hp in players) == sum(hp.total_contribution for hp in players)

        layers = pots(self.hand)
        assert sum(pot.amount for pot in layers) == middle
        collected = {hp.seat_number: hp.total_contribution - hp.street_contribution for hp in players}
        folded = {hp.seat_number for hp in players if hp.folded}
        levels = sorted({chips for chips in collected.values() if chips > 0})
        assert len(layers) == len(levels)
        previous_eligible = {hp.seat_number for hp in players}
        for pot, (previous, level) in zip(layers, pairwise([0, *levels]), strict=True):
            assert sum(chips > previous for chips in collected.values()) >= 2  # never a one-contributor pot
            assert pot.amount > 0
            assert pot.eligible_seats
            assert not pot.eligible_seats & folded
            assert all(collected[seat_number] >= level for seat_number in pot.eligible_seats)
            assert pot.eligible_seats <= previous_eligible
            previous_eligible = set(pot.eligible_seats)

        # What a live player can win: from each participant, as many collected chips as the player has collected.
        for hp in players:
            if not hp.folded:
                winnable = sum(min(chips, collected[hp.seat_number]) for chips in collected.values())
                assert sum(pot.amount for pot in layers if hp.seat_number in pot.eligible_seats) == winnable

        if is_round_complete(self.betting):  # a completed round is collected: nothing in front, nothing unmatched
            assert all(hp.street_contribution == 0 for hp in players)
            highest = max(hp.total_contribution for hp in players)
            assert sum(hp.total_contribution == highest for hp in players) >= 2
            # A player who can still bet has matched the highest total contribution.
            assert all(hp.total_contribution == highest for hp in players if not hp.folded and not hp.all_in)


@pytest.fixture
def stakes() -> Stakes:
    return STAKES


@pytest.fixture
def make_hand() -> Callable[[dict[int, int], int], PokerHand]:
    return _make_hand


@pytest.fixture
def started_hand() -> Callable[[dict[int, int], int], PokerHand]:
    return _started_hand


@pytest.fixture
def by_seat() -> Callable[[PokerHand], dict[int, HandPlayerState]]:
    return _by_seat


@pytest.fixture
def betting() -> Callable[[PokerHand], BettingState]:
    return _betting


@pytest.fixture
def player_snapshot() -> Callable[[PokerHand], dict[int, PlayerSnapshot]]:
    return _player_snapshot


@pytest.fixture
def play() -> Callable[..., None]:
    return _play


@pytest.fixture
def hand_snapshot() -> Callable[[PokerHand], HandSnapshot]:
    return _hand_snapshot


@pytest.fixture
def checked(replay_facts: Callable[..., Any]) -> Callable[[PokerHand], CheckedHand]:
    return lambda hand: CheckedHand(hand, replay_facts)

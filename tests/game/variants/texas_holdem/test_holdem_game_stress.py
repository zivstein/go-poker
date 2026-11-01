"""Seeded whole games driven only through `HoldemGame.start`, `next_hand` and `act`, with table churn between hands.

`test_hand_flow_stress` and `test_hand_stress` own the betting and showdown matrices, so this test only covers what a
continuous game adds: what happens from one hand to the next. The driver asks `current_actor` and `legal_actions`
(reads) who must act and what is legal, plays simple random legal moves, and between hands seats new waiting
players, sits players out and back to ready, and stands up busted (and now and then solvent) players. During a hand
it also tries `next_hand`, `start` and an `act` on the previous settled hand, each of which must be rejected and
change nothing.

Checked for every hand: `start` and `next_hand` return `game.hand`, settled or waiting for a decision; the button is the
next ready player with chips clockwise from the previous button seat (computed here independently); every ready player
with chips plays, and nobody else but a waiting player who entered outside the button and small blind; busted and
sitting-out players never play and keep their statuses; the stakes are the game's; the chips of the seated players are
conserved from hand to hand, adjusted exactly for players who sit down or stand up with chips. Every hand's history
starts with `HandStarted`, numbered 1, 2, 3, ... with no gap (a rejected call consumes no number), and its participants
are written out here independently from the live players at the start (id, seat, position, blind, and the stack before
any blind); that first event never changes. After each start and each act, the facts replayed from the history (see
`replay_facts`, stacks, showdown and settlement included) equal the live hand, the history holds exactly the betting
actions played and it follows the orchestrated presentation order. When a hand settles its whole history is captured as
an independent copy, together with the facts folded from it and the live stacks. The game retains nothing, but this
driver retains every settled hand: after the later hands, churn and rejections every earlier settled history still
equals its copy, and after each later hand it is folded again (see `fold_history`) and gives the same facts, final
stacks and settlement, although the live players' stacks have long moved on. A game ends when the lifecycle reports
fewer than two possible players, or at a hand cap. After an `InvalidPlayerCount` some games seat a new player and go
on, since there is no game-over state.

The seeds are fixed, so a failure names the seed that reproduces it. The counters keep the seed set honest.
"""

import copy
import random
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import NOTHING_LEGAL, LegalActions, legal_actions
from go_poker.game.betting.pots import middle_pot
from go_poker.game.betting.stakes import Stakes
from go_poker.game.game_lifecycle import GameAlreadyStartedError
from go_poker.game.hand_history import HandHistory, HandParticipant, HandStarted
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.position import InvalidPlayerCount, Position
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem import hand_flow
from go_poker.game.variants.texas_holdem.game import HandInProgressError, HoldemGame
from go_poker.game.variants.texas_holdem.hand_flow import current_actor
from go_poker.game.variants.texas_holdem.hand_strength import hand_strength

STAKES = Stakes(small_blind=5, big_blind=10)
SEEDS = range(80)
MAX_HANDS = 30
MAX_STEPS = 500  # far more calls than any generated hand needs
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
READY = PlayerStatus.READY
WAITING = PlayerStatus.WAITING
SITTING_OUT = PlayerStatus.SITTING_OUT


def seated(table: Table) -> dict[int, Player]:
    return {seat.number: seat.player for seat in table.occupied_seats if seat.player is not None}


def total_stacks(table: Table) -> int:
    return sum(player.stack for player in seated(table).values())


def ready_with_chips(table: Table) -> list[int]:
    return [number for number, player in seated(table).items() if player.status is READY and player.stack > 0]


def expected_button(ready: list[int], previous: int) -> int:
    """The next ready seat clockwise from the previous button seat, which anchors the search even if it left."""
    after = sorted(seat for seat in ready if seat > previous)
    return after[0] if after else min(ready)


def hand_state(hand: PokerHand, *, with_stacks: bool = True) -> dict[str, Any]:
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "showdown": hand.showdown,
        "number": hand.number,
        "history": hand.history,
        "players": [
            (
                state.seat_number,
                state.player.stack if with_stacks else None,
                state.folded,
                state.all_in,
                state.street_contribution,
                state.total_contribution,
                list(state.hole_cards),
            )
            for state in hand.players
        ],
    }


def world(game: HoldemGame, table: Table) -> tuple[Any, ...]:
    """The button, every seated player and the game's hand with its state."""
    players = [(number, player, player.stack, player.status) for number, player in seated(table).items()]
    hand = game.hand
    return table.button_seat_number, players, hand, None if hand is None else hand_state(hand)


def betting_action(rng: random.Random, legal: LegalActions, aggression: int) -> Action:
    options: list[tuple[Action, int]] = [(CHECK, 6)] if legal.can_check else [(FOLD, 3)]
    if legal.can_call:
        options.append((CALL, 6))
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        options.append((Action(kind, legal.short_all_in_target), aggression))
    elif legal.min_full_target is not None and legal.max_target is not None:
        options.append((Action(kind, legal.min_full_target), aggression))
        options.append((Action(kind, legal.max_target), max(1, aggression // 2)))
    return rng.choices([action for action, _ in options], [weight for _, weight in options])[0]


@dataclass(frozen=True)
class SettledRecord:
    """A settled hand as captured at settlement: an independent copy of its history, the facts folded from it and the
    live stacks, none of which may change afterwards."""

    history: HandHistory
    facts: Any
    stacks: dict[int, int]


class Driver:
    """One seeded game: the table, the game, the expected chip total and the counters."""

    def __init__(self, seed: int, counters: Counter[str], checks: HistoryChecks) -> None:
        self.seed = seed
        self.checks = checks
        self.rng = random.Random(seed)
        self.counters = counters
        self.table = Table(self.rng.randint(3, 9))
        self.game = HoldemGame(self.table, STAKES)
        self.aggression = self.rng.choice([1, 4, 8])
        self.short = self.rng.random() < 0.6  # short stacks bust often
        self.total = 0
        self.previous: PokerHand | None = None
        self.previous_state: dict[str, Any] = {}
        self.started = 0  # hands returned so far; the next hand must be numbered one more
        # Each hand with its independently written HandStarted, and its whole history copy once it has settled.
        self.recorded: list[tuple[PokerHand, HandStarted, SettledRecord | None]] = []
        self.betting_actions: list[tuple[int, Action]] = []  # the betting actions played in the current hand
        for seat in self.rng.sample(range(1, self.table.max_seats + 1), self.rng.randint(2, self.table.max_seats)):
            self.sit_down(seat)

    # --- table churn ---------------------------------------------------------------------------------------------

    def empty_seats(self) -> list[int]:
        return [n for n in range(1, self.table.max_seats + 1) if not self.table.get_seat(n).is_occupied]

    def sit_down(self, seat: int) -> None:
        stack = self.rng.randint(15, 250) if self.short else self.rng.randint(200, 2_000)
        self.table.sit_in(Player(f"P{seat}-{self.rng.random()}", stack=stack), seat)
        self.total += stack

    def churn(self) -> None:
        """Between hands: seat newcomers, sit players out and back, stand up busted (and sometimes solvent) players."""
        rng = self.rng
        empty = self.empty_seats()
        if empty and rng.random() < 0.3:
            self.sit_down(rng.choice(empty))
            self.counters["newcomers"] += 1
        for number, player in seated(self.table).items():
            roll = rng.random()
            solvent_ready = len(ready_with_chips(self.table)) > 1 or number not in ready_with_chips(self.table)
            if player.stack == 0 and roll < 0.5:
                self.table.stand_up(number)
                self.counters["stood_up_busted"] += 1
            elif player.status is SITTING_OUT and roll < 0.4:
                player.status = READY
                self.counters["back_from_sitting_out"] += 1
            elif player.status is not SITTING_OUT and player.stack > 0 and solvent_ready:
                if roll < 0.08:
                    player.status = SITTING_OUT
                    self.counters["sat_out"] += 1
                elif roll > 0.99:
                    self.table.stand_up(number)
                    self.total -= player.stack
                    self.counters["stood_up_solvent"] += 1

    # --- mischief ------------------------------------------------------------------------------------------------

    def probe_rejections(self) -> None:
        """Calls that must fail while the current hand is unsettled, each changing nothing."""
        before = world(self.game, self.table)
        with pytest.raises(HandInProgressError):
            self.game.next_hand()
        assert world(self.game, self.table) == before
        with pytest.raises(GameAlreadyStartedError):
            self.game.start(self.forbidden_chooser)
        assert world(self.game, self.table) == before
        self.counters["rejections_mid_hand"] += 1

    @staticmethod
    def forbidden_chooser(seats: tuple[int, ...]) -> int:
        raise AssertionError("a rejected start must not ask for a button")

    def probe_previous_hand(self) -> None:
        if self.previous is None:
            return
        with pytest.raises(HandAlreadySettledError):
            hand_flow.act(self.previous, self.rng.choice([1, 99]), self.rng.choice([FOLD, CHECK, ShowdownAction.SHOW]))
        assert hand_state(self.previous, with_stacks=False) == self.previous_state
        self.counters["rejections_previous_hand"] += 1

    # --- checks --------------------------------------------------------------------------------------------------

    def assert_chips_conserved(self, hand: PokerHand) -> None:
        in_play = total_stacks(self.table)
        if hand.settlement is None:
            in_play += sum(state.street_contribution for state in hand.players) + middle_pot(hand)
        assert in_play == self.total, f"seed {self.seed}: chips are not conserved"

    def assert_awaiting_or_settled(self, hand: PokerHand) -> None:
        assert hand is self.game.hand
        self.assert_chips_conserved(hand)
        replayed = self.checks.replay_facts(hand)
        assert replayed.actions == self.betting_actions, f"seed {self.seed}: the history lost an action"
        self.checks.assert_orchestrated_order(hand.history)
        if hand.settlement is not None:
            assert current_actor(hand) is None
            return
        actor = current_actor(hand)
        assert actor is not None
        betting = hand.betting
        assert betting is not None
        if betting.current_actor is not None:
            assert legal_actions(hand) != NOTHING_LEGAL
        else:
            assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.INTERACTIVE

    def assert_history_at_start(self, hand: PokerHand, before: dict[int, tuple[PlayerStatus, int]]) -> None:
        """The first event equals `HandStarted` written from the live players; earlier histories are intact."""
        self.started += 1
        assert hand.number == hand.history.number == self.started, f"seed {self.seed}: wrong hand number"
        players = seated(self.table)
        expected = HandStarted(
            number=self.started,
            participants=tuple(
                HandParticipant(
                    seat=state.seat_number,
                    player_id=players[state.seat_number].player_id,
                    position=state.position,
                    blind=state.blind,
                    starting_stack=before[state.seat_number][1],
                )
                for state in hand.players
            ),
        )
        assert hand.history.events[0] == expected, f"seed {self.seed}: hand {self.started} history is wrong"
        self.recorded.append((hand, expected, None))
        self.assert_recorded_histories_intact()
        self.counters["histories_checked"] += 1

    def record_settled_history(self, hand: PokerHand) -> None:
        """Capture the settled hand as it is now, to compare after later hands."""
        assert hand.history.is_complete
        index = next(i for i, (recorded, _, _) in enumerate(self.recorded) if recorded is hand)
        record = SettledRecord(
            copy.deepcopy(hand.history),
            self.checks.fold_history(hand.history),
            {state.seat_number: state.player.stack for state in hand.players},
        )
        assert {seat: facts.stack for seat, facts in record.facts.seats.items()} == record.stacks
        self.recorded[index] = (hand, self.recorded[index][1], record)

    def assert_recorded_histories_intact(self, *, refold: bool = False) -> None:
        """Every retained history still starts as it did and, once settled, equals its copy. With `refold`, every
        settled history is also folded again: its facts, final stacks and settlement equal those captured at
        settlement, and it keeps the orchestrated order, however far the live stacks have moved."""
        for number, (hand, started, record) in enumerate(self.recorded, start=1):
            assert hand.history.events[0] == started, f"seed {self.seed}: the history of hand {number} changed"
            if record is None:
                continue
            assert hand.history == record.history, f"seed {self.seed}: the settled history of hand {number} changed"
            if refold:
                facts = self.checks.fold_history(hand.history)
                assert facts == record.facts, f"seed {self.seed}: hand {number} no longer folds to its facts"
                assert facts.settlement == hand.settlement
                self.checks.assert_orchestrated_order(hand.history)
                self.counters["histories_refolded"] += 1
                self.counters["refolded_after_stacks_moved"] += any(
                    state.player.stack != record.stacks[state.seat_number] for state in hand.players
                )

    def assert_new_hand(
        self, hand: PokerHand, before: dict[int, tuple[PlayerStatus, int]], button: int | None, started: bool
    ) -> None:
        """What a hand just returned by `start` or `next_hand` must satisfy, given the seats before the call."""
        self.betting_actions = []
        self.assert_awaiting_or_settled(hand)
        self.assert_history_at_start(hand, before)
        assert hand.betting is not None and hand.betting.stakes == STAKES
        in_hand = {state.seat_number: state for state in hand.players}
        assert self.table.button_seat_number == next(iter(in_hand)) == button
        for number, (status, stack) in before.items():
            player = seated(self.table)[number]
            if number in in_hand:
                assert stack > 0 and status is not SITTING_OUT and player.status is READY
                if status is WAITING and not started:
                    assert in_hand[number].position not in (Position.BTN, Position.SB)
                    self.counters["waiting_entered"] += 1
            else:
                assert player.status is status  # not playing changes nobody's status
                self.counters["busted_skipped"] += stack == 0
                self.counters["sitting_out_skipped"] += status is SITTING_OUT
                self.counters["waiting_stays"] += status is WAITING and stack > 0
                assert not (status is READY and stack > 0), f"seed {self.seed}: a ready player with chips was left out"

    # --- play ----------------------------------------------------------------------------------------------------

    def play_hand(self, hand: PokerHand) -> None:
        rng = self.rng
        steps = 0
        while hand.settlement is None:
            steps += 1
            assert steps < MAX_STEPS, f"seed {self.seed}: the hand did not end"
            seat = current_actor(hand)
            assert seat is not None
            if rng.random() < 0.15:
                self.probe_rejections()
            if rng.random() < 0.15:
                self.probe_previous_hand()
            if hand.showdown is not None:
                self.game.act(seat, rng.choice(list(ShowdownAction)))
            else:
                action = betting_action(rng, legal_actions(hand), self.aggression)
                self.game.act(seat, action)
                self.betting_actions.append((seat, action))
            self.assert_awaiting_or_settled(hand)
        showdown = hand.showdown
        settlement = hand.settlement
        assert settlement is not None
        for seat, rank in settlement.showdown_ranks:
            best = hand_strength(hand, seat)  # the derived river strength must agree with the settled rank
            assert best is not None and best.rank == rank, f"seed {self.seed}: seat {seat} strength disagrees"
            self.counters["strength_parity"] += 1
        self.record_settled_history(hand)
        self.counters["hands"] += 1
        self.counters["interactive"] += showdown is not None and showdown.kind is ShowdownKind.INTERACTIVE
        self.counters["busts"] += sum(state.player.stack == 0 for state in hand.players)
        self.previous, self.previous_state = hand, hand_state(hand, with_stacks=False)

    def begin(self) -> PokerHand:
        chosen: list[int] = []

        def choose(seats: tuple[int, ...]) -> int:
            chosen.append(self.rng.choice(seats))
            return chosen[-1]

        before = {number: (player.status, player.stack) for number, player in seated(self.table).items()}
        starters = [number for number, (status, stack) in before.items() if status is WAITING and stack > 0]
        hand = self.game.start(choose)
        assert len(chosen) == 1 and chosen[0] in starters
        assert {state.seat_number for state in hand.players} == set(starters)
        self.assert_new_hand(hand, before, chosen[0], started=True)
        return hand

    def next_hand(self) -> PokerHand | None:
        """The next hand, or None when the lifecycle reports fewer than two possible players (nothing changed)."""
        table = self.table
        previous_button = table.button_seat_number
        assert previous_button is not None
        before = {number: (player.status, player.stack) for number, player in seated(table).items()}
        ready = ready_with_chips(table)
        assert ready, f"seed {self.seed}: churn must leave a ready player with chips"
        candidates = [number for number, (status, stack) in before.items() if status is not SITTING_OUT and stack > 0]
        snapshot = world(self.game, table)
        try:
            hand = self.game.next_hand()
        except InvalidPlayerCount:
            assert len(candidates) < 2, f"seed {self.seed}: {candidates} are enough to play"
            assert world(self.game, table) == snapshot
            self.counters["below_two"] += 1
            return None
        self.assert_new_hand(hand, before, expected_button(ready, previous_button), started=False)
        return hand

    def play(self) -> None:
        hand: PokerHand | None = self.begin()
        recoveries = 0
        for _ in range(MAX_HANDS):
            assert hand is not None
            self.play_hand(hand)
            self.assert_recorded_histories_intact(refold=True)
            assert total_stacks(self.table) == self.total
            before = world(self.game, self.table)
            with pytest.raises(GameAlreadyStartedError):
                self.game.start(self.forbidden_chooser)  # never a restart, even after settlement
            assert world(self.game, self.table) == before
            self.churn()
            self.assert_recorded_histories_intact()
            hand = self.next_hand()
            if hand is None:
                if recoveries == 2 or self.rng.random() < 0.5 or not self.reseat():
                    return
                recoveries += 1
                self.counters["recovered"] += 1
                hand = self.next_hand()
                assert hand is not None, f"seed {self.seed}: a newcomer with chips did not make the hand playable"
        self.counters["hand_cap"] += 1
        self.assert_recorded_histories_intact(refold=True)

    def reseat(self) -> bool:
        """Seat one more player after a below-two ending; False when the table is full."""
        empty = self.empty_seats()
        if not empty:
            return False
        self.sit_down(self.rng.choice(empty))
        return True


@dataclass(frozen=True)
class HistoryChecks:
    """The shared history fixtures (see `tests/game/conftest.py`) a game uses."""

    replay_facts: Callable[[PokerHand], Any]
    fold_history: Callable[[HandHistory], Any]
    assert_orchestrated_order: Callable[[HandHistory], None]


def play_seed(seed: int, counters: Counter[str], checks: HistoryChecks) -> None:
    with pytest.MonkeyPatch.context() as patch:
        deck_rng = random.Random(f"decks-{seed}")
        original = Deck.shuffle
        patch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=deck_rng))
        Driver(seed, counters, checks).play()


@pytest.mark.parametrize("seed", SEEDS)
def test_holdem_game_plays_random_games_across_hands(
    seed: int,
    replay_facts: Callable[..., Any],
    fold_history: Callable[..., Any],
    assert_orchestrated_order: Callable[[HandHistory], None],
) -> None:
    play_seed(seed, Counter(), HistoryChecks(replay_facts, fold_history, assert_orchestrated_order))


def test_the_seeds_reach_every_cross_hand_shape(
    replay_facts: Callable[..., Any],
    fold_history: Callable[..., Any],
    assert_orchestrated_order: Callable[[HandHistory], None],
) -> None:
    counters: Counter[str] = Counter()
    checks = HistoryChecks(replay_facts, fold_history, assert_orchestrated_order)
    for seed in SEEDS:
        play_seed(seed, counters, checks)
    required: dict[str, int] = {
        "hands": 500,
        "strength_parity": 300,
        "busts": 30,
        "busted_skipped": 30,
        "waiting_entered": 20,
        "waiting_stays": 5,
        "sitting_out_skipped": 10,
        "back_from_sitting_out": 5,
        "newcomers": 20,
        "stood_up_busted": 10,
        "stood_up_solvent": 1,
        "interactive": 20,
        "below_two": 10,
        "recovered": 3,
        "hand_cap": 3,
        "rejections_mid_hand": 100,
        "rejections_previous_hand": 100,
        "histories_checked": 500,
        "histories_refolded": 5000,
        "refolded_after_stacks_moved": 4000,
    }
    missing = {key: (counters[key], need) for key, need in required.items() if counters[key] < need}
    assert not missing, f"the seed set no longer reaches enough of: {missing} (got {dict(counters)})"

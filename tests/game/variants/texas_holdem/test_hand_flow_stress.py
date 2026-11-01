"""Seeded whole hands driven only through `begin_hand`, `act` and `current_actor`, with mischief at every step.

Unlike the differential in `test_hand_stress`, which replays decisions made by a low-level driver, this driver never
touches a low-level operation: it asks `current_actor` who must act, plays a random legal betting action or SHOW or MUCK
for that seat, and nothing else. Before each real call it also tries a few calls that must be rejected (garbage, a
betting action during a showdown, a showdown action during betting, the wrong seat), each of which must change nothing.

Checked after every call: the hand is settled, or a betting actor with a legal action is waiting, or an incomplete
interactive showdown decider is waiting; `current_actor` names exactly that seat; chips are conserved; a waiting
interactive showdown is only ever reached by a river with nobody all-in and has the decision order of its river round.
Checked at the end: the hand settled within a bounded number of calls, a runout deals every remaining street without
starting its rounds, the settlement pays only live, unmucked seats, ranks exactly the shown seats and conserves chips,
and a settled hand rejects every further call.

The seeds are fixed, so a failure names the seed that reproduces it. The profiles give very different shapes: deep
passive stacks (interactive river showdowns, mucks), short aggressive stacks (all-in runouts from every street, side
pots) and folding tables (uncontested settlements on every street). The counters keep the seed set honest, so the test
cannot pass vacuously on hands that never reach those shapes.
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
from go_poker.game.betting.apply import NotPlayersTurnError
from go_poker.game.betting.legal_actions import NOTHING_LEGAL, LegalActions, legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import HandHistory
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.showdown import NotShowdownTurnError, ShowdownAction, ShowdownKind, decision_order
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.showdown import ShowdownNotStartedError

STAKES = Stakes(small_blind=5, big_blind=10)
SEEDS = range(600)
MAX_CALLS = 500  # far more calls than any generated hand needs
BURNED_AND_BOARD = 3 + 5  # cards off the deck once the river is dealt, besides the hole cards

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
GARBAGE: list[Any] = [None, "show", 7, True, ActionType.CHECK, object(), (1, CHECK)]

# (stack range, weight of fold when facing a bet, weight of aggression, chance of SHOW). Equal stacks and ties are
# common because the ranges are narrow.
PROFILES = {
    "deep_passive": ((5_000, 5_000), 1, 1, 0.5),
    "deep_passive_shower": ((5_000, 5_000), 1, 0, 0.95),
    "deep_passive_mucker": ((5_000, 5_000), 1, 0, 0.1),
    "short_aggressive": ((1, 200), 2, 8, 0.5),
    "medium": ((100, 1_500), 3, 4, 0.5),
    "folding": ((200, 2_000), 12, 3, 0.5),
}
PROFILE_NAMES = sorted(PROFILES)


def random_hand(rng: random.Random, stack_range: tuple[int, int]) -> PokerHand:
    seats = tuple(sorted(rng.sample(range(1, 10), rng.randint(2, 9))))
    assignments = assign_hand_seats(seats, rng.choice(seats))
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


def betting_action(rng: random.Random, legal: LegalActions, fold_weight: int, aggression: int) -> Action:
    options: list[tuple[Action, int]] = []
    if legal.can_check:
        options.append((CHECK, 6))
    else:
        options.append((FOLD, fold_weight))
    if legal.can_call:
        options.append((CALL, 6))
    if aggression:
        kind = ActionType.BET if legal.can_bet else ActionType.RAISE
        if legal.short_all_in_target is not None:
            options.append((Action(kind, legal.short_all_in_target), aggression))
        elif legal.min_full_target is not None and legal.max_target is not None:
            low, high = legal.min_full_target, legal.max_target
            between = low + int((high - low) * rng.random() ** 3)
            options += [(Action(kind, low), aggression), (Action(kind, between), aggression)]
            options.append((Action(kind, high), max(1, aggression // 2)))
    return rng.choices([action for action, _ in options], [weight for _, weight in options])[0]


def snapshot(hand: PokerHand) -> dict[str, Any]:
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
                hp.seat_number,
                hp.player.stack,
                hp.folded,
                hp.all_in,
                hp.street_contribution,
                hp.total_contribution,
                list(hp.hole_cards),
            )
            for hp in hand.players
        ],
        "pots": pots(hand),
    }


def assert_rejected(hand: PokerHand, error: type[Exception], seat: int, action: Any) -> None:
    before = snapshot(hand)
    with pytest.raises(error):
        act(hand, seat, action)
    assert snapshot(hand) == before


def probe_rejections(hand: PokerHand, rng: random.Random) -> None:
    """Calls that must fail in every state of an unsettled hand, each leaving the hand exactly as it was."""
    seats = [hp.seat_number for hp in hand.players]
    waiting = current_actor(hand)
    assert waiting is not None
    in_showdown = hand.betting is not None and hand.betting.current_actor is None
    assert_rejected(hand, TypeError, rng.choice([waiting, 99, *seats]), rng.choice(GARBAGE))
    wrong = rng.choice([seat for seat in seats if seat != waiting])
    if in_showdown:
        assert_rejected(hand, NotShowdownTurnError, wrong, ShowdownAction.SHOW)
        assert_rejected(hand, NotShowdownTurnError, 99, ShowdownAction.MUCK)
        assert_rejected(hand, NotPlayersTurnError, waiting, rng.choice([FOLD, CHECK, CALL]))
    else:
        assert_rejected(hand, ShowdownNotStartedError, rng.choice(seats), rng.choice(list(ShowdownAction)))
        assert_rejected(hand, NotPlayersTurnError, wrong, rng.choice([FOLD, CHECK, CALL]))
        assert_rejected(hand, NotPlayersTurnError, 99, CALL)


def assert_waiting(hand: PokerHand) -> None:
    """The postcondition of an unsettled hand: exactly one of a betting actor or a showdown decider is waiting."""
    assert hand.settlement is None
    betting = hand.betting
    assert betting is not None
    if betting.current_actor is not None:
        assert hand.showdown is None  # a showdown never starts while someone can still bet
        assert current_actor(hand) == betting.current_actor
        assert legal_actions(hand) != NOTHING_LEGAL
        return
    showdown = hand.showdown
    assert showdown is not None and showdown.kind is ShowdownKind.INTERACTIVE and not showdown.is_complete
    assert current_actor(hand) == showdown.current_decider is not None
    # An interactive showdown is reached by a river round with nobody all-in, with every card dealt.
    assert hand.street is Street.RIVER and betting.street is Street.RIVER and len(hand.board) == 5
    live = [hp for hp in hand.players if not hp.folded]
    assert len(live) >= 2 and all(hp.player.stack > 0 and not hp.all_in for hp in live)


def total_chips_in_play(hand: PokerHand) -> int:
    in_front = sum(hp.street_contribution for hp in hand.players)
    return sum(hp.player.stack for hp in hand.players) + in_front + middle_pot(hand)


def river_order(hand: PokerHand, river_actions: list[tuple[int, Action]]) -> tuple[int, ...]:
    """The decision order expected from the river's own actions: the last bettor or raiser first, else the first live
    seat left of the button, then clockwise. Computed from the actions played, not from the engine's aggressor."""
    seats = [hp.seat_number for hp in hand.players]
    live = {hp.seat_number for hp in hand.players if not hp.folded}
    aggressors = [seat for seat, action in river_actions if action.type in (ActionType.BET, ActionType.RAISE)]
    return tuple(decision_order(seats, live, aggressors[-1] if aggressors else None))


def check_settled(hand: PokerHand, total: int, counters: Counter[str], decisions_made: bool) -> None:
    settlement = hand.settlement
    assert settlement is not None
    assert current_actor(hand) is None
    assert sum(hp.player.stack for hp in hand.players) == total
    live = {hp.seat_number for hp in hand.players if not hp.folded}
    payouts = settlement.payouts
    assert (
        sum(payouts.values()) == sum(hp.total_contribution for hp in hand.players) == sum(p.amount for p in pots(hand))
    )
    assert set(payouts) <= live
    ranked = {seat for seat, _ in settlement.showdown_ranks}
    showdown = hand.showdown
    if len(live) == 1:
        counters[f"uncontested_{hand.street.name.lower()}"] += 1
        assert showdown is None and not ranked
        assert hand.betting is not None
        return
    assert showdown is not None and showdown.is_complete
    assert set(showdown.order) == live
    assert ranked == set(showdown.shown)
    assert set(payouts) <= set(showdown.contenders)
    assert len(hand.board) == 5 and hand.street is Street.RIVER
    assert len(hand.burned_cards) == 3
    assert len(hand.deck) == 52 - 2 * len(hand.players) - BURNED_AND_BOARD
    if showdown.kind is ShowdownKind.ALL_IN:
        assert not showdown.decisions and not decisions_made
        assert showdown.order == tuple(sorted(showdown.order, key=lambda seat: canonical_index(hand, seat)))
        assert hand.betting is not None
        counters[f"runout_after_{hand.betting.street.name.lower()}"] += 1
    else:
        counters["interactive"] += 1
        counters["interactive_mucks"] += bool(showdown.mucked)
        counters["unshown_winner"] += not ranked
        counters["interactive_all_mucked_but_one"] += len(showdown.contenders) == 1 and len(showdown.decisions) > 0
    counters["multi_pot"] += len(settlement.pot_awards) > 1


def canonical_index(hand: PokerHand, seat: int) -> int:
    seats = [hp.seat_number for hp in hand.players]  # button first
    clockwise = [*seats[1:], *seats[:1]]
    return clockwise.index(seat)


def assert_history_replays(hand: PokerHand, checks: HistoryChecks, betting_actions: list[tuple[int, Action]]) -> None:
    """The facts replayed from the history equal the live hand (stacks, all-in, showdown and settlement included), the
    history holds exactly the betting actions played, and it follows the orchestrated presentation order."""
    assert checks.replay_facts(hand).actions == betting_actions
    checks.assert_orchestrated_order(hand.history)


@dataclass(frozen=True)
class HistoryChecks:
    """The shared history fixtures (see `tests/game/conftest.py`) a seed uses."""

    replay_facts: Callable[[PokerHand], Any]
    assert_orchestrated_order: Callable[[HandHistory], None]


def play_seed(seed: int, counters: Counter[str], checks: HistoryChecks) -> None:
    rng = random.Random(seed)
    name = PROFILE_NAMES[seed % len(PROFILE_NAMES)]
    stack_range, fold_weight, aggression, show_chance = PROFILES[name]
    hand = random_hand(rng, stack_range)
    total = sum(hp.player.stack for hp in hand.players)
    assert current_actor(hand) is None  # nothing has begun

    begin_hand(hand, STAKES)
    betting_actions: list[tuple[int, Action]] = []
    assert_history_replays(hand, checks, betting_actions)
    river_actions: list[tuple[int, Action]] = []
    decisions_made = False
    calls = 0
    while hand.settlement is None:
        calls += 1
        assert calls < MAX_CALLS, f"seed {seed}: the hand did not end"
        assert_waiting(hand)
        assert total_chips_in_play(hand) == total
        seat = current_actor(hand)
        assert seat is not None
        if rng.random() < 0.5:
            probe_rejections(hand, rng)
        if hand.showdown is not None:
            if not hand.showdown.decisions:
                assert hand.showdown.order == river_order(hand, river_actions), f"seed {seed}"
            decision = ShowdownAction.SHOW if rng.random() < show_chance else ShowdownAction.MUCK
            act(hand, seat, decision)
            decisions_made = True
            assert_history_replays(hand, checks, betting_actions)
            continue
        assert hand.betting is not None
        legal = legal_actions(hand)
        action = betting_action(rng, legal, fold_weight, aggression)
        if hand.betting.street is Street.RIVER:
            river_actions.append((seat, action))
        act(hand, seat, action)
        betting_actions.append((seat, action))
        assert_history_replays(hand, checks, betting_actions)

    check_settled(hand, total, counters, decisions_made)
    assert hand.history.is_complete and hand.history.settlement == hand.settlement
    assert_settled_rejects_everything(hand, rng)


def assert_settled_rejects_everything(hand: PokerHand, rng: random.Random) -> None:
    seats = [hp.seat_number for hp in hand.players]
    for _ in range(4):
        seat = rng.choice([*seats, 99])
        action = rng.choice([FOLD, CHECK, CALL, *ShowdownAction, *GARBAGE])
        assert_rejected(hand, HandAlreadySettledError, seat, action)
    before = snapshot(hand)
    with pytest.raises(HandAlreadySettledError):
        begin_hand(hand, STAKES)
    assert snapshot(hand) == before
    assert current_actor(hand) is None


@pytest.mark.parametrize("seed", SEEDS)
def test_hand_flow_alone_drives_random_hands_to_settlement(
    seed: int, replay_facts: Callable[..., Any], assert_orchestrated_order: Callable[[HandHistory], None]
) -> None:
    play_seed(seed, Counter(), HistoryChecks(replay_facts, assert_orchestrated_order))


def test_the_seeds_reach_every_shape_the_flow_must_handle(
    replay_facts: Callable[..., Any], assert_orchestrated_order: Callable[[HandHistory], None]
) -> None:
    counters: Counter[str] = Counter()
    checks = HistoryChecks(replay_facts, assert_orchestrated_order)
    for seed in SEEDS:
        play_seed(seed, counters, checks)
    required: dict[str, int] = {
        "interactive": 30,
        "interactive_mucks": 15,
        "unshown_winner": 5,
        "interactive_all_mucked_but_one": 5,
        "runout_after_preflop": 30,
        "runout_after_flop": 10,
        "runout_after_turn": 10,
        "runout_after_river": 10,
        "uncontested_preflop": 20,
        "uncontested_flop": 10,
        "uncontested_turn": 5,
        "uncontested_river": 3,
        "multi_pot": 20,
    }
    missing = {key: (counters[key], need) for key, need in required.items() if counters[key] < need}
    assert not missing, f"the seed set no longer reaches enough of: {missing} (got {dict(counters)})"

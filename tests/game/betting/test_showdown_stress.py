"""Seeded river showdowns with nobody all-in: the interactive showdown against an independent oracle.

`test_hand_stress` reaches a non-all-in river showdown in only a handful of its seeds, because its generator is
aggressive and its stacks often small. Here the stacks are deep and the play is passive and rarely folds, so a bet or
raise never reaches an all-in and most hands reach the river contested. Each seed's showdown is then started and decided
with seeded SHOW and MUCK decisions, with a show probability of its own.

The oracle never reads the engine's showdown state to decide what is expected. The decision order comes from the actions
applied on the river alone, not from `BettingState.last_aggressor`, so the engine's aggressor is checked too. After
every decision the shown, mucked and contending seats, the current decider and completion are recomputed from the order
and the decisions made so far. Out-of-turn decisions and an early settlement are probed at every step and must change
nothing. The settlement is compared with an independent award of each pot: only shown hands are ranked, the best shown
contender (or the sole contender, unranked) wins, a mucked seat is never paid, chips are conserved.
The seeds are fixed, so a failure names the seed that reproduces it.
"""

import copy
import random
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest

from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import is_round_complete, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import HandAlreadySettledError
from go_poker.game.showdown import NotShowdownTurnError, Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    ShowdownAlreadyStartedError,
    ShowdownIncompleteError,
    ShowdownNotStartedError,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)

type HandFactory = Callable[..., PokerHand]

SEEDS = range(300)
DEEP_STACK = 1_000_000  # no generated bet or raise comes near it
MIN_SHOWDOWNS = 150  # how many seeds must end in a contested river showdown
MIN_PER_SHAPE = 20  # and how many of those must reach each shape of decision order and outcome listed in `Shapes`
MIN_TIES = 5  # random hands rarely tie, so a tie among shown hands needs fewer
SHOW_PROBABILITIES = (0.1, 0.3, 0.5, 0.7, 0.9)  # one is chosen per seed

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK


def choose_action(rng: random.Random, hand: PokerHand) -> Action:
    legal = legal_actions(hand)
    if legal.can_check:
        if legal.can_bet and rng.random() < 0.35:
            assert legal.min_full_target is not None
            return Action(ActionType.BET, legal.min_full_target + rng.randint(0, 40))
        return CHECK
    roll = rng.random()
    if roll < 0.08:
        return FOLD
    if roll < 0.2 and legal.min_full_target is not None:
        return Action(ActionType.RAISE, legal.min_full_target + rng.randint(0, 40))
    return CALL


def play_round(rng: random.Random, hand: PokerHand) -> int | None:
    """Play the current round to its end; return the seat of the last bet or raise applied in it, by this driver's own
    count."""
    assert hand.betting is not None
    aggressor = None
    while not is_round_complete(hand.betting):
        actor = hand.betting.current_actor
        assert actor is not None
        action = choose_action(rng, hand)
        apply_action(hand, actor, action)
        if action.type in (ActionType.BET, ActionType.RAISE):
            aggressor = actor
    return aggressor


def expected_decision_order(hand: PokerHand, aggressor: int | None) -> tuple[int, ...]:
    """Live seats clockwise from the seat after the button, rotated to start at the aggressor."""
    seats = [state.seat_number for state in hand.players]  # the button first
    live = [seat for seat in (*seats[1:], seats[0]) if not folded(hand, seat)]
    start = live.index(aggressor) if aggressor is not None else 0
    return tuple(live[start:] + live[:start])


def play_to_river_showdown(seed: int, make_hand: HandFactory) -> tuple[PokerHand, int | None] | None:
    """Play the seed's hand to a completed river round and return it with the river's aggressor, or None when the hand
    was won uncontested before the river."""
    rng = random.Random(seed)
    seat_numbers = sorted(rng.sample(range(1, 10), rng.randint(2, 9)))
    hand = make_hand({seat: DEEP_STACK for seat in seat_numbers}, button_seat_number=rng.choice(seat_numbers))
    hand.deck.shuffle(_rng=random.Random(f"deck-{seed}"))
    initialize_betting(hand, Stakes(small_blind=50, big_blind=100))
    deal_hole_cards(hand)
    aggressor = play_round(rng, hand)
    while hand.street is not Street.RIVER:
        if sum(not state.folded for state in hand.players) < 2:
            return None
        deal_next_street(hand)
        start_betting_round(hand)
        aggressor = play_round(rng, hand)
    if sum(not state.folded for state in hand.players) < 2:
        return None
    return hand, aggressor


def folded(hand: PokerHand, seat: int) -> bool:
    return next(state for state in hand.players if state.seat_number == seat).folded


def betting(hand: PokerHand) -> BettingState:
    assert hand.betting is not None
    return hand.betting


def snapshot(hand: PokerHand) -> dict[str, Any]:
    """Everything about the hand, for comparing before and after (the deck by its size: drawing is its only change)."""
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "showdown": hand.showdown,
        "players": [
            (
                state.seat_number,
                state.player.stack,
                state.folded,
                state.all_in,
                state.street_contribution,
                state.total_contribution,
                tuple(state.hole_cards),
            )
            for state in hand.players
        ],
        "pots": pots(hand),
        "middle_pot": middle_pot(hand),
    }


def unchanged_but(state: dict[str, Any], *names: str) -> dict[str, Any]:
    """A snapshot without the named parts, for checking that only they changed."""
    return {key: value for key, value in state.items() if key not in names}


@dataclass(frozen=True)
class Derived:
    """What the oracle says a showdown's state is, from its order and the decisions made so far."""

    shown: tuple[int, ...]
    mucked: tuple[int, ...]
    contenders: tuple[int, ...]
    current_decider: int | None
    complete: bool


def oracle_derived(order: tuple[int, ...], decisions: list[ShowdownAction]) -> Derived:
    """Recompute the derived showdown state from the order and the decisions alone."""
    shown, mucked = [], []
    for index, action in enumerate(decisions):
        (shown if action is SHOW else mucked).append(order[index])
    contenders = tuple(seat for seat in order if seat not in mucked)
    complete = len(decisions) == len(order) or len(contenders) == 1
    return Derived(tuple(shown), tuple(mucked), contenders, None if complete else order[len(decisions)], complete)


def check_against_oracle(hand: PokerHand, order: tuple[int, ...], decisions: list[ShowdownAction]) -> Derived:
    showdown = hand.showdown
    assert showdown is not None
    expected = oracle_derived(order, decisions)
    assert showdown == Showdown(ShowdownKind.INTERACTIVE, order, tuple(decisions))
    assert (
        Derived(showdown.shown, showdown.mucked, showdown.contenders, showdown.current_decider, showdown.is_complete)
        == expected
    )
    return expected


def probe_rejections(hand: PokerHand, order: tuple[int, ...], expected: Derived) -> None:
    """Every seat that is not the current decider, folded and unknown seats included, is rejected for both actions;
    settling is rejected while decisions are pending. None of it changes the hand."""
    before = snapshot(hand)
    others = [*order, 0, 99] + [state.seat_number for state in hand.players if state.folded]
    for seat in others:
        if seat == expected.current_decider:
            continue
        for action in ShowdownAction:
            with pytest.raises(NotShowdownTurnError):
                apply_showdown_action(hand, seat, action)
            assert snapshot(hand) == before
    if not expected.complete:
        with pytest.raises(ShowdownIncompleteError):
            settle_hand(hand)
        assert snapshot(hand) == before
    with pytest.raises(ShowdownAlreadyStartedError):
        start_showdown(hand)
    assert snapshot(hand) == before


@dataclass
class Outcome:
    """The decisions a seed's showdown ended with and the shapes they make."""

    order: tuple[int, ...]
    decisions: list[ShowdownAction]
    derived: Derived


def decide_to_completion(seed: int, hand: PokerHand, order: tuple[int, ...]) -> Outcome:
    """Start the showdown and decide it with seeded decisions, checking the oracle and the probes at every step."""
    before_start = snapshot(hand)
    with pytest.raises(ShowdownNotStartedError):
        settle_hand(hand)
    with pytest.raises(ShowdownNotStartedError):
        apply_showdown_action(hand, order[0], SHOW)
    assert snapshot(hand) == before_start

    start_showdown(hand)
    show_probability = random.Random(f"show-{seed}").choice(SHOW_PROBABILITIES)
    rng = random.Random(f"decisions-{seed}")
    decisions: list[ShowdownAction] = []
    while True:
        expected = check_against_oracle(hand, order, decisions)
        probe_rejections(hand, order, expected)
        if expected.complete:
            return Outcome(order, decisions, expected)
        assert expected.current_decider == order[len(decisions)]
        wrong_type_before = snapshot(hand)
        for wrong_action in (Action(ActionType.CALL), ActionType.CALL, "show", None):
            with pytest.raises(TypeError):
                apply_showdown_action(hand, order[len(decisions)], wrong_action)  # type: ignore[arg-type]
            assert snapshot(hand) == wrong_type_before
        action = SHOW if rng.random() < show_probability else MUCK
        previous = hand.showdown
        before = snapshot(hand)
        apply_showdown_action(hand, order[len(decisions)], action)
        decisions.append(action)
        after = snapshot(hand)
        assert unchanged_but(after, "showdown") == unchanged_but(before, "showdown")
        assert hand.showdown is not previous


def oracle_awards(hand: PokerHand, ranks: dict[int, HandRank], contenders: set[int]) -> list[dict[int, int]]:
    """Each pot's shares by an independent award: among its eligible contenders only, the best rank wins (a sole one
    needs no rank), and equal ranks split the pot with the odd chips going one each clockwise from the seat left of
    the button."""
    seats = [state.seat_number for state in hand.players]  # clockwise, button first
    clockwise = [*seats[1:], seats[0]]
    awards = []
    for pot in pots(hand):
        final = [seat for seat in clockwise if seat in pot.eligible_seats and seat in contenders]
        assert final
        if len(final) > 1:
            best = max(ranks[seat] for seat in final)
            final = [seat for seat in final if ranks[seat] == best]
        share, odd = divmod(pot.amount, len(final))
        awards.append({seat: share + (1 if index < odd else 0) for index, seat in enumerate(final)})
    return awards


def check_settlement(hand: PokerHand, outcome: Outcome) -> dict[str, bool]:
    """Settle the decided hand and compare everything with the oracle; return the outcome shapes the hand has."""
    derived = outcome.derived
    live = [state for state in hand.players if not state.folded]
    contenders = set(derived.contenders)
    shown_ranks = {
        state.seat_number: evaluate_best([*state.hole_cards, *hand.board])
        for state in live
        if state.seat_number in derived.shown
    }
    mucked_ranks = {
        state.seat_number: evaluate_best([*state.hole_cards, *hand.board])
        for state in live
        if state.seat_number in derived.mucked
    }
    starting_chips = {state.seat_number: state.player.stack + state.total_contribution for state in hand.players}
    layers = pots(hand)
    middle = middle_pot(hand)
    expected_awards = oracle_awards(hand, shown_ranks, contenders)
    showdown = hand.showdown
    history = {
        state.seat_number: (state.folded, state.total_contribution, state.street_contribution) for state in hand.players
    }
    before = snapshot(hand)

    settle_hand(hand)

    settlement = hand.settlement
    assert settlement is not None
    after = snapshot(hand)
    assert unchanged_but(after, "settlement", "players") == unchanged_but(before, "settlement", "players")
    assert hand.showdown is showdown
    assert settlement.showdown_ranks == tuple(shown_ranks.items())  # only shown seats, in hand order
    assert [award.pot for award in settlement.pot_awards] == list(layers) == list(pots(hand))  # the pot as contested
    assert [dict(award.shares) for award in settlement.pot_awards] == expected_awards
    payouts = settlement.payouts
    assert not set(payouts) & set(derived.mucked)
    assert set(payouts) <= contenders
    assert sum(payouts.values()) == middle
    for state in hand.players:
        assert state.player.stack == starting_chips[state.seat_number] - state.total_contribution + payouts.get(
            state.seat_number, 0
        )
        assert (state.folded, state.total_contribution, state.street_contribution) == history[state.seat_number]
    assert sum(state.player.stack for state in hand.players) == sum(starting_chips.values())
    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)
    with pytest.raises(HandAlreadySettledError):
        apply_showdown_action(hand, outcome.order[0], SHOW)
    assert snapshot(hand) == after

    best_contender = max(shown_ranks.values(), default=None)
    return {
        "tie_among_shown": any(len(award) > 1 for award in expected_awards),
        "mucked_best": bool(mucked_ranks)
        and best_contender is not None
        and max(mucked_ranks.values()) > best_contender,
    }


class Shapes:
    """Shapes of decision order and outcome the seeds must keep reaching."""

    def __init__(self) -> None:
        self.no_bet = 0  # nobody bet on the river
        self.aggressor_first = 0  # the aggressor is the first live seat left of the button, so the order is canonical
        self.aggressor_after = 0  # the aggressor decides first and the order wraps back to the seats before it
        self.button_aggressor = 0  # the button is the aggressor, so it decides first
        self.folded_skipped = 0  # a seat that folded sits between live seats of the order
        self.first_shows = 0  # the first decider shows
        self.first_mucks = 0  # the first decider mucks
        self.show_then_muck = 0  # somebody mucks after an earlier seat showed
        self.unshown_winner = 0  # the last contender wins without having shown
        self.everyone_shows = 0  # every seat decides and every decision is SHOW
        self.tie_among_shown = 0  # a pot split between equally ranked shown hands
        self.mucked_best = 0  # a seat that mucked held a better hand than any contender
        self.heads_up_muck = 0  # two live seats and the first decider mucks


def run_seed(seed: int, make_hand: HandFactory, shapes: Shapes | None = None) -> bool:
    """Play and settle the seed's showdown, checking it; return whether the seed reached a contested river showdown."""
    result = play_to_river_showdown(seed, make_hand)
    if result is None:
        return False
    hand, aggressor = result
    order = expected_decision_order(hand, aggressor)
    assert not any(state.all_in for state in hand.players if not state.folded)
    assert betting(hand).last_aggressor == aggressor

    outcome = decide_to_completion(seed, hand, order)
    settlement_shapes = check_settlement(hand, outcome)
    if shapes is not None:
        record_shapes(shapes, hand, aggressor, outcome, settlement_shapes)
    return True


def record_shapes(
    shapes: Shapes, hand: PokerHand, aggressor: int | None, outcome: Outcome, settlement_shapes: dict[str, bool]
) -> None:
    seats = [state.seat_number for state in hand.players]
    canonical = [*seats[1:], seats[0]]
    live = [seat for seat in canonical if not folded(hand, seat)]
    decisions, derived = outcome.decisions, outcome.derived
    shapes.no_bet += aggressor is None
    shapes.aggressor_first += aggressor is not None and aggressor == live[0]
    shapes.aggressor_after += aggressor is not None and aggressor != live[0]
    shapes.button_aggressor += aggressor == seats[0]
    shapes.folded_skipped += any(
        folded(hand, seat) and canonical.index(live[0]) < canonical.index(seat) < canonical.index(live[-1])
        for seat in canonical
    )
    shapes.first_shows += decisions[0] is SHOW
    shapes.first_mucks += decisions[0] is MUCK
    shapes.show_then_muck += any(action is MUCK and SHOW in decisions[:index] for index, action in enumerate(decisions))
    shapes.unshown_winner += len(derived.contenders) == 1 and not set(derived.contenders) & set(derived.shown)
    shapes.everyone_shows += len(decisions) == len(outcome.order) and all(action is SHOW for action in decisions)
    shapes.tie_among_shown += settlement_shapes["tie_among_shown"]
    shapes.mucked_best += settlement_shapes["mucked_best"]
    shapes.heads_up_muck += len(live) == 2 and decisions[0] is MUCK


def test_river_showdowns_match_the_independent_oracle_at_every_step(make_hand: HandFactory) -> None:
    for seed in SEEDS:
        try:
            run_seed(seed, make_hand)
        except AssertionError as error:
            raise AssertionError(f"seed {seed}") from error


def test_the_seeds_keep_reaching_every_shape_of_river_showdown(make_hand: HandFactory) -> None:
    """The seed set is useful only while it keeps reaching the shapes of decision order and outcome it checks."""
    shapes = Shapes()
    showdowns = sum(run_seed(seed, make_hand, shapes) for seed in SEEDS)

    assert showdowns >= MIN_SHOWDOWNS, showdowns
    counts = vars(shapes)
    assert all(count >= MIN_PER_SHAPE for name, count in counts.items() if name != "tie_among_shown"), counts
    assert shapes.tie_among_shown >= MIN_TIES, counts

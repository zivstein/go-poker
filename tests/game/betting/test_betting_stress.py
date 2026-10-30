"""Deterministic randomized betting hands, driven through the public dealing and betting operations.

Each seed builds a hand of 2–9 players with uneven stacks (some around or below the blinds, so short blinds, short
calls, short bets and raises, and several all-in levels happen) and plays random legal actions: folds, checks, calls,
full bets and raises at the minimum, the maximum and in between, and short all-in targets, street by street until
betting is closed or the river round is complete. `CheckedHand` asserts the betting and accounting invariants after
every step; the tests here add the end-of-hand properties and check that the seed set keeps reaching the all-in rules.
The seeds are fixed, so every run plays the same hands and a failure names the seed that reproduces it.
"""

import random
from collections.abc import Callable
from dataclasses import dataclass, fields
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.no_limit import has_raise_rights
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.street import Street

# The conftest `CheckedHand`, which test modules cannot import.
type CheckedHand = Any
type HandFactory = Callable[..., PokerHand]

STAKES = Stakes(small_blind=50, big_blind=100)
SEEDS = range(200)
MAX_STEPS = 1_000  # far more steps than any generated hand needs
MIN_OCCURRENCES = 10  # how often, at least, the seed set must reach each rule it stresses

# Each player's stack comes from one of these ranges, equally likely: around or below the blinds, a few big blinds,
# medium, and very deep.
STACK_RANGES = ((1, 150), (150, 600), (600, 3_000), (3_000, 20_000))

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


@dataclass
class Exercised:
    """How often the generated hands met the rules this test is meant to stress."""

    short_blinds: int = 0  # blinds posted for less than the full blind
    short_calls: int = 0
    short_bets_and_raises: int = 0
    raise_rights_denied: int = 0  # turns of a pending actor who faced only short all-ins since acting
    returns: int = 0  # collections that gave unmatched chips back
    river_betting: int = 0  # hands with an action on the river
    all_in_run_outs: int = 0  # hands whose betting closed before the river with two or more live players
    side_pots: int = 0  # hands ending with a main pot and at least two side pots
    folded_dead_money: int = 0  # hands ending with a folded player's dead money in a side pot
    deepest_layering: int = 0  # the most pots a hand ended with


def random_hand(rng: random.Random, make_hand: HandFactory) -> PokerHand:
    seat_numbers = sorted(rng.sample(range(1, 10), rng.randint(2, 9)))
    stacks = {seat_number: rng.randint(*rng.choice(STACK_RANGES)) for seat_number in seat_numbers}
    return make_hand(stacks, button_seat_number=rng.choice(seat_numbers))


def random_action(rng: random.Random, legal: LegalActions) -> Action:
    """A random legal action. Passive options are likelier, so rounds end, but aggression is common enough to put
    players all-in at many different levels."""
    choices: list[tuple[Action, int]] = [(FOLD, 1 if legal.can_check else 3)]
    if legal.can_check:
        choices.append((CHECK, 6))
    if legal.can_call:
        choices.append((CALL, 6))
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        choices.append((Action(kind, legal.short_all_in_target), 6))
    elif legal.min_full_target is not None and legal.max_target is not None:
        low, high = legal.min_full_target, legal.max_target
        # Sizes in between lean towards the minimum, so deep players keep chips for later streets.
        between = low + int((high - low) * rng.random() ** 3)
        choices += [(Action(kind, low), 2), (Action(kind, between), 2), (Action(kind, high), 1)]
    return rng.choices([action for action, _ in choices], [weight for _, weight in choices])[0]


def play_random_hand(seed: int, checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory) -> Exercised:
    """Play the seed's hand to the end of its betting, checking every step, then check the end-of-hand properties."""
    rng = random.Random(seed)
    h = checked(random_hand(rng, make_hand))
    exercised = Exercised()
    blinds = {Blind.SMALL: STAKES.small_blind, Blind.BIG: STAKES.big_blind}
    exercised.short_blinds = sum(
        h.starting_chips[hp.seat_number] < blinds[hp.blind] for hp in h.hand.players if hp.blind in blinds
    )
    h.start(STAKES)

    for _ in range(MAX_STEPS):
        if is_round_complete(h.betting):
            if is_betting_closed(h.hand) or h.hand.street is Street.RIVER:
                break
            h.next_street()
            continue

        actor = h.betting.current_actor
        legal = legal_actions(h.hand)
        action = random_action(rng, legal)
        exercised.raise_rights_denied += not has_raise_rights(h.betting, actor)
        exercised.short_calls += action == CALL and legal.call_amount < legal.amount_owed
        exercised.short_bets_and_raises += action.amount is not None and action.amount == legal.short_all_in_target
        if h.hand.street is Street.RIVER:
            exercised.river_betting = 1

        stacks_before = {hp.seat_number: hp.player.stack for hp in h.hand.players}
        h.act((actor, action))
        exercised.returns += any(hp.player.stack > stacks_before[hp.seat_number] for hp in h.hand.players)
    else:
        pytest.fail(f"Seed {seed}: betting did not end within {MAX_STEPS} steps")

    check_end_of_hand(h, exercised)
    return exercised


def check_end_of_hand(h: CheckedHand, exercised: Exercised) -> None:
    """Check the collected end state of the hand's betting, and run the board out when betting closed early."""
    players = h.hand.players
    live = {hp.seat_number for hp in players if not hp.folded}
    layers = pots(h.hand)

    # Betting has ended: no further betting is possible, or the river round is complete.
    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand) or h.hand.street is Street.RIVER
    # Nothing is left in front, every chip is in a stack or in the middle, and the pots hold the whole middle.
    assert all(hp.street_contribution == 0 for hp in players)
    assert sum(hp.player.stack for hp in players) + middle_pot(h.hand) == sum(h.starting_chips.values())
    assert sum(pot.amount for pot in layers) == middle_pot(h.hand) == sum(hp.total_contribution for hp in players)
    # Every live player has chips in the main pot, and no pot has a single contributor.
    assert layers[0].eligible_seats == live
    assert len(layers) <= len(players) - 1

    main_pot_level = min(hp.total_contribution for hp in players if hp.total_contribution > 0)
    exercised.side_pots = len(layers) >= 3
    exercised.folded_dead_money = any(hp.folded and hp.total_contribution > main_pot_level for hp in players)
    exercised.deepest_layering = len(layers)

    if is_betting_closed(h.hand) and len(live) >= 2:
        # Two or more live players and nobody left to bet: every later round asks nobody to act and moves no chips.
        exercised.all_in_run_outs = h.hand.street is not Street.RIVER
        totals = {hp.seat_number: hp.total_contribution for hp in players}
        while h.hand.street is not Street.RIVER:
            h.next_street()
            assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
            assert {hp.seat_number: hp.total_contribution for hp in players} == totals
            assert pots(h.hand) == layers


@pytest.mark.parametrize("seed", SEEDS)
def test_random_hand_keeps_every_betting_and_accounting_invariant(
    seed: int, checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Every step of the seed's hand keeps the invariants `CheckedHand` checks, and the hand ends collected: nothing
    in front, every chip in a stack or in the pots, the main pot contested by every live player, and, when betting
    closes early with two or more live players, later rounds that ask nobody to act and move no chips."""
    play_random_hand(seed, checked, make_hand)


def test_random_hands_keep_reaching_short_all_ins_and_deep_side_pots(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """The seed set is useful only while it keeps reaching the all-in rules, so a change to the generator or the
    engine that quietly stops producing them fails here. Across the seeds there are short blinds, short calls, short
    bets and raises, pending players a short all-in did not let raise, returned chips, river betting, all-in run-outs,
    folded players' dead money in side pots, and a nine-handed hand with a main pot and seven side pots."""
    seen = Exercised()
    for seed in SEEDS:
        exercised = play_random_hand(seed, checked, make_hand)
        for counter in fields(Exercised):
            if counter.name != "deepest_layering":
                setattr(seen, counter.name, getattr(seen, counter.name) + getattr(exercised, counter.name))
        seen.deepest_layering = max(seen.deepest_layering, exercised.deepest_layering)

    assert seen.deepest_layering == 8  # nine-handed, the deepest layering a hand can have
    counts = {
        counter.name: getattr(seen, counter.name) for counter in fields(Exercised) if counter.name != "deepest_layering"
    }
    assert all(count >= MIN_OCCURRENCES for count in counts.values()), counts

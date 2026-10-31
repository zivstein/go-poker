"""Deterministic randomized hands, driven through the public dealing, betting and settlement operations.

Each seed builds a hand of 2-9 players with uneven stacks (some around or below the blinds, so short blinds, short
calls, short bets and raises, and several all-in levels happen) and a seeded shuffled deck, and plays random legal
actions: folds, checks, calls, full bets and raises at the minimum, the maximum and in between, and short all-in
targets, street by street until betting is closed or the river round is complete. `CheckedHand` asserts the betting and
accounting invariants after every step. The remaining streets are then dealt and the hand is settled, and the tests
here add the end-of-hand and settlement properties: the settlement invariants, table-wide chip conservation, winners
that really hold the best hands among the shown contenders, rejection of settling too early or twice, the showdown every
contested hand ends with (an all-in one is complete at once; an interactive one is started and decided with seeded SHOW
and MUCK decisions; none for an uncontested hand), and the awarding rules on the same hand's pots under tie-heavy chosen
ranks and seeded contender subsets. They also check that the seed set keeps reaching the rules it stresses.
The seeds are fixed, so every run plays the same hands and a failure names the seed that reproduces it. This is the
main seeded hand driver in the repository; `test_showdown_stress` is a second one, with deep stacks and passive play,
for dense non-all-in river showdowns and their decisions.
"""

import copy
import random
from collections.abc import Callable
from dataclasses import dataclass, fields
from itertools import pairwise
from typing import Any

import pytest

from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.no_limit import has_raise_rights
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.settlement import HandAlreadySettledError, PotAward, _award_pots
from go_poker.game.showdown import NotShowdownTurnError, Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    IncompleteBoardError,
    ShowdownAlreadyStartedError,
    ShowdownIncompleteError,
    ShowdownNotReadyError,
    ShowdownNotStartedError,
    UncontestedHandError,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)

# The conftest `CheckedHand`, which test modules cannot import.
type CheckedHand = Any
type HandFactory = Callable[..., PokerHand]

STAKES = Stakes(small_blind=50, big_blind=100)
SEEDS = range(200)
MAX_STEPS = 1_000  # far more steps than any generated hand needs
MIN_OCCURRENCES = 10  # how often, at least, the seed set must reach each rule it stresses
# The generator is aggressive, so hands that reach the river with nobody all-in are rare; the seed set has a few.
RARE_COUNTERS = ("interactive_showdowns", "aggressor_showdowns", "mucked_showdowns", "unshown_winners")

# Each player's stack comes from one of these ranges, equally likely: around or below the blinds, a few big blinds,
# medium, and very deep.
STACK_RANGES = ((1, 150), (150, 600), (600, 3_000), (3_000, 20_000))

# Few distinct ranks, so chosen-rank ties are common. Hand strength is not under test there, only the awarding rules.
BEST = HandRank(HandCategory.FLUSH, (14, 10, 8, 5, 3))
MIDDLE = HandRank(HandCategory.TWO_PAIR, (9, 4, 14))
WEAK = HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 6, 4))
RANK_CHOICES = (BEST, MIDDLE, WEAK)

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
    unstarted_round_settlements: int = 0  # run-outs also settled with the skipped rounds never started
    side_pots: int = 0  # hands ending with a main pot and at least two side pots
    folded_dead_money: int = 0  # hands ending with a folded player's dead money in a side pot
    deepest_layering: int = 0  # the most pots a hand ended with
    contested_showdowns: int = 0  # settled hands with two or more live players
    uncontested_settlements: int = 0  # settled hands with one live player
    all_in_showdowns: int = 0  # settled hands whose showdown was ALL_IN
    interactive_showdowns: int = 0  # settled hands with an INTERACTIVE river showdown (rare, see RARE_COUNTERS)
    aggressor_showdowns: int = 0  # interactive decision orders starting with a river bettor or raiser (rare)
    mucked_showdowns: int = 0  # interactive showdowns where somebody mucked (rare)
    unshown_winners: int = 0  # interactive showdowns won by the last contender without showing (rare)
    different_pot_winners: int = 0  # settled hands with several pots that were not all won by the same winners
    paid_all_ins_cleared: int = 0  # all-in players paid at settlement, who stop being all-in
    unpaid_all_ins_kept: int = 0  # all-in players paid nothing, who keep their zero stack and all_in
    # From the chosen-rank awards on the hand's pots (see `check_chosen_rank_awards`):
    odd_chip_splits: int = 0  # pots whose winners did not all get the same chips
    tied_pots: int = 0  # pots with several winners
    identical_adjacent_pots: int = 0  # neighbouring pots with the same eligible seats
    multi_odd_chip_pots: int = 0  # pots with several winners and two or more odd chips
    contender_subsets: int = 0  # chosen-rank awards where some live seat was not a contender
    sole_contender_side_pots: int = 0  # pots with several eligible seats but one final contender, won unranked
    best_rank_excluded: int = 0  # pots where a non-contender held the best chosen rank among the eligible seats


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
    """Play the seed's hand to the end of its betting, checking every step, then deal the rest of the board, settle it
    and check the end-of-hand and settlement properties.

    The deck is shuffled by a generator of its own, so the cards do not change the seed's betting sequence."""
    rng = random.Random(seed)
    hand = random_hand(rng, make_hand)
    hand.deck.shuffle(_rng=random.Random(f"deck-{seed}"))
    h = checked(hand)
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
            if live_count(h.hand) >= 2:
                assert_rejected(h.hand)  # a street boundary: the board is not complete yet
                if h.hand.street is Street.TURN:
                    probe = copy.deepcopy(h.hand)
                    deal_next_street(probe)  # the river is dealt but its round is not started, so betting may go on
                    assert_rejected(probe)
            h.next_street()
            if live_count(h.hand) >= 2 and not is_round_complete(h.betting):
                assert_rejected(h.hand)  # the new round is in progress
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

    unstarted_rounds = check_end_of_hand(h, exercised)
    check_settlement(h, exercised, seed, unstarted_rounds)
    return exercised


def check_end_of_hand(h: CheckedHand, exercised: Exercised) -> PokerHand | None:
    """Check the collected end state of the hand's betting, and run the board out when betting closed early.

    Returns a copy of the hand taken when betting closed early, with the remaining streets dealt but their betting
    rounds never started (the other way to reach the river, which settlement must treat the same), or None."""
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

    unstarted_rounds = None
    if is_betting_closed(h.hand) and len(live) >= 2:
        # Two or more live players and nobody left to bet: every later round asks nobody to act and moves no chips.
        exercised.all_in_run_outs = h.hand.street is not Street.RIVER
        if h.hand.street is not Street.RIVER:
            unstarted_rounds = copy.deepcopy(h.hand)
            while unstarted_rounds.street is not Street.RIVER:
                deal_next_street(unstarted_rounds)
            exercised.unstarted_round_settlements = 1
        totals = {hp.seat_number: hp.total_contribution for hp in players}
        while h.hand.street is not Street.RIVER:
            assert_rejected(h.hand)  # the board is not complete yet
            h.next_street()
            assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
            assert {hp.seat_number: hp.total_contribution for hp in players} == totals
            assert pots(h.hand) == layers
    return unstarted_rounds


def live_count(hand: PokerHand) -> int:
    return sum(not hp.folded for hp in hand.players)


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
        "accounting": [
            (hp.seat_number, hp.folded, hp.street_contribution, hp.total_contribution, tuple(hp.hole_cards))
            for hp in hand.players
        ],
        "chips": [(hp.seat_number, hp.player.stack, hp.all_in) for hp in hand.players],
        "pots": pots(hand),
        "middle_pot": middle_pot(hand),
    }


def assert_rejected(hand: PokerHand) -> None:
    """A contested hand that is not ready cannot be settled: the board is incomplete or betting may continue. The
    rejection leaves the hand exactly as it was."""
    error = IncompleteBoardError if len(hand.board) < 5 else ShowdownNotReadyError
    before = snapshot(hand)
    with pytest.raises(error):
        settle_hand(hand)
    assert snapshot(hand) == before


def canonical_live(hand: PokerHand) -> list[int]:
    """The live seats clockwise from the first seat left of the button, the button last."""
    seats = [hp.seat_number for hp in hand.players]  # clockwise, button first
    return [
        seat for seat in [*seats[1:], seats[0]] if not next(hp for hp in hand.players if hp.seat_number == seat).folded
    ]


def expected_showdown(hand: PokerHand, all_in_seats: set[int]) -> Showdown:
    """The showdown a ready contested hand starts with, stated without the implementation: ALL_IN when a live player is
    all-in (every live seat in canonical order), else the INTERACTIVE river decision order. No decisions yet."""
    live = canonical_live(hand)
    if all_in_seats & set(live):
        return Showdown(ShowdownKind.ALL_IN, tuple(live))
    assert hand.betting is not None
    start = live.index(hand.betting.last_aggressor) if hand.betting.last_aggressor is not None else 0
    return Showdown(ShowdownKind.INTERACTIVE, tuple(live[start:] + live[:start]))


def expected_derived(showdown: Showdown) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...], int | None, bool]:
    """Shown, mucked, contenders, current decider and completion of a showdown, recomputed from its order and decisions
    alone, stated without the implementation."""
    if showdown.kind is ShowdownKind.ALL_IN:
        return showdown.order, (), showdown.order, None, True
    pairs = list(zip(showdown.order, showdown.decisions, strict=False))
    shown = tuple(seat for seat, action in pairs if action is ShowdownAction.SHOW)
    mucked = tuple(seat for seat, action in pairs if action is ShowdownAction.MUCK)
    contenders = tuple(seat for seat in showdown.order if seat not in mucked)
    complete = len(showdown.decisions) == len(showdown.order) or len(contenders) == 1
    return shown, mucked, contenders, None if complete else showdown.order[len(showdown.decisions)], complete


def decide_seeded(rng: random.Random, hand: PokerHand, show_probability: float) -> None:
    """Start an interactive showdown and let each decider in turn SHOW or MUCK at random until it is complete, checking
    each step against the oracle. Out-of-turn decisions and an early settlement are rejected without a change."""
    start_showdown(hand)
    expected = expected_showdown(hand, set())
    assert hand.showdown == expected
    while True:
        showdown = hand.showdown
        assert showdown is not None
        assert (
            showdown.shown,
            showdown.mucked,
            showdown.contenders,
            showdown.current_decider,
            showdown.is_complete,
        ) == expected_derived(showdown)
        decider = showdown.current_decider
        other_seat = next((seat for seat in showdown.order if seat != decider), 99)
        before = snapshot(hand)
        with pytest.raises(NotShowdownTurnError):
            apply_showdown_action(hand, other_seat, ShowdownAction.SHOW)
        assert snapshot(hand) == before
        if decider is None:
            break
        with pytest.raises(ShowdownIncompleteError):
            settle_hand(hand)
        assert snapshot(hand) == before
        apply_showdown_action(
            hand, decider, ShowdownAction.SHOW if rng.random() < show_probability else ShowdownAction.MUCK
        )


def check_showdown_record(
    hand: PokerHand, all_in_seats: set[int], contested: bool, exercised: Exercised, show_probability: float
) -> None:
    """After settling: a contested hand has a complete showdown covering exactly its live seats, and an uncontested
    hand has none. Starting or deciding in a settled hand is rejected as settled."""
    if not contested:
        assert hand.showdown is None
        return
    showdown = hand.showdown
    assert showdown is not None and showdown.is_complete
    expected = expected_showdown(hand, all_in_seats)
    assert (showdown.kind, showdown.order) == (expected.kind, expected.order)
    assert sorted(showdown.order) == sorted(hp.seat_number for hp in hand.players if not hp.folded)
    assert not any(next(hp for hp in hand.players if hp.seat_number == seat).folded for seat in showdown.mucked)
    with pytest.raises(HandAlreadySettledError):
        start_showdown(hand)
    with pytest.raises(HandAlreadySettledError):
        apply_showdown_action(hand, showdown.order[0], ShowdownAction.MUCK)
    assert hand.showdown is showdown
    interactive = showdown.kind is ShowdownKind.INTERACTIVE
    exercised.all_in_showdowns = not interactive
    exercised.interactive_showdowns = interactive
    exercised.aggressor_showdowns = interactive and hand.betting is not None and hand.betting.last_aggressor is not None
    exercised.mucked_showdowns = bool(showdown.mucked)
    exercised.unshown_winners = interactive and len(showdown.contenders) == 1 and not showdown.shown


def check_awards(
    hand: PokerHand,
    awards: tuple[PotAward, ...],
    ranks: dict[int, HandRank],
    layers: tuple[Pot, ...],
    contenders: set[int],
) -> None:
    """The awarding rules, stated without the implementation: every pot is won by the best-ranked of its eligible seats
    that are contenders (a sole such seat takes it unranked), split in whole chips that differ by at most one, the
    larger first, in clockwise order from the seat left of the button, and only contenders are paid. The award's pot is
    the pot as derived, whatever the contenders."""
    seats = [hp.seat_number for hp in hand.players]  # clockwise, button first
    clockwise = [*seats[1:], seats[0]]  # first seat left of the button ... the button
    assert [award.pot for award in awards] == list(layers)
    paid: dict[int, int] = {}
    for award in awards:
        final = award.pot.eligible_seats & contenders
        winners = award.winners
        assert final and winners and set(winners) <= final
        if len(final) > 1:
            best = max(ranks[seat] for seat in final)
            assert set(winners) == {seat for seat in final if ranks[seat] == best}
        positions = [clockwise.index(seat) for seat in winners]
        assert positions == sorted(positions)
        amounts = [chips for _, chips in award.shares]
        assert sum(amounts) == award.pot.amount
        assert min(amounts) >= 1
        assert amounts == sorted(amounts, reverse=True)  # the larger shares come first
        assert max(amounts) - min(amounts) <= 1
        assert min(amounts) == award.pot.amount // len(winners)
        for seat, chips in award.shares:
            paid[seat] = paid.get(seat, 0) + chips
    assert sum(paid.values()) == middle_pot(hand)
    assert set(paid) <= contenders
    assert all(not hand.players[seats.index(seat)].folded for seat in paid)


def check_chosen_rank_awards(h: CheckedHand, exercised: Exercised, seed: int) -> None:
    """Award the hand's pots with tie-heavy chosen ranks, which real hands rarely produce, and check the awarding
    rules on the pots this hand really has. An uncontested hand has no ranks. It is awarded twice: with every live seat
    a contender, then with a seeded subset of them (see `check_contender_subset_awards`)."""
    hand = h.hand
    layers = pots(hand)
    live = [hp.seat_number for hp in hand.players if not hp.folded]
    rank_rng = random.Random(f"ranks-{seed}")
    ranks = {} if len(live) == 1 else {seat: rank_rng.choice(RANK_CHOICES) for seat in live}

    awards = _award_pots(layers, ranks, set(live), [hp.seat_number for hp in hand.players])

    check_awards(hand, awards, ranks, layers, set(live))
    exercised.identical_adjacent_pots = sum(a.eligible_seats == b.eligible_seats for a, b in pairwise(layers))
    exercised.tied_pots = sum(len(award.winners) > 1 for award in awards)
    exercised.odd_chip_splits = sum(len({chips for _, chips in award.shares}) > 1 for award in awards)
    exercised.multi_odd_chip_pots = sum(
        award.pot.amount % len(award.winners) >= 2 for award in awards if len(award.winners) > 1
    )
    check_contender_subset_awards(h, exercised, seed, ranks)


def check_contender_subset_awards(h: CheckedHand, exercised: Exercised, seed: int, ranks: dict[int, HandRank]) -> None:
    """Award the same pots among a seeded subset of the live seats, as a showdown with mucks would, and check the
    awarding rules. The subset always keeps every pot covered: it holds a seat of the deepest pot, whose eligible seats
    are inside every other pot's. Seats outside it keep their ranks, sometimes the best, which the awards must ignore,
    and a pot with a single final contender is won by it whatever the ranks say."""
    hand = h.hand
    layers = pots(hand)
    live = [hp.seat_number for hp in hand.players if not hp.folded]
    subset_rng = random.Random(f"contenders-{seed}")
    covering_seat = subset_rng.choice(sorted(layers[-1].eligible_seats))
    contenders = {seat for seat in live if subset_rng.random() < 0.6} | {covering_seat}

    awards = _award_pots(layers, ranks, contenders, [hp.seat_number for hp in hand.players])

    check_awards(hand, awards, ranks, layers, contenders)
    exercised.contender_subsets = contenders != set(live)
    exercised.sole_contender_side_pots = sum(
        len(award.pot.eligible_seats) > 1 and len(award.pot.eligible_seats & contenders) == 1 for award in awards
    )
    exercised.best_rank_excluded = sum(
        len(award.pot.eligible_seats & contenders) > 1
        and max(ranks[seat] for seat in award.pot.eligible_seats)
        > max(ranks[seat] for seat in award.pot.eligible_seats & contenders)
        for award in awards
    )


def unchanged_but(state: dict[str, Any], *names: str) -> dict[str, Any]:
    """A snapshot without the named parts, for checking that only they changed."""
    return {key: value for key, value in state.items() if key not in names}


def check_early_showdown(hand: PokerHand, contested: bool, all_in_seats: set[int], seed: int) -> None:
    """Starting the showdown of a ready hand before settling it, on a copy: an uncontested hand cannot start one; a
    contested hand gets the expected showdown and changes nothing else, cannot start twice, and settling keeps the
    showdown as it is (an interactive one after its decisions)."""
    early = copy.deepcopy(hand)
    before = snapshot(early)
    if not contested:
        with pytest.raises(UncontestedHandError):
            start_showdown(early)
        assert snapshot(early) == before
        return

    expected = expected_showdown(early, all_in_seats)
    if expected.kind is ShowdownKind.INTERACTIVE:
        decide_seeded(random.Random(f"early-{seed}"), early, 0.5)
        showdown = early.showdown
        assert showdown is not None and showdown.is_complete
    else:
        start_showdown(early)
        showdown = early.showdown
        assert showdown == expected
        after = snapshot(early)
        assert unchanged_but(after, "showdown") == unchanged_but(before, "showdown")
    with pytest.raises(ShowdownAlreadyStartedError):
        start_showdown(early)

    settle_hand(early)
    assert early.showdown is showdown


def check_settlement(h: CheckedHand, exercised: Exercised, seed: int, unstarted_rounds: PokerHand | None) -> None:
    """Settle the finished betting (dealing the rest of the board of a contested hand first, which the run-out already
    did) and check everything settlement promises. An all-in hand settles directly; an interactive one needs its
    showdown started and decided first, with seeded SHOW and MUCK decisions."""
    hand = h.hand
    live = [hp for hp in hand.players if not hp.folded]
    contested = len(live) >= 2
    layers = pots(hand)
    middle = middle_pot(hand)
    all_in_before = {hp.seat_number for hp in hand.players if hp.all_in}
    show_probability = random.Random(f"show-{seed}").choice((0.15, 0.5, 0.85))
    check_early_showdown(hand, contested, all_in_before, seed)
    if contested:
        assert len(hand.board) == 5
        if expected_showdown(hand, all_in_before).kind is ShowdownKind.INTERACTIVE:
            before_start = snapshot(hand)
            with pytest.raises(ShowdownNotStartedError):
                settle_hand(hand)
            assert snapshot(hand) == before_start
            decide_seeded(random.Random(f"decisions-{seed}"), hand, show_probability)
    showdown = hand.showdown
    if contested and showdown is None:
        # A direct settlement of an ALL_IN hand records the complete showdown: every live hand is shown and competes.
        assert expected_showdown(hand, all_in_before).kind is ShowdownKind.ALL_IN
        contenders = shown = set(canonical_live(hand))
    else:
        contenders = set(showdown.contenders) if showdown is not None else {hp.seat_number for hp in live}
        shown = set(showdown.shown) if showdown is not None else set()
    if contested:
        # Only shown hands are evaluated: the settlement ranks exactly the shown seats, in hand order.
        expected_ranks = {
            hp.seat_number: evaluate_best([*hp.hole_cards, *hand.board]) for hp in live if hp.seat_number in shown
        }
    else:
        expected_ranks = {}  # an uncontested hand is settled on whatever street it ended, without evaluating anything
    before = snapshot(hand)  # taken right before settling: dealing is not part of settlement

    settle_hand(hand)

    settlement = hand.settlement
    assert settlement is not None
    after = snapshot(hand)
    # Settlement changes stacks, all_in and the settlement record, and nothing else; the only other change is an ALL_IN
    # showdown recorded together with it, and an existing showdown is the same object.
    assert before["settlement"] is None and after["settlement"] is settlement
    assert unchanged_but(after, "chips", "settlement", "showdown") == unchanged_but(
        before, "chips", "settlement", "showdown"
    )
    if showdown is None and contested:
        assert hand.showdown == expected_showdown(hand, all_in_before)
        showdown = hand.showdown
    assert hand.showdown is showdown
    check_showdown_record(hand, all_in_before, contested, exercised, show_probability)

    assert settlement.showdown_ranks == tuple(expected_ranks.items())
    payouts = settlement.payouts
    assert set(payouts) <= contenders
    for hp in hand.players:
        assert hp.player.stack == h.starting_chips[hp.seat_number] - hp.total_contribution + payouts.get(
            hp.seat_number, 0
        )
        assert hp.all_in == (hp.player.stack == 0)
    assert sum(payouts.values()) == middle == sum(pot.amount for pot in layers)
    assert sum(hp.player.stack for hp in hand.players) == sum(h.starting_chips.values())  # no chip appears or vanishes
    check_awards(hand, settlement.pot_awards, expected_ranks, layers, contenders)

    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)
    assert snapshot(hand) == after

    if unstarted_rounds is not None:
        # Reaching the river without starting the skipped rounds changes nothing about the settlement.
        assert unstarted_rounds.board == hand.board
        settle_hand(unstarted_rounds)
        assert unstarted_rounds.settlement == settlement
        assert unstarted_rounds.showdown == hand.showdown
        assert [(hp.player.stack, hp.all_in) for hp in unstarted_rounds.players] == [
            (hp.player.stack, hp.all_in) for hp in hand.players
        ]

    exercised.contested_showdowns = contested
    exercised.uncontested_settlements = not contested
    exercised.different_pot_winners = len(layers) >= 2 and len({award.winners for award in settlement.pot_awards}) >= 2
    now_all_in = {hp.seat_number for hp in hand.players if hp.all_in}
    exercised.paid_all_ins_cleared = len({seat for seat in all_in_before if seat in payouts} - now_all_in)
    exercised.unpaid_all_ins_kept = len({seat for seat in all_in_before if seat not in payouts} & now_all_in)
    check_chosen_rank_awards(h, exercised, seed)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_hand_keeps_every_betting_accounting_and_settlement_invariant(
    seed: int, checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Every step of the seed's hand keeps the invariants `CheckedHand` checks, and the hand ends collected: nothing
    in front, every chip in a stack or in the pots, the main pot contested by every live player, and, when betting
    closes early with two or more live players, later rounds that ask nobody to act and move no chips. The hand then
    settles correctly: see `check_settlement`."""
    play_random_hand(seed, checked, make_hand)


def test_random_hands_keep_reaching_the_rules_they_stress(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """The seed set is useful only while it keeps reaching the all-in rules, so a change to the generator or the
    engine that quietly stops producing them fails here. Across the seeds there are short blinds, short calls, short
    bets and raises, pending players a short all-in did not let raise, returned chips, river betting, all-in run-outs,
    folded players' dead money in side pots, and a nine-handed hand with a main pot and seven side pots. Settlement is
    reached both contested and uncontested, with different winners for different pots, with paid all-in players who stop
    being all-in and unpaid ones who keep it; and the chosen ranks reach odd-chip splits, tied pots, identical adjacent
    pots and pots with several odd chips."""
    seen = Exercised()
    for seed in SEEDS:
        exercised = play_random_hand(seed, checked, make_hand)
        for counter in fields(Exercised):
            if counter.name != "deepest_layering":
                setattr(seen, counter.name, getattr(seen, counter.name) + getattr(exercised, counter.name))
        seen.deepest_layering = max(seen.deepest_layering, exercised.deepest_layering)

    assert seen.deepest_layering == 8  # nine-handed, the deepest layering a hand can have
    counts = {
        counter.name: getattr(seen, counter.name)
        for counter in fields(Exercised)
        if counter.name != "deepest_layering" and counter.name not in RARE_COUNTERS
    }
    assert all(count >= MIN_OCCURRENCES for count in counts.values()), counts
    assert all(getattr(seen, name) >= 1 for name in RARE_COUNTERS), {
        name: getattr(seen, name) for name in RARE_COUNTERS
    }

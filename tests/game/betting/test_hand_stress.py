"""Deterministic randomized hands, driven through the public dealing, betting and settlement operations.

Each seed builds a hand of 2-9 players with uneven stacks (some around or below the blinds, so short blinds, short
calls, short bets and raises, and several all-in levels happen) and a seeded shuffled deck, and plays random legal
actions: folds, checks, calls, full bets and raises at the minimum, the maximum and in between, and short all-in
targets, street by street until betting is closed or the river round is complete. `CheckedHand` asserts the betting and
accounting invariants after every step. The remaining streets are then dealt and the hand is settled, and the tests
here add the end-of-hand and settlement properties: the settlement invariants, table-wide chip conservation, winners
that really hold the best hands, rejection of settling too early or twice, the reveal every contested hand ends with
(none for an uncontested one), and the awarding rules on the same hand's pots under tie-heavy chosen ranks. They also
check that the seed set keeps reaching the rules it stresses.
The seeds are fixed, so every run plays the same hands and a failure names the seed that reproduces it. This is the
main seeded hand driver in the repository; `test_reveal_stress` is a second one, with deep stacks and passive play, for
dense non-all-in river showdowns.
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
from go_poker.game.reveal import Reveal, RevealKind
from go_poker.game.settlement import HandAlreadySettledError, PotAward, _award_pots
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    HandAlreadyRevealedError,
    IncompleteBoardError,
    ShowdownNotReadyError,
    UncontestedHandError,
    reveal_hands,
    settle_hand,
)

# The conftest `CheckedHand`, which test modules cannot import.
type CheckedHand = Any
type HandFactory = Callable[..., PokerHand]

STAKES = Stakes(small_blind=50, big_blind=100)
SEEDS = range(200)
MAX_STEPS = 1_000  # far more steps than any generated hand needs
MIN_OCCURRENCES = 10  # how often, at least, the seed set must reach each rule it stresses
# The generator is aggressive, so hands that reach the river with nobody all-in are rare; the seed set has a few.
RARE_COUNTERS = ("showdown_reveals", "aggressor_showdowns")

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
    all_in_reveals: int = 0  # settled hands revealed all-in
    showdown_reveals: int = 0  # settled hands revealed in the river show order (rare, see RARE_COUNTERS)
    aggressor_showdowns: int = 0  # river show orders starting with a river bettor or raiser (rare)
    different_pot_winners: int = 0  # settled hands with several pots that were not all won by the same winners
    paid_all_ins_cleared: int = 0  # all-in players paid at settlement, who stop being all-in
    unpaid_all_ins_kept: int = 0  # all-in players paid nothing, who keep their zero stack and all_in
    # From the chosen-rank awards on the hand's pots (see `check_chosen_rank_awards`):
    odd_chip_splits: int = 0  # pots whose winners did not all get the same chips
    tied_pots: int = 0  # pots with several winners
    identical_adjacent_pots: int = 0  # neighbouring pots with the same eligible seats
    multi_odd_chip_pots: int = 0  # pots with several winners and two or more odd chips


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
        "reveal": hand.reveal,
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


def expected_reveal(hand: PokerHand, all_in_seats: set[int]) -> Reveal:
    """The reveal of a ready contested hand, stated without the implementation: ALL_IN when a live player is all-in
    (every live seat clockwise from the first seat left of the button), else the river show order."""
    seats = [hp.seat_number for hp in hand.players]  # clockwise, button first
    live = [seat for seat in [*seats[1:], seats[0]] if seat in {hp.seat_number for hp in hand.players if not hp.folded}]
    if all_in_seats & set(live):
        return Reveal(RevealKind.ALL_IN, tuple(live))
    assert hand.betting is not None
    start = live.index(hand.betting.last_aggressor) if hand.betting.last_aggressor is not None else 0
    return Reveal(RevealKind.SHOWDOWN, tuple(live[start:] + live[:start]))


def check_reveal(hand: PokerHand, all_in_seats: set[int], contested: bool) -> None:
    """After settling directly: a contested hand has a reveal covering exactly its live seats, and an uncontested hand
    has none. Revealing a settled hand is rejected as settled."""
    if not contested:
        assert hand.reveal is None
        return
    expected = expected_reveal(hand, all_in_seats)
    assert hand.reveal == expected
    assert sorted(expected.seats) == sorted(hp.seat_number for hp in hand.players if not hp.folded)
    with pytest.raises(HandAlreadySettledError):
        reveal_hands(hand)


def check_awards(
    hand: PokerHand, awards: tuple[PotAward, ...], ranks: dict[int, HandRank], layers: tuple[Pot, ...]
) -> None:
    """The awarding rules, stated without the implementation: every pot is won by the best-ranked eligible seats, split
    in whole chips that differ by at most one, the larger first, in clockwise order from the seat left of the button,
    and only live seats are paid."""
    seats = [hp.seat_number for hp in hand.players]  # clockwise, button first
    clockwise = [*seats[1:], seats[0]]  # first seat left of the button ... the button
    assert [award.pot for award in awards] == list(layers)
    paid: dict[int, int] = {}
    for award in awards:
        eligible = award.pot.eligible_seats
        winners = award.winners
        assert winners and set(winners) <= eligible
        if len(eligible) > 1:
            best = max(ranks[seat] for seat in eligible)
            assert set(winners) == {seat for seat in eligible if ranks[seat] == best}
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
    assert all(not hand.players[seats.index(seat)].folded for seat in paid)


def check_chosen_rank_awards(h: CheckedHand, exercised: Exercised, seed: int) -> None:
    """Award the hand's pots with tie-heavy chosen ranks, which real hands rarely produce, and check the awarding
    rules on the pots this hand really has. An uncontested hand has no ranks."""
    hand = h.hand
    layers = pots(hand)
    live = [hp.seat_number for hp in hand.players if not hp.folded]
    rank_rng = random.Random(f"ranks-{seed}")
    ranks = {} if len(live) == 1 else {seat: rank_rng.choice(RANK_CHOICES) for seat in live}

    awards = _award_pots(layers, ranks, [hp.seat_number for hp in hand.players])

    check_awards(hand, awards, ranks, layers)
    exercised.identical_adjacent_pots = sum(a.eligible_seats == b.eligible_seats for a, b in pairwise(layers))
    exercised.tied_pots = sum(len(award.winners) > 1 for award in awards)
    exercised.odd_chip_splits = sum(len({chips for _, chips in award.shares}) > 1 for award in awards)
    exercised.multi_odd_chip_pots = sum(
        award.pot.amount % len(award.winners) >= 2 for award in awards if len(award.winners) > 1
    )


def check_early_reveal(hand: PokerHand, contested: bool, all_in_seats: set[int]) -> None:
    """Revealing a ready hand before settling it, on a copy: an uncontested hand cannot be revealed; a contested hand
    gets the expected reveal and changes nothing else, cannot be revealed twice, and settling keeps the reveal as it
    is."""
    early = copy.deepcopy(hand)
    before = snapshot(early)
    if not contested:
        with pytest.raises(UncontestedHandError):
            reveal_hands(early)
        assert snapshot(early) == before
        return

    reveal_hands(early)
    after = snapshot(early)
    reveal = early.reveal
    assert reveal == expected_reveal(early, all_in_seats)
    assert {k: v for k, v in after.items() if k != "reveal"} == {k: v for k, v in before.items() if k != "reveal"}
    with pytest.raises(HandAlreadyRevealedError):
        reveal_hands(early)
    assert snapshot(early) == after

    settle_hand(early)
    assert early.reveal is reveal


def check_settlement(h: CheckedHand, exercised: Exercised, seed: int, unstarted_rounds: PokerHand | None) -> None:
    """Settle the finished betting (dealing the rest of the board of a contested hand first, which the run-out already
    did) and check everything settlement promises."""
    hand = h.hand
    live = [hp for hp in hand.players if not hp.folded]
    contested = len(live) >= 2
    layers = pots(hand)
    middle = middle_pot(hand)
    if contested:
        assert len(hand.board) == 5
        expected_ranks = {hp.seat_number: evaluate_best([*hp.hole_cards, *hand.board]) for hp in live}
    else:
        expected_ranks = {}  # an uncontested hand is settled on whatever street it ended, without evaluating anything
    all_in_before = {hp.seat_number for hp in hand.players if hp.all_in}
    check_early_reveal(hand, contested, all_in_before)
    before = snapshot(hand)  # taken right before settling: dealing is not part of settlement

    settle_hand(hand)

    settlement = hand.settlement
    assert settlement is not None
    after = snapshot(hand)
    # Settlement changes stacks, all_in and the settlement record, and nothing else.
    assert before["settlement"] is None and after["settlement"] is settlement
    assert {k: v for k, v in after.items() if k not in ("chips", "settlement", "reveal")} == {
        k: v for k, v in before.items() if k not in ("chips", "settlement", "reveal")
    }
    check_reveal(hand, all_in_before, contested)
    exercised.all_in_reveals = hand.reveal is not None and hand.reveal.kind is RevealKind.ALL_IN
    exercised.showdown_reveals = hand.reveal is not None and hand.reveal.kind is RevealKind.SHOWDOWN
    exercised.aggressor_showdowns = exercised.showdown_reveals and h.betting.last_aggressor is not None

    assert settlement.showdown_ranks == tuple(expected_ranks.items())
    payouts = settlement.payouts
    for hp in hand.players:
        assert hp.player.stack == h.starting_chips[hp.seat_number] - hp.total_contribution + payouts.get(
            hp.seat_number, 0
        )
        assert hp.all_in == (hp.player.stack == 0)
    assert sum(payouts.values()) == middle == sum(pot.amount for pot in layers)
    assert sum(hp.player.stack for hp in hand.players) == sum(h.starting_chips.values())  # no chip appears or vanishes
    check_awards(hand, settlement.pot_awards, expected_ranks, layers)

    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)
    assert snapshot(hand) == after

    if unstarted_rounds is not None:
        # Reaching the river without starting the skipped rounds changes nothing about the settlement.
        assert unstarted_rounds.board == hand.board
        settle_hand(unstarted_rounds)
        assert unstarted_rounds.settlement == settlement
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
    assert seen.showdown_reveals >= 1 and seen.aggressor_showdowns >= 1

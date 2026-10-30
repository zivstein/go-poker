"""Pot awarding fed with pots derived from real betting.

The pots here come from `pots(hand)` after real betting operations, not from hand-written pots, so they have the shapes
the engine really produces: a short all-in level, folded players' dead money, and adjacent pots whose eligible seats are
identical. Ranks are chosen by the test (hand strength is not what is under test), and `_award_pots` is checked against
the awarding rules, first on one concrete hand and then on seeded random hands.
"""

import random
from itertools import pairwise

import pytest

from go_poker.core.deck import Deck
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.settlement import PotAward, Settlement, _award_pots
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

STAKES = Stakes(small_blind=5, big_blind=10)

BEST = HandRank(HandCategory.FLUSH, (14, 10, 8, 5, 3))
MIDDLE = HandRank(HandCategory.TWO_PAIR, (9, 4, 14))
WEAK = HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 6, 4))
RANK_CHOICES = (BEST, MIDDLE, WEAK)  # few distinct ranks, so ties are common

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def start_hand(stacks: dict[int, int], button_seat: int) -> PokerHand:
    """A hand clockwise from the button with its blinds posted, preflop betting initialized and hole cards dealt."""
    assignments = assign_hand_seats(tuple(stacks), button_seat)
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat}", stack=stacks[seat], status=PlayerStatus.READY),
            seat_number=seat,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat, assignment in assignments.items()
    )
    hand = PokerHand(players=players, deck=Deck())
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    return hand


def pot(amount: int, *eligible_seats: int) -> Pot:
    return Pot(amount, frozenset(eligible_seats))


# =============================================================================
# REAL-BETTING SCENARIO: short all-in, dead money, adjacent identical pots
# =============================================================================


def short_all_in_with_dead_money() -> PokerHand:
    """Seats 1, 3, 5, 7, 9 with the button at seat 3, so the seats clockwise from the button are 3, 5, 7, 9, 1.

    Seat 9 raises to 30 and seat 1 calls; the button, seat 3, calls all-in for 25. The small blind (seat 5, 5 chips) and
    the big blind (seat 7, 10 chips) fold, leaving dead money below and between the live levels.
    """
    hand = start_hand({1: 100, 3: 25, 5: 100, 7: 100, 9: 100}, button_seat=3)
    for seat, action in ((9, raise_to(30)), (1, CALL), (3, CALL), (5, FOLD), (7, FOLD)):
        apply_action(hand, seat, action)
    assert is_round_complete(hand.betting)  # type: ignore[arg-type]
    return hand


def test_real_pots_have_adjacent_pots_with_identical_eligible_seats() -> None:
    """The scenario's premise: the collected levels 5, 10, 25 and 30 give three pots seats 1, 3 and 9 all contest, and
    a last pot only seats 1 and 9 can win."""
    assert pots(short_all_in_with_dead_money()) == (
        pot(25, 1, 3, 9),
        pot(20, 1, 3, 9),
        pot(45, 1, 3, 9),
        pot(10, 1, 9),
    )


def test_two_tied_winners_split_every_identical_pot_with_odd_chips_wrapping_past_the_button() -> None:
    """Seats 9 and 1 tie for the best hand and the short stack, seat 3 (the button), is weakest. Seat 9 is the first
    seat left of the button among the winners, although seat 1 has the lower number, so it takes each pot's odd chip;
    odd chips are decided per pot, not carried from one pot to the next."""
    hand = short_all_in_with_dead_money()
    ranks = {1: BEST, 3: WEAK, 9: BEST}

    awards = _award_pots(pots(hand), ranks, [state.seat_number for state in hand.players])

    assert [award.shares for award in awards] == [
        ((9, 13), (1, 12)),
        ((9, 10), (1, 10)),
        ((9, 23), (1, 22)),
        ((9, 5), (1, 5)),
    ]
    assert Settlement(awards, ()).payouts == {9: 51, 1: 49}


def test_a_three_way_tie_in_the_odd_pots_gives_the_button_the_last_odd_chip() -> None:
    """With the button, seat 3, tied in too, the order is 9, 1, 3: the 25-chip pot's one odd chip goes to seat 9, and
    the 20-chip pot's two to seats 9 and 1. The last pot is not open to seat 3, which is all-in for less."""
    hand = short_all_in_with_dead_money()
    ranks = {1: BEST, 3: BEST, 9: BEST}

    awards = _award_pots(pots(hand), ranks, [state.seat_number for state in hand.players])

    assert [award.shares for award in awards] == [
        ((9, 9), (1, 8), (3, 8)),
        ((9, 7), (1, 7), (3, 6)),
        ((9, 15), (1, 15), (3, 15)),
        ((9, 5), (1, 5)),
    ]


def test_the_best_short_stack_wins_only_the_pots_it_reaches_with_the_dead_money() -> None:
    """The button's best hand takes the three pots it is eligible for, dead money included; the last pot goes to the
    better of the others, and the folded blinds, who hold no rank, never take a share."""
    hand = short_all_in_with_dead_money()
    ranks = {1: MIDDLE, 3: BEST, 9: WEAK}

    awards = _award_pots(pots(hand), ranks, [state.seat_number for state in hand.players])

    assert Settlement(awards, ()).payouts == {3: 90, 1: 10}


# =============================================================================
# SEEDED RANDOM HANDS
# =============================================================================

SEEDS = range(300)
STACK_RANGES = ((1, 40), (40, 150), (150, 600))


def random_action(rng: random.Random, legal: LegalActions) -> Action:
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
        choices += [(Action(kind, low), 3), (Action(kind, rng.randint(low, high)), 2), (Action(kind, high), 1)]
    return rng.choices([action for action, _ in choices], [weight for _, weight in choices])[0]


def play_random_betting(rng: random.Random) -> PokerHand:
    """A random hand of 2-9 uneven stacks, played through real betting until it is closed or the river round is done."""
    seats = sorted(rng.sample(range(1, 10), rng.randint(2, 9)))
    hand = start_hand({seat: rng.randint(*rng.choice(STACK_RANGES)) for seat in seats}, rng.choice(seats))
    for _ in range(1_000):
        if is_round_complete(hand.betting):  # type: ignore[arg-type]
            if is_betting_closed(hand) or hand.street is Street.RIVER:
                return hand
            deal_next_street(hand)
            start_betting_round(hand)
            continue
        actor = hand.betting.current_actor  # type: ignore[union-attr]
        assert actor is not None
        apply_action(hand, actor, random_action(rng, legal_actions(hand)))
    pytest.fail("betting did not end")


def check_awards(
    hand: PokerHand, awards: tuple[PotAward, ...], ranks: dict[int, HandRank], layers: tuple[Pot, ...]
) -> None:
    """The awarding rules, stated without the implementation: every pot is won by the best-ranked eligible seats, split
    in whole chips that differ by at most one, the larger first, in clockwise order from the seat left of the button."""
    seats = [state.seat_number for state in hand.players]  # clockwise, button first
    clockwise = [*seats[1:], seats[0]]  # first seat left of the button ... the button
    assert [award.pot for award in awards] == list(layers)
    for award in awards:
        eligible = award.pot.eligible_seats
        winners = award.winners
        assert winners and set(winners) <= eligible
        if len(eligible) > 1:
            best = max(ranks[seat] for seat in eligible)
            assert set(winners) == {seat for seat in eligible if ranks[seat] == best}
        # In clockwise order from the seat left of the button, the button last.
        positions = [clockwise.index(seat) for seat in winners]
        assert positions == sorted(positions)
        amounts = [chips for _, chips in award.shares]
        assert sum(amounts) == award.pot.amount
        assert min(amounts) >= 1
        assert amounts == sorted(amounts, reverse=True)  # the larger shares come first
        assert max(amounts) - min(amounts) <= 1
        assert min(amounts) == award.pot.amount // len(winners)
    payouts = Settlement(awards, ()).payouts
    assert sum(payouts.values()) == middle_pot(hand)
    assert all(not hand.players[seats.index(seat)].folded for seat in payouts)


@pytest.mark.parametrize("seed", SEEDS)
def test_random_engine_pots_are_awarded_by_the_rules(seed: int) -> None:
    rng = random.Random(seed)
    hand = play_random_betting(rng)
    layers = pots(hand)
    live = [state.seat_number for state in hand.players if not state.folded]
    # An uncontested hand has no showdown ranks; otherwise every live player has one, drawn to tie often.
    ranks = {} if len(live) == 1 else {seat: rng.choice(RANK_CHOICES) for seat in live}

    awards = _award_pots(layers, ranks, [state.seat_number for state in hand.players])

    check_awards(hand, awards, ranks, layers)


def test_random_hands_keep_reaching_odd_chips_ties_and_identical_adjacent_pots() -> None:
    """The seed set stays useful only while it reaches what it checks."""
    odd_chip_splits = tied_pots = identical_adjacent = multi_winner_odd_pots = uncontested = 0
    for seed in SEEDS:
        rng = random.Random(seed)
        hand = play_random_betting(rng)
        layers = pots(hand)
        live = [state.seat_number for state in hand.players if not state.folded]
        ranks = {} if len(live) == 1 else {seat: rng.choice(RANK_CHOICES) for seat in live}
        awards = _award_pots(layers, ranks, [state.seat_number for state in hand.players])
        uncontested += len(live) == 1
        identical_adjacent += any(a.eligible_seats == b.eligible_seats for a, b in pairwise(layers))
        tied_pots += sum(len(award.winners) > 1 for award in awards)
        odd_chip_splits += sum(len({chips for _, chips in award.shares}) > 1 for award in awards)
        multi_winner_odd_pots += sum(
            award.pot.amount % len(award.winners) >= 2 for award in awards if len(award.winners) > 1
        )

    assert min(odd_chip_splits, tied_pots, identical_adjacent, multi_winner_odd_pots, uncontested) >= 10, (
        odd_chip_splits,
        tied_pots,
        identical_adjacent,
        multi_winner_odd_pots,
        uncontested,
    )

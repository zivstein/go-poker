"""Pots and their awards against a chip-by-chip oracle (ADR 0001 §1, GitHub issue #2).

`pots(hand)` and the awarding rules are checked on many seeded hand-built collected states without reusing any of the
production's level arithmetic or its merge. The oracle walks the middle pot one chip height at a time, asks who could
win the chips at that height, and calls every maximal run of heights with the same eligible seats one pot. The awards
are recomputed from those pots with their own odd-chip order. So a defect that merged pots by something other than
their eligible seats (the winners, say), kept equivalent layers apart, or let a folded level split a pot is caught by a
different formulation than the code's.

The states are hand-built collected contributions, as in test_pots.py; the integration tests reach such states through
real betting.
"""

import random
from collections.abc import Callable

from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import Settlement, _award_pots, _settle

type HandFactory = Callable[[dict[int, int], int], PokerHand]

MAX_SEATS = 9
RANKS = (
    HandRank(HandCategory.FLUSH, (14, 10, 8, 5, 3)),
    HandRank(HandCategory.TWO_PAIR, (9, 4, 14)),
    HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 6, 4)),
)
CONTRIBUTION_CHOICES = (5, 10, 15, 25, 25, 50, 75, 100)  # repeated levels, many equal and some distinct


def collected_hand(
    make_hand: HandFactory, button: int, contributions: dict[int, int], folded: set[int], all_in: set[int]
) -> PokerHand:
    """A hand after a collected betting round: each seat has the given chips committed and nothing in front."""
    hand = make_hand(starting_stacks(contributions, all_in), button)
    for state in hand.players:
        state.total_contribution = contributions[state.seat_number]
        state.folded = state.seat_number in folded
        state.all_in = state.seat_number in all_in
        state.player.stack -= state.total_contribution
    return hand


def starting_stacks(contributions: dict[int, int], all_in: set[int]) -> dict[int, int]:
    """1000 chips each, except an all-in seat, which started with exactly what it put in."""
    return {seat: chips if seat in all_in else 1000 for seat, chips in contributions.items()}


def oracle_pots(contributions: dict[int, int], folded: set[int]) -> list[Pot]:
    """The pots, one chip height at a time: the chips at height h are one from every seat that collected at least h, and
    the seats that can win them are the live ones among those. Equal neighbouring heights are one pot."""
    live = set(contributions) - folded
    result: list[tuple[int, frozenset[int]]] = []
    for height in range(1, max(contributions[seat] for seat in live) + 1):
        eligible = frozenset(seat for seat in live if contributions[seat] >= height)
        chips = sum(1 for chips in contributions.values() if chips >= height)
        if result and result[-1][1] == eligible:
            result[-1] = (result[-1][0] + chips, eligible)
        else:
            result.append((chips, eligible))
    return [Pot(amount, eligible) for amount, eligible in result]


def oracle_shares(
    pot: Pot, button: int, contenders: set[int], ranks: dict[int, HandRank]
) -> tuple[tuple[int, int], ...]:
    """Who gets what from one pot: the best-ranked of its eligible contenders split it, the odd chips going one each
    clockwise from the first seat left of the button, which is the button's own seat last."""
    clockwise_from_left_of_button = sorted(pot.eligible_seats & contenders, key=lambda seat: (seat - button - 1) % 100)
    best = max(ranks[seat] for seat in clockwise_from_left_of_button)
    winners = [seat for seat in clockwise_from_left_of_button if ranks[seat] == best]
    shares = []
    for index, seat in enumerate(winners):
        shares.append((seat, pot.amount // len(winners) + (1 if index < pot.amount % len(winners) else 0)))
    return tuple(shares)


def random_state(rng: random.Random) -> tuple[int, dict[int, int], set[int], set[int]]:
    """A button, collected contributions per seat, the folded seats and the all-in seats of a hand: at least two seats
    and one live one, and the highest collected level held by a live seat (a folded player never holds more than
    everyone who stays live, since folding needs a larger bet to face). Not every state is one real betting reaches: an
    unmatched top level would have been returned, but `pots` is a pure function of the contributions and is checked on
    them all."""
    seats = sorted(rng.sample(range(1, MAX_SEATS + 1), rng.randint(2, MAX_SEATS)))
    contributions = {seat: rng.choice(CONTRIBUTION_CHOICES) for seat in seats}
    folded = {seat for seat in seats if rng.random() < 0.45}
    top_seat = max(seats, key=lambda seat: (contributions[seat], rng.random()))
    folded.discard(top_seat)
    live = set(seats) - folded
    top_live = max(contributions[seat] for seat in live)
    for seat in folded:
        contributions[seat] = min(contributions[seat], top_live)
    all_in = {seat for seat in live if contributions[seat] < top_live and rng.random() < 0.7}
    return rng.choice(seats), contributions, folded, all_in


def test_pots_equal_the_chip_by_chip_oracle_and_never_share_eligible_seats(make_hand: HandFactory) -> None:
    rng = random.Random("pots-chip-oracle")
    multi_pot_hands = merged_hands = 0
    for _ in range(1500):
        button, contributions, folded, all_in = random_state(rng)
        hand = collected_hand(make_hand, button, contributions, folded, all_in)

        layers = pots(hand)
        expected = oracle_pots(contributions, folded)

        assert list(layers) == expected, (button, contributions, folded)
        assert sum(pot.amount for pot in layers) == middle_pot(hand) == sum(contributions.values())
        eligible_sets = [pot.eligible_seats for pot in layers]
        assert len(set(eligible_sets)) == len(eligible_sets)  # no two pots share eligible seats
        assert all(later < earlier for earlier, later in zip(eligible_sets, eligible_sets[1:], strict=False))  # strict
        assert all(pot.eligible_seats and not pot.eligible_seats & folded for pot in layers)
        multi_pot_hands += len(layers) > 1
        merged_hands += len({level for level in contributions.values()}) > len(layers)

    assert multi_pot_hands > 500  # real side pots stay apart in many of the states
    assert merged_hands > 500  # and folded or repeated levels merge in many of them


def test_awards_equal_the_oracle_with_ties_odd_chips_mucks_and_conservation(make_hand: HandFactory) -> None:
    rng = random.Random("awards-chip-oracle")
    checked = tied_pots = odd_pots = multi_odd_pots = same_winners_in_several_pots = muck_hands = 0
    while checked < 1500:
        button, contributions, folded, all_in = random_state(rng)
        hand = collected_hand(make_hand, button, contributions, folded, all_in)
        live = set(contributions) - folded
        mucked = {seat for seat in live if rng.random() < 0.2}
        contenders = live - mucked
        layers = oracle_pots(contributions, folded)
        if not contenders or any(not pot.eligible_seats & contenders for pot in layers):
            continue  # a pot nobody competes for is an engine invariant violation, never a reachable settlement
        ranks = {seat: rng.choice(RANKS[:2] if rng.random() < 0.7 else RANKS) for seat in contenders}
        checked += 1
        muck_hands += bool(mucked)

        seats_from_button = [state.seat_number for state in hand.players]
        awards = _award_pots(pots(hand), ranks, contenders, seats_from_button)
        expected = [oracle_shares(pot, button, contenders, ranks) for pot in layers]

        assert [award.pot for award in awards] == layers
        assert [award.shares for award in awards] == expected, (button, contributions, folded, mucked, ranks)
        tied_pots += sum(len(shares) > 1 for shares in expected)
        odd_pots += sum(len({chips for _, chips in shares}) > 1 for shares in expected)
        multi_odd_pots += sum(
            len(shares) > 1 and pot.amount % len(shares) >= 2 for pot, shares in zip(layers, expected, strict=True)
        )
        winner_sets = [frozenset(seat for seat, _ in shares) for shares in expected]
        same_winners_in_several_pots += len(set(winner_sets)) < len(winner_sets)  # same winners, pots still apart

        settlement = _settle(hand, ranks if len(contenders) > 1 else {}, contenders)
        assert sum(settlement.payouts.values()) == sum(contributions.values())
        started = starting_stacks(contributions, all_in)
        assert sum(state.player.stack for state in hand.players) == sum(started.values())  # chips conserved
        for state in hand.players:
            paid = settlement.payouts.get(state.seat_number, 0)
            assert state.player.stack == started[state.seat_number] - contributions[state.seat_number] + paid
            assert state.all_in == (state.player.stack == 0)

    assert tied_pots > 500 and odd_pots > 150 and multi_odd_pots > 50 and muck_hands > 200
    assert same_winners_in_several_pots > 300  # winners alone never merge pots: those pots are still separate


def test_side_pots_with_the_same_winners_split_their_odd_chips_independently(make_hand: HandFactory) -> None:
    """Seat 1 is all-in for 5, seats 2 and 3 are live with 12 each, and seats 4 and 5 folded with 1 and 6. Seats 2 and 3
    tie for everything they reach and seat 1 is weakest. The main pot of 21 (seats 1, 2 and 3) and the side pot of 15
    (seats 2 and 3) have different eligible seats, so they are two pots although the same two seats win both: each
    decides its own odd chip, and seat 2, the first left of the button, takes both: 19 / 17. Merged because of their
    winners they would be one pot of 36 paid 18 / 18, which is what a wrong merge would do."""
    contributions = {1: 5, 2: 12, 3: 12, 4: 1, 5: 6}
    hand = collected_hand(make_hand, 1, contributions, folded={4, 5}, all_in={1})
    ranks = {1: RANKS[2], 2: RANKS[0], 3: RANKS[0]}

    awards = _award_pots(pots(hand), ranks, {1, 2, 3}, [1, 2, 3, 4, 5])

    assert [(award.pot.amount, set(award.pot.eligible_seats)) for award in awards] == [(21, {1, 2, 3}), (15, {2, 3})]
    assert [award.shares for award in awards] == [((2, 11), (3, 10)), ((2, 8), (3, 7))]
    assert Settlement(awards, ()).payouts == {2: 19, 3: 17}

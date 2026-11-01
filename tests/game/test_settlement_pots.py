"""Pot awarding fed with pots derived from real betting.

The pots here come from `pots(hand)` after real betting operations, not from hand-written pots, so they have the shapes
the engine really produces: a short all-in level, folded players' dead money, and adjacent pots whose eligible seats are
identical. Ranks are chosen by the test (hand strength is not what is under test). The awarding rules are also checked
on seeded random hands by the one seeded hand driver, in tests/game/betting/test_hand_stress.py.

Contender subsets model showdown mucks. `_settle` is driven directly here because it is internal and takes the final
contenders as given; the Hold'em-level tests reach the same awards through the public operations.

The contender-subset and muck tests on layered all-in pots exercise the variant-agnostic `_settle` / `_award_pots`
contract directly. In Hold'em a muck only happens in an interactive showdown, where no live player is all-in and every
pot has the same eligible seats, so some of these states (for example a mucked all-in seat keeping `all_in` with a zero
stack) are not reachable through Hold'em operations.
"""

import pytest

from go_poker.core.deck import Deck
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.betting.rounds import is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.settlement import Settlement, SettlementInvariantError, _award_pots, _settle
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards

STAKES = Stakes(small_blind=5, big_blind=10)

BEST = HandRank(HandCategory.FLUSH, (14, 10, 8, 5, 3))
MIDDLE = HandRank(HandCategory.TWO_PAIR, (9, 4, 14))
WEAK = HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 6, 4))

# The live seats of the short-all-in scenario: seats 5 and 7 fold.
ALL_LIVE = {1, 3, 9}

FOLD = Action(ActionType.FOLD)
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
    hand = PokerHand(players=players, deck=Deck(), number=1)
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

    awards = _award_pots(pots(hand), ranks, ALL_LIVE, [state.seat_number for state in hand.players])

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

    awards = _award_pots(pots(hand), ranks, ALL_LIVE, [state.seat_number for state in hand.players])

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

    awards = _award_pots(pots(hand), ranks, ALL_LIVE, [state.seat_number for state in hand.players])

    assert Settlement(awards, ()).payouts == {3: 90, 1: 10}


# =============================================================================
# CONTENDER SUBSETS ON THE SAME REAL POTS (muck at showdown)
# =============================================================================


def players_by_seat(hand: PokerHand) -> dict[int, HandPlayerState]:
    return {state.seat_number: state for state in hand.players}


def stacks_and_all_in(hand: PokerHand) -> dict[int, tuple[int, bool]]:
    return {seat: (state.player.stack, state.all_in) for seat, state in players_by_seat(hand).items()}


def test_dead_money_is_in_the_pots_but_folded_seats_are_never_eligible() -> None:
    """Seats 5 and 7 folded after putting chips in: they fund the first pots yet are eligible for none."""
    hand = short_all_in_with_dead_money()
    folded = {seat for seat, state in players_by_seat(hand).items() if state.folded}

    assert folded == {5, 7}
    assert all(players_by_seat(hand)[seat].total_contribution > 0 for seat in folded)
    assert all(not (folded & real_pot.eligible_seats) for real_pot in pots(hand))


def test_a_muck_gives_the_remaining_contenders_the_main_pots_and_a_sole_contender_the_last_side_pot() -> None:
    """Seat 1 mucks, leaving seats 3 and 9. They tie for the three pots both reach, seat 9 taking each odd chip. The
    last pot is eligible only to seats 1 and 9, so seat 9 is its sole final contender and takes it without a rank;
    seat 1 holds no rank. Each pot is still the pot as derived, seat 1 eligible, and the all-in seat 3 is paid and
    stops being all-in."""
    hand = short_all_in_with_dead_money()
    pots_before = pots(hand)

    _settle(hand, {3: BEST, 9: BEST}, {3, 9})

    assert hand.settlement is not None
    assert [award.shares for award in hand.settlement.pot_awards] == [
        ((9, 13), (3, 12)),
        ((9, 10), (3, 10)),
        ((9, 23), (3, 22)),
        ((9, 10),),
    ]
    assert tuple(award.pot for award in hand.settlement.pot_awards) == pots_before == pots(hand)
    assert 1 in hand.settlement.pot_awards[-1].pot.eligible_seats
    assert hand.settlement.payouts == {9: 56, 3: 44}
    assert hand.settlement.showdown_ranks == ((3, BEST), (9, BEST))
    assert stacks_and_all_in(hand) == {1: (70, False), 3: (44, False), 5: (95, False), 7: (90, False), 9: (126, False)}
    assert sum(state.player.stack for state in hand.players) == 100 + 25 + 100 + 100 + 100


def test_a_muck_by_the_short_stack_leaves_it_all_in_and_unpaid_while_the_others_split_every_pot() -> None:
    """Seat 3 mucks. Its chips stay in the pots, which are still eligible to it, but it takes nothing and, unpaid, keeps
    all_in with its zero stack. Seat 9 wins all four pots against seat 1."""
    hand = short_all_in_with_dead_money()

    _settle(hand, {1: MIDDLE, 9: BEST}, {1, 9})

    assert hand.settlement is not None
    assert hand.settlement.payouts == {9: 100}
    assert stacks_and_all_in(hand)[3] == (0, True)
    assert all(3 in award.pot.eligible_seats for award in hand.settlement.pot_awards[:3])


def test_a_pot_only_one_contender_is_eligible_for_goes_to_it_while_a_better_rank_wins_the_shared_pots() -> None:
    """Seats 1 and 3 are the contenders; seat 9 mucked. Seat 3 holds the best rank and wins the pots both reach, but is
    not eligible for the last pot, which seat 1 takes as its only final contender."""
    hand = short_all_in_with_dead_money()

    _settle(hand, {1: MIDDLE, 3: BEST}, {1, 3})

    assert hand.settlement is not None
    assert [award.shares for award in hand.settlement.pot_awards] == [((3, 25),), ((3, 20),), ((3, 45),), ((1, 10),)]
    assert stacks_and_all_in(hand)[1] == (80, False)


def test_a_last_contender_takes_every_layered_pot_without_any_rank() -> None:
    """Seats 1 and 3 muck: seat 9 wins all four pots unshown, and the settlement holds no ranks."""
    hand = short_all_in_with_dead_money()

    _settle(hand, {}, {9})

    assert hand.settlement is not None
    assert [award.shares for award in hand.settlement.pot_awards] == [((9, 25),), ((9, 20),), ((9, 45),), ((9, 10),)]
    assert hand.settlement.showdown_ranks == ()
    assert stacks_and_all_in(hand)[9] == (170, False)
    assert stacks_and_all_in(hand)[3] == (0, True)


# =============================================================================
# POT INVARIANT VIOLATIONS ON REAL POTS
# =============================================================================


def assert_violation_changes_nothing(hand: PokerHand, ranks: dict[int, HandRank], contenders: set[int]) -> None:
    stacks_before = stacks_and_all_in(hand)
    pots_before = pots(hand)
    middle_before = middle_pot(hand)

    with pytest.raises(SettlementInvariantError):
        _settle(hand, ranks, contenders)

    assert stacks_and_all_in(hand) == stacks_before
    assert hand.settlement is None
    assert pots(hand) == pots_before
    assert middle_pot(hand) == middle_before


def test_a_pot_without_a_final_contender_is_raised_before_any_change() -> None:
    """Seat 3 is the only contender, but the last pot is eligible only to seats 1 and 9. The first three pots would be
    payable, and none of them is paid."""
    assert_violation_changes_nothing(short_all_in_with_dead_money(), {3: BEST}, {3})


def test_contenders_who_are_eligible_for_no_pot_are_raised_before_any_change() -> None:
    """Seats 5 and 7 folded, so they are eligible for no pot at all."""
    assert_violation_changes_nothing(short_all_in_with_dead_money(), {5: BEST, 7: BEST}, {5, 7})


def test_a_pot_with_two_final_contenders_one_of_them_unranked_is_raised_before_any_change() -> None:
    """Seats 3 and 9 contest the first pots but only seat 3 has a rank."""
    assert_violation_changes_nothing(short_all_in_with_dead_money(), {3: BEST}, {3, 9})


def test_a_pot_with_three_final_contenders_one_of_them_unranked_is_raised_before_any_change() -> None:
    assert_violation_changes_nothing(short_all_in_with_dead_money(), {1: BEST, 3: MIDDLE}, {1, 3, 9})

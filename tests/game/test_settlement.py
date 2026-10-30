from dataclasses import FrozenInstanceError

import pytest

from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.pots import Pot
from go_poker.game.settlement import PotAward, Settlement, _award_pots

# Pots and ranks are built directly: pot awarding is a pure function of the pots, the ranks and the seat order. Seat
# orders are the hand's seats clockwise with the button first, as in `hand.players`.

BEST = HandRank(HandCategory.FLUSH, (14, 10, 8, 5, 3))
GOOD = HandRank(HandCategory.TWO_PAIR, (9, 4, 14))
FAIR = HandRank(HandCategory.ONE_PAIR, (8, 14, 6, 3))
WEAK = HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 6, 4))


def pot(amount: int, *eligible_seats: int) -> Pot:
    return Pot(amount, frozenset(eligible_seats))


def award_one(pot_to_award: Pot, ranks: dict[int, HandRank], seats_from_button: tuple[int, ...]) -> PotAward:
    (pot_award,) = _award_pots([pot_to_award], ranks, seats_from_button)
    return pot_award


# =============================================================================
# SINGLE ELIGIBLE SEAT AND SOLE WINNER
# =============================================================================


def test_single_eligible_pot_goes_to_that_seat_without_ranks() -> None:
    """An uncontested hand passes no ranks: a pot with exactly one eligible seat is awarded to it whole."""
    pot_award = award_one(pot(30, 2), {}, (1, 2, 3))

    assert pot_award == PotAward(pot(30, 2), ((2, 30),))


def test_single_eligible_pot_ignores_ranks_that_would_beat_it() -> None:
    """The only eligible seat wins even when another seat holds a better rank: ranks are not consulted."""
    pot_award = award_one(pot(30, 2), {1: BEST, 2: WEAK}, (1, 2, 3))

    assert pot_award.shares == ((2, 30),)


def test_best_rank_among_eligible_seats_wins_the_whole_pot() -> None:
    pot_award = award_one(pot(100, 1, 2, 3), {1: FAIR, 2: BEST, 3: GOOD}, (1, 2, 3))

    assert pot_award == PotAward(pot(100, 1, 2, 3), ((2, 100),))


def test_ranks_of_the_same_category_are_compared_by_their_tiebreakers_and_tie_only_when_equal() -> None:
    """Pairs of aces differing only in the last kicker are not a tie; identical ranks built separately are."""
    pair_aces_king = HandRank(HandCategory.ONE_PAIR, (14, 13, 9, 5))
    pair_aces_queen = HandRank(HandCategory.ONE_PAIR, (14, 12, 9, 5))
    pair_aces_king_again = HandRank(HandCategory.ONE_PAIR, (14, 13, 9, 5))

    beaten = award_one(pot(100, 1, 2), {1: pair_aces_king, 2: pair_aces_queen}, (1, 2))
    tied = award_one(pot(100, 1, 2), {1: pair_aces_king_again, 2: pair_aces_king}, (1, 2))

    assert beaten.shares == ((1, 100),)
    assert tied.shares == ((2, 50), (1, 50))


def test_awards_are_in_pot_order() -> None:
    awards = _award_pots([pot(30, 1, 2), pot(20, 2), pot(10, 1, 2)], {1: BEST, 2: GOOD}, (1, 2))

    assert [(award.pot, award.shares) for award in awards] == [
        (pot(30, 1, 2), ((1, 30),)),
        (pot(20, 2), ((2, 20),)),
        (pot(10, 1, 2), ((1, 10),)),
    ]


# =============================================================================
# TIES, SPLITS AND ODD CHIPS
# =============================================================================


@pytest.mark.parametrize(
    ("amount", "expected_shares"),
    [
        (100, ((3, 50), (1, 50))),
        (101, ((3, 51), (1, 50))),
    ],
    ids=["no-odd-chip", "one-odd-chip"],
)
def test_two_way_tie_splits_the_pot(amount: int, expected_shares: tuple[tuple[int, int], ...]) -> None:
    """Seats 1 and 3 tie; button seat 1 is last in order, so seat 3 (first left of the button among them) goes first.
    A different rank for seat 2 never joins the split, and equal ranks tie."""
    pot_award = award_one(pot(amount, 1, 2, 3), {1: BEST, 2: GOOD, 3: BEST}, (1, 2, 3))

    assert pot_award.shares == expected_shares


@pytest.mark.parametrize(
    ("amount", "expected_shares"),
    [
        (90, ((2, 30), (3, 30), (1, 30))),
        (91, ((2, 31), (3, 30), (1, 30))),
        (92, ((2, 31), (3, 31), (1, 30))),
    ],
    ids=["no-odd-chip", "one-odd-chip", "two-odd-chips"],
)
def test_three_way_tie_splits_the_pot(amount: int, expected_shares: tuple[tuple[int, int], ...]) -> None:
    """Odd chips go one each to the earliest tied winners clockwise from the button; the button is last."""
    pot_award = award_one(pot(amount, 1, 2, 3), {1: BEST, 2: BEST, 3: BEST}, (1, 2, 3))

    assert pot_award.shares == expected_shares


def test_odd_chip_goes_to_a_higher_seat_left_of_the_button_before_a_lower_one() -> None:
    """Seats are not consecutive and the order wraps: with the button at seat 5, seat 9 is left of the button and seat
    2 comes only after the wrap, so the odd chip goes to seat 9 although seat 2 has the lower number."""
    pot_award = award_one(pot(101, 2, 5, 7, 9), {2: BEST, 5: WEAK, 7: GOOD, 9: BEST}, (5, 7, 9, 2))

    assert pot_award.shares == ((9, 51), (2, 50))


def test_odd_chips_wrap_past_the_button_and_the_button_comes_last() -> None:
    """Three tied winners including the button, two odd chips: the two seats left of the button, wrapped, take them."""
    pot_award = award_one(pot(92, 2, 5, 9), {2: BEST, 5: BEST, 9: BEST}, (5, 7, 9, 2))

    assert pot_award.shares == ((9, 31), (2, 31), (5, 30))


def test_heads_up_big_blind_gets_the_odd_chip_and_the_button_is_last() -> None:
    """Heads-up the button is the small blind: the big blind is the first seat left of the button."""
    pot_award = award_one(pot(101, 3, 6), {3: BEST, 6: BEST}, (3, 6))

    assert pot_award.shares == ((6, 51), (3, 50))


def test_odd_chips_are_allocated_per_pot() -> None:
    """Each pot is split independently, so each pot's odd chip goes to the first tied winner in order."""
    awards = _award_pots([pot(61, 1, 2, 3), pot(41, 1, 2, 3)], {1: BEST, 2: BEST, 3: WEAK}, (1, 2, 3))

    assert [award.shares for award in awards] == [((2, 31), (1, 30)), ((2, 21), (1, 20))]


# =============================================================================
# SIDE POTS AND ELIGIBILITY
# =============================================================================


def test_a_side_pot_can_be_won_by_a_different_player_than_the_main_pot() -> None:
    """Seat 2 is all-in short with the best hand: it wins the main pot but is not eligible for the side pot, which
    goes to the best of the others."""
    main_pot, side_pot = pot(400, 1, 2, 3, 4), pot(200, 1, 3, 4)
    awards = _award_pots([main_pot, side_pot], {1: FAIR, 2: BEST, 3: GOOD, 4: WEAK}, (1, 2, 3, 4))

    assert awards == (PotAward(main_pot, ((2, 400),)), PotAward(side_pot, ((3, 200),)))


def test_a_best_hand_short_stack_wins_only_the_main_pot() -> None:
    """The short stack holds the best hand but is eligible only for the main pot; the better of the others wins the
    side pot, so a better hand that is not eligible never takes a pot."""
    main_pot, side_pot = pot(300, 1, 2, 3), pot(400, 2, 3)
    awards = _award_pots([main_pot, side_pot], {1: BEST, 2: WEAK, 3: GOOD}, (1, 2, 3))

    assert awards == (PotAward(main_pot, ((1, 300),)), PotAward(side_pot, ((3, 400),)))


def test_ranks_of_seats_that_are_not_eligible_never_tie_into_a_pot() -> None:
    """A seat ineligible for the pot holds the same best rank as an eligible one but takes no share."""
    pot_award = award_one(pot(100, 2, 3), {1: BEST, 2: BEST, 3: GOOD}, (1, 2, 3))

    assert pot_award.shares == ((2, 100),)


# =============================================================================
# RESULT TYPES
# =============================================================================


def test_winners_are_derived_from_the_shares_in_share_order() -> None:
    pot_award = PotAward(pot(91, 1, 2, 3), ((2, 31), (3, 30), (1, 30)))

    assert pot_award.winners == (2, 3, 1)


def test_payouts_sum_across_pots_and_omit_unpaid_seats() -> None:
    settlement = Settlement(
        pot_awards=(
            PotAward(pot(61, 1, 2, 3), ((2, 31), (1, 30))),
            PotAward(pot(40, 2, 3), ((2, 40),)),
            PotAward(pot(10, 1, 3), ((1, 10),)),
        ),
        showdown_ranks=((1, BEST), (2, BEST), (3, WEAK)),
    )

    assert settlement.payouts == {2: 71, 1: 40}


def test_an_uncontested_settlement_has_no_showdown_ranks() -> None:
    settlement = Settlement(pot_awards=(PotAward(pot(30, 2), ((2, 30),)),), showdown_ranks=())

    assert (settlement.payouts, settlement.showdown_ranks) == ({2: 30}, ())


def test_result_types_reject_mutation() -> None:
    pot_award = PotAward(pot(30, 2), ((2, 30),))
    settlement = Settlement(pot_awards=(pot_award,), showdown_ranks=())

    with pytest.raises(FrozenInstanceError):
        pot_award.shares = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        pot_award.pot = pot(1, 1)  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        settlement.pot_awards = ()  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        settlement.showdown_ranks = ((1, BEST),)  # type: ignore[misc]
    with pytest.raises(AttributeError):
        pot_award.winners = ()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        settlement.payouts = {}  # type: ignore[misc]


def test_mutating_the_returned_payouts_does_not_affect_the_settlement() -> None:
    settlement = Settlement(pot_awards=(PotAward(pot(30, 2), ((2, 30),)),), showdown_ranks=())

    settlement.payouts[2] = 0
    settlement.payouts[9] = 5

    assert settlement.payouts == {2: 30}

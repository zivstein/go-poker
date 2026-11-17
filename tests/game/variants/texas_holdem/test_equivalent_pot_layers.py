"""Regression: equivalent pot layers are one pot, so odd chips are split once per eligible-seat set (ADR 0001 §1).

A folded player's collected contribution is a level that changes nobody's eligibility. Split layer by layer, the chips
below and above such a level each paid their own odd chips, so tied winners could be paid differently from a single
pot of the same chips: the reproduced five-player case paid 66 / 64 for 130 chips two tied seats contested alike.

Every hand here is played through the public `begin_hand` and `act` operations from a deck stacked by the shared
`stacked_hand` fixture, and each test checks the pots, every award, the final stacks and chip conservation.
"""

from collections.abc import Callable

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)

# A board straight that every hand below plays: no hole card here is a ten, which alone would beat it, and two hole
# clubs make at most four, so whoever reaches the showdown ties.
STRAIGHT_BOARD = "5c 6d 7h 8s 9c"
# No pair or flush is possible and its only straight needs an eight and a ten in the hole: pocket pairs and high cards
# decide, and equal high cards tie.
DRY_BOARD = "2c 4d 7h 9s Jc"

type NewHand = Callable[..., PokerHand]


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def pot(amount: int, *eligible_seats: int) -> Pot:
    return Pot(amount, frozenset(eligible_seats))


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    """Each action by the seat whose turn it is: the order is part of what is checked."""
    for seat, action in actions:
        assert current_actor(hand) == seat
        act(hand, seat, action)


def check_down_and_show(hand: PokerHand) -> None:
    """Every remaining betting turn checks and every showdown decider shows, until the hand settles."""
    while hand.settlement is None:
        seat = current_actor(hand)
        assert seat is not None
        act(hand, seat, ShowdownAction.SHOW if hand.showdown is not None else CHECK)


def assert_settled(hand: PokerHand, layers: list[Pot], shares: list[tuple[tuple[int, int], ...]]) -> None:
    """The pots and the exact award of each, and that the settlement pays out exactly the middle, conserving chips."""
    settlement = hand.settlement
    assert settlement is not None
    assert list(pots(hand)) == layers
    assert [award.pot for award in settlement.pot_awards] == layers
    assert [award.shares for award in settlement.pot_awards] == shares
    contributed = sum(state.total_contribution for state in hand.players)
    assert sum(settlement.payouts.values()) == middle_pot(hand) == contributed
    assert len({award.pot.eligible_seats for award in settlement.pot_awards}) == len(layers)
    assert hand.history.settlement == settlement


def stacks(hand: PokerHand) -> dict[int, int]:
    return {state.seat_number: state.player.stack for state in hand.players}


def test_the_reproduced_five_player_tie_splits_130_chips_65_65_not_66_64(stacked_hand: NewHand) -> None:
    """The C6.3 plan §7 case. Five players, the button on seat 3, so the order from the small blind is 4, 5, 1, 2, 3.
    UTG (seat 1) raises to 25, seats 2 and 3 call and the blinds fold; on the flop seat 1 bets 20, seat 2 folds and the
    button calls. Seats 1 and 3 play the board straight. The collected levels 5, 10, 25 and 45 once made four layers of
    25, 20, 45 and 40, all for seats 1 and 3, and seat 1 took the odd chip of the 25 and the 45: 66 / 64. They are one
    pot of 130, split 65 / 65."""
    holes = {1: "2h 3d", 2: "Ah Kh", 3: "2s 3c", 4: "Qh Qd", 5: "Jh Js"}
    hand = stacked_hand(holes, STRAIGHT_BOARD, button=3)
    begin_hand(hand, STAKES)
    play(hand, (1, raise_to(25)), (2, CALL), (3, CALL), (4, FOLD), (5, FOLD))
    play(hand, (1, bet(20)), (2, FOLD), (3, CALL))
    check_down_and_show(hand)

    assert_settled(hand, [pot(130, 1, 3)], [((1, 65), (3, 65))])
    assert stacks(hand) == {3: 1020, 4: 995, 5: 990, 1: 1020, 2: 975}
    assert sum(stacks(hand).values()) == 5 * 1000


def test_a_three_way_tie_over_the_folded_blinds_splits_one_pot_evenly(stacked_hand: NewHand) -> None:
    """UTG raises to 25, seats 2 and 3 call, the blinds fold and everyone checks down to a three-way tie. The folded
    blinds' 5 and 10 are inside the one 90-chip pot, 30 each; split as layers of 25, 20 and 45 it paid 31 / 30 / 29."""
    holes = {1: "2h 3d", 2: "2s 3c", 3: "Ah 4d", 4: "Qh Qd", 5: "Jh Js"}
    hand = stacked_hand(holes, STRAIGHT_BOARD, button=3)
    begin_hand(hand, STAKES)
    play(hand, (1, raise_to(25)), (2, CALL), (3, CALL), (4, FOLD), (5, FOLD))
    check_down_and_show(hand)

    assert_settled(hand, [pot(90, 1, 2, 3)], [((1, 30), (2, 30), (3, 30))])
    assert stacks(hand) == {3: 1005, 4: 995, 5: 990, 1: 1005, 2: 1005}


def test_a_merged_pot_pays_its_odd_chip_once_clockwise_from_the_button(stacked_hand: NewHand) -> None:
    """Seven seats with the button on seat 3, so the odd-chip order is 4, 5, 6, 7, 1, 2, 3. Seats 6 and 1 play to the
    river and tie; five others fold at five different levels: the blinds at 5 and 10, then seats 7, 2 and 3 at 25, 35
    and 50. Every folded level leaves seats 6 and 1 the only ones eligible, so the 245 chips are one pot with one odd
    chip, which seat 6 takes as the first winner left of the button although seat 1 has the lower number: 123 / 122.
    Split as six layers (35, 30, 75, 40, 45, 20) three of them odd, it paid seat 6 all three: 124 / 121."""
    holes = {6: "2h 3d", 1: "2s 3c", 7: "Ah Kd", 2: "As Kc", 3: "Qh Jd", 4: "Qs Jc", 5: "Ad Kh"}
    hand = stacked_hand(holes, STRAIGHT_BOARD, button=3)
    begin_hand(hand, STAKES)
    play(hand, (6, raise_to(25)), (7, CALL), (1, CALL), (2, CALL), (3, CALL), (4, FOLD), (5, FOLD))
    play(hand, (6, bet(10)), (7, FOLD), (1, CALL), (2, CALL), (3, CALL))
    play(hand, (6, bet(15)), (1, CALL), (2, FOLD), (3, CALL))
    play(hand, (6, bet(10)), (1, CALL), (3, FOLD))
    assert {state.seat_number: state.total_contribution for state in hand.players} == {
        3: 50,
        4: 5,
        5: 10,
        6: 60,
        7: 25,
        1: 60,
        2: 35,
    }
    check_down_and_show(hand)

    assert_settled(hand, [pot(245, 1, 6)], [((6, 123), (1, 122))])
    assert (stacks(hand)[6], stacks(hand)[1]) == (1063, 1062)
    assert sum(stacks(hand).values()) == 7 * 1000


def test_a_folded_level_between_all_in_levels_merges_while_real_side_pots_stay_apart(stacked_hand: NewHand) -> None:
    """Four seats with the button on seat 1, so the order from the small blind is 2, 3, 4, 1. Seat 4 is all-in for 100
    with aces. Seat 1 raises to 195 and the small blind (seat 2) calls it; the big blind (seat 3) raises to 400, seat 1
    calls and seat 2 folds its 195. Seats 1 and 3 check down with the same king-queen high.

    Eligibility changes only at the all-in's 100, so there are two pots: the main pot of 400 seat 4 wins, and one side
    pot of 695 for seats 1 and 3, the folded 195 inside it. Seats 1 and 3 tie it with one odd chip, to seat 3, the first
    of them left of the button; the all-in seat is never paid from the side pot."""
    holes = {1: "Kh Qd", 2: "3h 3d", 3: "Ks Qc", 4: "Ah Ad"}
    hand = stacked_hand(holes, DRY_BOARD, button=1, stacks={1: 1000, 2: 1000, 3: 1000, 4: 100})
    begin_hand(hand, STAKES)
    play(hand, (4, raise_to(100)), (1, raise_to(195)), (2, CALL), (3, raise_to(400)), (1, CALL), (2, FOLD))
    check_down_and_show(hand)

    assert_settled(hand, [pot(400, 1, 3, 4), pot(695, 1, 3)], [((4, 400),), ((3, 348), (1, 347))])
    assert stacks(hand) == {1: 947, 2: 805, 3: 948, 4: 400}
    assert sum(stacks(hand).values()) == 3100
    assert all(not state.all_in for state in hand.players)

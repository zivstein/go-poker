"""Pot awarding fed with pots derived from real betting.

The pots here come from `pots(hand)` after real betting operations, not from hand-written pots, so they have the shapes
the engine really produces: a short all-in level, folded players' dead money, and adjacent pots whose eligible seats are
identical. Ranks are chosen by the test (hand strength is not what is under test). The awarding rules are also checked
on seeded random hands by the one seeded hand driver, in tests/game/betting/test_hand_stress.py.
"""

from go_poker.core.deck import Deck
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import Pot, pots
from go_poker.game.betting.rounds import is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.settlement import Settlement, _award_pots
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards

STAKES = Stakes(small_blind=5, big_blind=10)

BEST = HandRank(HandCategory.FLUSH, (14, 10, 8, 5, 3))
MIDDLE = HandRank(HandCategory.TWO_PAIR, (9, 4, 14))
WEAK = HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 6, 4))

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

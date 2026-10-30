"""End-to-end Hold'em settlement scenarios.

Every hand reaches its end through the real public operations (`initialize_betting`, `deal_hole_cards`, `apply_action`,
`deal_next_street`, `start_betting_round`, `settle_hand`) from a deck stacked by the shared `stacked_hand` fixture. Each
scenario asserts the exact pots, the exact share of every pot, the final stacks and `all_in` flags, and that the
contributions and `folded` flags still describe what was contested.

Both boards hold no pair and no flush is possible on them. On DRY_BOARD the only possible straight (7-8-9-T-J) needs
both an eight and a ten in the hole cards, which no scenario deals, so there a pocket pair beats any unpaired hand and
higher pairs beat lower ones. On BROADWAY_BOARD any ten makes the same straight. Equal hands tie.
"""

from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import settle_hand

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CALL = Action(ActionType.CALL)

# No pair or flush is possible on this board. Its only possible straight (7-8-9-T-J) needs an eight and a ten in the
# hole cards and no scenario deals both, so hands are ranked by their pocket pair or high cards.
DRY_BOARD = "2c 4d 7h 9s Jc"
# Every ace-high to ten-high straight needs a ten: whoever holds one plays the broadway straight and ties the others.
BROADWAY_BOARD = "Ah Kd Qc Jh 3s"

type NewHand = Callable[..., PokerHand]
type Shares = list[tuple[tuple[int, int], ...]]


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    for seat, action in actions:
        apply_action(hand, seat, action)


def next_street(hand: PokerHand) -> None:
    """Deal the next street, then start its betting round."""
    deal_next_street(hand)
    start_betting_round(hand)


def deal_remaining_streets(hand: PokerHand) -> None:
    """After betting closed early, deal the rest of the board (nobody can act in the skipped rounds)."""
    while hand.street is not Street.RIVER:
        deal_next_street(hand)


def shove_in_turn(hand: PokerHand) -> None:
    """Everyone to act puts all their chips in, in turn: raise to the whole stack when that is a legal raise, else call
    (a player facing only all-in opponents can call no more than they have matched)."""
    betting = hand.betting
    assert betting is not None
    for _ in range(100):
        actor = betting.current_actor
        if actor is None:
            return
        state = next(state for state in hand.players if state.seat_number == actor)
        target = state.player.stack + state.street_contribution
        can_raise = legal_actions(hand).can_raise and target > betting.current_bet
        play(hand, (actor, raise_to(target) if can_raise else CALL))
    pytest.fail("the all-in round did not end")


def pot(amount: int, *eligible_seats: int) -> Pot:
    return Pot(amount, frozenset(eligible_seats))


def accounting(hand: PokerHand) -> list[tuple[int, bool, int, int]]:
    """Per seat, what settlement must preserve: the folded flag and the street and total contributions."""
    return [(s.seat_number, s.folded, s.street_contribution, s.total_contribution) for s in hand.players]


def settle_and_assert(
    hand: PokerHand,
    layers: list[Pot],
    shares: Shares,
    stacks: dict[int, int],
    all_in: set[int],
) -> None:
    """Settle the hand, then check the pots, every pot's exact shares, the final stacks and the seats left all-in."""
    assert list(pots(hand)) == layers
    middle = middle_pot(hand)
    history = accounting(hand)
    starting_chips = sum(state.player.stack + state.total_contribution for state in hand.players)

    settle_hand(hand)

    assert hand.settlement is not None
    assert [award.pot for award in hand.settlement.pot_awards] == layers
    assert [award.shares for award in hand.settlement.pot_awards] == shares
    assert {state.seat_number: state.player.stack for state in hand.players} == stacks
    assert {state.seat_number for state in hand.players if state.all_in} == all_in
    assert accounting(hand) == history
    assert list(pots(hand)) == layers
    assert middle_pot(hand) == middle == sum(hand.settlement.payouts.values())
    assert sum(state.player.stack for state in hand.players) == starting_chips


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    """A stacked hand with its blinds posted and hole cards dealt; takes holes, board, button and stacks."""

    def build(holes: dict[int, str], board: str, button: int = 1, stacks: dict[int, int] | None = None) -> PokerHand:
        hand = stacked_hand(holes, board, button=button, stacks=stacks)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        return hand

    return build


# =============================================================================
# 1. NINE-MAX, MANY SIDE POTS, DIFFERENT WINNERS
# =============================================================================


def test_nine_max_all_in_hand_pays_each_layer_to_its_own_winner(new_hand: NewHand) -> None:
    """All nine seats put their whole stack in preflop with the button on seat 5, so the layers are the eight distinct
    stack levels below the biggest. Hand strength, best first, follows the stack sizes with one exception: the shortest
    stack (seat 6, aces) wins the main pot, the next (seat 2, kings) the first side pot, the fourth shortest (seat 4,
    queens) two layers, and the third shortest (seat 8, eights) wins nothing, so it stays all-in with no chips. The
    deepest seat 7 has only ace-king; facing only all-in opponents it can match just 700 and keeps its other 200."""
    stacks = {6: 40, 2: 90, 8: 150, 4: 230, 9: 310, 1: 420, 5: 560, 3: 700, 7: 900}
    holes = {
        6: "Ah Ad",
        2: "Kh Kd",
        4: "Qh Qd",
        9: "Th Td",
        8: "8h 8d",
        1: "6h 6d",
        5: "5h 5d",
        3: "3h 3d",
        7: "Ac Kc",
    }
    hand = new_hand(holes, DRY_BOARD, button=5, stacks=stacks)
    shove_in_turn(hand)
    assert is_round_complete(hand.betting) and is_betting_closed(hand)  # type: ignore[arg-type]
    deal_remaining_streets(hand)

    settle_and_assert(
        hand,
        layers=[
            pot(360, 1, 2, 3, 4, 5, 6, 7, 8, 9),
            pot(400, 1, 2, 3, 4, 5, 7, 8, 9),
            pot(420, 1, 3, 4, 5, 7, 8, 9),
            pot(480, 1, 3, 4, 5, 7, 9),
            pot(400, 1, 3, 5, 7, 9),
            pot(440, 1, 3, 5, 7),
            pot(420, 3, 5, 7),
            pot(280, 3, 7),
        ],
        shares=[((6, 360),), ((2, 400),), ((4, 420),), ((4, 480),), ((9, 400),), ((1, 440),), ((5, 420),), ((3, 280),)],
        stacks={1: 440, 2: 400, 3: 280, 4: 900, 5: 420, 6: 360, 7: 200, 8: 0, 9: 400},
        all_in={8},
    )
    assert sum(state.total_contribution for state in hand.players) == 3200  # seat 7 never put in more than 700


# =============================================================================
# 2. TIED MAIN POT, SIDE POT FOR A THIRD PLAYER
# =============================================================================


def test_two_short_all_ins_tie_the_main_pot_and_a_third_player_wins_the_side_pot(new_hand: NewHand) -> None:
    """With the button on seat 3 the seats run 4, 1, 2, 3 clockwise from the small blind. Seats 2 and 4 are all-in for
    100 with aces of different suits, and tie; seats 3 and 1 go to 300 with kings and queens. The main pot splits
    between seats 4 and 2 (in that order, though seat 2 has the lower number) and seat 3 wins the 400-chip side pot."""
    holes = {1: "Qh Qd", 2: "As Ac", 3: "Kh Kd", 4: "Ah Ad"}
    hand = new_hand(holes, DRY_BOARD, button=3, stacks={1: 300, 2: 100, 3: 300, 4: 100})
    play(hand, (2, raise_to(100)), (3, raise_to(300)), (4, CALL), (1, CALL))
    deal_remaining_streets(hand)

    settle_and_assert(
        hand,
        layers=[pot(400, 1, 2, 3, 4), pot(400, 1, 3)],
        shares=[((4, 200), (2, 200)), ((3, 400),)],
        stacks={1: 0, 2: 200, 3: 400, 4: 200},
        all_in={1},
    )


# =============================================================================
# 3. ODD CHIPS IN SEVERAL POTS, WRAPPING PAST THE BUTTON
# =============================================================================


def test_odd_chips_go_clockwise_from_the_button_in_every_pot_they_occur_in(new_hand: NewHand) -> None:
    """Seven seats with the button on seat 3, so the order for odd chips is 4, 5, 6, 7, 1, 2, 3. Seats 5, 7, 1 and 3
    (the button) each hold a ten and play the board's broadway straight, tying wherever they are eligible; seats 6 and
    2 are weaker. Seat 4 folds the small blind. The pots are 35, 186, 65, 52, 63 and 74 chips, split 4-, 4-, 4-, 3-, 3-
    and 2-ways with 3, 2, 1, 1, 0 and 0 odd chips: the first seats in the order (5, then 7, then 1) take them, so seat
    5 comes before seat 1 although it has the higher number, and the button is always last."""
    holes = {
        5: "Th 4c",
        7: "Td 5c",
        1: "Tc 6d",
        3: "Ts 7d",
        6: "8c 8d",
        2: "9c 9d",
        4: "2h 2d",
    }
    stacks = {6: 36, 7: 49, 1: 83, 2: 62, 3: 200, 4: 100, 5: 120}
    hand = new_hand(holes, BROADWAY_BOARD, button=3, stacks=stacks)
    play(
        hand,
        (6, raise_to(36)),  # all-in
        (7, raise_to(49)),  # all-in, a short raise
        (1, raise_to(83)),  # all-in
        (2, CALL),  # all-in for 62
        (3, raise_to(200)),
        (4, FOLD),  # the small blind's 5 chips are dead money
        (5, CALL),  # the big blind calls all-in for 120, so 80 of seat 3's raise comes back
    )
    assert is_round_complete(hand.betting)  # type: ignore[arg-type]
    deal_remaining_streets(hand)

    settle_and_assert(
        hand,
        layers=[
            pot(35, 1, 2, 3, 5, 6, 7),
            pot(186, 1, 2, 3, 5, 6, 7),
            pot(65, 1, 2, 3, 5, 7),
            pot(52, 1, 2, 3, 5),
            pot(63, 1, 3, 5),
            pot(74, 3, 5),
        ],
        shares=[
            ((5, 9), (7, 9), (1, 9), (3, 8)),
            ((5, 47), (7, 47), (1, 46), (3, 46)),
            ((5, 17), (7, 16), (1, 16), (3, 16)),
            ((5, 18), (1, 17), (3, 17)),
            ((5, 21), (1, 21), (3, 21)),
            ((5, 37), (3, 37)),
        ],
        stacks={1: 109, 2: 0, 3: 225, 4: 95, 5: 149, 6: 0, 7: 72},
        all_in={2, 6},
    )


# =============================================================================
# 4. FOLDED DEAD MONEY
# =============================================================================


def test_dead_money_goes_to_the_winners_of_the_layers_it_was_put_into(new_hand: NewHand) -> None:
    """Seat 4 is all-in for 100 with the best hand; seat 3 has kings. Seats 5, 1 and 2 fold after putting in 30, 150
    and 250, so their chips sit in four layers: seat 4 wins the two layers up to its 100 chips with the dead money in
    them, and seat 3, the only live player contributing above that, wins the two layers above, which hold the rest of
    the dead money. Seat 3's 200 unmatched turn chips go back to it before any of this."""
    holes = {1: "6h 6d", 2: "5h 5d", 3: "Kh Kd", 4: "Ah Ad", 5: "3h 3d"}
    hand = new_hand(holes, DRY_BOARD, stacks={4: 100})
    play(hand, (4, raise_to(30)), (5, CALL), (1, CALL), (2, CALL), (3, CALL))
    next_street(hand)
    play(
        hand,
        (2, bet(40)),
        (3, raise_to(120)),
        (4, CALL),  # all-in for 70 more
        (5, FOLD),  # 30 dead
        (1, CALL),
        (2, CALL),
    )
    next_street(hand)
    play(hand, (2, bet(100)), (3, raise_to(300)), (1, FOLD), (2, FOLD))  # 150 and 250 dead; seat 3 gets 200 back
    assert is_betting_closed(hand)
    deal_remaining_streets(hand)

    settle_and_assert(
        hand,
        layers=[pot(150, 3, 4), pot(280, 3, 4), pot(150, 3), pot(200, 3)],
        shares=[((4, 150),), ((4, 280),), ((3, 150),), ((3, 200),)],
        stacks={1: 850, 2: 750, 3: 1100, 4: 430, 5: 970},
        all_in=set(),
    )
    assert {state.seat_number: state.folded for state in hand.players} == {
        1: True,
        2: True,
        3: False,
        4: False,
        5: True,
    }


# =============================================================================
# 5. UNCONTESTED WIN AFTER AN UNMATCHED BET
# =============================================================================


def test_an_uncontested_win_after_a_returned_unmatched_bet_pays_only_the_matched_pot(new_hand: NewHand) -> None:
    """Seat 1 raises to 40, the small blind folds its 5 and the big blind calls. On the flop seat 3 bets 60, seat 1
    raises to 200 and seat 3 folds: 60 of the raise is matched by seat 3's bet, the other 140 comes back to seat 1 at
    collection. The board is still the flop, and seat 1 wins only the 205 in the pots."""
    holes = {1: "Ah Ad", 2: "Kh Kd", 3: "Qh Qd"}
    hand = new_hand(holes, DRY_BOARD)
    play(hand, (1, raise_to(40)), (2, FOLD), (3, CALL))
    next_street(hand)
    play(hand, (3, bet(60)), (1, raise_to(200)), (3, FOLD))
    assert hand.street is Street.FLOP
    assert hand.betting is not None
    assert [state.player.stack for state in hand.players] == [900, 995, 900]  # seat 1 already has its 140 back

    settle_and_assert(
        hand,
        layers=[pot(15, 1), pot(190, 1)],
        shares=[((1, 15),), ((1, 190),)],
        stacks={1: 1105, 2: 995, 3: 900},
        all_in=set(),
    )
    assert hand.settlement is not None
    assert hand.settlement.showdown_ranks == ()
    assert len(hand.board) == 3

"""Hold'em settlement through the public `settle_hand`.

Every hand reaches its end through the real dealing and betting operations, from a deck stacked by the shared
`stacked_hand` fixture. Unless a test says otherwise the three seats are the button (1), the small blind (2) and the big
blind (3); preflop seat 1 acts first and on every later street seat 2 does. Seat 2 holds a set of kings on the default
board, seat 1 a pair of aces and seat 3 nothing, so seat 2 wins every showdown that is not set up otherwise.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import is_betting_closed, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import HandAlreadySettledError, PotAward, Settlement
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    IncompleteBoardError,
    ShowdownNotReadyError,
    settle_hand,
    showdown_ranks,
)

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
ROYAL_FLUSH_BOARD = "As Ks Qs Js Ts"
TYING_HOLES = {1: "2c 3d", 2: "4h 5c", 3: "6d 7h"}  # all three play the royal flush on the board

PREVIOUS_STREET = {Street.FLOP: Street.PREFLOP, Street.TURN: Street.FLOP, Street.RIVER: Street.TURN}

type NewHand = Callable[..., PokerHand]


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


def check_street(hand: PokerHand) -> None:
    """Everyone still to act checks, in turn."""
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


def call_preflop(hand: PokerHand) -> None:
    play(hand, (1, CALL), (2, CALL), (3, CHECK))


def check_to(hand: PokerHand, street: Street) -> None:
    """From a hand that has just completed its preflop round, check every street up to and including `street`."""
    while hand.street is not street:
        next_street(hand)
        check_street(hand)


def deal_remaining_streets(hand: PokerHand, *, start_rounds: bool) -> None:
    """Deal every street still to come, optionally starting each one's betting round (nobody can act in them)."""
    while hand.street is not Street.RIVER:
        if start_rounds:
            next_street(hand)
        else:
            deal_next_street(hand)


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    """A stacked hand with its blinds posted and hole cards dealt; takes optional stacks, holes, board and button."""

    def build(
        stacks: dict[int, int] | None = None,
        holes: dict[int, str] | None = None,
        board: str = BOARD,
        button: int = 1,
    ) -> PokerHand:
        hand = stacked_hand(holes or HOLES, board, button=button, stacks=stacks)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        return hand

    return build


@pytest.fixture
def all_in_preflop(new_hand: NewHand) -> PokerHand:
    """All three seats are all-in for 100 each preflop, so betting is closed with the board still empty."""
    hand = new_hand(stacks={1: 100, 2: 100, 3: 100})
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    assert is_betting_closed(hand)
    return hand


# -----------------------------------------------------------------------------
# What a hand's state is checked against
# -----------------------------------------------------------------------------


def hand_snapshot(hand: PokerHand) -> dict[str, Any]:
    """Everything about the hand, for comparing before and after (the deck by its size: drawing is its only change)."""
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "players": [
            (
                state.seat_number,
                state.player.stack,
                state.folded,
                state.all_in,
                state.street_contribution,
                state.total_contribution,
                list(state.hole_cards),
            )
            for state in hand.players
        ],
        "pots": pots(hand),
        "middle_pot": middle_pot(hand),
    }


def accounting_history(snapshot: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Per seat: contributions, folded flag and hole cards, which settlement never changes (stack and all_in do)."""
    return [(seat, folded, street, total, hole) for seat, _, folded, _, street, total, hole in snapshot["players"]]


def settled(hand: PokerHand) -> Settlement:
    assert hand.settlement is not None
    return hand.settlement


def settle_and_check(hand: PokerHand) -> Settlement:
    """Settle the hand and check the invariants every successful settlement keeps; return the settlement."""
    starting_chips = {state.seat_number: state.player.stack + state.total_contribution for state in hand.players}
    before = hand_snapshot(hand)
    middle_before = middle_pot(hand)
    pots_before = pots(hand)

    settle_hand(hand)

    settlement = settled(hand)
    payouts = settlement.payouts
    for state in hand.players:
        assert state.player.stack == starting_chips[state.seat_number] - state.total_contribution + payouts.get(
            state.seat_number, 0
        )
        assert state.all_in == (state.player.stack == 0)
    assert sum(payouts.values()) == middle_before == sum(pot.amount for pot in pots_before)
    assert [award.pot for award in settlement.pot_awards] == list(pots_before)
    assert all(sum(chips for _, chips in award.shares) == award.pot.amount for award in settlement.pot_awards)

    after = hand_snapshot(hand)
    for field in ("street", "board", "burned", "deck", "betting", "pots", "middle_pot"):
        assert after[field] == before[field]
    assert accounting_history(after) == accounting_history(before)
    return settlement


def assert_rejected(hand: PokerHand, error: type[Exception]) -> None:
    """`settle_hand` raises `error` and leaves the hand exactly as it was."""
    before = hand_snapshot(hand)

    with pytest.raises(error):
        settle_hand(hand)

    assert hand_snapshot(hand) == before
    assert hand.settlement is None


# =============================================================================
# UNCONTESTED HANDS
# =============================================================================


@pytest.mark.parametrize(
    ("street", "winner", "payout"),
    [(Street.PREFLOP, 3, 10), (Street.FLOP, 2, 30), (Street.TURN, 2, 30), (Street.RIVER, 2, 30)],
)
def test_a_sole_live_player_wins_uncontested_on_any_street(
    new_hand: NewHand, street: Street, winner: int, payout: int
) -> None:
    """Preflop the big blind wins the blinds (the small blind's unmatched half is not theirs to lose); on later streets
    seat 2 bets, both fold, the bet is returned unmatched and the winner takes the three preflop calls."""
    hand = new_hand()
    if street is Street.PREFLOP:
        play(hand, (1, FOLD), (2, FOLD))
    else:
        call_preflop(hand)
        check_to(hand, PREVIOUS_STREET[street])
        next_street(hand)
        play(hand, (2, bet(20)), (3, FOLD), (1, FOLD))

    settlement = settle_and_check(hand)

    assert settlement.payouts == {winner: payout}
    assert settlement.showdown_ranks == ()
    assert hand.street is street


def test_an_uncontested_win_on_the_river_still_has_no_showdown_ranks(new_hand: NewHand) -> None:
    """The board is complete, but with one live player nothing is evaluated."""
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, bet(20)), (3, FOLD), (1, FOLD))

    settlement = settle_and_check(hand)

    assert len(hand.board) == 5
    assert settlement.showdown_ranks == ()


def test_folded_dead_money_in_several_pots_all_goes_to_the_sole_live_player(new_hand: NewHand) -> None:
    """Seat 2 folds with 30 collected, seat 1 with 70, and seat 3 wins: dead money at two levels makes two pots, both
    awarded to seat 3, whose own unmatched chips above 70 have been returned."""
    hand = new_hand()
    call_preflop(hand)
    next_street(hand)
    play(hand, (2, bet(20)), (3, CALL), (1, raise_to(60)), (2, FOLD), (3, raise_to(200)), (1, FOLD))

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((3, 90),), ((3, 80),)]
    assert settlement.payouts == {3: 170}
    assert [state.player.stack for state in hand.players] == [930, 970, 1100]


def test_an_all_in_player_whose_opponents_fold_wins_uncontested_and_is_not_all_in(new_hand: NewHand) -> None:
    """Seat 1 shoves 100; both blinds fold. The unmatched 90 comes back before the win, so seat 1 wins the 25 the blinds
    and its matched call put in and ends with chips, not all-in."""
    hand = new_hand(stacks={1: 100})
    play(hand, (1, raise_to(100)), (2, FOLD), (3, FOLD))

    settlement = settle_and_check(hand)

    assert settlement.payouts == {1: 25}
    assert [(state.player.stack, state.all_in) for state in hand.players] == [(115, False), (995, False), (990, False)]


# =============================================================================
# SHOWDOWNS
# =============================================================================


def test_showdown_after_a_completed_river_round(new_hand: NewHand) -> None:
    """The river round was played to its end with a bet and two calls; the best hand wins and ranks are recorded for
    every live seat in hand order."""
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, bet(20)), (3, CALL), (1, CALL))

    settlement = settle_and_check(hand)

    assert settlement.payouts == {2: 90}
    assert settlement.showdown_ranks == (
        (1, HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9))),
        (2, HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9))),
        (3, HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4))),
    )
    assert settlement.showdown_ranks == tuple(showdown_ranks(hand).items())


@pytest.mark.parametrize("start_rounds", [False, True], ids=["later-rounds-not-started", "later-rounds-started"])
def test_showdown_after_an_earlier_all_in_with_the_remaining_streets_dealt(
    all_in_preflop: PokerHand, start_rounds: bool
) -> None:
    """With everyone all-in preflop no later round can ask anyone to act, so once the board is dealt the hand settles
    whether or not those empty rounds were started."""
    hand = all_in_preflop
    deal_remaining_streets(hand, start_rounds=start_rounds)

    settlement = settle_and_check(hand)

    assert settlement.payouts == {2: 300}
    assert hand.betting is not None
    assert hand.betting.street is (Street.RIVER if start_rounds else Street.PREFLOP)


def test_showdown_when_one_player_with_chips_faces_only_all_in_opponents(new_hand: NewHand) -> None:
    """Seats 2 and 3 are all-in preflop and seat 1 calls with chips behind: seat 1 owes nothing, so no later round can
    ask anyone to act and the dealt board settles. Seat 1, not all-in, is unaffected by the all_in rule."""
    hand = new_hand(stacks={2: 100, 3: 100})
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    deal_remaining_streets(hand, start_rounds=False)

    settlement = settle_and_check(hand)

    assert settlement.payouts == {2: 300}
    assert [(state.player.stack, state.all_in) for state in hand.players] == [(900, False), (300, False), (0, True)]


@pytest.mark.parametrize("street", [Street.FLOP, Street.TURN])
def test_showdown_after_betting_closes_on_a_later_street_with_the_remaining_streets_dealt(
    new_hand: NewHand, street: Street
) -> None:
    """Seat 2 bets all-in, seat 3 folds and seat 1, the only player left with chips, calls: no later round can ask
    anyone to act, so the dealt board settles without the remaining rounds being started."""
    hand = new_hand(stacks={2: 200})
    call_preflop(hand)
    check_to(hand, PREVIOUS_STREET[street])
    next_street(hand)
    play(hand, (2, bet(190)), (3, FOLD), (1, CALL))
    assert is_betting_closed(hand)
    deal_remaining_streets(hand, start_rounds=False)

    settlement = settle_and_check(hand)

    assert settlement.payouts == {2: 410}
    assert [(state.player.stack, state.all_in) for state in hand.players] == [(800, False), (410, False), (990, False)]


@pytest.mark.parametrize("street", [Street.FLOP, Street.TURN])
def test_a_facing_all_in_player_who_has_not_yet_acted_blocks_settlement_even_with_the_board_dealt(
    new_hand: NewHand, street: Street
) -> None:
    """Seat 2 is all-in and seat 3 folded, so seat 1 is the only player who could still act, but it has not answered
    the bet yet. Dealing ahead does not make the hand ready."""
    hand = new_hand(stacks={2: 200})
    call_preflop(hand)
    check_to(hand, PREVIOUS_STREET[street])
    next_street(hand)
    play(hand, (2, bet(190)), (3, FOLD))
    assert hand.betting is not None
    assert hand.betting.current_actor == 1
    deal_remaining_streets(hand, start_rounds=False)

    assert_rejected(hand, ShowdownNotReadyError)

    play(hand, (1, CALL))
    settle_and_check(hand)


def test_ties_split_the_pots_and_the_odd_chips_go_clockwise_from_the_button(new_hand: NewHand) -> None:
    """Seat 1 raises to 25, seat 2 folds its 5 and seat 3 calls: the pots are 15 and 40, tied between seats 1 and 3.
    Seat 3 is first left of the button, so it takes the 15-chip pot's odd chip."""
    hand = new_hand(holes={1: "As Qh", 2: "9c 9d", 3: "Ac Qd"}, board="Kc Kd 7h 4s 2d")
    play(hand, (1, raise_to(25)), (2, FOLD), (3, CALL))
    check_to(hand, Street.RIVER)

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((3, 8), (1, 7)), ((3, 20), (1, 20))]
    assert settlement.payouts == {3: 28, 1: 27}


def test_odd_chips_follow_the_hands_clockwise_order_not_ascending_seat_numbers(new_hand: NewHand) -> None:
    """With the button on seat 2 the seats run 3, 1, 2 clockwise from it. Seat 2 raises to 25, the small blind (seat 3)
    folds its 5 and the big blind (seat 1) calls; seats 1 and 2 tie. Seat 1 is the first tied winner left of the button,
    so it takes the 15-chip pot's odd chip, though the button (seat 2) sits first in the hand's player order."""
    hand = new_hand(holes={1: "As Qh", 2: "Ac Qd", 3: "9c 9d"}, board="Kc Kd 7h 4s 2d", button=2)
    play(hand, (2, raise_to(25)), (3, FOLD), (1, CALL))
    check_to(hand, Street.RIVER)

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((1, 8), (2, 7)), ((1, 20), (2, 20))]


# =============================================================================
# ALL-IN STATE AFTER PAYOUT
# =============================================================================


def test_a_paid_all_in_player_is_no_longer_all_in(all_in_preflop: PokerHand) -> None:
    hand = all_in_preflop
    deal_remaining_streets(hand, start_rounds=False)
    winner = next(state for state in hand.players if state.seat_number == 2)
    assert winner.all_in

    settle_and_check(hand)

    assert (winner.player.stack, winner.all_in) == (300, False)


def test_an_unpaid_all_in_player_keeps_all_in_with_a_zero_stack(all_in_preflop: PokerHand) -> None:
    hand = all_in_preflop
    deal_remaining_streets(hand, start_rounds=False)

    settle_and_check(hand)

    losers = [state for state in hand.players if state.seat_number != 2]
    assert [(state.player.stack, state.all_in) for state in losers] == [(0, True), (0, True)]


def test_an_all_in_player_winning_only_the_main_pot_is_paid_and_stops_being_all_in(new_hand: NewHand) -> None:
    """Seat 2 is all-in for 100 against seats 1 and 3, who put 300 in and play the river; seat 2 wins the 300 main pot
    and seat 1, the better of the other two, the 400 side pot."""
    hand = new_hand(stacks={2: 100})
    play(hand, (1, raise_to(300)), (2, CALL), (3, CALL))
    check_to(hand, Street.RIVER)
    seat_two = next(state for state in hand.players if state.seat_number == 2)
    assert seat_two.all_in

    settlement = settle_and_check(hand)

    assert settlement.pot_awards == (
        PotAward(pots(hand)[0], ((2, 300),)),
        PotAward(pots(hand)[1], ((1, 400),)),
    )
    assert (seat_two.player.stack, seat_two.all_in) == (300, False)
    assert [state.player.stack for state in hand.players if state.seat_number != 2] == [1100, 700]


@pytest.mark.parametrize(
    ("seat_three_holes", "side_pot_winner", "seat_three_after"),
    [("Jd Jh", 3, (200, False)), ("3s 4s", 1, (0, True))],
    ids=["side-pot-won-by-a-second-all-in", "side-pot-lost-by-a-second-all-in"],
)
def test_each_pot_is_paid_to_its_own_winner_and_all_in_is_cleared_only_for_paid_seats(
    new_hand: NewHand, seat_three_holes: str, side_pot_winner: int, seat_three_after: tuple[int, bool]
) -> None:
    """Seat 1 raises to 500 and seats 2 and 3 call all-in for 100 and 200, the rest of the raise coming back. Seat 2 (a
    set of kings) wins the 300 main pot with the smallest stack. The 200 side pot between seats 1 and 3 goes to whoever
    holds the better hand: a second all-in set, or seat 1's pair of aces over an all-in seat left with nothing."""
    hand = new_hand(stacks={2: 100, 3: 200}, holes={**HOLES, 3: seat_three_holes})
    play(hand, (1, raise_to(500)), (2, CALL), (3, CALL))
    deal_remaining_streets(hand, start_rounds=False)

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((2, 300),), ((side_pot_winner, 200),)]
    by_seat = {state.seat_number: (state.player.stack, state.all_in) for state in hand.players}
    assert by_seat[2] == (300, False)
    assert by_seat[3] == seat_three_after
    assert by_seat[1] == (1000 - 200 + (200 if side_pot_winner == 1 else 0), False)


# =============================================================================
# REJECTIONS
# =============================================================================


def test_a_hand_without_a_betting_state_is_rejected(stacked_hand: NewHand, deal_to: Callable[..., None]) -> None:
    """Even a full board dealt without any betting cannot be settled."""
    hand = stacked_hand(HOLES, BOARD)
    deal_to(hand, Street.RIVER)

    assert_rejected(hand, BettingNotInitializedError)


@pytest.mark.parametrize("street", [Street.FLOP, Street.TURN])
def test_a_contested_hand_before_the_river_is_rejected(new_hand: NewHand, street: Street) -> None:
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, street)

    assert_rejected(hand, IncompleteBoardError)


@pytest.mark.parametrize("street", [Street.PREFLOP, Street.FLOP, Street.TURN])
def test_a_contested_hand_with_betting_closed_early_still_needs_the_whole_board(
    all_in_preflop: PokerHand, street: Street
) -> None:
    hand = all_in_preflop
    while hand.street is not street:
        deal_next_street(hand)

    assert_rejected(hand, IncompleteBoardError)


def test_a_river_dealt_without_its_round_started_is_rejected_while_two_players_can_act(new_hand: NewHand) -> None:
    """The board is complete, but the turn round is the last one played and seats 1, 2 and 3 can still bet."""
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.TURN)
    deal_next_street(hand)

    assert_rejected(hand, ShowdownNotReadyError)


def test_a_river_round_in_progress_is_rejected(new_hand: NewHand) -> None:
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, CHECK))

    assert_rejected(hand, ShowdownNotReadyError)


def test_settling_twice_is_rejected_and_changes_nothing(new_hand: NewHand) -> None:
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.RIVER)
    settle_and_check(hand)
    before = hand_snapshot(hand)

    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)

    assert hand_snapshot(hand) == before


def test_settling_an_uncontested_hand_twice_is_rejected_and_changes_nothing(new_hand: NewHand) -> None:
    hand = new_hand()
    play(hand, (1, FOLD), (2, FOLD))
    settle_and_check(hand)
    before = hand_snapshot(hand)

    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)

    assert hand_snapshot(hand) == before


def test_a_second_settlement_is_reported_as_already_settled_even_when_the_payout_reopened_betting(
    new_hand: NewHand,
) -> None:
    """Everyone is all-in preflop and the pot is split three ways, so all three are paid and stop being all-in. Betting
    then looks open again (three players can act in a round that is not the river's), which must not hide that the hand
    is settled."""
    hand = new_hand(stacks={1: 100, 2: 100, 3: 100}, holes=TYING_HOLES, board=ROYAL_FLUSH_BOARD)
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    deal_remaining_streets(hand, start_rounds=False)
    settle_and_check(hand)
    assert not is_betting_closed(hand)
    before = hand_snapshot(hand)

    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)

    assert hand_snapshot(hand) == before

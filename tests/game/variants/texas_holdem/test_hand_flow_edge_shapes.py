"""Edge shapes of whole hands driven only through `hand_flow`: blinds that finish or nearly finish the hand, the river
with an all-in somewhere, a player who is the only one left, heads-up order and the guard on a settled hand.

Hands come from the shared `stacked_hand` fixture: seats 1 (button), 2 (small blind) and 3 (big blind), blinds 5/10 and
1000 chips each unless stated; preflop seat 1 acts first and on later streets seat 2 does. Hole cards are chosen by
strength on DRY_BOARD (no pair, no flush, no straight possible for these cards): AA (seat 1) beats KK (seat 2), which
beats 3s 4s (seat 3). The expected chips are worked out by hand in each test.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import NOTHING_LEGAL, legal_actions
from go_poker.game.betting.pots import pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

DRY_BOARD = "2c 4d 7h 9s Jc"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
HEADS_UP = {1: "Ah Ad", 2: "Kd Kh"}

type StackedHand = Callable[..., PokerHand]
type Move = tuple[int, Action | ShowdownAction]


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def assert_waiting_or_settled(hand: PokerHand) -> None:
    if hand.settlement is not None:
        assert current_actor(hand) is None
    elif hand.betting is not None and hand.betting.current_actor is not None:
        assert current_actor(hand) == hand.betting.current_actor and legal_actions(hand) != NOTHING_LEGAL
        assert hand.showdown is None
    else:
        assert hand.showdown is not None and not hand.showdown.is_complete
        assert current_actor(hand) == hand.showdown.current_decider


class Flow:
    def __init__(self, hand: PokerHand) -> None:
        self.hand = hand
        self.total = sum(state.player.stack for state in hand.players)

    def begin(self) -> Flow:
        begin_hand(self.hand, STAKES)
        assert_waiting_or_settled(self.hand)
        return self

    def play(self, *moves: Move) -> Flow:
        for seat, action in moves:
            assert current_actor(self.hand) == seat
            act(self.hand, seat, action)
            assert_waiting_or_settled(self.hand)
        return self

    def stacks(self) -> dict[int, int]:
        return {state.seat_number: state.player.stack for state in self.hand.players}

    def assert_settled(self, stacks: dict[int, int], payouts: dict[int, int], ranked: set[int]) -> None:
        settlement = self.hand.settlement
        assert settlement is not None
        assert self.stacks() == stacks
        assert settlement.payouts == payouts
        assert {seat for seat, _ in settlement.showdown_ranks} == ranked
        assert sum(self.stacks().values()) == self.total
        assert current_actor(self.hand) is None


def flow(stacked_hand: StackedHand, holes: dict[int, str] = HOLES, **kwargs: Any) -> Flow:
    return Flow(stacked_hand(holes, DRY_BOARD, **kwargs))


def limp(f: Flow) -> Flow:
    return f.play((1, CALL), (2, CALL), (3, CHECK))


def check_street(f: Flow) -> Flow:
    return f.play((2, CHECK), (3, CHECK), (1, CHECK))


def at_river(f: Flow) -> Flow:
    limp(f)
    check_street(f)
    check_street(f)
    assert f.hand.street is Street.RIVER and current_actor(f.hand) == 2
    return f


def all_in_flow(stacked_hand: StackedHand) -> Flow:
    """Seat 1 (100 chips) shoves preflop and seats 2 and 3 (300 each) call; seats 2 and 3 go on betting."""
    f = flow(stacked_hand, stacks={1: 100, 2: 300, 3: 300}).begin()
    return f.play((1, raise_to(100)), (2, CALL), (3, CALL))


# =============================================================================
# BLINDS THAT FINISH OR NEARLY FINISH THE HAND
# =============================================================================


def test_a_short_small_blind_heads_up_finishes_the_hand_in_begin_hand(stacked_hand: StackedHand) -> None:
    """Seat 1 posts its 3 chips all-in; the big blind (seat 2) gets 7 back and has nobody to bet against."""
    f = flow(stacked_hand, HEADS_UP, stacks={1: 3, 2: 1000}).begin()

    f.assert_settled({1: 6, 2: 997}, {1: 6}, {1, 2})
    assert f.hand.showdown is not None and f.hand.showdown.kind is ShowdownKind.ALL_IN
    assert f.hand.street is Street.RIVER and len(f.hand.board) == 5


def test_a_short_big_blind_heads_up_leaves_the_decision_to_the_small_blind(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, HEADS_UP, stacks={1: 1000, 2: 6}).begin()

    assert f.hand.settlement is None and current_actor(f.hand) == 1 and f.hand.showdown is None
    f.play((1, CALL))

    f.assert_settled({1: 1006, 2: 0}, {1: 12}, {1, 2})
    assert f.hand.showdown is not None and f.hand.showdown.kind is ShowdownKind.ALL_IN


def test_a_short_big_blind_heads_up_folding_the_small_blind_settles_without_a_showdown(
    stacked_hand: StackedHand,
) -> None:
    f = flow(stacked_hand, HEADS_UP, stacks={1: 1000, 2: 6}).begin()

    f.play((1, FOLD))

    # The big blind's sixth chip, which the small blind never matched, went back to it.
    f.assert_settled({1: 995, 2: 11}, {2: 10}, set())
    assert f.hand.showdown is None and f.hand.board == []


def test_both_blinds_all_in_three_handed_still_asks_the_button(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, stacks={1: 1000, 2: 5, 3: 10}).begin()

    assert f.hand.settlement is None and f.hand.showdown is None and current_actor(f.hand) == 1
    f.play((1, CALL))

    f.assert_settled({1: 1015, 2: 0, 3: 0}, {1: 25}, {1, 2, 3})
    assert f.hand.showdown is not None and f.hand.showdown.order == (2, 3, 1)


def test_both_blinds_all_in_three_handed_with_the_button_folding_runs_out_between_the_blinds(
    stacked_hand: StackedHand,
) -> None:
    f = flow(stacked_hand, stacks={1: 1000, 2: 5, 3: 10}).begin()

    f.play((1, FOLD))

    # Seat 2's kings win the 10 chips both blinds can contest; seat 3's extra 5 went back.
    f.assert_settled({1: 1000, 2: 10, 3: 5}, {2: 10}, {2, 3})
    assert f.hand.showdown is not None and f.hand.showdown.order == (2, 3)
    assert f.hand.street is Street.RIVER and len(f.hand.board) == 5


def test_a_short_big_blind_three_handed_lets_the_other_two_keep_betting(stacked_hand: StackedHand) -> None:
    """Seat 3 posts its 6 all-in. The button and small blind call 10, so there is a flop with seat 2 to act, and the
    hand goes on between seats 1 and 2 until the river without an interactive showdown, because seat 3 is all-in."""
    f = flow(stacked_hand, stacks={1: 1000, 2: 1000, 3: 6}).begin()
    assert current_actor(f.hand) == 1

    f.play((1, CALL), (2, CALL))

    assert f.hand.street is Street.FLOP and f.hand.showdown is None and current_actor(f.hand) == 2
    f.play((2, CHECK), (1, CHECK), (2, CHECK), (1, CHECK), (2, CHECK), (1, CHECK))

    assert f.hand.showdown is not None and f.hand.showdown.kind is ShowdownKind.ALL_IN
    assert f.hand.showdown.order == (2, 3, 1)
    # Seat 3 put in 6, seats 1 and 2 put in 10: seat 1's aces win the whole 26.
    f.assert_settled({1: 1016, 2: 990, 3: 0}, {1: 26}, {1, 2, 3})
    assert [pot.amount for pot in pots(f.hand)] == [18, 8]


# =============================================================================
# THE RIVER WITH AN ALL-IN
# =============================================================================


def test_a_river_all_in_called_by_one_player_with_the_other_folded_is_an_all_in_showdown(
    stacked_hand: StackedHand,
) -> None:
    f = at_river(flow(stacked_hand).begin())
    f.play((2, CHECK), (3, bet(990)), (1, FOLD), (2, CALL))

    f.assert_settled({1: 990, 2: 2010, 3: 0}, {2: 2010}, {2, 3})
    assert f.hand.showdown is not None
    assert (f.hand.showdown.kind, f.hand.showdown.order) == (ShowdownKind.ALL_IN, (2, 3))


def test_a_short_all_in_call_on_the_river_makes_an_all_in_showdown_in_canonical_order(
    stacked_hand: StackedHand,
) -> None:
    """Seat 3 has 40 chips left on the river. Seat 2 bets, so an interactive order would start with seat 2 and end
    with seat 1 or 3, but the all-in showdown tables everybody at once in canonical order."""
    f = flow(stacked_hand, stacks={1: 1000, 2: 1000, 3: 50}).begin()
    at_river(f)

    f.play((2, bet(100)), (3, CALL), (1, CALL))

    assert f.hand.showdown is not None and f.hand.showdown.kind is ShowdownKind.ALL_IN
    assert f.hand.showdown.order == (2, 3, 1) and f.hand.showdown.decisions == ()
    # Seats 1 and 2 put in 110 and seat 3 put in 50: the aces win the 150 main pot and the 120 side pot.
    assert [pot.amount for pot in pots(f.hand)] == [150, 120]
    f.assert_settled({1: 1160, 2: 890, 3: 0}, {1: 270}, {1, 2, 3})


def test_a_short_all_in_call_with_the_other_caller_folded_returns_the_unmatched_bet(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, stacks={1: 1000, 2: 1000, 3: 50}).begin()
    at_river(f)

    f.play((2, bet(100)), (3, CALL), (1, FOLD))

    # Seat 2's bet is matched only up to 40, so 60 goes back. Seats 2 and 3 put in 50 each and seat 1 folded 10: the
    # kings win all 110.
    assert f.hand.showdown is not None and f.hand.showdown.kind is ShowdownKind.ALL_IN
    assert f.hand.showdown.order == (2, 3)
    f.assert_settled({1: 990, 2: 1060, 3: 0}, {2: 110}, {2, 3})


def test_a_river_all_in_with_unmatched_chips_returned_still_ends_in_an_all_in_showdown(
    stacked_hand: StackedHand,
) -> None:
    """Seat 3 shoves 990 into seat 1's 290; seat 2 folds. Seat 3 gets 700 back and has chips, but seat 1 is all-in."""
    f = flow(stacked_hand, stacks={1: 300, 2: 1000, 3: 1000}).begin()
    at_river(f)

    f.play((2, CHECK), (3, bet(990)), (1, CALL), (2, FOLD))

    assert f.hand.showdown is not None
    assert (f.hand.showdown.kind, f.hand.showdown.order) == (ShowdownKind.ALL_IN, (3, 1))
    f.assert_settled({1: 610, 2: 990, 3: 700}, {1: 610}, {1, 3})


def test_a_river_bet_by_a_player_with_chips_left_is_an_interactive_showdown_led_by_the_bettor(
    stacked_hand: StackedHand,
) -> None:
    f = flow(stacked_hand).begin()
    at_river(f)

    f.play((2, bet(100)), (3, FOLD), (1, CALL))

    assert f.hand.showdown is not None
    assert (f.hand.showdown.kind, f.hand.showdown.order) == (ShowdownKind.INTERACTIVE, (2, 1))
    f.play((2, SHOW), (1, SHOW))
    f.assert_settled({1: 1120, 2: 890, 3: 990}, {1: 230}, {1, 2})


def test_a_player_all_in_earlier_is_not_interactive_when_the_others_bet_the_river(stacked_hand: StackedHand) -> None:
    """Seat 1 is all-in since preflop; seat 3 bets the river and seat 2 calls. The aggressor does not lead: the showdown
    is ALL_IN with every hand tabled in canonical order, and the side pot goes to the kings."""
    f = all_in_flow(stacked_hand)
    f.play((2, CHECK), (3, CHECK), (2, CHECK), (3, CHECK), (2, CHECK), (3, bet(50)), (2, CALL))

    assert f.hand.showdown is not None
    assert (f.hand.showdown.kind, f.hand.showdown.order, f.hand.showdown.decisions) == (
        ShowdownKind.ALL_IN,
        (2, 3, 1),
        (),
    )
    # Seat 1: 100. Seats 2 and 3: 150 each. The aces win the 300 main pot, the kings the 100 side pot.
    f.assert_settled({1: 300, 2: 250, 3: 150}, {1: 300, 2: 100}, {1, 2, 3})


# =============================================================================
# THE ALL-IN PLAYER IS THE ONLY ONE LEFT, OR THE ONLY ONE WHO STAYS
# =============================================================================


def test_an_all_in_player_whose_opponents_fold_wins_uncontested_without_a_showdown(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, stacks={1: 100, 2: 300, 3: 300}).begin()

    f.play((1, raise_to(100)), (2, FOLD), (3, FOLD))

    # Seat 1 keeps its unmatched 90 and wins the 25 chips of the blinds.
    f.assert_settled({1: 115, 2: 295, 3: 290}, {1: 25}, set())
    assert f.hand.showdown is None and f.hand.board == []


def test_a_bet_folded_to_the_all_in_player_runs_the_board_out_against_the_bettor(stacked_hand: StackedHand) -> None:
    f = all_in_flow(stacked_hand)

    f.play((2, bet(50)), (3, FOLD))

    assert f.hand.showdown is not None
    assert (f.hand.showdown.kind, f.hand.showdown.order) == (ShowdownKind.ALL_IN, (2, 1))
    assert f.hand.street is Street.RIVER and f.hand.betting is not None and f.hand.betting.street is Street.FLOP
    f.assert_settled({1: 300, 2: 200, 3: 200}, {1: 300}, {1, 2})


def test_a_raise_over_a_bet_and_a_fold_leaves_the_raiser_against_the_all_in_player(stacked_hand: StackedHand) -> None:
    f = all_in_flow(stacked_hand)

    f.play((2, bet(50)), (3, raise_to(150)), (2, FOLD))

    assert f.hand.showdown is not None
    assert (f.hand.showdown.kind, f.hand.showdown.order) == (ShowdownKind.ALL_IN, (3, 1))
    # Seat 3's raise to 150 is matched only by seat 2's 50, so 100 of it goes back. Main pot 300 (seat 1's aces), side
    # pot 100 (seat 3's, the only live seat in it).
    f.assert_settled({1: 300, 2: 150, 3: 250}, {1: 300, 3: 100}, {1, 3})


# =============================================================================
# HEADS-UP ORDER
# =============================================================================


def test_heads_up_the_small_blind_acts_first_preflop_and_the_big_blind_first_after(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, HEADS_UP).begin()
    assert current_actor(f.hand) == 1  # the button is the small blind
    f.play((1, CALL), (2, CHECK))

    for _ in range(3):
        assert current_actor(f.hand) == 2
        f.play((2, CHECK), (1, CHECK))

    assert f.hand.showdown is not None and f.hand.showdown.order == (2, 1)


def test_heads_up_a_river_bet_by_the_small_blind_makes_it_decide_first(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, HEADS_UP).begin().play((1, CALL), (2, CHECK))
    for _ in range(2):
        f.play((2, CHECK), (1, CHECK))

    f.play((2, CHECK), (1, bet(40)), (2, CALL))

    assert f.hand.showdown is not None and f.hand.showdown.order == (1, 2)
    f.play((1, SHOW), (2, SHOW))
    f.assert_settled({1: 1050, 2: 950}, {1: 100}, {1, 2})


def test_heads_up_a_river_raise_by_the_big_blind_makes_it_decide_first(stacked_hand: StackedHand) -> None:
    f = flow(stacked_hand, HEADS_UP).begin().play((1, CALL), (2, CHECK))
    for _ in range(2):
        f.play((2, CHECK), (1, CHECK))

    f.play((2, bet(40)), (1, raise_to(120)), (2, CALL))

    assert f.hand.showdown is not None and f.hand.showdown.order == (1, 2)


# =============================================================================
# CALLS BEFORE THE HAND BEGINS, AND AFTER IT IS OVER
# =============================================================================


def test_acting_before_the_hand_begins_is_rejected_by_betting_without_a_change(stacked_hand: StackedHand) -> None:
    hand = stacked_hand(HOLES, DRY_BOARD)
    before = copy.deepcopy(hand.players), hand.betting, hand.street, len(hand.deck)

    with pytest.raises(BettingNotInitializedError):
        act(hand, 1, CALL)

    assert (copy.deepcopy(hand.players), hand.betting, hand.street, len(hand.deck)) == before


def settled_by(stacked_hand: StackedHand, how: str) -> Flow:
    """A settled hand reached by each way a hand can end."""
    f = flow(stacked_hand).begin()
    match how:
        case "folds":
            f.play((1, FOLD), (2, FOLD))
        case "all_in":
            f.play((1, raise_to(1000)), (2, CALL), (3, CALL))
        case "interactive":
            at_river(f)
            check_street(f)
            f.play((2, SHOW), (3, SHOW), (1, SHOW))
        case "unshown":
            at_river(f)
            check_street(f)
            f.play((2, MUCK), (3, MUCK))
    assert f.hand.settlement is not None
    return f


@pytest.mark.parametrize("how", ["folds", "all_in", "interactive", "unshown"])
@pytest.mark.parametrize("action", [FOLD, CHECK, CALL, SHOW, MUCK, None, "check"])
def test_every_way_of_ending_leaves_a_hand_that_rejects_every_further_call_as_settled(
    stacked_hand: StackedHand, how: str, action: Any
) -> None:
    """A payout clears `all_in`, which makes betting look open again; the settled guard must still come first."""
    f = settled_by(stacked_hand, how)
    hand = f.hand
    stacks, settlement, showdown = f.stacks(), hand.settlement, hand.showdown
    pots_before = pots(hand)

    for seat in (1, 2, 3, 99):
        with pytest.raises(HandAlreadySettledError):
            act(hand, seat, action)
    with pytest.raises(HandAlreadySettledError):
        begin_hand(hand, STAKES)

    assert (f.stacks(), hand.settlement, hand.showdown, pots(hand)) == (stacks, settlement, showdown, pots_before)
    assert current_actor(hand) is None


def test_the_all_in_cleared_by_a_payout_does_not_make_the_settled_hand_look_open(stacked_hand: StackedHand) -> None:
    f = settled_by(stacked_hand, "all_in")

    assert f.hand.betting is not None and f.hand.betting.current_actor is None
    assert not any(state.all_in for state in f.hand.players if state.player.stack > 0)
    assert current_actor(f.hand) is None
    with pytest.raises(HandAlreadySettledError):
        act(f.hand, 1, CHECK)


def test_the_unpaid_losers_of_an_all_in_hand_keep_their_all_in_flag_and_the_hand_still_has_no_actor(
    stacked_hand: StackedHand,
) -> None:
    f = settled_by(stacked_hand, "all_in")

    assert [state.all_in for state in f.hand.players] == [False, True, True]
    assert current_actor(f.hand) is None

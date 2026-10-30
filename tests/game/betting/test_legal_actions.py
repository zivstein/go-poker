import copy
from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type BettingLookup = Callable[[PokerHand], BettingState]
type Play = Callable[..., None]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def legal(
    *,
    can_fold: bool = False,
    can_check: bool = False,
    can_call: bool = False,
    amount_owed: int = 0,
    call_amount: int = 0,
    call_is_all_in: bool = False,
    can_bet: bool = False,
    can_raise: bool = False,
    min_full_target: int | None = None,
    max_target: int | None = None,
    short_all_in_target: int | None = None,
) -> LegalActions:
    """Expected legal actions; anything not given is not legal, owed, or set."""
    return LegalActions(
        can_fold=can_fold,
        can_check=can_check,
        can_call=can_call,
        amount_owed=amount_owed,
        call_amount=call_amount,
        call_is_all_in=call_is_all_in,
        can_bet=can_bet,
        can_raise=can_raise,
        min_full_target=min_full_target,
        max_target=max_target,
        short_all_in_target=short_all_in_target,
    )


@pytest.fixture
def called_around(started_hand: HandFactory, play: Play) -> PokerHand:
    """Three-handed preflop (button 1, SB 2, BB 3), hole cards dealt, after the button and small blind call."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL))
    return hand


@pytest.fixture
def facing_raise_to_30(started_hand: HandFactory, play: Play) -> Callable[[int], PokerHand]:
    """Four-handed preflop (button 5, SB 8, BB 1, UTG 3): UTG raises to 30, the button folds, the small blind acts.

    The returned factory takes the chips the small blind started the hand with; 5 of them are posted.
    """

    def make(small_blind_chips: int) -> PokerHand:
        hand = started_hand({5: 1000, 8: small_blind_chips, 1: 1000, 3: 1000}, button_seat_number=5)
        play(hand, (3, Action(ActionType.RAISE, 30)), (5, FOLD))
        return hand

    return make


# =============================================================================
# PREFLOP
# =============================================================================


def test_first_actor_facing_the_big_blind_may_fold_call_or_raise(
    started_hand: HandFactory, betting: BettingLookup
) -> None:
    """UTG owes the big blind: fold, call 10, or raise to between two big blinds and the whole stack."""
    hand = started_hand({1: 1000, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    betting_before = copy.deepcopy(betting(hand))

    assert legal_actions(hand) == legal(
        can_fold=True,
        can_call=True,
        amount_owed=10,
        call_amount=10,
        can_raise=True,
        min_full_target=20,
        max_target=1000,
    )
    assert hand.betting == betting_before  # derived on request, nothing stored


def test_big_blind_option_when_called_around(called_around: PokerHand) -> None:
    """With the big blind matched, the big blind may check or raise, and may still fold."""
    assert legal_actions(called_around) == legal(
        can_fold=True, can_check=True, can_raise=True, min_full_target=20, max_target=1000
    )


# =============================================================================
# UNOPENED ROUND
# =============================================================================


def test_unopened_round_allows_check_or_bet(called_around: PokerHand, play: Play) -> None:
    """On the flop with nothing bet, the small blind may check or bet between the big blind and the whole stack."""
    hand = called_around
    play(hand, (3, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    assert legal_actions(hand) == legal(can_fold=True, can_check=True, can_bet=True, min_full_target=10, max_target=990)


def test_stack_below_the_big_blind_may_only_open_with_a_short_all_in_bet(started_hand: HandFactory, play: Play) -> None:
    """Called around preflop, the big blind is left with 6 chips, less than the full bet of 10. On the flop, after the
    small blind checks, it may check or bet all-in to 6 and to no other target, while `min_full_target` still reports
    the big blind."""
    hand = started_hand({1: 1000, 2: 1000, 3: 16}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    play(hand, (2, CHECK))

    assert legal_actions(hand) == legal(
        can_fold=True, can_check=True, can_bet=True, min_full_target=10, max_target=6, short_all_in_target=6
    )


# =============================================================================
# FACING A RAISE
# =============================================================================


def test_raise_minimum_follows_last_full_raise_and_call_counts_street_contribution(
    facing_raise_to_30: Callable[[int], PokerHand],
) -> None:
    """Facing a raise to 30 (a raise of 20), the small blind owes and calls 25 more and may raise to at least 50."""
    assert legal_actions(facing_raise_to_30(1000)) == legal(
        can_fold=True,
        can_call=True,
        amount_owed=25,
        call_amount=25,
        can_raise=True,
        min_full_target=50,
        max_target=1000,
    )


@pytest.mark.parametrize(
    "small_blind_chips, expected",
    [
        pytest.param(
            50,
            legal(
                can_fold=True,
                can_call=True,
                amount_owed=25,
                call_amount=25,
                can_raise=True,
                min_full_target=50,
                max_target=50,
            ),
            id="whole-stack-reaches-minimum-raise",
        ),
        pytest.param(
            49,
            legal(
                can_fold=True,
                can_call=True,
                amount_owed=25,
                call_amount=25,
                can_raise=True,
                min_full_target=50,
                max_target=49,
                short_all_in_target=49,
            ),
            id="short-all-in-raise-below-minimum-raise",
        ),
        pytest.param(
            30,
            legal(can_fold=True, can_call=True, amount_owed=25, call_amount=25, call_is_all_in=True),
            id="call-with-whole-stack",
        ),
        pytest.param(
            20,
            legal(can_fold=True, can_call=True, amount_owed=25, call_amount=15, call_is_all_in=True),
            id="short-all-in-call",
        ),
    ],
)
def test_stack_limits_raise_and_call(
    small_blind_chips: int, expected: LegalActions, facing_raise_to_30: Callable[[int], PokerHand]
) -> None:
    """A stack that reaches the minimum full target allows any raise up to it; a stack above the current bet but
    below that minimum allows only the short all-in raise to the whole stack, while `min_full_target` still reports
    the full minimum. A call is legal whenever chips are owed: it commits the amount owed, or the whole stack when
    that is less (a short call), and a call that uses the whole stack is all-in. With no chips beyond the current
    bet, there is no raise."""
    assert legal_actions(facing_raise_to_30(small_blind_chips)) == expected


# =============================================================================
# RAISE RIGHTS
# =============================================================================


def test_player_who_acted_regains_raise_rights_after_a_full_raise(started_hand: HandFactory, play: Play) -> None:
    """UTG limps at 10 and the button raises to 30, a full raise of 20. UTG now faces exactly one full raise more
    than the bet it acted at, so it may re-raise to at least 50."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 1000}, button_seat_number=5)
    play(hand, (3, CALL), (5, Action(ActionType.RAISE, 30)), (8, FOLD), (1, FOLD))

    assert legal_actions(hand) == legal(
        can_fold=True,
        can_call=True,
        amount_owed=20,
        call_amount=20,
        can_raise=True,
        min_full_target=50,
        max_target=1000,
    )


# =============================================================================
# NO OPPONENT CAN RESPOND
# =============================================================================


@pytest.mark.parametrize(
    "stacks, button_seat_number, actions",
    [
        pytest.param({3: 10, 7: 1000}, 7, [], id="heads-up"),
        pytest.param({1: 1000, 2: 1000, 3: 10}, 1, [(1, FOLD)], id="three-handed-button-folded"),
    ],
)
def test_no_bet_or_raise_when_every_other_live_player_is_all_in(
    stacks: dict[int, int],
    button_seat_number: int,
    actions: list[tuple[int, Action]],
    started_hand: HandFactory,
    play: Play,
) -> None:
    """When the big blind is all-in by posting and every other opponent folded, the small blind can only fold or
    call the outstanding chips."""
    hand = started_hand(stacks, button_seat_number=button_seat_number)
    play(hand, *actions)
    assert legal_actions(hand) == legal(can_fold=True, can_call=True, amount_owed=5, call_amount=5)


def test_amount_owed_is_measured_against_the_largest_all_in_opponent(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """Four-handed, the big blind is all-in for 3 of the 10 blind, UTG calls all-in for 7 and the button folds. The
    small blind, with 5 in, is the only player left who can act: it still owes the 2 that UTG, the larger of the two
    all-in players, can contest (not the nominal 10, nor nothing against the big blind's 3), so it stays pending and
    may only call or fold."""
    hand = started_hand({5: 1000, 8: 1000, 1: 3, 3: 7}, button_seat_number=5)
    play(hand, (3, CALL), (5, FOLD))

    assert betting(hand).pending_actors == {8}
    assert legal_actions(hand) == legal(can_fold=True, can_call=True, amount_owed=2, call_amount=2)


# =============================================================================
# NOBODY TO ACT
# =============================================================================


def test_nothing_is_legal_when_nobody_is_to_act(started_hand: HandFactory, betting: BettingLookup) -> None:
    """A round that is complete has no current actor, so no action is legal."""
    hand = started_hand({3: 1000, 7: 5}, button_seat_number=7)
    assert betting(hand).current_actor is None
    assert legal_actions(hand) == legal()


def test_legal_actions_need_initialized_betting(make_hand: HandFactory) -> None:
    """A hand whose betting was never initialized has no legal actions to derive."""
    with pytest.raises(BettingNotInitializedError):
        legal_actions(make_hand({3: 1000, 7: 1000}, button_seat_number=7))

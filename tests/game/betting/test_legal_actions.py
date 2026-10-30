import copy
from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.chips import commit_chips
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
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
            49, legal(can_fold=True, can_call=True, amount_owed=25, call_amount=25), id="stack-below-minimum-raise"
        ),
        pytest.param(
            30,
            legal(can_fold=True, can_call=True, amount_owed=25, call_amount=25, call_is_all_in=True),
            id="call-with-whole-stack",
        ),
        pytest.param(20, legal(can_fold=True, amount_owed=25), id="call-above-stack"),
    ],
)
def test_stack_limits_raise_and_call(
    small_blind_chips: int, expected: LegalActions, facing_raise_to_30: Callable[[int], PokerHand]
) -> None:
    """A raise needs the whole stack to reach the minimum full target and a call needs the stack to cover the amount
    owed; a call of exactly the whole stack is all-in. Short all-in raises and calls are not legal yet, so a call
    above the stack commits nothing (`call_amount` 0) while the amount owed is still reported."""
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


def test_no_bet_or_raise_without_raise_rights(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """On the flop seat 2 bets 50, seat 3 goes all-in to 70 (a short raise of 20, below the full raise of 50) and
    seat 1 calls. Seat 2 acted at 50 and faces only 20 more, so it may call or fold but not raise, although seat 1
    could still respond and seat 2's stack reaches the minimum raise."""
    hand = started_hand({1: 1000, 2: 1000, 3: 80}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    play(hand, (2, Action(ActionType.BET, 50)))

    # Short all-in raises are not legal yet, so seat 3's raise to 70 is set up directly with the changes it makes:
    # its whole stack is committed, the current bet becomes 70 (the last full raise size stays 50), seat 3 has acted
    # at 70, and every other eligible player owes a response, seat 1 first.
    commit_chips(by_seat(hand)[3], 70)
    state = betting(hand)
    state.current_bet = 70
    state.acted_at_bet[3] = 70
    state.pending_actors = {1, 2}
    state.current_actor = 1
    play(hand, (1, CALL))

    assert legal_actions(hand) == legal(can_fold=True, can_call=True, amount_owed=20, call_amount=20)


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

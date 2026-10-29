import copy
from collections.abc import Callable

import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.chips import commit_chips
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

STAKES = Stakes(small_blind=5, big_blind=10)


def make_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """Build a hand clockwise from the button, with each seat's player holding the given stack."""
    assignments = assign_hand_seats(tuple(stacks), button_seat_number)
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=stacks[seat_number], status=PlayerStatus.READY),
            seat_number=seat_number,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat_number, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=Deck())


def started_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """A hand with its blinds posted and preflop betting initialized."""
    hand = make_hand(stacks, button_seat_number)
    initialize_betting(hand, STAKES)
    return hand


def by_seat(hand: PokerHand) -> dict[int, HandPlayerState]:
    return {hand_player.seat_number: hand_player for hand_player in hand.players}


def betting(hand: PokerHand) -> BettingState:
    assert hand.betting is not None
    return hand.betting


def to_act(hand: PokerHand, seat_number: int, pending: set[int]) -> None:
    """Hand the action to the given seat, as the actions before it (applied in a later cycle) would have."""
    betting(hand).current_actor = seat_number
    betting(hand).pending_actors = pending


def legal(
    *,
    can_fold: bool = False,
    can_check: bool = False,
    can_call: bool = False,
    call_amount: int = 0,
    can_bet: bool = False,
    can_raise: bool = False,
    min_target: int | None = None,
    max_target: int | None = None,
) -> LegalActions:
    """Expected legal actions; anything not given is not legal."""
    return LegalActions(can_fold, can_check, can_call, call_amount, can_bet, can_raise, min_target, max_target)


def three_handed_called_around() -> PokerHand:
    """Three-handed preflop (button 1, SB 2, BB 3) after the button calls and the small blind completes."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    seats = by_seat(hand)
    commit_chips(seats[1], 10)
    commit_chips(seats[2], 5)
    to_act(hand, 3, pending={3})
    return hand


def facing_raise_to_30(small_blind_chips: int) -> PokerHand:
    """Four-handed preflop (button 5, SB 8, BB 1, UTG 3): UTG raises to 30, the button folds, the small blind acts.

    The small blind started the hand with `small_blind_chips` and has posted 5 of them.
    """
    hand = started_hand({5: 1000, 8: small_blind_chips, 1: 1000, 3: 1000}, button_seat_number=5)
    seats = by_seat(hand)
    commit_chips(seats[3], 30)
    betting(hand).current_bet = 30
    betting(hand).last_full_raise_size = 20
    seats[5].folded = True
    to_act(hand, 8, pending={8, 1})
    return hand


# =============================================================================
# PREFLOP
# =============================================================================


def test_first_actor_facing_the_big_blind_may_fold_call_or_raise() -> None:
    """UTG owes the big blind: fold, call 10, or raise to between two big blinds and the whole stack."""
    hand = started_hand({1: 1000, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    betting_before = copy.deepcopy(betting(hand))

    assert legal_actions(hand) == legal(
        can_fold=True, can_call=True, call_amount=10, can_raise=True, min_target=20, max_target=1000
    )
    assert hand.betting == betting_before  # derived on request, nothing stored


def test_big_blind_option_when_called_around() -> None:
    """With the big blind matched, the big blind may check or raise, and may still fold."""
    hand = three_handed_called_around()
    assert legal_actions(hand) == legal(can_fold=True, can_check=True, can_raise=True, min_target=20, max_target=1000)


# =============================================================================
# UNOPENED ROUND
# =============================================================================


def test_unopened_round_allows_check_or_bet() -> None:
    """On the flop with nothing bet, the small blind may check or bet between the big blind and the whole stack."""
    hand = three_handed_called_around()
    deal_hole_cards(hand)
    deal_next_street(hand)
    for hand_player in hand.players:
        hand_player.street_contribution = 0
    hand.betting = BettingState(
        street=Street.FLOP,
        stakes=STAKES,
        current_bet=0,
        last_full_raise_size=STAKES.big_blind,
        current_actor=2,
        pending_actors={1, 2, 3},
    )
    assert legal_actions(hand) == legal(can_fold=True, can_check=True, can_bet=True, min_target=10, max_target=990)


# =============================================================================
# FACING A RAISE
# =============================================================================


def test_raise_minimum_follows_last_full_raise_and_call_counts_street_contribution() -> None:
    """Facing a raise to 30 (a raise of 20), the small blind calls 25 more and may raise to at least 50."""
    hand = facing_raise_to_30(small_blind_chips=1000)
    assert legal_actions(hand) == legal(
        can_fold=True, can_call=True, call_amount=25, can_raise=True, min_target=50, max_target=1000
    )


@pytest.mark.parametrize(
    "small_blind_chips, expected",
    [
        pytest.param(
            50,
            legal(can_fold=True, can_call=True, call_amount=25, can_raise=True, min_target=50, max_target=50),
            id="whole-stack-reaches-minimum-raise",
        ),
        pytest.param(49, legal(can_fold=True, can_call=True, call_amount=25), id="stack-below-minimum-raise"),
        pytest.param(20, legal(can_fold=True, call_amount=25), id="call-above-stack"),
    ],
)
def test_stack_limits_raise_and_call(small_blind_chips: int, expected: LegalActions) -> None:
    """A raise needs the whole stack to reach the minimum target and a call needs the stack to cover it;
    short all-in raises and calls are not legal in Milestone 2."""
    assert legal_actions(facing_raise_to_30(small_blind_chips)) == expected


# =============================================================================
# NO OPPONENT CAN RESPOND
# =============================================================================


def big_blind_all_in_heads_up() -> PokerHand:
    return started_hand({3: 10, 7: 1000}, button_seat_number=7)


def big_blind_all_in_after_button_folds() -> PokerHand:
    hand = started_hand({1: 1000, 2: 1000, 3: 10}, button_seat_number=1)
    by_seat(hand)[1].folded = True
    to_act(hand, 2, pending={2})
    return hand


@pytest.mark.parametrize(
    "make",
    [
        pytest.param(big_blind_all_in_heads_up, id="heads-up"),
        pytest.param(big_blind_all_in_after_button_folds, id="three-handed-button-folded"),
    ],
)
def test_no_bet_or_raise_when_every_other_live_player_is_all_in(make: Callable[[], PokerHand]) -> None:
    """When every other non-folded player is all-in, the small blind can only fold or call the outstanding chips."""
    assert legal_actions(make()) == legal(can_fold=True, can_call=True, call_amount=5)


# =============================================================================
# NOBODY TO ACT
# =============================================================================


def test_nothing_is_legal_when_nobody_is_to_act() -> None:
    """A round that is complete has no current actor, so no action is legal."""
    hand = started_hand({3: 1000, 7: 5}, button_seat_number=7)
    assert betting(hand).current_actor is None
    assert legal_actions(hand) == legal()


def test_legal_actions_need_initialized_betting() -> None:
    """A hand whose betting was never initialized has no legal actions to derive."""
    with pytest.raises(BettingNotInitializedError):
        legal_actions(make_hand({3: 1000, 7: 1000}, button_seat_number=7))

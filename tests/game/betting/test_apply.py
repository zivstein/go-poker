from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, NotPlayersTurnError, apply_action
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.rounds import is_round_complete, start_betting_round
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type BettingLookup = Callable[[PokerHand], BettingState]
type HandSnapshotter = Callable[[PokerHand], object]
type PlayerSnapshotter = Callable[[PokerHand], dict[int, tuple[int, int, int, bool, bool]]]
type Play = Callable[..., None]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


FOUR_HANDED = {5: 1000, 8: 1000, 1: 1000, 3: 1000}  # button 5, SB 8, BB 1, UTG 3


# =============================================================================
# REJECTED ACTIONS
# =============================================================================


@pytest.mark.parametrize(
    "stacks, button_seat_number, seat_number",
    [
        pytest.param(FOUR_HANDED, 5, 5, id="not-the-current-actor"),
        pytest.param({3: 1000, 7: 5}, 7, 3, id="round-already-complete"),
    ],
)
def test_action_out_of_turn_is_rejected_without_changes(
    stacks: dict[int, int],
    button_seat_number: int,
    seat_number: int,
    started_hand: HandFactory,
    hand_snapshot: HandSnapshotter,
) -> None:
    """Only the current actor may act; once a round is complete nobody may."""
    hand = started_hand(stacks, button_seat_number=button_seat_number)
    before = hand_snapshot(hand)

    with pytest.raises(NotPlayersTurnError):
        apply_action(hand, seat_number, CALL)

    assert hand_snapshot(hand) == before


@pytest.mark.parametrize(
    "action",
    [
        pytest.param(CHECK, id="check-facing-a-bet"),
        pytest.param(bet(20), id="bet-when-a-bet-exists"),
        pytest.param(raise_to(19), id="raise-below-minimum"),
        pytest.param(raise_to(1001), id="raise-above-stack"),
    ],
)
def test_illegal_action_is_rejected_without_changes(
    action: Action, started_hand: HandFactory, hand_snapshot: HandSnapshotter
) -> None:
    """UTG facing the big blind may only fold, call, or raise to between 20 and 1000."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    before = hand_snapshot(hand)

    with pytest.raises(IllegalActionError):
        apply_action(hand, 3, action)

    assert hand_snapshot(hand) == before


@pytest.mark.parametrize(
    "actions_first, seat_number, action, error",
    [
        pytest.param([], 5, raise_to(15), NotPlayersTurnError, id="short-all-in-out-of-turn"),
        pytest.param([(3, CALL)], 5, raise_to(14), IllegalActionError, id="below-minimum-and-not-the-all-in-target"),
        pytest.param([(3, CALL)], 5, raise_to(16), IllegalActionError, id="above-the-all-in-target"),
        pytest.param(
            [(3, CALL), (5, raise_to(15)), (8, CALL), (1, CALL)],
            3,
            raise_to(25),
            IllegalActionError,
            id="raise-without-raise-rights-after-a-short-all-in",
        ),
    ],
)
def test_illegal_short_all_in_action_is_rejected_without_changes(
    actions_first: list[tuple[int, Action]],
    seat_number: int,
    action: Action,
    error: type[Exception],
    started_hand: HandFactory,
    hand_snapshot: HandSnapshotter,
    play: Play,
) -> None:
    """The button has 15 chips, so its only raise is the short all-in to 15. Its all-in is rejected before its turn,
    any other target is rejected, and UTG, who limped at 10 and faces only 5 more after it, may not raise."""
    hand = started_hand({**FOUR_HANDED, 5: 15}, button_seat_number=5)
    play(hand, *actions_first)
    before = hand_snapshot(hand)

    with pytest.raises(error):
        apply_action(hand, seat_number, action)

    assert hand_snapshot(hand) == before


def test_action_needs_initialized_betting(make_hand: HandFactory) -> None:
    """A hand whose betting was never initialized cannot take actions."""
    with pytest.raises(BettingNotInitializedError):
        apply_action(make_hand(FOUR_HANDED, button_seat_number=5), 3, CALL)


# =============================================================================
# FOLD, CHECK, CALL
# =============================================================================


def test_fold_removes_the_player_and_passes_action_clockwise_around_the_table(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup
) -> None:
    """UTG, the last seat from the button, folds without moving chips; the action wraps to the button."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    apply_action(hand, 3, FOLD)

    utg = by_seat(hand)[3]
    assert (utg.folded, utg.player.stack, utg.total_contribution) == (True, 1000, 0)
    assert betting(hand).pending_actors == {5, 8, 1}
    assert betting(hand).current_actor == 5


def test_call_commits_the_call_amount_and_passes_action(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """The small blind's call adds only what it still owes; the big blind then has its option."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    play(hand, (3, CALL), (5, CALL), (8, CALL))

    small_blind = by_seat(hand)[8]
    assert (small_blind.player.stack, small_blind.street_contribution, small_blind.total_contribution) == (990, 10, 10)
    assert betting(hand).pending_actors == {1}
    assert betting(hand).current_actor == 1


def test_big_blind_check_after_everyone_calls_completes_the_round(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """Preflop called around, the big blind's check leaves nobody pending: the round is complete."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    play(hand, (3, CALL), (5, CALL), (8, CALL), (1, CHECK))

    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()
    assert is_round_complete(betting(hand))
    assert betting(hand).current_bet == 10


# =============================================================================
# BET AND RAISE
# =============================================================================


def test_raises_add_target_minus_contribution_and_set_the_next_minimum(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """A raise target is the street contribution after the action. UTG raises 10 -> 30 (a raise of 20); the small
    blind, with 5 in, re-raises to 80 by adding 75 (a raise of 50), so the next minimum raise is to 130."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    seats = by_seat(hand)

    apply_action(hand, 3, raise_to(30))
    assert (seats[3].player.stack, seats[3].street_contribution) == (970, 30)
    assert (betting(hand).current_bet, betting(hand).last_full_raise_size) == (30, 20)
    assert betting(hand).pending_actors == {5, 8, 1}
    assert legal_actions(hand).min_full_target == 50

    play(hand, (5, FOLD), (8, raise_to(80)))
    assert (seats[8].player.stack, seats[8].street_contribution, seats[8].total_contribution) == (920, 80, 80)
    assert (betting(hand).current_bet, betting(hand).last_full_raise_size) == (80, 50)
    assert betting(hand).pending_actors == {1, 3}
    assert betting(hand).current_actor == 1
    assert legal_actions(hand).min_full_target == 130


def test_bet_after_checks_reopens_action(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """On the flop, the small blind and big blind check and the button bets 25: both owe an action again."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)

    play(hand, (2, CHECK), (3, CHECK), (1, bet(25)))

    assert (betting(hand).current_bet, betting(hand).last_full_raise_size) == (25, 25)
    assert by_seat(hand)[1].player.stack == 965
    assert betting(hand).pending_actors == {2, 3}
    assert betting(hand).current_actor == 2


@pytest.mark.parametrize(
    "utg_chips, action",
    [
        pytest.param(300, raise_to(300), id="raise-with-whole-stack"),
        pytest.param(10, CALL, id="call-with-whole-stack"),
    ],
)
def test_full_action_with_whole_stack_puts_player_all_in(
    utg_chips: int, action: Action, started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup
) -> None:
    """A full call or raise that uses the whole stack marks the player all-in, and they are never pending again,
    even when a later raise reopens the action."""
    hand = started_hand({**FOUR_HANDED, 3: utg_chips}, button_seat_number=5)
    apply_action(hand, 3, action)

    utg = by_seat(hand)[3]
    assert (utg.player.stack, utg.total_contribution, utg.all_in) == (0, utg_chips, True)
    assert betting(hand).pending_actors == {5, 8, 1}
    assert betting(hand).current_actor == 5

    # A re-raise makes every other eligible player owe a response again, but never the all-in player.
    min_reraise = legal_actions(hand).min_full_target
    assert min_reraise is not None
    apply_action(hand, 5, raise_to(min_reraise))
    assert betting(hand).pending_actors == {8, 1}


# =============================================================================
# SHORT ALL-INS
# =============================================================================


def test_short_call_commits_the_whole_stack_and_leaves_the_current_bet(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """UTG raises to 30 and the button folds. The small blind, with 5 in and 15 behind, owes 25 and calls all-in for
    its last 15: it stays below the current bet, which keeps its value, and owes no further action."""
    hand = started_hand({**FOUR_HANDED, 8: 20}, button_seat_number=5)
    play(hand, (3, raise_to(30)), (5, FOLD), (8, CALL))

    small_blind = by_seat(hand)[8]
    assert (small_blind.player.stack, small_blind.street_contribution, small_blind.total_contribution) == (0, 20, 20)
    assert small_blind.all_in is True
    assert (betting(hand).current_bet, betting(hand).last_full_raise_size) == (30, 20)
    assert betting(hand).pending_actors == {1}
    assert betting(hand).current_actor == 1


def test_short_opening_bet_keeps_the_last_full_raise_size(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """On the flop the small blind checks and the big blind bets all-in for its last 6, below the full bet of 10. The
    current bet becomes 6 but the last full raise size stays 10, so the next minimum raise is to 16, and both other
    players owe a response."""
    hand = started_hand({1: 1000, 2: 1000, 3: 16}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    play(hand, (2, CHECK), (3, bet(6)))

    big_blind = by_seat(hand)[3]
    assert (big_blind.player.stack, big_blind.street_contribution, big_blind.all_in) == (0, 6, True)
    assert (betting(hand).current_bet, betting(hand).last_full_raise_size) == (6, 10)
    assert betting(hand).pending_actors == {1, 2}
    assert betting(hand).current_actor == 1
    assert legal_actions(hand).min_full_target == 16


def test_short_raise_keeps_the_last_full_raise_size(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup
) -> None:
    """UTG raises all-in to its 15 chips, below the minimum raise to 20. The current bet becomes 15 but the last full
    raise size stays 10, so the next minimum raise is to 25, and every other player owes a response."""
    hand = started_hand({**FOUR_HANDED, 3: 15}, button_seat_number=5)
    apply_action(hand, 3, raise_to(15))

    utg = by_seat(hand)[3]
    assert (utg.player.stack, utg.street_contribution, utg.all_in) == (0, 15, True)
    assert (betting(hand).current_bet, betting(hand).last_full_raise_size) == (15, 10)
    assert betting(hand).pending_actors == {5, 8, 1}
    assert betting(hand).current_actor == 5
    assert legal_actions(hand).min_full_target == 25


# =============================================================================
# ACTED-AT BETS
# =============================================================================


def test_call_raise_and_fold_record_the_current_bet_right_after_them(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """A call or fold records the bet it faced and a raise its new bet. The blinds' posts are not actions, so they
    have no entry until they act, and a player's latest action replaces their earlier entry."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)

    play(hand, (3, CALL), (5, raise_to(30)), (8, FOLD))
    assert betting(hand).acted_at_bet == {3: 10, 5: 30, 8: 30}

    play(hand, (1, CALL), (3, CALL))
    assert betting(hand).acted_at_bet == {3: 30, 5: 30, 8: 30, 1: 30}


def test_checks_and_a_bet_record_the_current_bet_right_after_them(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """A check is an action: the big blind's option check records the big blind, and the flop checks record the
    unopened bet of 0. The flop bet records its target."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    assert betting(hand).acted_at_bet == {1: 10, 2: 10, 3: 10}

    deal_next_street(hand)
    start_betting_round(hand)
    play(hand, (2, CHECK), (3, CHECK), (1, bet(25)))
    assert betting(hand).acted_at_bet == {2: 0, 3: 0, 1: 25}


# =============================================================================
# EARLY ROUND ENDINGS
# =============================================================================


def test_everyone_else_folding_ends_the_round_and_returns_the_uncalled_chips_without_awarding_any(
    started_hand: HandFactory, player_snapshot: PlayerSnapshotter, betting: BettingLookup, play: Play
) -> None:
    """When the button and small blind fold, the big blind is the only player left: nobody acts, and the round is
    collected. The big blind's 5 above the small blind are uncalled and go back to its stack; the other 10 are
    collected into the middle and not awarded to anyone (payout belongs to settlement)."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    play(hand, (1, FOLD), (2, FOLD))

    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()
    assert player_snapshot(hand) == {
        1: (1000, 0, 0, True, False),  # button
        2: (995, 0, 5, True, False),  # small blind
        3: (995, 0, 5, False, False),  # big blind
    }


def test_player_owing_chips_to_all_in_opponents_must_call_or_fold_then_round_completes(
    started_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, play: Play
) -> None:
    """The button raises all-in and the small blind folds: the big blind can only fold or call, and calling closes
    the round."""
    hand = started_hand({1: 1000, 2: 1000, 3: 2000}, button_seat_number=1)
    play(hand, (1, raise_to(1000)), (2, FOLD))

    assert betting(hand).pending_actors == {3}
    legal = legal_actions(hand)
    assert (legal.can_call, legal.call_amount, legal.can_raise) == (True, 990, False)

    apply_action(hand, 3, CALL)
    assert by_seat(hand)[3].player.stack == 1000
    assert betting(hand).current_actor is None
    assert is_round_complete(betting(hand))


def test_round_completes_automatically_when_nobody_can_respond_and_nothing_is_owed(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """The button calls all-in and the small blind folds: the big blind owes nothing and nobody could respond to a
    bet, so the round completes without a check."""
    hand = started_hand({1: 10, 2: 1000, 3: 1000}, button_seat_number=1)
    play(hand, (1, CALL), (2, FOLD))

    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()

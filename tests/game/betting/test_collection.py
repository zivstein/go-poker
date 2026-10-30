from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import IllegalActionError, apply_action
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand

# The end-of-round collection runs inside the betting operation that completes a round, so it is driven through real
# actions here, at the conftest blinds of 5/10.

type HandFactory = Callable[..., PokerHand]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type HandSnapshotter = Callable[[PokerHand], object]
type PlayerSnapshotter = Callable[[PokerHand], dict[int, tuple[int, int, int, bool, bool]]]
type Play = Callable[..., None]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


FOUR_HANDED = {5: 1000, 8: 1000, 1: 1000, 3: 1000}  # button 5, SB 8, BB 1, UTG 3


def test_sole_top_contributor_gets_back_only_what_nobody_else_matched(
    started_hand: HandFactory, player_snapshot: PlayerSnapshotter, play: Play
) -> None:
    """UTG raises to 40 and the button calls all-in for its last 25. The small blind re-raises to 100, the big blind
    folds, UTG raises to 250 and the small blind folds, which completes the round. UTG alone has the highest total
    contribution, and the next highest is the small blind's folded 100, so UTG gets its 150 above that back: folded
    contributions count as matched, and the button's smaller all-in does not lower that threshold. Every player's
    chips in front, folded players' included, are then collected, keeping the normalized totals."""
    hand = started_hand({**FOUR_HANDED, 5: 25}, button_seat_number=5)
    play(hand, (3, raise_to(40)), (5, CALL), (8, raise_to(100)), (1, FOLD), (3, raise_to(250)), (8, FOLD))

    assert player_snapshot(hand) == {
        5: (0, 0, 25, False, True),  # button
        8: (900, 0, 100, True, False),  # small blind
        1: (990, 0, 10, True, False),  # big blind
        3: (900, 0, 100, False, False),  # UTG
    }


def test_matched_top_contribution_returns_nothing_and_collects_every_player_s_chips_in_front(
    started_hand: HandFactory, player_snapshot: PlayerSnapshotter, play: Play
) -> None:
    """UTG raises to 30, the button calls and both blinds fold. Two players share the highest total contribution, so
    nothing is unmatched and nothing is returned; every chip in front, the folded blinds' included, is collected."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    play(hand, (3, raise_to(30)), (5, CALL), (8, FOLD), (1, FOLD))

    assert player_snapshot(hand) == {
        5: (970, 0, 30, False, False),  # button
        8: (995, 0, 5, True, False),  # small blind
        1: (990, 0, 10, True, False),  # big blind
        3: (970, 0, 30, False, False),  # UTG
    }


def test_rejected_action_by_the_last_pending_player_neither_returns_nor_collects_chips(
    started_hand: HandFactory, by_seat: SeatLookup, hand_snapshot: HandSnapshotter, play: Play
) -> None:
    """UTG raises to 30 and the button and small blind fold. The big blind is the last player owed an action, and
    checking would have completed the round and returned UTG's uncalled 20. The check is illegal, so it is rejected
    and changes nothing: nothing is returned and every chip stays in front."""
    hand = started_hand(FOUR_HANDED, button_seat_number=5)
    play(hand, (3, raise_to(30)), (5, FOLD), (8, FOLD))
    before = hand_snapshot(hand)

    with pytest.raises(IllegalActionError):
        apply_action(hand, 1, CHECK)

    assert hand_snapshot(hand) == before
    assert {seat: hp.street_contribution for seat, hp in by_seat(hand).items()} == {5: 0, 8: 5, 1: 10, 3: 30}

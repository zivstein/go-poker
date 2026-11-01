"""Adversarial QA for Hold'em derived hand strength.

These cases target selection and lookup mistakes the Engineer's literal and seeded tests cannot tell apart:

- equal-rank selection where the hole cards' own order interacts with the board's (a hole card the same rank as an
  earlier board card must lose to it even when the other hole card is also in the five);
- a seat looked up by seat number in a hand whose seats are neither contiguous nor start at 1;
- river strength read for every seat (shown, mucked and folded) after an all-in runout and after an interactive
  showdown with a muck, compared with `evaluate_best` and the settlement rank.
"""

from collections.abc import Callable

import pytest

from go_poker.core.card import Card
from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandCategory
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.hand_strength import SeatNotInHandError, hand_strength, holdem_hand_strength

type Cards = Callable[[str], list[Card]]

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def check_or_call(hand: PokerHand, seat: int) -> None:
    act(hand, seat, CHECK if legal_actions(hand).can_check else CALL)


@pytest.mark.parametrize(
    "hole, board, expected",
    [
        pytest.param("9d 8s", "9c 7h 6d 5c 2s", "9c 8s 7h 6d 5c", id="second-hole-card-needed-board-nine-wins"),
        pytest.param("8s 9d", "9c 7h 6d 5c 2s", "9c 8s 7h 6d 5c", id="hole-cards-dealt-the-other-way"),
        pytest.param("9d 5d", "9c 8h 7s 6d 5c", "9c 8h 7s 6d 5c", id="both-hole-cards-duplicate-board-ranks"),
        pytest.param("8s 9d", "5c 6d 7h 9c 9s", "9c 8s 7h 6d 5c", id="nine-on-the-board-twice-and-in-the-hole"),
        pytest.param("8s 9d", "5c 6d 7h 9s", "9s 8s 7h 6d 5c", id="the-turn-nine-beats-the-hole-nine"),
        pytest.param("9d 5d", "9c 8h 7s 6h 2c", "9c 8h 7s 6h 5d", id="only-the-needed-hole-card-is-used"),
        pytest.param("Kd Qd", "Kc Ks Qc Qs 2h", "Kc Ks Kd Qc Qs", id="full-house-with-two-trips-keeps-the-board-pair"),
        pytest.param("Kd Kh", "7c 7d 7h 7s 2c", "7c 7d 7h 7s Kd", id="board-quads-take-the-first-dealt-hole-kicker"),
        pytest.param("Kh Kd", "7c 7d 7h 7s 2c", "7c 7d 7h 7s Kh", id="board-quads-take-the-first-dealt-hole-kicker-b"),
        pytest.param("Kd Kh", "7c 7d 7h 7s Ac", "7c 7d 7h 7s Ac", id="a-higher-board-kicker-means-the-board-plays"),
    ],
)
def test_equal_rank_selection(cards: Cards, hole: str, board: str, expected: str) -> None:
    best = holdem_hand_strength(cards(hole), cards(board))
    assert best is not None
    assert list(best.cards) == cards(expected)


@pytest.mark.parametrize("button", [2, 5, 8])
def test_seats_are_looked_up_by_seat_number_not_by_index(
    stacked_hand: Callable[..., PokerHand], cards: Cards, button: int
) -> None:
    holes = {2: "Ah Ad", 5: "Kd Kh", 8: "3s 4s"}
    hand = stacked_hand(holes, "2c 7d 9h Jc Ks", button=button)
    begin_hand(hand, STAKES)
    while hand.street is not Street.RIVER:
        seat = current_actor(hand)
        assert seat is not None
        check_or_call(hand, seat)

    expected = {2: "Pair of Aces", 5: "Three of a kind, Kings", 8: "King high"}
    for seat, text in expected.items():
        best = hand_strength(hand, seat)
        assert best is not None and best.description == text
        assert best.rank == evaluate_best([*cards(holes[seat]), *hand.board])
    for unknown in (0, 1, 3, 4, 6, 7, 9):
        with pytest.raises(SeatNotInHandError):
            hand_strength(hand, unknown)


def _assert_every_seat_matches(hand: PokerHand, expected_cards: dict[int, str], cards: Cards) -> None:
    """Every participant's river strength is the `evaluate_best` rank of its own hole cards and the board, whether it
    was shown, mucked or folded, and each shown seat's strength is its settlement rank."""
    assert hand.settlement is not None
    shown = dict(hand.settlement.showdown_ranks)
    for state in hand.players:
        best = hand_strength(hand, state.seat_number)
        assert best is not None
        assert best.rank == evaluate_best([*state.hole_cards, *hand.board])
        if state.seat_number in shown:
            assert best.rank == shown[state.seat_number]
        if state.seat_number in expected_cards:
            assert list(best.cards) == cards(expected_cards[state.seat_number])


def test_an_all_in_runout_on_a_royal_board_reads_the_board_for_every_seat(
    stacked_hand: Callable[..., PokerHand], cards: Cards
) -> None:
    """The board is a royal flush: every seat plays the board (even the one holding an ace), ranks tie, and the strength
    of every seat, folded or not, is the settlement rank."""
    holes = {1: "2c 3d", 2: "Ah Kd", 3: "9c 8d", 4: "Qd Jd"}
    hand = stacked_hand(holes, "Ts Js Qs Ks As")
    begin_hand(hand, STAKES)
    act(hand, 4, Action(ActionType.RAISE, 1000))
    act(hand, 1, FOLD)
    act(hand, 2, CALL)
    act(hand, 3, CALL)

    assert hand.settlement is not None
    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.ALL_IN
    assert [seat for seat, _ in hand.settlement.showdown_ranks] == [2, 3, 4]
    royal = "As Ks Qs Js Ts"
    _assert_every_seat_matches(hand, dict.fromkeys(holes, royal), cards)
    best = hand_strength(hand, 1)  # the folded seat
    assert best is not None and best.description == "Royal flush"
    assert best.rank.category is HandCategory.STRAIGHT_FLUSH


def test_an_interactive_showdown_with_a_muck_reads_every_seat(
    stacked_hand: Callable[..., PokerHand], cards: Cards
) -> None:
    holes = {1: "9d 2s", 2: "Ts 3c", 3: "2d 3s"}
    hand = stacked_hand(holes, "5c 6d 7h 8s 9c")
    begin_hand(hand, STAKES)
    while hand.showdown is None:
        seat = current_actor(hand)
        assert seat is not None
        check_or_call(hand, seat)
    assert hand.showdown.kind is ShowdownKind.INTERACTIVE
    while hand.settlement is None:
        seat = current_actor(hand)
        assert seat is not None
        act(hand, seat, ShowdownAction.MUCK if seat == 3 else ShowdownAction.SHOW)

    assert hand.showdown.mucked == (3,)
    _assert_every_seat_matches(hand, {1: "9c 8s 7h 6d 5c", 2: "Ts 9c 8s 7h 6d", 3: "9c 8s 7h 6d 5c"}, cards)

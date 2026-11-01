from collections.abc import Callable

import pytest

import go_poker.game.variants.texas_holdem.showdown as showdown_module
from go_poker.core.card import Card
from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import (
    InvalidHoleCardCountError,
    deal_hole_cards,
    deal_next_street,
)
from go_poker.game.variants.texas_holdem.showdown import IncompleteBoardError, _showdown_ranks

# `_showdown_ranks` is the internal helper settle_hand uses to rank the shown seats; the public read is `hand_strength`.
# Hands are dealt through the real dealing operations from a deck stacked by the shared `stacked_hand` fixture.

ALL_SEATS = {1, 2, 3}
STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)


def seat_state(hand: PokerHand, seat: int) -> HandPlayerState:
    return next(state for state in hand.players if state.seat_number == seat)


@pytest.fixture
def hand_with(
    stacked_hand: Callable[..., PokerHand], deal_to: Callable[[PokerHand, Street], None]
) -> Callable[..., PokerHand]:
    """A river hand where seat 1 holds a pair of aces, seat 2 a set of kings and seat 3 nothing on the board."""

    def build(board: str = "2c 7d 9h Jc Ks") -> PokerHand:
        hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, board)
        deal_to(hand, Street.RIVER)
        return hand

    return build


def fold_button(hand: PokerHand) -> None:
    """Seat 1 (the button) acts first preflop; fold it through the real betting operations."""
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, FOLD)


def table_state(hand: PokerHand) -> tuple[Street, list[Card], list[Card], dict[int, list[Card]], int]:
    return (
        hand.street,
        list(hand.board),
        list(hand.burned_cards),
        {state.seat_number: list(state.hole_cards) for state in hand.players},
        len(hand.deck),
    )


# =============================================================================
# HAND STRENGTH
# =============================================================================


def test_hole_cards_improve_on_the_board(hand_with: Callable[..., PokerHand]) -> None:
    """Each live player's rank is their best five of two hole cards and the five board cards, keyed by seat."""
    hand = hand_with()

    assert _showdown_ranks(hand, ALL_SEATS) == {
        1: HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9)),
        2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9)),
        3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
    }
    assert list(_showdown_ranks(hand, ALL_SEATS)) == [1, 2, 3]


def test_the_board_plays_when_no_hole_card_improves_it(
    stacked_hand: Callable[..., PokerHand], deal_to: Callable[[PokerHand, Street], None]
) -> None:
    """A royal flush on the board is every player's best five, so the ranks are equal (suits never separate them)."""
    hand = stacked_hand({1: "2c 3d", 2: "4h 5c", 3: "6d 7h"}, "As Ks Qs Js Ts")
    deal_to(hand, Street.RIVER)

    royal_flush = HandRank(HandCategory.STRAIGHT_FLUSH, (14,))
    assert _showdown_ranks(hand, ALL_SEATS) == {1: royal_flush, 2: royal_flush, 3: royal_flush}


def test_different_hole_cards_of_different_suits_that_play_equally_rank_equal(
    stacked_hand: Callable[..., PokerHand], deal_to: Callable[[PokerHand, Street], None]
) -> None:
    """Both players play the board's top cards with the same hole-card ranks in other suits, so the ranks are equal and
    a better kicker (seat 3's ace) is not."""
    hand = stacked_hand({1: "Qh Jd", 2: "Qs Jc", 3: "Ah 2d"}, "Kc 9d 7h 4s 3c")
    deal_to(hand, Street.RIVER)

    ranks = _showdown_ranks(hand, ALL_SEATS)

    assert ranks[1] == ranks[2] == HandRank(HandCategory.HIGH_CARD, (13, 12, 11, 9, 7))
    assert ranks[3] > ranks[1]


def test_ranks_are_keyed_in_hand_order_from_the_button(
    stacked_hand: Callable[..., PokerHand], deal_to: Callable[[PokerHand, Street], None]
) -> None:
    """With the button at seat 2 the hand's seats run 2, 3, 1; the ranks follow that order, not the seat numbers."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks", button=2)
    deal_to(hand, Street.RIVER)

    assert list(_showdown_ranks(hand, ALL_SEATS)) == [2, 3, 1]


def test_a_folded_player_left_out_of_the_supplied_seats_is_not_ranked(
    stacked_hand: Callable[..., PokerHand],
) -> None:
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    fold_button(hand)
    while hand.street is not Street.RIVER:
        deal_next_street(hand)

    assert _showdown_ranks(hand, {2, 3}) == {
        2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9)),
        3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
    }


def test_only_the_supplied_seats_are_ranked_even_when_every_seat_is_live(hand_with: Callable[..., PokerHand]) -> None:
    """Which seats to rank is the caller's decision: a live seat that is not supplied (a mucked or unshown one) is
    absent, and the supplied seats keep hand order."""
    hand = hand_with()

    assert _showdown_ranks(hand, {3, 1}) == {
        1: HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9)),
        3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
    }
    assert _showdown_ranks(hand, {2}) == {2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9))}
    assert _showdown_ranks(hand, set()) == {}


def test_only_the_supplied_seats_are_evaluated(
    hand_with: Callable[..., PokerHand], monkeypatch: pytest.MonkeyPatch
) -> None:
    hand = hand_with()
    evaluated: list[list[Card]] = []

    def spy(seven_cards: list[Card]) -> HandRank:
        evaluated.append(list(seven_cards))
        return evaluate_best(seven_cards)

    monkeypatch.setattr(showdown_module, "evaluate_best", spy)

    _showdown_ranks(hand, {2})

    assert evaluated == [[*seat_state(hand, 2).hole_cards, *hand.board]]


def test_ranking_does_not_change_the_hand(hand_with: Callable[..., PokerHand]) -> None:
    hand = hand_with()
    before = table_state(hand)

    _showdown_ranks(hand, ALL_SEATS)

    assert table_state(hand) == before


# =============================================================================
# VALIDATION
# =============================================================================


@pytest.mark.parametrize("street", [Street.PREFLOP, Street.FLOP, Street.TURN])
def test_an_incomplete_board_is_rejected(
    stacked_hand: Callable[..., PokerHand], deal_to: Callable[[PokerHand, Street], None], street: Street
) -> None:
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    deal_to(hand, street)
    before = table_state(hand)

    with pytest.raises(IncompleteBoardError):
        _showdown_ranks(hand, ALL_SEATS)

    assert table_state(hand) == before


@pytest.mark.parametrize("extra", [False, True], ids=["one-hole-card", "three-hole-cards"])
def test_a_live_player_without_exactly_two_hole_cards_is_rejected(
    hand_with: Callable[..., PokerHand], cards: Callable[[str], list[Card]], extra: bool
) -> None:
    hand = hand_with()
    if extra:
        seat_state(hand, 3).hole_cards.append(cards("Qd")[0])
    else:
        seat_state(hand, 3).hole_cards.pop()
    before = table_state(hand)

    with pytest.raises(InvalidHoleCardCountError):
        _showdown_ranks(hand, ALL_SEATS)

    assert table_state(hand) == before


def test_a_seat_that_is_not_supplied_is_not_validated_even_with_the_wrong_hole_card_count(
    stacked_hand: Callable[..., PokerHand],
) -> None:
    """Only the supplied seats' hole cards are checked, whether the unsupplied seat folded or not."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    fold_button(hand)
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    seat_state(hand, 1).hole_cards.pop()

    assert list(_showdown_ranks(hand, {2, 3})) == [2, 3]
    with pytest.raises(InvalidHoleCardCountError):
        _showdown_ranks(hand, ALL_SEATS)


def test_the_board_is_checked_even_when_no_seat_is_supplied(
    stacked_hand: Callable[..., PokerHand], deal_to: Callable[[PokerHand, Street], None]
) -> None:
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    deal_to(hand, Street.TURN)

    with pytest.raises(IncompleteBoardError):
        _showdown_ranks(hand, set())

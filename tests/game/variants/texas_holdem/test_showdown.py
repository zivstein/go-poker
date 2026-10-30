from collections.abc import MutableSequence
from random import Random
from typing import Any

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import (
    HOLE_CARD_COUNT,
    InvalidHoleCardCountError,
    deal_hole_cards,
    deal_next_street,
)
from go_poker.game.variants.texas_holdem.showdown import IncompleteBoardError, showdown_ranks

# Hands are dealt through the real dealing operations from a deck stacked with the test-local rng below, which uses the
# existing Deck.shuffle seam.

SEATS = (1, 2, 3)
BUTTON = 1
STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)

_RANKS = {str(rank): rank for rank in Rank if rank <= 10} | {
    "T": Rank.TEN,
    "J": Rank.JACK,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
    "A": Rank.ACE,
}
_SUITS = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}


def cards(text: str) -> list[Card]:
    """Parse cards such as "As Td 9c" (rank, then suit)."""
    return [Card(_RANKS[token[0]], _SUITS[token[1]]) for token in text.split()]


class StackedRandom(Random):
    """A shuffle that puts the given cards on top of the deck, so they are drawn first, in this order."""

    def __init__(self, draw_order: list[Card]) -> None:
        super().__init__()
        self._draw_order = draw_order

    def shuffle(self, x: MutableSequence[Any]) -> None:
        rest = [card for card in x if card not in self._draw_order]
        # draw() pops from the end, so the first card to draw goes last.
        x[:] = rest + list(reversed(self._draw_order))


def stacked_hand(holes: dict[int, str], board: str, button: int = BUTTON) -> PokerHand:
    """A three-handed hand (button seat 1 unless given) whose hole cards and board are the given ones once dealt.

    The hole cards are dealt one per player per round starting left of the button; each street burns one card first,
    which here are cards nobody else uses.
    """
    hole_cards = {seat: cards(text) for seat, text in holes.items()}
    board_cards = cards(board)
    assignments = assign_hand_seats(SEATS, button)
    clockwise = list(assignments)  # button first
    deal_order = (*clockwise[1:], clockwise[0])
    used = [card for seat_cards in hole_cards.values() for card in seat_cards] + board_cards
    burns = iter(card for card in Deck.create_new_deck() if card not in used)

    draw_order = [hole_cards[seat][round_index] for round_index in range(HOLE_CARD_COUNT) for seat in deal_order]
    draw_order += [next(burns), *board_cards[:3], next(burns), board_cards[3], next(burns), board_cards[4]]

    deck = Deck()
    deck.shuffle(_rng=StackedRandom(draw_order))
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat}", stack=1000, status=PlayerStatus.READY),
            seat_number=seat,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=deck)


def deal_to(hand: PokerHand, street: Street) -> None:
    deal_hole_cards(hand)
    while hand.street is not street:
        deal_next_street(hand)


def seat_state(hand: PokerHand, seat: int) -> HandPlayerState:
    return next(state for state in hand.players if state.seat_number == seat)


def hand_with(board: str = "2c 7d 9h Jc Ks") -> PokerHand:
    """A river hand where seat 1 holds a pair of aces, seat 2 a set of kings and seat 3 nothing on the board."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, board)
    deal_to(hand, Street.RIVER)
    return hand


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


def test_hole_cards_improve_on_the_board() -> None:
    """Each live player's rank is their best five of two hole cards and the five board cards, keyed by seat."""
    hand = hand_with()

    assert showdown_ranks(hand) == {
        1: HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9)),
        2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9)),
        3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
    }
    assert list(showdown_ranks(hand)) == [1, 2, 3]


def test_the_board_plays_when_no_hole_card_improves_it() -> None:
    """A royal flush on the board is every player's best five, so the ranks are equal (suits never separate them)."""
    hand = stacked_hand({1: "2c 3d", 2: "4h 5c", 3: "6d 7h"}, "As Ks Qs Js Ts")
    deal_to(hand, Street.RIVER)

    royal_flush = HandRank(HandCategory.STRAIGHT_FLUSH, (14,))
    assert showdown_ranks(hand) == {1: royal_flush, 2: royal_flush, 3: royal_flush}


def test_different_hole_cards_of_different_suits_that_play_equally_rank_equal() -> None:
    """Both players play the board's top cards with the same hole-card ranks in other suits, so the ranks are equal and
    a better kicker (seat 3's ace) is not."""
    hand = stacked_hand({1: "Qh Jd", 2: "Qs Jc", 3: "Ah 2d"}, "Kc 9d 7h 4s 3c")
    deal_to(hand, Street.RIVER)

    ranks = showdown_ranks(hand)

    assert ranks[1] == ranks[2] == HandRank(HandCategory.HIGH_CARD, (13, 12, 11, 9, 7))
    assert ranks[3] > ranks[1]


def test_ranks_are_keyed_in_hand_order_from_the_button() -> None:
    """With the button at seat 2 the hand's seats run 2, 3, 1; the ranks follow that order, not the seat numbers."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks", button=2)
    deal_to(hand, Street.RIVER)

    assert list(showdown_ranks(hand)) == [2, 3, 1]


def test_a_folded_player_is_excluded() -> None:
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    fold_button(hand)
    while hand.street is not Street.RIVER:
        deal_next_street(hand)

    assert showdown_ranks(hand) == {
        2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9)),
        3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
    }


def test_showdown_ranks_does_not_change_the_hand() -> None:
    hand = hand_with()
    before = table_state(hand)

    showdown_ranks(hand)

    assert table_state(hand) == before


# =============================================================================
# VALIDATION
# =============================================================================


@pytest.mark.parametrize("street", [Street.PREFLOP, Street.FLOP, Street.TURN])
def test_an_incomplete_board_is_rejected(street: Street) -> None:
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    deal_to(hand, street)
    before = table_state(hand)

    with pytest.raises(IncompleteBoardError):
        showdown_ranks(hand)

    assert table_state(hand) == before


@pytest.mark.parametrize("extra", [False, True], ids=["one-hole-card", "three-hole-cards"])
def test_a_live_player_without_exactly_two_hole_cards_is_rejected(extra: bool) -> None:
    hand = hand_with()
    if extra:
        seat_state(hand, 3).hole_cards.append(cards("Qd")[0])
    else:
        seat_state(hand, 3).hole_cards.pop()
    before = table_state(hand)

    with pytest.raises(InvalidHoleCardCountError):
        showdown_ranks(hand)

    assert table_state(hand) == before


def test_a_folded_player_with_the_wrong_hole_card_count_is_not_rejected() -> None:
    """Only live players are validated and evaluated."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}, "2c 7d 9h Jc Ks")
    fold_button(hand)
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    seat_state(hand, 1).hole_cards.pop()

    assert list(showdown_ranks(hand)) == [2, 3]

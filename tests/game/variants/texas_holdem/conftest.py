"""Hold'em test helpers shared by several modules, exposed as fixtures because test modules cannot import each other.

Hands are dealt through the real dealing operations from a deck stacked with the test-local rng below, which uses the
existing Deck.shuffle seam.
"""

from collections.abc import Callable, MutableSequence
from random import Random
from typing import Any

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import HOLE_CARD_COUNT, deal_hole_cards, deal_next_street

BUTTON = 1
STARTING_CHIPS = 1000

_RANKS = {str(rank): rank for rank in Rank if rank <= 10} | {
    "T": Rank.TEN,
    "J": Rank.JACK,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
    "A": Rank.ACE,
}
_SUITS = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}


def _cards(text: str) -> list[Card]:
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


def _draw_order(holes: dict[int, str], board: str, button: int = BUTTON) -> list[Card]:
    """The cards in the order a hand of the seats in `holes` with this button draws them, so that the hole cards and
    board are the given ones once dealt. Every seat in the hand needs hole cards, so `holes` also says who plays.

    The hole cards are dealt one per player per round starting left of the button; each street burns one card first,
    which here are cards nobody else uses.
    """
    hole_cards = {seat: _cards(text) for seat, text in holes.items()}
    board_cards = _cards(board)
    assignments = assign_hand_seats(tuple(sorted(holes)), button)
    clockwise = list(assignments)  # button first
    deal_order = (*clockwise[1:], clockwise[0])
    used = [card for seat_cards in hole_cards.values() for card in seat_cards] + board_cards
    burns = iter(card for card in Deck.create_new_deck() if card not in used)

    draw_order = [hole_cards[seat][round_index] for round_index in range(HOLE_CARD_COUNT) for seat in deal_order]
    draw_order += [next(burns), *board_cards[:3], next(burns), board_cards[3], next(burns), board_cards[4]]
    return draw_order


def _stacked_hand(
    holes: dict[int, str], board: str, button: int = BUTTON, stacks: dict[int, int] | None = None
) -> PokerHand:
    """A hand of the seats in `holes` (button seat 1 unless given) whose hole cards and board are the given ones once
    dealt. Every seat in the hand needs hole cards, so `holes` also says who plays.

    Every seat starts with STARTING_CHIPS unless `stacks` gives its chips. See `_draw_order` for the dealing.
    """
    assignments = assign_hand_seats(tuple(sorted(holes)), button)
    draw_order = _draw_order(holes, board, button)

    deck = Deck()
    deck.shuffle(_rng=StackedRandom(draw_order))
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat}", stack=(stacks or {}).get(seat, STARTING_CHIPS), status=PlayerStatus.READY),
            seat_number=seat,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=deck)


class DeckQueue(Random):
    """A shuffle that stacks each new deck with the next queued draw order, one order per hand."""

    def __init__(self, draw_orders: list[list[Card]]) -> None:
        super().__init__()
        self._pending = list(draw_orders)

    def shuffle(self, x: MutableSequence[Any]) -> None:
        assert self._pending, "a hand was started without a queued deck"
        StackedRandom(self._pending.pop(0)).shuffle(x)

    @property
    def unused(self) -> int:
        return len(self._pending)


def _deal_to(hand: PokerHand, street: Street) -> None:
    deal_hole_cards(hand)
    while hand.street is not street:
        deal_next_street(hand)


@pytest.fixture
def cards() -> Callable[[str], list[Card]]:
    return _cards


@pytest.fixture
def stacked_hand() -> Callable[..., PokerHand]:
    return _stacked_hand


@pytest.fixture
def deal_to() -> Callable[[PokerHand, Street], None]:
    return _deal_to


@pytest.fixture
def draw_order() -> Callable[..., list[Card]]:
    return _draw_order


@pytest.fixture
def queue_decks(monkeypatch: pytest.MonkeyPatch) -> Callable[..., DeckQueue]:
    """Queue one stacked draw order per hand: the lifecycle's next shuffles use them in turn, through Deck's own
    `_rng` seam, and fail when more hands start than were queued."""

    def queue(*draw_orders: list[Card]) -> DeckQueue:
        rng = DeckQueue(list(draw_orders))
        original = Deck.shuffle
        monkeypatch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=rng))
        return rng

    return queue

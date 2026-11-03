"""Application-layer test helpers, exposed as fixtures because test modules cannot import each other.

Decks are stacked through `Deck`'s own shuffle seam (the `queue_decks` fixture): one queued draw order per hand, in
the order the hands start. The helpers are copies of the small parts of the engine's Hold'em test conftest.
"""

from collections.abc import Callable, MutableSequence
from random import Random
from typing import Any

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.results import Accepted
from go_poker.app.session import TableSession
from go_poker.app.views import TableSettings
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.betting.stakes import Stakes
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.variants.texas_holdem.dealing import HOLE_CARD_COUNT
from go_poker.game.variants.texas_holdem.view import holdem_view

STAKES = Stakes(small_blind=5, big_blind=10)
BUY_IN = 1000
NAMES = ("alice", "bob", "carol", "dave", "erin", "frank")

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


class DeckQueue(Random):
    """A shuffle that stacks each new deck with the next queued draw order, one order per hand."""

    def __init__(self, draw_orders: list[list[Card]]) -> None:
        super().__init__()
        self._pending = list(draw_orders)

    def shuffle(self, x: MutableSequence[Any]) -> None:
        assert self._pending, "a hand was started without a queued deck"
        StackedRandom(self._pending.pop(0)).shuffle(x)


def _draw_order(holes: dict[int, str], board: str, button: int = 1) -> list[Card]:
    """The cards in the order a hand of the seats in `holes` with this button draws them, so that the hole cards and
    board are the given ones once dealt. Each street burns one card first, which here are cards nobody else uses."""
    hole_cards = {seat: _cards(text) for seat, text in holes.items()}
    board_cards = _cards(board)
    clockwise = list(assign_hand_seats(tuple(sorted(holes)), button))  # button first
    deal_order = (*clockwise[1:], clockwise[0])
    used = [card for seat_cards in hole_cards.values() for card in seat_cards] + board_cards
    burns = iter(card for card in Deck.create_new_deck() if card not in used)

    draw_order = [hole_cards[seat][round_index] for round_index in range(HOLE_CARD_COUNT) for seat in deal_order]
    draw_order += [next(burns), *board_cards[:3], next(burns), board_cards[3], next(burns), board_cards[4]]
    return draw_order


def _user_id(name: str) -> UserId:
    """A user id whose text is distinctive, so a leak of it is easy to find."""
    return UserId(f"uid-{name}-7f3a")


def _display_name(name: str) -> DisplayName:
    """The display name of a test member: the capitalized name."""
    return DisplayName(name.capitalize())


@pytest.fixture
def draw_order() -> Callable[..., list[Card]]:
    return _draw_order


@pytest.fixture
def queue_decks(monkeypatch: pytest.MonkeyPatch) -> Callable[..., DeckQueue]:
    """Queue one stacked draw order per hand: the lifecycle's next shuffles use them in turn, through Deck's own `_rng`
    seam, and fail when more hands start than were queued."""

    def queue(*draw_orders: list[Card]) -> DeckQueue:
        rng = DeckQueue(list(draw_orders))
        original = Deck.shuffle
        monkeypatch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=rng))
        return rng

    return queue


@pytest.fixture(autouse=True)
def check_every_transition_view(monkeypatch: pytest.MonkeyPatch) -> None:
    """At the moment each shared transition is captured, every member's `game` view must equal the engine's own
    `holdem_view` for that member's seat, so cascades are checked at each step and not only at their final state."""
    original = TableSession._record  # noqa: SLF001

    def checked(session: TableSession, cause: Any) -> Any:
        transition = original(session, cause)
        for user_id, view in transition.views.items():
            seat = session._members[user_id].seat  # noqa: SLF001
            assert view.game == holdem_view(session._table, session._game.hand, seat)  # noqa: SLF001
        return transition

    monkeypatch.setattr(TableSession, "_record", checked)


type MakeSession = Callable[..., TableSession]


@pytest.fixture
def make_session() -> MakeSession:
    """A table whose first name is the host. Names join in order at seats 1, 2, 3, ...; the button is the lowest
    starting seat.

    `joined` is how many of the names join; the rest are free to join later.
    """

    def make(joined: int = 3, *, max_seats: int = 6) -> TableSession:
        settings = TableSettings(STAKES, BUY_IN, max_seats)
        session = TableSession.create(
            "table-1",
            "ABCD",
            settings,
            _user_id(NAMES[0]),
            _display_name(NAMES[0]),
            1,
            choose_button=lambda seats: seats[0],
        )
        for seat, name in enumerate(NAMES[1:joined], start=2):
            result = session.join(_user_id(name), session.revision, _display_name(name), seat)
            assert isinstance(result, Accepted)
        return session

    return make

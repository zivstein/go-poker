import random

import pytest

from go_poker.core import deck as deck_module
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck, DeckEmptyError


def test_deck_is_52_unique_cards():
    deck = Deck()
    deck_set = set()
    assert len(deck) == 52
    for _ in range(52):
        deck_set.add(deck.draw())
    assert len(deck) == 0
    assert len(deck_set) == 52


def test_single_draw():
    deck = Deck()
    assert len(deck) == 52
    card = deck.draw()
    assert isinstance(card, Card)
    assert len(deck) == 51


def test_draw_from_empty_deck():
    deck = Deck()
    for _ in range(52):
        deck.draw()
    with pytest.raises(DeckEmptyError):
        deck.draw()


def test_deck_contains_expected_cards():
    deck = Deck()
    _test_deck_contains_expected_cards(deck)


def _test_deck_contains_expected_cards(deck: Deck, drawn_cards: list[Card] | None = None) -> None:
    expected = {Card(rank, suit) for rank in Rank for suit in Suit}
    if drawn_cards is not None:
        expected.difference_update(drawn_cards)
    assert len(deck) == len(expected)

    actual = {deck.draw() for _ in range(len(deck))}

    assert actual == expected
    assert len(deck) == 0


def test_shuffle_preserves_cards():
    deck = Deck()
    deck.shuffle()
    _test_deck_contains_expected_cards(deck)


def test_shuffle_partially_drawn_deck():
    deck = Deck()
    drawn_cards = [deck.draw() for _ in range(10)]

    deck.shuffle()

    _test_deck_contains_expected_cards(deck, drawn_cards)


def test_independent_decks():
    deck1 = Deck()
    deck2 = Deck()

    drawn_cards = [deck1.draw() for _ in range(10)]

    _test_deck_contains_expected_cards(deck2)
    _test_deck_contains_expected_cards(deck1, drawn_cards)


def draw_all_in_order(deck: Deck) -> list[Card]:
    return [deck.draw() for _ in range(len(deck))]


def test_new_deck_is_in_creation_order() -> None:
    """A new deck is not shuffled; it draws its creation order from the end."""
    assert draw_all_in_order(Deck()) == list(reversed(Deck.create_new_deck()))


def test_default_shuffle_uses_the_os_csprng() -> None:
    """Without a test rng, shuffles use the unseedable OS CSPRNG."""
    assert isinstance(deck_module._SYSTEM_RANDOM, random.SystemRandom)


def test_plain_shuffle_uses_the_module_generator(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shuffle without a test rng draws its order from the module's _SYSTEM_RANDOM generator."""
    monkeypatch.setattr("go_poker.core.deck._SYSTEM_RANDOM", random.Random(9))
    deck = Deck()
    deck.shuffle()
    expected = Deck.create_new_deck()
    random.Random(9).shuffle(expected)
    assert draw_all_in_order(deck) == list(reversed(expected))


def test_shuffle_uses_the_given_test_rng() -> None:
    """With the test seam, the deck order is exactly the given generator's shuffle of a fresh deck."""
    deck = Deck()
    deck.shuffle(_rng=random.Random(7))
    expected = Deck.create_new_deck()
    random.Random(7).shuffle(expected)
    assert draw_all_in_order(deck) == list(reversed(expected))

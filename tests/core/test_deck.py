import pytest

from go_poker.core.card import Card, Suit, Rank
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

def _test_deck_contains_expected_cards(deck: Deck, drawn_cards: list[Card] | None = None ) -> None:
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
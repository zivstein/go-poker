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


def test_card_is_in_deck_until_drawn() -> None:
    """Membership is true for every undrawn card and false for a card once it has been drawn."""
    deck = Deck()
    assert all(Card(rank, suit) in deck for rank in Rank for suit in Suit)
    drawn = deck.draw()
    assert drawn not in deck
    assert all(card in deck for card in Deck.create_new_deck() if card != drawn)


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


def shuffled_with_seed(seed: int) -> list[Card]:
    deck = Deck()
    deck.shuffle(_rng=random.Random(seed))
    return draw_all_in_order(deck)


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


def test_default_shuffles_differ() -> None:
    """Two default shuffles give different orders; equal orders have probability 1 in 52!."""
    first, second = Deck(), Deck()
    first.shuffle()
    second.shuffle()
    assert draw_all_in_order(first) != draw_all_in_order(second)


def test_shuffle_with_same_seed_gives_same_order() -> None:
    """Two decks shuffled with equally seeded test generators deal the same cards in the same order."""
    assert shuffled_with_seed(42) == shuffled_with_seed(42)


def test_shuffle_with_different_seeds_gives_different_orders() -> None:
    """Different seeds produce different deck orders."""
    assert shuffled_with_seed(1) != shuffled_with_seed(2)


def test_shuffle_uses_the_given_test_rng() -> None:
    """The deck order is exactly the given generator's shuffle of a fresh deck."""
    expected = Deck.create_new_deck()
    random.Random(7).shuffle(expected)
    assert shuffled_with_seed(7) == list(reversed(expected))


def test_shuffle_with_rng_preserves_cards() -> None:
    """Shuffling with a test generator keeps the same 52 cards."""
    deck = Deck()
    deck.shuffle(_rng=random.Random(3))
    _test_deck_contains_expected_cards(deck)


def test_shuffle_with_rng_partially_drawn_deck() -> None:
    """Shuffling a partially drawn deck with a test generator keeps exactly the undrawn cards."""
    deck = Deck()
    drawn_cards = [deck.draw() for _ in range(10)]
    deck.shuffle(_rng=random.Random(3))
    _test_deck_contains_expected_cards(deck, drawn_cards)

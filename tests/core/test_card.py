from go_poker.core.card import Card, Rank, Suit


def test_card_has_correct_rank():
    card = Card(Rank.ACE, Suit.SPADES)

    assert card.rank == Rank.ACE


def test_card_has_correct_suit():
    card = Card(Rank.ACE, Suit.SPADES)

    assert card.suit == Suit.SPADES


def test_card_string_representation():
    card = Card(Rank.ACE, Suit.SPADES)

    assert str(card) == "A♠"

def test_rank_ordering():
    assert Rank.ACE > Rank.KING

def test_identical_cards_are_equal():
    card1 = Card(Rank.ACE, Suit.SPADES)
    card2 = Card(Rank.ACE, Suit.SPADES)

    assert card1 == card2

def test_different_cards_are_not_equal():
    card1 = Card(Rank.ACE, Suit.SPADES)
    card2 = Card(Rank.KING, Suit.SPADES)

    assert card1 != card2

def test_card_is_hashable():
    card = Card(Rank.ACE, Suit.SPADES)

    cards = {card}

    assert card in cards
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.street import Street

FULL_DECK = {Card(rank, suit) for rank in Rank for suit in Suit}


def make_players() -> tuple[HandPlayerState, ...]:
    assignments = [
        (5, Position.BTN, Blind.NONE),
        (8, Position.SB, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
    ]
    return tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=1000, status=PlayerStatus.READY),
            seat_number=seat_number,
            position=position,
            blind=blind,
        )
        for seat_number, position, blind in assignments
    )


def draw_all(deck: Deck) -> set[Card]:
    return {deck.draw() for _ in range(len(deck))}


def test_new_hand_keeps_players_in_order() -> None:
    """The hand holds the given participant states, in the given order."""
    players = make_players()
    hand = PokerHand(players=players)
    assert hand.players == players
    assert all(held is given for held, given in zip(hand.players, players, strict=True))


def test_new_hand_has_full_deck_and_empty_board() -> None:
    """A new hand starts with its own full 52-card deck and no community cards."""
    hand = PokerHand(players=make_players())
    assert isinstance(hand.deck, Deck)
    assert len(hand.deck) == 52
    assert draw_all(hand.deck) == FULL_DECK
    assert hand.board == []


def test_hands_do_not_share_deck_or_board() -> None:
    """Each hand gets its own deck and board, so changes to one never affect another."""
    first = PokerHand(players=make_players())
    second = PokerHand(players=make_players())
    assert first.deck is not second.deck
    assert first.board is not second.board

    first.board.append(first.deck.draw())
    assert len(first.deck) == 51
    assert len(second.deck) == 52
    assert second.board == []


def test_new_hand_starts_preflop_without_burned_cards() -> None:
    """A new hand starts on the preflop street with an empty board and nothing burned."""
    hand = PokerHand(players=make_players())
    assert hand.street is Street.PREFLOP
    assert hand.board == []
    assert hand.burned_cards == []


def test_hands_do_not_share_burned_cards() -> None:
    """Each hand gets its own burned cards, so burning in one hand never affects another."""
    first = PokerHand(players=make_players())
    second = PokerHand(players=make_players())
    assert first.burned_cards is not second.burned_cards

    first.burned_cards.append(first.deck.draw())
    assert second.burned_cards == []

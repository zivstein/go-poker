from collections.abc import Callable

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import DuplicateCardError, PokerHand, ensure_unique_cards
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


# =============================================================================
# CARD UNIQUENESS
# =============================================================================

# A new deck draws from the end of its creation order, so the first card created is drawn last.
UNDRAWN_CARD = Deck.create_new_deck()[0]


def fully_dealt_hand() -> PokerHand:
    """A hand whose players hold two cards each, with three burned and five board cards, all drawn from its deck."""
    hand = PokerHand(players=make_players())
    for state in hand.players:
        state.hole_cards.extend([hand.deck.draw(), hand.deck.draw()])
    hand.burned_cards.extend(hand.deck.draw() for _ in range(3))
    hand.board.extend(hand.deck.draw() for _ in range(5))
    return hand


def test_fresh_hand_has_unique_cards() -> None:
    """A hand with nothing dealt passes the uniqueness check."""
    ensure_unique_cards(PokerHand(players=make_players()))


def test_fully_dealt_hand_has_unique_cards() -> None:
    """A hand whose dealt cards were all drawn from its deck passes the uniqueness check."""
    hand = fully_dealt_hand()
    assert UNDRAWN_CARD in hand.deck
    ensure_unique_cards(hand)


def share_hole_card_between_players(hand: PokerHand) -> None:
    hand.players[1].hole_cards[0] = hand.players[0].hole_cards[0]


def put_hole_card_on_board(hand: PokerHand) -> None:
    hand.board[0] = hand.players[0].hole_cards[1]


def put_burned_card_on_board(hand: PokerHand) -> None:
    hand.board[4] = hand.burned_cards[0]


def repeat_card_on_board(hand: PokerHand) -> None:
    hand.board[1] = hand.board[0]


def put_undrawn_card_on_board(hand: PokerHand) -> None:
    hand.board[2] = UNDRAWN_CARD


def give_undrawn_card_as_hole_card(hand: PokerHand) -> None:
    hand.players[2].hole_cards[0] = UNDRAWN_CARD


def burn_undrawn_card(hand: PokerHand) -> None:
    hand.burned_cards[1] = UNDRAWN_CARD


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(share_hole_card_between_players, id="hole-cards-of-two-players"),
        pytest.param(put_hole_card_on_board, id="hole-cards-and-board"),
        pytest.param(put_burned_card_on_board, id="board-and-burned-cards"),
        pytest.param(repeat_card_on_board, id="within-the-board"),
        pytest.param(put_undrawn_card_on_board, id="board-card-still-in-deck"),
        pytest.param(give_undrawn_card_as_hole_card, id="hole-card-still-in-deck"),
        pytest.param(burn_undrawn_card, id="burned-card-still-in-deck"),
    ],
)
def test_duplicated_card_is_rejected(tamper: Callable[[PokerHand], None]) -> None:
    """A card held in two places, or dealt while still in the deck, fails the uniqueness check."""
    hand = fully_dealt_hand()
    tamper(hand)
    with pytest.raises(DuplicateCardError):
        ensure_unique_cards(hand)

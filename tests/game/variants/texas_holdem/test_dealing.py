from random import Random

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck, DeckEmptyError
from go_poker.game.game_lifecycle import start_game
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Position
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.dealing import (
    HOLE_CARD_COUNT,
    HoleCardsAlreadyDealtError,
    deal_hole_cards,
)

PLAYER_COUNTS = range(2, 10)


def make_hand(seat_numbers: tuple[int, ...], button_seat_number: int) -> PokerHand:
    """Build a hand clockwise from the button with an unshuffled deck, so the draw order is known."""
    assignments = assign_hand_seats(seat_numbers, button_seat_number)
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=1000, status=PlayerStatus.READY),
            seat_number=seat_number,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat_number, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=Deck())


def make_hand_of(player_count: int) -> PokerHand:
    return make_hand(tuple(range(1, player_count + 1)), button_seat_number=1)


def draw_order() -> list[Card]:
    """The order an unshuffled deck hands out its cards (draw takes from the end)."""
    return list(reversed(Deck.create_new_deck()))


def remaining_cards(deck: Deck) -> list[Card]:
    return [deck.draw() for _ in range(len(deck))]


def hole_cards_by_seat(hand: PokerHand) -> dict[int, list[Card]]:
    return {state.seat_number: list(state.hole_cards) for state in hand.players}


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_every_player_gets_two_cards_and_deck_shrinks_accordingly(player_count: int) -> None:
    """Each participant ends with exactly two cards, taken from the hand's own deck."""
    hand = make_hand_of(player_count)
    deal_hole_cards(hand)
    assert all(len(state.hole_cards) == HOLE_CARD_COUNT for state in hand.players)
    assert len(hand.deck) == 52 - HOLE_CARD_COUNT * player_count


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_hole_cards_are_unique_and_never_left_in_the_deck(player_count: int) -> None:
    """No card is dealt twice, and every dealt card has left the deck."""
    hand = make_hand_of(player_count)
    deal_hole_cards(hand)
    dealt = [card for state in hand.players for card in state.hole_cards]
    assert len(set(dealt)) == len(dealt)
    left_in_deck = set(remaining_cards(hand.deck))
    assert left_in_deck.isdisjoint(dealt)
    assert left_in_deck | set(dealt) == {Card(rank, suit) for rank in Rank for suit in Suit}


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_cards_go_one_at_a_time_starting_left_of_the_button(player_count: int) -> None:
    """Each round gives one card per player, starting clockwise of the button and ending with the button."""
    hand = make_hand_of(player_count)
    deal_hole_cards(hand)
    order = draw_order()
    deal_order = [*hand.players[1:], hand.players[0]]
    for offset, state in enumerate(deal_order):
        assert state.hole_cards == [order[offset], order[offset + player_count]]


def test_exact_deal_order_with_three_players() -> None:
    """With BTN, SB, BB the small blind gets the first card and the button the last of each round."""
    hand = make_hand((2, 5, 9), button_seat_number=9)
    assert [state.position for state in hand.players] == [Position.BTN, Position.SB, Position.BB]
    c = draw_order()
    deal_hole_cards(hand)
    assert hole_cards_by_seat(hand) == {
        2: [c[0], c[3]],  # small blind
        5: [c[1], c[4]],  # big blind
        9: [c[2], c[5]],  # button
    }


def test_exact_deal_order_heads_up() -> None:
    """Heads-up the big blind gets the first card and the button (small blind) the second of each round."""
    hand = make_hand((3, 7), button_seat_number=7)
    assert [state.position for state in hand.players] == [Position.BTN, Position.BB]
    c = draw_order()
    deal_hole_cards(hand)
    assert hole_cards_by_seat(hand) == {
        3: [c[0], c[2]],  # big blind
        7: [c[1], c[3]],  # button and small blind
    }


def test_no_card_is_burned_before_hole_cards() -> None:
    """The first card off the deck is the first hole card dealt."""
    hand = make_hand_of(3)
    deal_hole_cards(hand)
    assert hand.players[1].hole_cards[0] == draw_order()[0]


def test_dealing_hole_cards_leaves_the_board_empty() -> None:
    """Hole-card dealing never touches the community board."""
    hand = make_hand_of(4)
    deal_hole_cards(hand)
    assert hand.board == []


def test_dealing_twice_raises_and_changes_nothing() -> None:
    """A hand is dealt hole cards once; a second deal is rejected without drawing."""
    hand = make_hand_of(3)
    deal_hole_cards(hand)
    dealt = hole_cards_by_seat(hand)
    with pytest.raises(HoleCardsAlreadyDealtError):
        deal_hole_cards(hand)
    assert hole_cards_by_seat(hand) == dealt
    assert len(hand.deck) == 52 - 6
    assert remaining_cards(hand.deck) == draw_order()[6:]


def test_any_player_already_holding_cards_blocks_the_deal() -> None:
    """If one participant already holds a card, nobody is dealt and the deck is untouched."""
    hand = make_hand_of(3)
    held = Card(Rank.ACE, Suit.SPADES)
    hand.players[2].hole_cards.append(held)
    with pytest.raises(HoleCardsAlreadyDealtError):
        deal_hole_cards(hand)
    assert hole_cards_by_seat(hand) == {1: [], 2: [], 3: [held]}
    assert len(hand.deck) == 52


@pytest.mark.parametrize("cards_left", [0, 1, 5])
def test_insufficient_deck_raises_and_changes_nothing(cards_left: int) -> None:
    """A deck too small for the whole deal is rejected before any card is drawn."""
    hand = make_hand_of(3)
    for _ in range(52 - cards_left):
        hand.deck.draw()
    with pytest.raises(DeckEmptyError):
        deal_hole_cards(hand)
    assert all(state.hole_cards == [] for state in hand.players)
    assert len(hand.deck) == cards_left
    assert remaining_cards(hand.deck) == draw_order()[52 - cards_left :]


def test_deck_with_exactly_enough_cards_is_dealt_out() -> None:
    """A deck holding exactly the cards needed is fully dealt."""
    hand = make_hand_of(3)
    for _ in range(52 - 6):
        hand.deck.draw()
    deal_hole_cards(hand)
    assert len(hand.deck) == 0
    assert all(len(state.hole_cards) == HOLE_CARD_COUNT for state in hand.players)


def test_seeded_game_start_then_deal_is_reproducible() -> None:
    """A hand started with a seeded rng and then dealt gets exactly the cards an identically seeded deck yields."""
    seed = 17
    expected_deck = Deck()
    expected_deck.shuffle(_rng=Random(seed))
    order = remaining_cards(expected_deck)

    table = Table(9)
    for seat_number in (2, 4, 6, 8):
        table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
    hand = start_game(table, lambda seats: 4, _rng=Random(seed))
    deal_hole_cards(hand)

    player_count = len(hand.players)
    deal_order = [*hand.players[1:], hand.players[0]]
    assert [state.seat_number for state in deal_order] == [6, 8, 2, 4]
    for offset, state in enumerate(deal_order):
        assert len(state.hole_cards) == HOLE_CARD_COUNT
        assert state.hole_cards == [order[offset], order[offset + player_count]]
    assert len(hand.deck) == 52 - HOLE_CARD_COUNT * player_count
    assert remaining_cards(hand.deck) == order[HOLE_CARD_COUNT * player_count :]

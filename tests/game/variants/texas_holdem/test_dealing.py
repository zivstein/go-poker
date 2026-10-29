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
from go_poker.game.street import Street
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.dealing import (
    BOARD_CARD_COUNTS,
    BURN_CARD_COUNT,
    HOLE_CARD_COUNT,
    HandPastPreflopError,
    HoleCardsAlreadyDealtError,
    HoleCardsNotDealtError,
    NoNextStreetError,
    deal_hole_cards,
    deal_next_street,
)

PLAYER_COUNTS = range(2, 10)
STREET_BEFORE = {Street.FLOP: Street.PREFLOP, Street.TURN: Street.FLOP, Street.RIVER: Street.TURN}


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


def deal_to(hand: PokerHand, street: Street) -> None:
    """Deal hole cards, then deal streets until the hand reaches the given street."""
    deal_hole_cards(hand)
    while hand.street is not street:
        deal_next_street(hand)


def snapshot(hand: PokerHand) -> tuple[Street, list[Card], list[Card], dict[int, list[Card]], int]:
    return hand.street, list(hand.board), list(hand.burned_cards), hole_cards_by_seat(hand), len(hand.deck)


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


# =============================================================================
# STREETS AND BOARD DEALING
# =============================================================================


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_full_deal_burns_one_card_before_each_street_in_draw_order(player_count: int) -> None:
    """Hole cards, then burn + flop, burn + turn and burn + river come off the deck in that order."""
    hand = make_hand_of(player_count)
    c = draw_order()
    hole = HOLE_CARD_COUNT * player_count

    deal_hole_cards(hand)
    assert hand.street is Street.PREFLOP
    assert hand.board == []
    assert hand.burned_cards == []
    assert len(hand.deck) == 52 - hole

    deal_next_street(hand)
    assert hand.street is Street.FLOP
    assert hand.burned_cards == [c[hole]]
    assert hand.board == c[hole + 1 : hole + 4]
    assert len(hand.deck) == 52 - hole - 4

    deal_next_street(hand)
    assert hand.street is Street.TURN
    assert hand.burned_cards == [c[hole], c[hole + 4]]
    assert hand.board == c[hole + 1 : hole + 4] + [c[hole + 5]]
    assert len(hand.deck) == 52 - hole - 6

    deal_next_street(hand)
    assert hand.street is Street.RIVER
    assert hand.burned_cards == [c[hole], c[hole + 4], c[hole + 6]]
    assert hand.board == c[hole + 1 : hole + 4] + [c[hole + 5], c[hole + 7]]
    assert len(hand.deck) == 52 - hole - 8
    assert remaining_cards(hand.deck) == c[hole + 8 :]


def test_exact_full_deal_heads_up() -> None:
    """Heads-up the big blind and button get their hole cards, then three burns and five board cards follow."""
    hand = make_hand((3, 7), button_seat_number=7)
    c = draw_order()
    deal_to(hand, Street.RIVER)
    assert hole_cards_by_seat(hand) == {3: [c[0], c[2]], 7: [c[1], c[3]]}
    assert hand.burned_cards == [c[4], c[8], c[10]]
    assert hand.board == [c[5], c[6], c[7], c[9], c[11]]
    assert len(hand.deck) == 52 - 12


def test_street_card_counts() -> None:
    """Texas Hold'em burns one card per street and deals three, one and one board cards."""
    assert BURN_CARD_COUNT == 1
    assert BOARD_CARD_COUNTS == {Street.FLOP: 3, Street.TURN: 1, Street.RIVER: 1}


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_full_deal_reaches_river_with_every_card_accounted_for_once(player_count: int) -> None:
    """At the river the board holds five cards, and no card appears twice across hand and deck."""
    hand = make_hand_of(player_count)
    deal_to(hand, Street.RIVER)
    assert len(hand.board) == 5
    assert len(hand.burned_cards) == 3
    hole_cards = [card for state in hand.players for card in state.hole_cards]
    every_card = hole_cards + hand.board + hand.burned_cards + remaining_cards(hand.deck)
    assert len(every_card) == 52
    assert set(every_card) == {Card(rank, suit) for rank in Rank for suit in Suit}


def test_dealing_past_the_river_raises_and_changes_nothing() -> None:
    """There is no street after the river; the attempt draws nothing."""
    hand = make_hand_of(3)
    deal_to(hand, Street.RIVER)
    before = snapshot(hand)
    with pytest.raises(NoNextStreetError):
        deal_next_street(hand)
    assert snapshot(hand) == before
    assert remaining_cards(hand.deck) == draw_order()[6 + 8 :]


def test_flop_before_hole_cards_raises_and_changes_nothing() -> None:
    """The flop cannot be dealt until every participant holds their hole cards."""
    hand = make_hand_of(3)
    with pytest.raises(HoleCardsNotDealtError):
        deal_next_street(hand)
    assert snapshot(hand) == (Street.PREFLOP, [], [], {1: [], 2: [], 3: []}, 52)


def test_flop_with_a_participant_missing_hole_cards_raises_and_changes_nothing() -> None:
    """One participant short of hole cards is enough to block the flop."""
    hand = make_hand_of(3)
    deal_hole_cards(hand)
    hand.players[0].hole_cards.pop()
    before = snapshot(hand)
    with pytest.raises(HoleCardsNotDealtError):
        deal_next_street(hand)
    assert snapshot(hand) == before


@pytest.mark.parametrize("street", [Street.FLOP, Street.TURN, Street.RIVER])
def test_hole_cards_after_preflop_raise_and_change_nothing(street: Street) -> None:
    """Hole cards are only dealt preflop."""
    hand = make_hand_of(3)
    deal_to(hand, street)
    before = snapshot(hand)
    with pytest.raises(HandPastPreflopError):
        deal_hole_cards(hand)
    assert snapshot(hand) == before


def test_hole_cards_on_a_later_street_raise_even_before_any_were_dealt() -> None:
    """The street check rejects hole-card dealing on any street other than preflop."""
    hand = make_hand_of(3)
    hand.street = Street.FLOP
    with pytest.raises(HandPastPreflopError):
        deal_hole_cards(hand)
    assert snapshot(hand) == (Street.FLOP, [], [], {1: [], 2: [], 3: []}, 52)


@pytest.mark.parametrize("next_street", [Street.FLOP, Street.TURN, Street.RIVER])
def test_too_few_cards_for_a_street_raises_and_changes_nothing(next_street: Street) -> None:
    """A deck without room for the burn and the street's board cards is rejected before any card is drawn."""
    hand = make_hand_of(3)
    deal_to(hand, STREET_BEFORE[next_street])
    cards_needed = BURN_CARD_COUNT + BOARD_CARD_COUNTS[next_street]
    while len(hand.deck) > cards_needed - 1:
        hand.deck.draw()
    before = snapshot(hand)
    with pytest.raises(DeckEmptyError):
        deal_next_street(hand)
    assert snapshot(hand) == before
    assert remaining_cards(hand.deck) == draw_order()[52 - (cards_needed - 1) :]


@pytest.mark.parametrize("next_street", [Street.FLOP, Street.TURN, Street.RIVER])
def test_deck_with_exactly_enough_cards_deals_the_street(next_street: Street) -> None:
    """A deck holding exactly the burn and board cards needed is dealt out."""
    hand = make_hand_of(3)
    deal_to(hand, STREET_BEFORE[next_street])
    cards_needed = BURN_CARD_COUNT + BOARD_CARD_COUNTS[next_street]
    while len(hand.deck) > cards_needed:
        hand.deck.draw()
    deal_next_street(hand)
    assert hand.street is next_street
    assert len(hand.deck) == 0


def test_seeded_game_start_then_full_deal_is_reproducible() -> None:
    """Two identically seeded games dealt to the river get the same cards, all from the seeded deck order."""
    seed = 31

    def play() -> PokerHand:
        table = Table(9)
        for seat_number in (1, 3, 5, 8):
            table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
        hand = start_game(table, lambda seats: 5, _rng=Random(seed))
        deal_to(hand, Street.RIVER)
        return hand

    first, second = play(), play()
    assert snapshot(first) == snapshot(second)
    assert remaining_cards(first.deck) == remaining_cards(second.deck)

    expected_deck = Deck()
    expected_deck.shuffle(_rng=Random(seed))
    c = remaining_cards(expected_deck)
    hole = HOLE_CARD_COUNT * len(first.players)
    assert first.street is Street.RIVER
    assert first.burned_cards == [c[hole], c[hole + 4], c[hole + 6]]
    assert first.board == [*c[hole + 1 : hole + 4], c[hole + 5], c[hole + 7]]

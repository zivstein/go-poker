from collections.abc import Callable
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
    HandPastPreflopError,
    HoleCardsAlreadyDealtError,
    InvalidHoleCardCountError,
    NoNextStreetError,
    deal_hole_cards,
    deal_next_street,
)

FULL_DECK = {Card(rank, suit) for rank in Rank for suit in Suit}

type Deal = Callable[[PokerHand], None]
type HandSetup = Callable[[PokerHand], None]
type Snapshot = tuple[Street, list[Card], list[Card], dict[int, list[Card]], int]


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
    return PokerHand(players=players, deck=Deck(), number=1)


def make_three_handed() -> PokerHand:
    return make_hand((1, 2, 3), button_seat_number=1)


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


def dealt_to(street: Street) -> HandSetup:
    return lambda hand: deal_to(hand, street)


def nothing_dealt(hand: PokerHand) -> None:
    """Leave the hand as it starts: preflop, nothing dealt."""


def one_hole_card_short(hand: PokerHand) -> None:
    deal_hole_cards(hand)
    hand.players[-1].hole_cards.pop()


def one_hole_card_extra(hand: PokerHand) -> None:
    deal_hole_cards(hand)
    hand.players[0].hole_cards.append(hand.deck.draw())


def snapshot(hand: PokerHand) -> Snapshot:
    return hand.street, list(hand.board), list(hand.burned_cards), hole_cards_by_seat(hand), len(hand.deck)


def shuffle_decks_with(monkeypatch: pytest.MonkeyPatch, rng: Random) -> None:
    """Make every Deck.shuffle forward the given test rng through Deck's own _rng seam."""
    original = Deck.shuffle
    monkeypatch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: original(deck, _rng=rng))


def assert_unchanged(hand: PokerHand, before: Snapshot) -> None:
    """The hand matches the snapshot, and its unshuffled deck still holds its undrawn cards in their original order."""
    assert snapshot(hand) == before
    assert remaining_cards(hand.deck) == draw_order()[52 - before[4] :]


# =============================================================================
# HOLE-CARD DEALING
# =============================================================================


def test_heads_up_deal_order() -> None:
    """Heads-up the big blind gets the first card and the button (small blind) the second, in two rounds."""
    hand = make_hand((3, 7), button_seat_number=7)
    assert [state.position for state in hand.players] == [Position.BTN, Position.BB]
    c = draw_order()
    deal_hole_cards(hand)
    assert hole_cards_by_seat(hand) == {
        3: [c[0], c[2]],  # big blind
        7: [c[1], c[3]],  # button and small blind
    }
    assert len(hand.deck) == 48


def test_multiway_deal_order() -> None:
    """Each of two rounds gives one card per player, from the seat clockwise of the button round to the button."""
    hand = make_hand((1, 3, 4, 6, 8, 9), button_seat_number=4)
    assert [state.seat_number for state in hand.players] == [4, 6, 8, 9, 1, 3]
    assert hand.players[0].position is Position.BTN
    c = draw_order()
    deal_hole_cards(hand)
    assert hole_cards_by_seat(hand) == {
        6: [c[0], c[6]],  # small blind
        8: [c[1], c[7]],  # big blind
        9: [c[2], c[8]],
        1: [c[3], c[9]],
        3: [c[4], c[10]],
        4: [c[5], c[11]],  # button
    }
    assert hand.burned_cards == []
    assert len(hand.deck) == 40


# =============================================================================
# STREETS AND BOARD DEALING
# =============================================================================


def test_streets_progress_with_one_burn_before_each_board_deal() -> None:
    """Preflop moves to flop, turn and river; each burns one card, then deals three, one and one board cards."""
    hand = make_three_handed()
    c = draw_order()
    deal_hole_cards(hand)

    deal_next_street(hand)
    assert hand.street is Street.FLOP
    assert hand.burned_cards == [c[6]]
    assert hand.board == [c[7], c[8], c[9]]

    deal_next_street(hand)
    assert hand.street is Street.TURN
    assert hand.burned_cards == [c[6], c[10]]
    assert hand.board == [c[7], c[8], c[9], c[11]]

    deal_next_street(hand)
    assert hand.street is Street.RIVER
    assert hand.burned_cards == [c[6], c[10], c[12]]
    assert hand.board == [c[7], c[8], c[9], c[11], c[13]]
    assert remaining_cards(hand.deck) == c[14:]


@pytest.mark.parametrize(
    "setup",
    [
        pytest.param(nothing_dealt, id="no-hole-cards-dealt"),
        pytest.param(one_hole_card_short, id="one-card-short"),
        pytest.param(one_hole_card_extra, id="one-card-extra"),
    ],
)
def test_board_needs_exactly_two_hole_cards_per_player(setup: HandSetup) -> None:
    """The board is dealt only once every participant holds exactly two hole cards; otherwise nothing changes."""
    hand = make_three_handed()
    setup(hand)
    before = snapshot(hand)
    with pytest.raises(InvalidHoleCardCountError):
        deal_next_street(hand)
    assert_unchanged(hand, before)


@pytest.mark.parametrize(
    "setup, deal, error",
    [
        pytest.param(dealt_to(Street.PREFLOP), deal_hole_cards, HoleCardsAlreadyDealtError, id="hole-cards-twice"),
        pytest.param(dealt_to(Street.FLOP), deal_hole_cards, HandPastPreflopError, id="hole-cards-on-flop"),
        pytest.param(dealt_to(Street.RIVER), deal_next_street, NoNextStreetError, id="past-the-river"),
    ],
)
def test_illegal_transitions_raise_and_change_nothing(setup: HandSetup, deal: Deal, error: type[Exception]) -> None:
    """Hole cards are dealt once and only preflop, and no street follows the river; violations change nothing."""
    hand = make_three_handed()
    setup(hand)
    before = snapshot(hand)
    with pytest.raises(error):
        deal(hand)
    assert_unchanged(hand, before)


# =============================================================================
# DECK SIZE
# =============================================================================


@pytest.mark.parametrize(
    "setup, deal, cards_needed",
    [
        pytest.param(nothing_dealt, deal_hole_cards, 6, id="hole-cards"),
        pytest.param(dealt_to(Street.PREFLOP), deal_next_street, 4, id="flop"),
    ],
)
def test_deck_one_card_short_raises_and_changes_nothing(setup: HandSetup, deal: Deal, cards_needed: int) -> None:
    """A deck too small for the whole deal is rejected before any card is drawn."""
    hand = make_three_handed()
    setup(hand)
    while len(hand.deck) > cards_needed - 1:
        hand.deck.draw()
    before = snapshot(hand)
    with pytest.raises(DeckEmptyError):
        deal(hand)
    assert_unchanged(hand, before)


@pytest.mark.parametrize(
    "setup, deal, cards_needed, expected_street",
    [
        pytest.param(nothing_dealt, deal_hole_cards, 6, Street.PREFLOP, id="hole-cards"),
        pytest.param(dealt_to(Street.PREFLOP), deal_next_street, 4, Street.FLOP, id="flop"),
    ],
)
def test_deck_with_exactly_enough_cards_is_dealt_out(
    setup: HandSetup, deal: Deal, cards_needed: int, expected_street: Street
) -> None:
    """A deck holding exactly the cards needed is fully dealt."""
    hand = make_three_handed()
    setup(hand)
    while len(hand.deck) > cards_needed:
        hand.deck.draw()
    deal(hand)
    assert len(hand.deck) == 0
    assert all(len(state.hole_cards) == 2 for state in hand.players)
    assert hand.street is expected_street


# =============================================================================
# COMPLETE HAND
# =============================================================================


def test_complete_hand_from_game_start_to_river(monkeypatch: pytest.MonkeyPatch) -> None:
    """A started game's first hand is dealt to the river from its own shuffled deck in Texas Hold'em order."""
    shuffle_decks_with(monkeypatch, Random(2026))
    table = Table(9)
    for seat_number in (1, 3, 5, 8):
        table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
    hand = start_game(table, lambda seats: 5)
    deal_to(hand, Street.RIVER)

    cards = Deck.create_new_deck()
    Random(2026).shuffle(cards)
    o = list(reversed(cards))
    assert [state.position for state in hand.players][:3] == [Position.BTN, Position.SB, Position.BB]
    assert hole_cards_by_seat(hand) == {
        5: [o[3], o[7]],  # button
        8: [o[0], o[4]],  # small blind
        1: [o[1], o[5]],  # big blind
        3: [o[2], o[6]],
    }
    assert hand.burned_cards == [o[8], o[12], o[14]]
    assert hand.board == [o[9], o[10], o[11], o[13], o[15]]
    assert hand.street is Street.RIVER
    assert remaining_cards(hand.deck) == o[16:]


def test_complete_deal_accounts_for_every_card_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """After a full nine-handed deal, remaining deck, hole cards, burned cards and board are exactly the 52 cards."""
    shuffle_decks_with(monkeypatch, Random(9))
    table = Table(9)
    for seat_number in range(1, 10):
        table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
    hand = start_game(table, lambda seats: 1)
    deal_to(hand, Street.RIVER)

    hole_cards = [card for state in hand.players for card in state.hole_cards]
    every_card = remaining_cards(hand.deck) + hole_cards + hand.burned_cards + hand.board
    assert len(every_card) == 52
    assert set(every_card) == FULL_DECK

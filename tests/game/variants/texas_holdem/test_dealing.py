from collections.abc import Callable
from random import Random

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck, DeckEmptyError
from go_poker.game.game_lifecycle import start_game, start_next_hand
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import DuplicateCardError, PokerHand
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
FULL_DECK = {Card(rank, suit) for rank in Rank for suit in Suit}
# A new deck draws from the end of its creation order, so the first card created is drawn last.
UNDRAWN_CARD = Deck.create_new_deck()[0]

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


def snapshot(hand: PokerHand) -> Snapshot:
    return hand.street, list(hand.board), list(hand.burned_cards), hole_cards_by_seat(hand), len(hand.deck)


def assert_unchanged(hand: PokerHand, before: Snapshot) -> None:
    """The hand matches the snapshot, and its unshuffled deck still holds its undrawn cards in their original order."""
    assert snapshot(hand) == before
    assert remaining_cards(hand.deck) == draw_order()[52 - before[4] :]


def assert_dealt_to_river_in_order(hand: PokerHand, order: list[Card]) -> None:
    """Hole cards, burns and board cards of a hand dealt to the river came off the deck in Texas Hold'em order."""
    player_count = len(hand.players)
    deal_order = [*hand.players[1:], hand.players[0]]
    for offset, state in enumerate(deal_order):
        assert state.hole_cards == [order[offset], order[offset + player_count]]
    hole = HOLE_CARD_COUNT * player_count
    assert hand.burned_cards == [order[hole], order[hole + 4], order[hole + 6]]
    assert hand.board == [*order[hole + 1 : hole + 4], order[hole + 5], order[hole + 7]]


def assert_every_card_accounted_for_once(hand: PokerHand) -> None:
    """Hole cards, board, burned cards and the remaining deck are exactly the 52 distinct cards."""
    dealt = [card for state in hand.players for card in state.hole_cards] + hand.board + hand.burned_cards
    in_deck = {card for card in FULL_DECK if card in hand.deck}
    assert len(set(dealt)) == len(dealt)
    assert in_deck.isdisjoint(dealt)
    assert in_deck | set(dealt) == FULL_DECK
    assert len(hand.deck) == len(in_deck)


# =============================================================================
# HOLE-CARD DEALING
# =============================================================================


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_cards_go_one_at_a_time_starting_left_of_the_button(player_count: int) -> None:
    """Each round gives one card per player, starting clockwise of the button and ending with the button."""
    hand = make_hand_of(player_count)
    assert hand.players[0].position is Position.BTN
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


# =============================================================================
# DECK CONSUMPTION
# =============================================================================


@pytest.mark.parametrize("player_count", PLAYER_COUNTS)
def test_every_card_is_accounted_for_once_after_every_step(player_count: int) -> None:
    """After each deal, the deck shrank by exactly the dealt cards and no card is anywhere twice."""
    hand = make_hand_of(player_count)
    hand.deck.shuffle(_rng=Random(player_count))
    assert_every_card_accounted_for_once(hand)
    steps: list[tuple[Deal, Street, int, int]] = [
        (deal_hole_cards, Street.PREFLOP, 0, 0),
        (deal_next_street, Street.FLOP, 1, 3),
        (deal_next_street, Street.TURN, 2, 4),
        (deal_next_street, Street.RIVER, 3, 5),
    ]
    for deal, street, burned_count, board_count in steps:
        deal(hand)
        assert hand.street is street
        assert all(len(state.hole_cards) == HOLE_CARD_COUNT for state in hand.players)
        assert len(hand.burned_cards) == burned_count
        assert len(hand.board) == board_count
        assert len(hand.deck) == 52 - HOLE_CARD_COUNT * player_count - burned_count - board_count
        assert_every_card_accounted_for_once(hand)


# =============================================================================
# TRANSITIONS
# =============================================================================


def before_hole_cards(hand: PokerHand) -> None:
    """Leave the hand as it starts: preflop, nothing dealt."""


def with_partial_hole_cards(hand: PokerHand) -> None:
    deal_hole_cards(hand)
    hand.players[-1].hole_cards.pop()


def dealt_to(street: Street) -> HandSetup:
    return lambda hand: deal_to(hand, street)


@pytest.mark.parametrize("player_count", [2, 9])
@pytest.mark.parametrize(
    "setup, deal, expected_street",
    [
        pytest.param(before_hole_cards, deal_hole_cards, Street.PREFLOP, id="hole-cards-preflop"),
        pytest.param(dealt_to(Street.PREFLOP), deal_next_street, Street.FLOP, id="flop-after-hole-cards"),
        pytest.param(dealt_to(Street.FLOP), deal_next_street, Street.TURN, id="turn-after-flop"),
        pytest.param(dealt_to(Street.TURN), deal_next_street, Street.RIVER, id="river-after-turn"),
    ],
)
def test_legal_transitions(player_count: int, setup: HandSetup, deal: Deal, expected_street: Street) -> None:
    """Hole cards are dealt once, preflop; then each street follows the previous one up to the river."""
    hand = make_hand_of(player_count)
    setup(hand)
    deal(hand)
    assert hand.street is expected_street


@pytest.mark.parametrize("player_count", [2, 9])
@pytest.mark.parametrize(
    "setup, deal, error",
    [
        pytest.param(before_hole_cards, deal_next_street, HoleCardsNotDealtError, id="flop-before-hole-cards"),
        pytest.param(with_partial_hole_cards, deal_next_street, HoleCardsNotDealtError, id="flop-with-partial-hole"),
        pytest.param(with_partial_hole_cards, deal_hole_cards, HoleCardsAlreadyDealtError, id="hole-after-partial"),
        pytest.param(dealt_to(Street.PREFLOP), deal_hole_cards, HoleCardsAlreadyDealtError, id="hole-cards-twice"),
        pytest.param(dealt_to(Street.FLOP), deal_hole_cards, HandPastPreflopError, id="hole-cards-on-flop"),
        pytest.param(dealt_to(Street.TURN), deal_hole_cards, HandPastPreflopError, id="hole-cards-on-turn"),
        pytest.param(dealt_to(Street.RIVER), deal_hole_cards, HandPastPreflopError, id="hole-cards-on-river"),
        pytest.param(dealt_to(Street.RIVER), deal_next_street, NoNextStreetError, id="past-the-river"),
    ],
)
def test_illegal_transitions_raise_and_change_nothing(
    player_count: int, setup: HandSetup, deal: Deal, error: type[Exception]
) -> None:
    """Every illegal deal raises its own error before drawing, leaving street, cards and deck untouched."""
    hand = make_hand_of(player_count)
    setup(hand)
    before = snapshot(hand)
    with pytest.raises(error):
        deal(hand)
    assert_unchanged(hand, before)


# =============================================================================
# DUPLICATE-CARD PROTECTION
# =============================================================================


def put_undrawn_card_on_board(hand: PokerHand) -> None:
    hand.board.append(UNDRAWN_CARD)


def burn_undrawn_card(hand: PokerHand) -> None:
    hand.burned_cards.append(UNDRAWN_CARD)


def share_hole_card_between_players(hand: PokerHand) -> None:
    hand.players[1].hole_cards[0] = hand.players[0].hole_cards[0]


def give_undrawn_card_as_hole_card(hand: PokerHand) -> None:
    hand.players[0].hole_cards[1] = UNDRAWN_CARD


def put_hole_card_on_board(hand: PokerHand) -> None:
    hand.board.append(hand.players[0].hole_cards[0])


def put_burned_card_on_board(hand: PokerHand) -> None:
    hand.board.append(hand.burned_cards[0])


@pytest.mark.parametrize(
    "tamper",
    [
        pytest.param(put_undrawn_card_on_board, id="board-card-still-in-deck"),
        pytest.param(burn_undrawn_card, id="burned-card-still-in-deck"),
    ],
)
def test_hole_card_deal_rejects_duplicated_cards_and_changes_nothing(tamper: HandSetup) -> None:
    """Hole cards are not dealt to a hand holding a card that is also still in its deck."""
    hand = make_hand_of(3)
    tamper(hand)
    before = snapshot(hand)
    with pytest.raises(DuplicateCardError):
        deal_hole_cards(hand)
    assert_unchanged(hand, before)


@pytest.mark.parametrize(
    "street, tamper",
    [
        *(
            pytest.param(street, tamper, id=f"{street.name.lower()}-{tamper.__name__}")
            for street in (Street.PREFLOP, Street.FLOP, Street.TURN)
            for tamper in (
                share_hole_card_between_players,
                give_undrawn_card_as_hole_card,
                put_hole_card_on_board,
                put_undrawn_card_on_board,
            )
        ),
        pytest.param(Street.FLOP, put_burned_card_on_board, id="flop-put_burned_card_on_board"),
        pytest.param(Street.TURN, put_burned_card_on_board, id="turn-put_burned_card_on_board"),
    ],
)
def test_street_deal_rejects_duplicated_cards_and_changes_nothing(street: Street, tamper: HandSetup) -> None:
    """The next street is not dealt while a card is held twice or is dealt and still in the deck."""
    hand = make_hand_of(3)
    deal_to(hand, street)
    assert UNDRAWN_CARD in hand.deck
    tamper(hand)
    before = snapshot(hand)
    with pytest.raises(DuplicateCardError):
        deal_next_street(hand)
    assert_unchanged(hand, before)


# =============================================================================
# LIFECYCLE INTEGRATION
# =============================================================================


@pytest.mark.parametrize(
    "seat_numbers, expected_buttons",
    [
        pytest.param((2, 6), [6, 2, 6, 2], id="heads-up"),
        pytest.param((1, 3, 5, 8), [5, 8, 1, 3, 5], id="four-players"),
        pytest.param(tuple(range(1, 10)), [4, 5, 6, 7, 8], id="nine-players"),
    ],
)
def test_seeded_multi_hand_run_deals_every_hand_from_its_own_fresh_deck(
    seat_numbers: tuple[int, ...], expected_buttons: list[int]
) -> None:
    """Each hand of a seeded game is dealt to the river from its own deck, the button rotates, and a rerun matches."""
    seed = 2026

    def play() -> list[PokerHand]:
        table = Table(9)
        for seat_number in seat_numbers:
            table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
        rng = Random(seed)
        hands = [start_game(table, lambda seats: expected_buttons[0], _rng=rng)]
        deal_to(hands[0], Street.RIVER)
        for _ in expected_buttons[1:]:
            hand = start_next_hand(table, _rng=rng)
            deal_to(hand, Street.RIVER)
            hands.append(hand)
        return hands

    hands = play()
    assert [hand.players[0].seat_number for hand in hands] == expected_buttons
    assert all(hand.players[0].position is Position.BTN for hand in hands)
    assert len({id(hand.deck) for hand in hands}) == len(hands)

    # Each hand shuffles a fresh 52-card deck once with the shared generator, in hand order.
    reference_rng = Random(seed)
    for hand in hands:
        cards = Deck.create_new_deck()
        reference_rng.shuffle(cards)
        assert_dealt_to_river_in_order(hand, list(reversed(cards)))
        assert len(hand.deck) == 52 - HOLE_CARD_COUNT * len(seat_numbers) - 3 - 5
        assert_every_card_accounted_for_once(hand)

    rerun = play()
    assert [snapshot(hand) for hand in rerun] == [snapshot(hand) for hand in hands]
    assert [remaining_cards(hand.deck) for hand in rerun] == [remaining_cards(hand.deck) for hand in hands]

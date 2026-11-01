"""The events the Hold'em dealing operations record: `HoleCardsDealt` and `StreetDealt` (ADR 0004 §3, §4).

Hands are built by the shared `stacked_hand` fixture, so every dealt and burned card is known and written out here
independently. Burned cards are the first cards no hole card or board card uses, in deck order (2d, 2h, 2s). The
rejections of the dealing operations are in `test_dealing`, whose snapshot includes the history.
"""

from collections.abc import Callable

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindPost,
    BlindsPosted,
    HoleCardsDealt,
    SeatHoleCards,
    StreetDealt,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

STAKES = Stakes(small_blind=5, big_blind=10)
BOARD = "2c 7d 9h Jc Ks"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s", 4: "Qh Qd", 5: "5s 6s"}

type StackedHand = Callable[..., PokerHand]
type Cards = Callable[[str], list[Card]]


def seat_cards(cards: Cards, seat: int, text: str) -> SeatHoleCards:
    return SeatHoleCards(seat, tuple(cards(text)))


def test_hole_cards_are_recorded_per_seat_in_the_order_each_seat_received_them(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """Heads-up the button holds Ah then Ad and the big blind Kd then Kh; seats are listed button first."""
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD)
    deal_hole_cards(hand)

    assert hand.history.events[1:] == (HoleCardsDealt((seat_cards(cards, 1, "Ah Ad"), seat_cards(cards, 2, "Kd Kh"))),)


def test_multiway_hole_cards_are_listed_in_hand_order_not_in_dealing_or_seat_order(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """Five-handed with the button on seat 3 the hand order is 3, 4, 5, 1, 2, while the deal starts at seat 4."""
    hand = stacked_hand(HOLES, BOARD, button=3)
    deal_hole_cards(hand)

    assert [state.seat_number for state in hand.players] == [3, 4, 5, 1, 2]
    assert hand.history.events[1:] == (
        HoleCardsDealt(
            (
                seat_cards(cards, 3, "3s 4s"),
                seat_cards(cards, 4, "Qh Qd"),
                seat_cards(cards, 5, "5s 6s"),
                seat_cards(cards, 1, "Ah Ad"),
                seat_cards(cards, 2, "Kd Kh"),
            )
        ),
    )
    event = hand.history.events[1]
    assert isinstance(event, HoleCardsDealt)
    assert [(held.seat, list(held.cards)) for held in event.hole_cards] == [
        (state.seat_number, state.hole_cards) for state in hand.players
    ]


def test_every_street_records_its_burn_and_its_own_cards_only(stacked_hand: StackedHand, cards: Cards) -> None:
    """Flop, turn and river each record the one burned card and the board cards dealt by that call alone, equal to
    what the live hand gained."""
    hand = stacked_hand({seat: HOLES[seat] for seat in (1, 2, 3)}, BOARD)
    deal_hole_cards(hand)
    expected = (
        StreetDealt(Street.FLOP, tuple(cards("2d")), tuple(cards("2c 7d 9h"))),
        StreetDealt(Street.TURN, tuple(cards("2h")), tuple(cards("Jc"))),
        StreetDealt(Street.RIVER, tuple(cards("2s")), tuple(cards("Ks"))),
    )
    for event in expected:
        board_before, burned_before = len(hand.board), len(hand.burned_cards)
        deal_next_street(hand)
        assert hand.history.events[-1] == event
        assert event.cards == tuple(hand.board[board_before:])
        assert event.burned == tuple(hand.burned_cards[burned_before:])

    events = hand.history.events
    assert events[2:] == expected
    assert [card for event in expected for card in event.cards] == hand.board
    assert [card for event in expected for card in event.burned] == hand.burned_cards


def test_dealing_a_street_starts_no_betting_round(stacked_hand: StackedHand) -> None:
    """Dealing and starting betting are separate operations: a street dealt alone records `StreetDealt` only."""
    hand = stacked_hand({seat: HOLES[seat] for seat in (1, 2, 3)}, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, Action(ActionType.CALL))
    apply_action(hand, 2, Action(ActionType.CALL))
    apply_action(hand, 3, Action(ActionType.CHECK))
    length = len(hand.history.events)

    deal_next_street(hand)

    assert len(hand.history.events) == length + 1
    assert isinstance(hand.history.events[-1], StreetDealt)
    start_betting_round(hand)
    assert hand.history.events[-1] == BettingRoundStarted(Street.FLOP)


def test_low_level_order_is_recorded_as_called_and_not_normalized(stacked_hand: StackedHand, cards: Cards) -> None:
    """Dealing the hole cards before the blinds records them in that order; `begin_hand` does the opposite."""
    holes = {1: HOLES[1], 2: HOLES[2]}
    cards_first = stacked_hand(holes, BOARD)
    deal_hole_cards(cards_first)
    initialize_betting(cards_first, STAKES)

    blinds_first = stacked_hand(holes, BOARD)
    initialize_betting(blinds_first, STAKES)
    deal_hole_cards(blinds_first)

    dealt = HoleCardsDealt((seat_cards(cards, 1, "Ah Ad"), seat_cards(cards, 2, "Kd Kh")))
    blinds = BlindsPosted(STAKES, (BlindPost(1, Blind.SMALL, 5, False), BlindPost(2, Blind.BIG, 10, False)))
    assert cards_first.history.events[1:] == (dealt, blinds)
    assert blinds_first.history.events[1:] == (blinds, dealt)


def test_an_all_in_runout_dealt_by_hand_records_the_streets_without_any_round(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """Heads-up all-in preflop and called: the turn and river are dealt without starting a round for them, and the
    history holds the streets exactly as called."""
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD, stacks={1: 100, 2: 100})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, Action(ActionType.RAISE, 100))
    apply_action(hand, 2, Action(ActionType.CALL))
    for _ in range(3):
        deal_next_street(hand)

    assert hand.history.events[3:] == (
        ActionTaken(1, Action(ActionType.RAISE, 100), 95, True),
        ActionTaken(2, Action(ActionType.CALL), 90, True),
        BettingRoundCompleted(Street.PREFLOP),
        StreetDealt(Street.FLOP, tuple(cards("2d")), tuple(cards("2c 7d 9h"))),
        StreetDealt(Street.TURN, tuple(cards("2h")), tuple(cards("Jc"))),
        StreetDealt(Street.RIVER, tuple(cards("2s")), tuple(cards("Ks"))),
    )
    assert not any(isinstance(event, BettingRoundStarted) for event in hand.history.events)

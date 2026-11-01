"""Adversarial validation of what the Hold'em operations do and do not record (ADR 0004 §1, §4, §8).

Showdown, settlement, the derived reads and the orchestration record nothing in Cycle 3, and the low-level operations
record the call order they are given, even an order the flow would never produce.
"""

from collections.abc import Callable

import pytest

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import is_betting_closed, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    HandHistory,
    StreetDealt,
)
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.hand_strength import hand_strength
from go_poker.game.variants.texas_holdem.showdown import settle_hand, start_showdown

STAKES = Stakes(small_blind=5, big_blind=10)
BOARD = "2c 7d 9h Jc Ks"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)

type StackedHand = Callable[..., PokerHand]
type Cards = Callable[[str], list[Card]]


def checked_down_to_showdown(hand: PokerHand) -> None:
    """Call, call, check and then three checks on every street: an interactive showdown waits for its first decider."""
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(3):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)


def test_showdown_decisions_and_settlement_record_nothing(stacked_hand: StackedHand) -> None:
    """Every show or muck, and the settlement they end in, leave the history exactly as the river round left it."""
    hand = stacked_hand(HOLES, BOARD)
    checked_down_to_showdown(hand)
    at_showdown: HandHistory = hand.history
    assert hand.showdown is not None and hand.settlement is None

    while (decider := current_actor(hand)) is not None:
        act(hand, decider, ShowdownAction.SHOW if decider % 2 else ShowdownAction.MUCK)
        assert hand.history == at_showdown

    assert hand.settlement is not None
    assert hand.history == at_showdown
    assert isinstance(at_showdown.events[-1], BettingRoundCompleted)


def test_the_low_level_showdown_and_settlement_operations_record_nothing(stacked_hand: StackedHand) -> None:
    """An all-in runout started and settled by the low-level operations, with the history unchanged by each."""
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD, stacks={1: 100, 2: 100})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, Action(ActionType.RAISE, 100))
    apply_action(hand, 2, CALL)
    for _ in range(3):
        deal_next_street(hand)
    before = hand.history

    start_showdown(hand)
    assert hand.history == before
    settle_hand(hand)
    assert hand.history == before
    with pytest.raises(HandAlreadySettledError):
        deal_next_street(hand)
    with pytest.raises(HandAlreadySettledError):
        apply_action(hand, 1, CHECK)
    with pytest.raises(HandAlreadySettledError):
        start_betting_round(hand)
    with pytest.raises(HandAlreadySettledError):
        initialize_betting(hand, STAKES)
    with pytest.raises(HandAlreadySettledError):
        deal_hole_cards(hand)
    assert hand.history == before


def test_derived_reads_never_record_at_any_point_of_a_hand(stacked_hand: StackedHand) -> None:
    """Hand strength, the actor, legal actions, the pots and the betting-closed check are repeated at every step of a
    hand played to the river, and the history is only ever extended by the operations themselves."""
    hand = stacked_hand(HOLES, BOARD)

    def read_everything() -> HandHistory:
        before = hand.history
        if all(state.hole_cards for state in hand.players):  # strength needs the hole cards
            for seat in HOLES:
                hand_strength(hand, seat)
        current_actor(hand)
        if hand.betting is not None:
            legal_actions(hand)
            pots(hand)
            middle_pot(hand)
            is_betting_closed(hand)
        assert hand.history == before
        return before

    read_everything()
    begin_hand(hand, STAKES)
    read_everything()
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
        read_everything()
    for _ in range(3):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)
            read_everything()


def test_a_street_dealt_while_a_round_is_open_records_the_deal_and_the_round_keeps_its_street(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """The low-level operations record the order they are called in, and a round completed after the deal still
    completes its own street: the preflop round, not the flop the board has moved to."""
    hand = stacked_hand(HOLES, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, CALL)
    deal_next_street(hand)
    apply_action(hand, 2, CALL)
    apply_action(hand, 3, CHECK)

    assert hand.history.events[3:] == (
        ActionTaken(1, CALL, 10, False),
        StreetDealt(Street.FLOP, tuple(cards("2d")), tuple(cards("2c 7d 9h"))),
        ActionTaken(2, CALL, 5, False),
        ActionTaken(3, CHECK, 0, False),
        BettingRoundCompleted(Street.PREFLOP),
    )
    start_betting_round(hand)
    assert hand.history.events[-1] == BettingRoundStarted(Street.FLOP)

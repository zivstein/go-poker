"""Adversarial validation of what the Hold'em operations do and do not record (ADR 0004 §1, §4, §8).

The showdown and settlement operations record exactly `ShowdownStarted`, `ShowdownDecided` and `HandSettled`; the
derived reads and the orchestration record nothing; and the low-level operations record the call order they are given,
even an order the flow would never produce.
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
    HandSettled,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.hand_strength import hand_strength
from go_poker.game.variants.texas_holdem.showdown import apply_showdown_action, settle_hand, start_showdown

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


def test_each_showdown_decision_and_the_settlement_append_exactly_their_own_event(stacked_hand: StackedHand) -> None:
    """Every show or muck appends one `ShowdownDecided` and nothing else; the settlement they end in appends exactly
    `HandSettled`. The history taken at the start of the showdown is unchanged and stays incomplete."""
    hand = stacked_hand(HOLES, BOARD)
    checked_down_to_showdown(hand)
    at_showdown: HandHistory = hand.history
    assert hand.showdown is not None and hand.settlement is None
    assert at_showdown.events[-1] == ShowdownStarted(ShowdownKind.INTERACTIVE, (2, 3, 1))
    assert not at_showdown.is_complete

    expected = list(at_showdown.events)
    while (decider := current_actor(hand)) is not None:
        decision = ShowdownAction.SHOW if decider % 2 else ShowdownAction.MUCK
        act(hand, decider, decision)
        if hand.settlement is None:
            expected.append(ShowdownDecided(decider, decision))
            assert hand.history.events == (*expected,)
        else:
            expected += [ShowdownDecided(decider, decision), HandSettled(hand.settlement)]

    assert hand.settlement is not None
    assert hand.history.events == (*expected,)
    assert [event for event in hand.history.events if isinstance(event, ShowdownDecided)] == [
        ShowdownDecided(2, ShowdownAction.MUCK),
        ShowdownDecided(3, ShowdownAction.SHOW),
        ShowdownDecided(1, ShowdownAction.SHOW),
    ]
    assert hand.history.is_complete and hand.history.settlement == hand.settlement
    assert not at_showdown.is_complete and at_showdown.events == hand.history.events[: len(at_showdown.events)]


def test_the_low_level_showdown_and_settlement_operations_append_exactly_their_own_events(
    stacked_hand: StackedHand,
) -> None:
    """An all-in runout started, dealt and settled by the low-level operations: starting appends exactly
    `ShowdownStarted`, dealing appends the streets, settling appends exactly `HandSettled` (never a second start), and
    every rejected call on the settled hand leaves the history unchanged."""
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD, stacks={1: 100, 2: 100})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, Action(ActionType.RAISE, 100))
    apply_action(hand, 2, CALL)
    before = hand.history

    start_showdown(hand)
    assert hand.history.events == (*before.events, ShowdownStarted(ShowdownKind.ALL_IN, (2, 1)))
    for _ in range(3):
        deal_next_street(hand)
    dealt = hand.history
    assert [event.street for event in dealt.events[-3:] if isinstance(event, StreetDealt)] == [
        Street.FLOP,
        Street.TURN,
        Street.RIVER,
    ]

    settle_hand(hand)
    assert hand.settlement is not None
    assert hand.history.events == (*dealt.events, HandSettled(hand.settlement))
    settled = hand.history
    with pytest.raises(HandAlreadySettledError):
        settle_hand(hand)
    with pytest.raises(HandAlreadySettledError):
        start_showdown(hand)
    with pytest.raises(HandAlreadySettledError):
        apply_showdown_action(hand, 2, ShowdownAction.SHOW)
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
    assert hand.history == settled


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

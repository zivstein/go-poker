"""The history of orchestrated hands: `hand_flow` records nothing itself (ADR 0004 §1), so a hand played through
`begin_hand` and `act` has exactly the events of the low-level calls those make.

Hands are built by the shared `stacked_hand` fixture, so every card is known and written out here independently. The
three seats are the button (1), the small blind (2) and the big blind (3); blinds are 5/10. Burned cards are the first
cards no hole card or board card uses, in deck order (2d, 2h, 2s). Showdown and settlement events are recorded in a
later Cycle, so these histories end at the last betting or dealing event.
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
    ChipsReturned,
    HandEvent,
    HandHistory,
    HandParticipant,
    HandStarted,
    HoleCardsDealt,
    SeatHoleCards,
    StreetDealt,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
BOARD = "2c 7d 9h Jc Ks"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}

type StackedHand = Callable[..., PokerHand]
type Cards = Callable[[str], list[Card]]


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def three_handed_start(stack: int = 1000) -> HandStarted:
    return HandStarted(
        1,
        (
            HandParticipant(1, "P1", Position.BTN, Blind.NONE, stack),
            HandParticipant(2, "P2", Position.SB, Blind.SMALL, stack),
            HandParticipant(3, "P3", Position.BB, Blind.BIG, stack),
        ),
    )


def three_handed_dealt(cards: Cards) -> tuple[HandEvent, ...]:
    """The blinds and hole cards `begin_hand` records for the three-handed hand."""
    return (
        BlindsPosted(STAKES, (BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 10, False))),
        HoleCardsDealt(
            tuple(SeatHoleCards(seat, tuple(cards(HOLES[seat]))) for seat in (1, 2, 3)),
        ),
    )


def flop(cards: Cards) -> StreetDealt:
    return StreetDealt(Street.FLOP, tuple(cards("2d")), tuple(cards("2c 7d 9h")))


def turn(cards: Cards) -> StreetDealt:
    return StreetDealt(Street.TURN, tuple(cards("2h")), tuple(cards("Jc")))


def river(cards: Cards) -> StreetDealt:
    return StreetDealt(Street.RIVER, tuple(cards("2s")), tuple(cards("Ks")))


def test_beginning_a_hand_records_the_blinds_then_the_hole_cards(stacked_hand: StackedHand, cards: Cards) -> None:
    """`begin_hand` posts the blinds, then deals: the history holds exactly those two events after `HandStarted`."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)

    assert hand.history == HandHistory((three_handed_start(), *three_handed_dealt(cards)))


def test_a_hand_folded_to_the_big_blind_records_its_actions_and_the_returned_small_blind_excess(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """The button and small blind fold: the big blind's 5 unmatched chips go back and the preflop round completes."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    act(hand, 1, FOLD)
    act(hand, 2, FOLD)

    assert hand.history == HandHistory(
        (
            three_handed_start(),
            *three_handed_dealt(cards),
            ActionTaken(1, FOLD, 0, False),
            ActionTaken(2, FOLD, 0, False),
            ChipsReturned(3, 5),
            BettingRoundCompleted(Street.PREFLOP),
        )
    )


def test_a_hand_checked_down_to_the_river_records_every_street_and_round_in_order(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """Call, call, check preflop, then three checks on each street: every deal is followed by its round start and its
    completion comes after the last check."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(3):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)

    def checks() -> tuple[HandEvent, ...]:
        return tuple(ActionTaken(seat, CHECK, 0, False) for seat in (2, 3, 1))

    assert hand.history == HandHistory(
        (
            three_handed_start(),
            *three_handed_dealt(cards),
            ActionTaken(1, CALL, 10, False),
            ActionTaken(2, CALL, 5, False),
            ActionTaken(3, CHECK, 0, False),
            BettingRoundCompleted(Street.PREFLOP),
            flop(cards),
            BettingRoundStarted(Street.FLOP),
            *checks(),
            BettingRoundCompleted(Street.FLOP),
            turn(cards),
            BettingRoundStarted(Street.TURN),
            *checks(),
            BettingRoundCompleted(Street.TURN),
            river(cards),
            BettingRoundStarted(Street.RIVER),
            *checks(),
            BettingRoundCompleted(Street.RIVER),
        )
    )


def test_an_all_in_runout_dealt_by_the_flow_records_its_streets_without_any_round(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """Everyone is all-in preflop with 100 chips: the flow deals the whole board, recording the three streets after the
    preflop completion and no betting round start."""
    hand = stacked_hand(HOLES, BOARD, stacks={1: 100, 2: 100, 3: 100})
    begin_hand(hand, STAKES)
    act(hand, 1, raise_to(100))
    act(hand, 2, CALL)
    act(hand, 3, CALL)

    assert hand.history == HandHistory(
        (
            three_handed_start(100),
            *three_handed_dealt(cards),
            ActionTaken(1, raise_to(100), 100, True),
            ActionTaken(2, CALL, 95, True),
            ActionTaken(3, CALL, 90, True),
            BettingRoundCompleted(Street.PREFLOP),
            flop(cards),
            turn(cards),
            river(cards),
        )
    )


def test_blinds_that_end_the_betting_are_recorded_before_the_hole_cards(
    stacked_hand: StackedHand, cards: Cards
) -> None:
    """Heads-up with an all-in small blind of 3 and big blind of 7, the blinds alone complete the round, and
    `begin_hand` posts them before it deals: the completion comes before the hole cards, and the flow then runs the
    board out."""
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD, stacks={1: 3, 2: 7})
    begin_hand(hand, STAKES)

    assert hand.history == HandHistory(
        (
            HandStarted(
                1,
                (
                    HandParticipant(1, "P1", Position.BTN, Blind.SMALL, 3),
                    HandParticipant(2, "P2", Position.BB, Blind.BIG, 7),
                ),
            ),
            BlindsPosted(STAKES, (BlindPost(1, Blind.SMALL, 3, True), BlindPost(2, Blind.BIG, 7, True))),
            ChipsReturned(2, 4),
            BettingRoundCompleted(Street.PREFLOP),
            HoleCardsDealt((SeatHoleCards(1, tuple(cards("Ah Ad"))), SeatHoleCards(2, tuple(cards("Kd Kh"))))),
            flop(cards),
            turn(cards),
            river(cards),
        )
    )


def test_the_flow_and_the_matching_low_level_calls_give_equal_histories(stacked_hand: StackedHand) -> None:
    """The same stacked deck played through `begin_hand` and `act`, and through the low-level calls they make, ends
    with equal histories: the flow records nothing of its own."""
    flow = stacked_hand(HOLES, BOARD)
    begin_hand(flow, STAKES)
    act(flow, 1, raise_to(30))
    act(flow, 2, CALL)
    act(flow, 3, FOLD)
    act(flow, 2, Action(ActionType.BET, 40))
    act(flow, 1, FOLD)

    low = stacked_hand(HOLES, BOARD)
    initialize_betting(low, STAKES)
    deal_hole_cards(low)
    apply_action(low, 1, raise_to(30))
    apply_action(low, 2, CALL)
    apply_action(low, 3, FOLD)
    deal_next_street(low)
    start_betting_round(low)
    apply_action(low, 2, Action(ActionType.BET, 40))
    apply_action(low, 1, FOLD)

    assert flow.history == low.history
    assert flow.history.events[-2:] == (ChipsReturned(2, 40), BettingRoundCompleted(Street.FLOP))


def test_the_flow_and_the_low_level_calls_give_equal_histories_for_an_all_in_runout(
    stacked_hand: StackedHand,
) -> None:
    """The flow's runout deals the remaining streets exactly as calling `deal_next_street` three times does."""
    stacks = {1: 100, 2: 100, 3: 100}
    flow = stacked_hand(HOLES, BOARD, stacks=stacks)
    begin_hand(flow, STAKES)
    for seat, action in ((1, raise_to(100)), (2, CALL), (3, CALL)):
        act(flow, seat, action)

    low = stacked_hand(HOLES, BOARD, stacks=stacks)
    initialize_betting(low, STAKES)
    deal_hole_cards(low)
    for seat, action in ((1, raise_to(100)), (2, CALL), (3, CALL)):
        apply_action(low, seat, action)
    for _ in range(3):
        deal_next_street(low)

    assert flow.history == low.history

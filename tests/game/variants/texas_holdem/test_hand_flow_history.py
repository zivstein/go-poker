"""The history of orchestrated hands: `hand_flow` records nothing itself (ADR 0004 §1), so a hand played through
`begin_hand` and `act` has exactly the events of the low-level calls those make.

Hands are built by the shared `stacked_hand` fixture, so every card is known and written out here independently. The
three seats are the button (1), the small blind (2) and the big blind (3); blinds are 5/10. Burned cards are the first
cards no hole card or board card uses, in deck order (2d, 2h, 2s). Seat 2 (Kd Kh) makes three kings on the board, seat 1
(Ah Ad) a pair of aces and seat 3 (3s 4s) king-high, so seat 2 wins every contested hand here. Every history ends with
`HandSettled`; a contested hand has its `ShowdownStarted` right after the betting that decided it, and an all-in runout
is dealt after it.
"""

from collections.abc import Callable

from go_poker.core.card import Card
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import Pot
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
    HandSettled,
    HandStarted,
    HoleCardsDealt,
    SeatHoleCards,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.settlement import PotAward, Settlement
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand
from go_poker.game.variants.texas_holdem.showdown import settle_hand, start_showdown

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK
# What each seat's hole cards make with the board below.
RANKS = {
    1: HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9)),
    2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9)),
    3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
}
BOARD = "2c 7d 9h Jc Ks"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}

type StackedHand = Callable[..., PokerHand]
type Cards = Callable[[str], list[Card]]
type Replay = Callable[[PokerHand], object]
type Order = Callable[[HandHistory], None]


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


def settled(*awards: tuple[int, set[int], tuple[tuple[int, int], ...]], shown: tuple[int, ...] = ()) -> HandSettled:
    """`HandSettled` of pots given as (amount, eligible seats, shares), with the ranks of the shown seats."""
    return HandSettled(
        Settlement(
            tuple(PotAward(Pot(amount, frozenset(eligible)), shares) for amount, eligible, shares in awards),
            tuple((seat, RANKS[seat]) for seat in shown),
        )
    )


def limp() -> tuple[HandEvent, ...]:
    """Call, call, check: the preflop round with nobody raising."""
    return (
        ActionTaken(1, CALL, 10, False),
        ActionTaken(2, CALL, 5, False),
        ActionTaken(3, CHECK, 0, False),
        BettingRoundCompleted(Street.PREFLOP),
    )


def checks(street: Street) -> tuple[HandEvent, ...]:
    """A street's round checked through, from the first seat left of the button."""
    return (
        BettingRoundStarted(street),
        *(ActionTaken(seat, CHECK, 0, False) for seat in (2, 3, 1)),
        BettingRoundCompleted(street),
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


def test_a_hand_folded_to_the_big_blind_records_its_actions_the_returned_excess_and_an_uncontested_settlement(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
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
            settled((10, {3}, ((3, 10),))),
        )
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_a_hand_checked_down_to_the_river_records_every_street_and_round_in_order(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    """Call, call, check preflop, then three checks on each street: every deal is followed by its round start and its
    completion comes after the last check. The interactive showdown then starts right after the river round, in
    decision order from the first seat left of the button, and records each decision: seat 2 shows, seat 3 mucks and
    seat 1 shows, so seat 2 wins the whole pot with the best of the two shown hands."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(3):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)
    assert not hand.history.is_complete
    assert hand.history.settlement is None
    for seat, decision in ((2, SHOW), (3, MUCK), (1, SHOW)):
        act(hand, seat, decision)

    assert hand.history == HandHistory(
        (
            three_handed_start(),
            *three_handed_dealt(cards),
            *limp(),
            flop(cards),
            *checks(Street.FLOP),
            turn(cards),
            *checks(Street.TURN),
            river(cards),
            *checks(Street.RIVER),
            ShowdownStarted(ShowdownKind.INTERACTIVE, (2, 3, 1)),
            ShowdownDecided(2, SHOW),
            ShowdownDecided(3, MUCK),
            ShowdownDecided(1, SHOW),
            settled((30, {1, 2, 3}, ((2, 30),)), shown=(1, 2)),
        )
    )
    assert hand.history.is_complete
    assert hand.history.settlement == hand.settlement
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_an_all_in_runout_dealt_by_the_flow_records_its_streets_without_any_round(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    """Everyone is all-in preflop with 100 chips: the all-in showdown starts right after the preflop completion, before
    the flow deals the whole board, and the three streets have no betting round start."""
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
            ShowdownStarted(ShowdownKind.ALL_IN, (2, 3, 1)),
            flop(cards),
            turn(cards),
            river(cards),
            settled((300, {1, 2, 3}, ((2, 300),)), shown=(1, 2, 3)),
        )
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_blinds_that_end_the_betting_are_recorded_before_the_hole_cards(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    """Heads-up with an all-in small blind of 3 and big blind of 7, the blinds alone complete the round, and
    `begin_hand` posts them before it deals: the completion comes before the hole cards, and the all-in showdown starts
    after the hole cards, before the flow runs the board out."""
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
            ShowdownStarted(ShowdownKind.ALL_IN, (2, 1)),
            flop(cards),
            turn(cards),
            river(cards),
            settled((6, {1, 2}, ((2, 6),)), shown=(1, 2)),
        )
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


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
    assert flow.settlement is not None

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
    settle_hand(low)

    assert flow.history == low.history
    assert flow.history.events[-3:-1] == (ChipsReturned(2, 40), BettingRoundCompleted(Street.FLOP))
    assert flow.history.events[-1] == settled((30, {2}, ((2, 30),)), (40, {2}, ((2, 40),)))


def test_the_flow_and_the_low_level_calls_give_equal_histories_for_an_all_in_runout(
    stacked_hand: StackedHand,
) -> None:
    """The flow's runout equals starting the all-in showdown right after the betting, dealing the three streets and then
    settling: the flow records nothing of its own. (Dealing first and settling directly records the showdown start
    later, which the flow never does.)"""
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
    start_showdown(low)
    for _ in range(3):
        deal_next_street(low)
    settle_hand(low)

    assert flow.history == low.history


def all_in_prefix(cards: Cards, rounds: tuple[Street, ...]) -> tuple[HandEvent, ...]:
    """The three-handed hand with 200 for seats 2 and 3 up to the all-in round: a limp, then each street in `rounds`
    checked through and dealt."""
    dealt = {Street.FLOP: flop(cards), Street.TURN: turn(cards), Street.RIVER: river(cards)}
    events: list[HandEvent] = [*three_handed_dealt(cards), *limp()]
    for street in rounds:
        events += [dealt[street], *checks(street)]
    return (three_handed_start_with_stacks(), *events)


def three_handed_start_with_stacks() -> HandStarted:
    return HandStarted(
        1,
        (
            HandParticipant(1, "P1", Position.BTN, Blind.NONE, 1000),
            HandParticipant(2, "P2", Position.SB, Blind.SMALL, 200),
            HandParticipant(3, "P3", Position.BB, Blind.BIG, 200),
        ),
    )


def all_in_round(street: Street) -> tuple[HandEvent, ...]:
    """Seat 2 bets its last 190, seat 3 calls all-in and seat 1 calls: nobody can act, so betting is closed."""
    return (
        BettingRoundStarted(street),
        ActionTaken(2, Action(ActionType.BET, 190), 190, True),
        ActionTaken(3, CALL, 190, True),
        ActionTaken(1, CALL, 190, False),
        BettingRoundCompleted(street),
    )


def play_all_in_round(hand: PokerHand) -> None:
    act(hand, 2, Action(ActionType.BET, 190))
    act(hand, 3, CALL)
    act(hand, 1, CALL)


def test_an_all_in_on_the_flop_starts_its_showdown_before_the_turn_and_river(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    hand = stacked_hand(HOLES, BOARD, stacks={1: 1000, 2: 200, 3: 200})
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    play_all_in_round(hand)

    assert hand.history == HandHistory(
        (
            *all_in_prefix(cards, ()),
            flop(cards),
            *all_in_round(Street.FLOP),
            ShowdownStarted(ShowdownKind.ALL_IN, (2, 3, 1)),
            turn(cards),
            river(cards),
            settled((600, {1, 2, 3}, ((2, 600),)), shown=(1, 2, 3)),
        )
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_an_all_in_on_the_turn_starts_its_showdown_before_the_river(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    hand = stacked_hand(HOLES, BOARD, stacks={1: 1000, 2: 200, 3: 200})
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for seat in (2, 3, 1):
        act(hand, seat, CHECK)
    play_all_in_round(hand)

    assert hand.history == HandHistory(
        (
            *all_in_prefix(cards, (Street.FLOP,)),
            turn(cards),
            *all_in_round(Street.TURN),
            ShowdownStarted(ShowdownKind.ALL_IN, (2, 3, 1)),
            river(cards),
            settled((600, {1, 2, 3}, ((2, 600),)), shown=(1, 2, 3)),
        )
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_an_all_in_decided_by_the_river_round_has_no_runout_streets(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    hand = stacked_hand(HOLES, BOARD, stacks={1: 1000, 2: 200, 3: 200})
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(2):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)
    play_all_in_round(hand)

    assert hand.history == HandHistory(
        (
            *all_in_prefix(cards, (Street.FLOP, Street.TURN)),
            river(cards),
            *all_in_round(Street.RIVER),
            ShowdownStarted(ShowdownKind.ALL_IN, (2, 3, 1)),
            settled((600, {1, 2, 3}, ((2, 600),)), shown=(1, 2, 3)),
        )
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_a_river_showdown_starts_with_the_last_aggressor_and_records_each_decision(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    """Seat 3 bets the river and the others call: the decision order starts with seat 3 and goes clockwise, 3 1 2. Seat
    3 and seat 2 show, seat 1 mucks, and the pot goes to seat 2."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(2):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)
    for seat, action in ((2, CHECK), (3, Action(ActionType.BET, 20)), (1, CALL), (2, CALL)):
        act(hand, seat, action)
    for seat, decision in ((3, SHOW), (1, MUCK), (2, SHOW)):
        act(hand, seat, decision)

    assert hand.history.events[-11:] == (
        BettingRoundStarted(Street.RIVER),
        ActionTaken(2, CHECK, 0, False),
        ActionTaken(3, Action(ActionType.BET, 20), 20, False),
        ActionTaken(1, CALL, 20, False),
        ActionTaken(2, CALL, 20, False),
        BettingRoundCompleted(Street.RIVER),
        ShowdownStarted(ShowdownKind.INTERACTIVE, (3, 1, 2)),
        ShowdownDecided(3, SHOW),
        ShowdownDecided(1, MUCK),
        ShowdownDecided(2, SHOW),
        settled((90, {1, 2, 3}, ((2, 90),)), shown=(2, 3)),
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def heads_up_checked_to_the_river(stacked_hand: StackedHand) -> PokerHand:
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD)
    begin_hand(hand, STAKES)
    act(hand, 1, CALL)
    act(hand, 2, CHECK)
    for _ in range(3):
        act(hand, 2, CHECK)
        act(hand, 1, CHECK)
    return hand


def test_a_heads_up_showdown_ends_at_the_first_muck_without_asking_the_last_contender(
    stacked_hand: StackedHand, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    """The big blind decides first heads-up. Its muck leaves one contender, who is paid unshown and never decides."""
    hand = heads_up_checked_to_the_river(stacked_hand)
    act(hand, 2, MUCK)

    assert hand.history.events[-3:] == (
        ShowdownStarted(ShowdownKind.INTERACTIVE, (2, 1)),
        ShowdownDecided(2, MUCK),
        settled((20, {1, 2}, ((1, 20),))),
    )
    assert hand.history.is_complete
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_a_three_way_showdown_ends_when_the_second_muck_leaves_one_contender(
    stacked_hand: StackedHand, cards: Cards, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(3):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)
    act(hand, 2, MUCK)
    act(hand, 3, MUCK)

    assert hand.history.events[-4:] == (
        ShowdownStarted(ShowdownKind.INTERACTIVE, (2, 3, 1)),
        ShowdownDecided(2, MUCK),
        ShowdownDecided(3, MUCK),
        settled((30, {1, 2, 3}, ((1, 30),))),
    )
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_a_seat_that_showed_is_ranked_even_when_it_is_the_last_contender(
    stacked_hand: StackedHand, replay_facts: Replay, assert_orchestrated_order: Order
) -> None:
    """Seat 2 shows and seats 3 and 1 muck: the last contender is seat 2, who did show, so it alone is ranked."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    for seat, action in ((1, CALL), (2, CALL), (3, CHECK)):
        act(hand, seat, action)
    for _ in range(3):
        for seat in (2, 3, 1):
            act(hand, seat, CHECK)
    act(hand, 2, SHOW)
    act(hand, 3, MUCK)

    # Seat 1 is still asked: one muck leaves two contenders.
    assert not hand.history.is_complete
    act(hand, 1, MUCK)
    assert hand.history.events[-1] == settled((30, {1, 2, 3}, ((2, 30),)), shown=(2,))
    replay_facts(hand)
    assert_orchestrated_order(hand.history)

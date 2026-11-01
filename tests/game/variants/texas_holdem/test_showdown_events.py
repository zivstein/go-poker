"""The showdown and settlement events recorded by the low-level Hold'em operations (ADR 0004 §1, §3, §4, §7, §10).

`start_showdown` records `ShowdownStarted`, `apply_showdown_action` one `ShowdownDecided`, and `settle_hand` records
`HandSettled`, preceded by `ShowdownStarted` only when it builds the `ALL_IN` showdown itself. The low-level order is
faithful, never normalized: a caller that deals the board before settling directly has the showdown start after the
streets, which the orchestrated flow never produces.

Every hand is built by the shared `stacked_hand` fixture, so every card is written out here. Unless a test says
otherwise the three seats are the button (1), the small blind (2) and the big blind (3), blinds are 5/10, seat 2 holds
three kings on the default board, seat 1 a pair of aces and seat 3 king-high, so seat 2 wins every contested showdown
that is not set up otherwise. Completed histories are also folded again with the shared `fold_history`, which checks
the settlement facts from the history alone.
"""

from collections.abc import Callable
from typing import Any

import pytest

from go_poker.core.card import Card
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import Pot
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.hand_history import (
    BettingRoundCompleted,
    HandHistory,
    HandSettled,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.settlement import PotAward, Settlement, SettlementInvariantError
from go_poker.game.showdown import NotShowdownTurnError, Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import InvalidHoleCardCountError, deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand
from go_poker.game.variants.texas_holdem.showdown import (
    IncompleteBoardError,
    ShowdownAlreadyStartedError,
    ShowdownIncompleteError,
    ShowdownNotReadyError,
    ShowdownNotStartedError,
    UncontestedHandError,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK
ALL_IN = ShowdownKind.ALL_IN
INTERACTIVE = ShowdownKind.INTERACTIVE

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
ROYAL_FLUSH_BOARD = "As Ks Qs Js Ts"
# What each seat's hole cards make with the default board.
RANKS = {
    1: HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9)),
    2: HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9)),
    3: HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4)),
}
ROYAL = HandRank(HandCategory.STRAIGHT_FLUSH, (14,))

type NewHand = Callable[..., PokerHand]
type Cards = Callable[[str], list[Card]]
type FoldHistory = Callable[[HandHistory], Any]
type ReplayFacts = Callable[[PokerHand], Any]


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    for seat, action in actions:
        apply_action(hand, seat, action)


def next_street(hand: PokerHand) -> None:
    deal_next_street(hand)
    start_betting_round(hand)


def check_street(hand: PokerHand) -> None:
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


def call_preflop(hand: PokerHand) -> None:
    """Everyone calls the big blind and the big blind checks."""
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        apply_action(hand, actor, CHECK if hand.betting.pending_actors == {actor} else CALL)


def check_to(hand: PokerHand, street: Street) -> None:
    """From a hand that has completed its preflop round, check every street up to and including `street`."""
    while hand.street is not street:
        next_street(hand)
        check_street(hand)


def deal_remaining_streets(hand: PokerHand) -> None:
    while hand.street is not Street.RIVER:
        deal_next_street(hand)


def settled_event(
    *awards: tuple[int, set[int], tuple[tuple[int, int], ...]], ranks: dict[int, HandRank] | None = None
) -> HandSettled:
    """`HandSettled` of pots given as (amount, eligible seats, shares), with the ranks of the shown seats."""
    return HandSettled(
        Settlement(
            tuple(PotAward(Pot(amount, frozenset(eligible)), shares) for amount, eligible, shares in awards),
            tuple((ranks or {}).items()),
        )
    )


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    """A stacked hand with its blinds posted and hole cards dealt; takes optional stacks, holes, board and button."""

    def build(
        stacks: dict[int, int] | None = None,
        holes: dict[int, str] | None = None,
        board: str = BOARD,
        button: int = 1,
    ) -> PokerHand:
        hand = stacked_hand(holes or HOLES, board, button=button, stacks=stacks)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        return hand

    return build


@pytest.fixture
def river_hand(new_hand: NewHand) -> PokerHand:
    """Checked down to a completed river round with no bet: the interactive showdown can start."""
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.RIVER)
    return hand


@pytest.fixture
def all_in_hand(new_hand: NewHand) -> PokerHand:
    """All three seats all-in preflop for 100 each, the board not dealt: an all-in showdown is certain."""
    hand = new_hand(stacks={1: 100, 2: 100, 3: 100})
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    return hand


def assert_final_stacks_replay(hand: PokerHand, fold_history: FoldHistory, replay_facts: ReplayFacts) -> None:
    """The history alone folds to the live hand, and the stacks it folds to are the live stacks after the payout."""
    assert hand.history.is_complete and hand.history.settlement == hand.settlement
    facts = fold_history(hand.history)
    assert {seat: seat_facts.stack for seat, seat_facts in facts.seats.items()} == {
        state.seat_number: state.player.stack for state in hand.players
    }
    replay_facts(hand)


# =============================================================================
# START: ShowdownStarted
# =============================================================================


def test_starting_an_interactive_showdown_records_its_decision_order(river_hand: PokerHand) -> None:
    """With no river bet the first live seat left of the button decides first: 2, 3, then the button."""
    before = river_hand.history

    start_showdown(river_hand)

    assert river_hand.history.events == (*before.events, ShowdownStarted(INTERACTIVE, (2, 3, 1)))
    assert before.events[-1] == BettingRoundCompleted(Street.RIVER)
    assert river_hand.showdown == Showdown(INTERACTIVE, (2, 3, 1), ())


def test_the_last_river_aggressor_decides_first_and_the_started_order_records_it(new_hand: NewHand) -> None:
    hand = new_hand()
    call_preflop(hand)
    check_to(hand, Street.TURN)
    next_street(hand)
    play(hand, (2, CHECK), (3, bet(20)), (1, CALL), (2, CALL))
    before = hand.history

    start_showdown(hand)

    assert hand.history.events == (*before.events, ShowdownStarted(INTERACTIVE, (3, 1, 2)))


def test_the_order_of_an_all_in_showdown_is_the_canonical_storage_order_not_a_sequence(new_hand: NewHand) -> None:
    """Whoever raised last, the all-in start lists the live seats clockwise from the first seat left of the button."""
    hand = new_hand(stacks={1: 100, 2: 100, 3: 100})
    play(hand, (1, raise_to(100)), (2, CALL), (3, CALL))
    before = hand.history

    start_showdown(hand)

    assert hand.history.events == (*before.events, ShowdownStarted(ALL_IN, (2, 3, 1)))
    assert hand.showdown == Showdown(ALL_IN, (2, 3, 1), ())


def test_a_folded_seat_is_not_in_the_started_order(new_hand: NewHand) -> None:
    hand = new_hand(stacks={1: 100, 2: 100, 3: 100})
    play(hand, (1, raise_to(100)), (2, FOLD), (3, CALL))

    start_showdown(hand)

    assert hand.history.events[-1] == ShowdownStarted(ALL_IN, (3, 1))


def test_starting_then_dealing_then_settling_gives_the_orchestrated_history(
    stacked_hand: NewHand, all_in_hand: PokerHand
) -> None:
    """A low-level caller that starts the all-in showdown before dealing the runout records exactly what the flow does:
    the start right after the completing round, then the streets, then `HandSettled`."""
    flow = stacked_hand(HOLES, BOARD, stacks={1: 100, 2: 100, 3: 100})
    begin_hand(flow, STAKES)
    for seat, action in ((1, raise_to(100)), (2, CALL), (3, CALL)):
        act(flow, seat, action)

    low = all_in_hand
    start_showdown(low)
    deal_remaining_streets(low)
    settle_hand(low)

    assert low.history == flow.history
    assert [type(event).__name__ for event in low.history.events[-6:]] == [
        "BettingRoundCompleted",
        "ShowdownStarted",
        "StreetDealt",
        "StreetDealt",
        "StreetDealt",
        "HandSettled",
    ]


# =============================================================================
# DECISIONS: ShowdownDecided
# =============================================================================


def test_each_decision_appends_one_event_in_action_order(river_hand: PokerHand) -> None:
    start_showdown(river_hand)
    before = river_hand.history

    apply_showdown_action(river_hand, 2, SHOW)
    apply_showdown_action(river_hand, 3, MUCK)
    apply_showdown_action(river_hand, 1, SHOW)

    assert river_hand.history.events == (
        *before.events,
        ShowdownDecided(2, SHOW),
        ShowdownDecided(3, MUCK),
        ShowdownDecided(1, SHOW),
    )
    assert river_hand.showdown is not None
    assert river_hand.showdown.decisions == (SHOW, MUCK, SHOW)
    assert river_hand.settlement is None and not river_hand.history.is_complete


def test_heads_up_the_first_muck_leaves_the_other_seat_unasked_and_settles_unshown(stacked_hand: NewHand) -> None:
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2]}, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CHECK))
    check_to(hand, Street.RIVER)
    start_showdown(hand)
    assert hand.showdown is not None and hand.showdown.order == (2, 1)

    apply_showdown_action(hand, 2, MUCK)
    settle_hand(hand)

    assert hand.history.events[-3:] == (
        ShowdownStarted(INTERACTIVE, (2, 1)),
        ShowdownDecided(2, MUCK),
        settled_event((20, {1, 2}, ((1, 20),))),
    )
    assert hand.settlement is not None and hand.settlement.showdown_ranks == ()
    with pytest.raises(HandAlreadySettledError):
        apply_showdown_action(hand, 1, SHOW)


def test_three_way_two_mucks_leave_the_third_seat_unasked(river_hand: PokerHand) -> None:
    start_showdown(river_hand)

    apply_showdown_action(river_hand, 2, MUCK)
    apply_showdown_action(river_hand, 3, MUCK)
    settle_hand(river_hand)

    assert river_hand.history.events[-4:] == (
        ShowdownStarted(INTERACTIVE, (2, 3, 1)),
        ShowdownDecided(2, MUCK),
        ShowdownDecided(3, MUCK),
        settled_event((30, {1, 2, 3}, ((1, 30),))),
    )
    assert river_hand.settlement is not None and river_hand.settlement.showdown_ranks == ()


def test_a_show_then_a_muck_still_asks_the_third_seat(river_hand: PokerHand) -> None:
    """One muck leaves two contenders when the first seat showed, so the last seat still decides."""
    start_showdown(river_hand)
    apply_showdown_action(river_hand, 2, SHOW)
    apply_showdown_action(river_hand, 3, MUCK)
    assert river_hand.showdown is not None and river_hand.showdown.current_decider == 1

    apply_showdown_action(river_hand, 1, MUCK)
    settle_hand(river_hand)

    assert river_hand.history.events[-2:] == (
        ShowdownDecided(1, MUCK),
        settled_event((30, {1, 2, 3}, ((2, 30),)), ranks={2: RANKS[2]}),
    )


# =============================================================================
# SETTLEMENT: HandSettled, with or without a started showdown
# =============================================================================


def test_direct_all_in_settlement_records_the_showdown_start_then_the_settlement(all_in_hand: PokerHand) -> None:
    """With no showdown started, `settle_hand` builds the all-in showdown and appends exactly `ShowdownStarted` then
    `HandSettled`; the start equals the showdown it stored."""
    hand = all_in_hand
    deal_remaining_streets(hand)
    before = hand.history
    assert hand.showdown is None

    settle_hand(hand)

    assert hand.showdown == Showdown(ALL_IN, (2, 3, 1), ())
    assert hand.history.events == (
        *before.events,
        ShowdownStarted(hand.showdown.kind, hand.showdown.order),
        settled_event((300, {1, 2, 3}, ((2, 300),)), ranks=RANKS),
    )
    assert hand.history.events[-2] == ShowdownStarted(ALL_IN, (2, 3, 1))


def test_direct_all_in_settlement_after_dealing_is_faithful_not_normalized(
    stacked_hand: NewHand, all_in_hand: PokerHand
) -> None:
    """Dealing the board before settling directly puts the showdown start after the three streets, which makes no
    runout claim, and the history is not the orchestrated one of the same deck, whose showdown starts first."""
    hand = all_in_hand
    deal_remaining_streets(hand)
    settle_hand(hand)

    assert [type(event).__name__ for event in hand.history.events[-6:]] == [
        "BettingRoundCompleted",
        "StreetDealt",
        "StreetDealt",
        "StreetDealt",
        "ShowdownStarted",
        "HandSettled",
    ]
    assert [event.street for event in hand.history.events if isinstance(event, StreetDealt)] == [
        Street.FLOP,
        Street.TURN,
        Street.RIVER,
    ]

    flow = stacked_hand(HOLES, BOARD, stacks={1: 100, 2: 100, 3: 100})
    begin_hand(flow, STAKES)
    for seat, action in ((1, raise_to(100)), (2, CALL), (3, CALL)):
        act(flow, seat, action)
    assert flow.history != hand.history
    assert flow.history.settlement == hand.history.settlement
    assert sorted(map(repr, flow.history.events)) == sorted(map(repr, hand.history.events))  # same facts, other order


def test_an_explicitly_started_all_in_showdown_is_not_started_again_by_settlement(all_in_hand: PokerHand) -> None:
    hand = all_in_hand
    start_showdown(hand)
    deal_remaining_streets(hand)
    before = hand.history

    settle_hand(hand)

    assert hand.settlement is not None
    assert hand.history.events == (*before.events, HandSettled(hand.settlement))
    assert sum(isinstance(event, ShowdownStarted) for event in hand.history.events) == 1


def test_an_interactive_settlement_appends_only_the_settlement(river_hand: PokerHand) -> None:
    start_showdown(river_hand)
    for seat in (2, 3, 1):
        apply_showdown_action(river_hand, seat, SHOW)
    before = river_hand.history

    settle_hand(river_hand)

    assert river_hand.history.events == (
        *before.events,
        settled_event((30, {1, 2, 3}, ((2, 30),)), ranks=RANKS),
    )
    assert river_hand.history.settlement == river_hand.settlement


@pytest.mark.parametrize(
    ("street", "winner", "amount"),
    [(Street.PREFLOP, 3, 10), (Street.FLOP, 2, 30), (Street.TURN, 2, 30), (Street.RIVER, 2, 30)],
)
def test_an_uncontested_hand_records_only_the_settlement_on_every_street(
    new_hand: NewHand, street: Street, winner: int, amount: int
) -> None:
    hand = new_hand()
    if street is Street.PREFLOP:
        play(hand, (1, FOLD), (2, FOLD))
    else:
        call_preflop(hand)
        check_to(hand, {Street.FLOP: Street.PREFLOP, Street.TURN: Street.FLOP, Street.RIVER: Street.TURN}[street])
        next_street(hand)
        play(hand, (2, bet(20)), (3, FOLD), (1, FOLD))
    before = hand.history

    settle_hand(hand)

    assert hand.history.events == (*before.events, settled_event((amount, {winner}, ((winner, amount),))))
    assert not any(isinstance(event, ShowdownStarted | ShowdownDecided) for event in hand.history.events)
    assert hand.showdown is None


def test_a_history_taken_before_settlement_stays_incomplete(river_hand: PokerHand) -> None:
    start_showdown(river_hand)
    mid_hand = river_hand.history
    assert not mid_hand.is_complete and mid_hand.settlement is None

    for seat in (2, 3, 1):
        apply_showdown_action(river_hand, seat, SHOW)
    settle_hand(river_hand)

    assert river_hand.history.is_complete and river_hand.history.settlement == river_hand.settlement
    assert not mid_hand.is_complete and mid_hand.settlement is None
    assert river_hand.history.events[: len(mid_hand.events)] == mid_hand.events


# =============================================================================
# SETTLEMENT FACTS REPLAYED FROM THE HISTORY ALONE
# =============================================================================


def test_two_side_pots_with_different_winners_replay_to_the_live_stacks(
    new_hand: NewHand, fold_history: FoldHistory, replay_facts: ReplayFacts
) -> None:
    """Seat 1 raises to 500 and seats 2 and 3 call all-in for 100 and 200. Seat 2, with the smallest stack, wins the
    300 main pot with three kings; seat 3, with all-in jacks, wins the 200 side pot against seat 1's aces."""
    hand = new_hand(stacks={2: 100, 3: 200}, holes={**HOLES, 3: "Jd Jh"})
    play(hand, (1, raise_to(500)), (2, CALL), (3, CALL))
    deal_remaining_streets(hand)

    settle_hand(hand)

    ranks = {1: RANKS[1], 2: RANKS[2], 3: HandRank(HandCategory.THREE_OF_A_KIND, (11, 13, 9))}
    assert hand.history.events[-1] == settled_event(
        (300, {1, 2, 3}, ((2, 300),)), (200, {1, 3}, ((3, 200),)), ranks=ranks
    )
    assert_final_stacks_replay(hand, fold_history, replay_facts)
    assert {state.seat_number: state.player.stack for state in hand.players} == {1: 800, 2: 300, 3: 200}


def test_a_three_way_odd_chip_split_with_dead_money_in_two_pots_goes_clockwise_from_the_button(
    stacked_hand: NewHand, fold_history: FoldHistory, replay_facts: ReplayFacts
) -> None:
    """Seats 1, 3 and 4 call 10 and play the royal flush on the board, tied; the small blind (seat 2) folds its 5. The
    pots are 20 and 15, dead money in both. Odd chips go first to the seat left of the button, so seat 3 and seat 4 take
    the 20-chip pot's two odd chips, and the button is last."""
    holes = {1: "2c 3d", 2: "2d 3h", 3: "4h 5c", 4: "6d 7h"}
    hand = stacked_hand(holes, ROYAL_FLUSH_BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (4, CALL), (1, CALL), (2, FOLD), (3, CHECK))
    check_to(hand, Street.RIVER)
    start_showdown(hand)
    assert hand.showdown is not None and hand.showdown.order == (3, 4, 1)
    for seat in (3, 4, 1):
        apply_showdown_action(hand, seat, SHOW)

    settle_hand(hand)

    assert hand.history.events[-1] == settled_event(
        (20, {1, 3, 4}, ((3, 7), (4, 7), (1, 6))),
        (15, {1, 3, 4}, ((3, 5), (4, 5), (1, 5))),
        ranks={1: ROYAL, 3: ROYAL, 4: ROYAL},
    )
    assert_final_stacks_replay(hand, fold_history, replay_facts)
    assert {state.seat_number: state.player.stack for state in hand.players} == {1: 1001, 2: 995, 3: 1002, 4: 1002}


def test_a_mucked_seat_stays_eligible_in_the_recorded_pot_but_is_unpaid(
    river_hand: PokerHand, fold_history: FoldHistory, replay_facts: ReplayFacts
) -> None:
    """Seat 2 holds the best hand but mucks: it stays eligible for the pot it contested and wins nothing, so seat 1's
    aces take it, and only the two shown seats are ranked."""
    start_showdown(river_hand)
    for seat, decision in ((2, MUCK), (3, SHOW), (1, SHOW)):
        apply_showdown_action(river_hand, seat, decision)

    settle_hand(river_hand)

    assert river_hand.history.events[-1] == settled_event((30, {1, 2, 3}, ((1, 30),)), ranks={1: RANKS[1], 3: RANKS[3]})
    assert_final_stacks_replay(river_hand, fold_history, replay_facts)


def test_unpaid_all_in_seats_replay_with_zero_stacks_and_stay_all_in(
    all_in_hand: PokerHand, fold_history: FoldHistory, replay_facts: ReplayFacts
) -> None:
    hand = all_in_hand
    deal_remaining_streets(hand)
    settle_hand(hand)

    facts = fold_history(hand.history)

    assert {seat: (seat_facts.stack, seat_facts.all_in) for seat, seat_facts in facts.seats.items()} == {
        1: (0, True),
        2: (300, False),
        3: (0, True),
    }
    assert_final_stacks_replay(hand, fold_history, replay_facts)


def test_folded_dead_money_replays_into_every_pot_of_an_uncontested_hand(
    new_hand: NewHand, fold_history: FoldHistory, replay_facts: ReplayFacts
) -> None:
    """Seat 1 raises to 30 and both call. On the flop seat 3 bets 40, seat 1 raises to 100, seat 2 folds its 30 and seat
    3 calls; on the turn seat 1 bets 50 and seat 3 folds. Seat 1 wins both layers, which hold seat 2's and seat 3's
    folded chips, unshown: the 30-level pot of 90 and the 100-chip layer above it of 200."""
    hand = new_hand()
    play(hand, (1, raise_to(30)), (2, CALL), (3, CALL))
    next_street(hand)
    play(hand, (2, CHECK), (3, bet(40)), (1, raise_to(100)), (2, FOLD), (3, CALL))
    next_street(hand)
    play(hand, (3, CHECK), (1, bet(50)), (3, FOLD))
    before = hand.history

    settle_hand(hand)

    assert hand.history.events == (
        *before.events,
        settled_event((90, {1}, ((1, 90),)), (200, {1}, ((1, 200),))),
    )
    assert_final_stacks_replay(hand, fold_history, replay_facts)
    assert {state.seat_number: state.player.stack for state in hand.players} == {1: 1160, 2: 970, 3: 870}


# =============================================================================
# REJECTIONS LEAVE THE HISTORY ALONE
# =============================================================================


def assert_history_unchanged(hand: PokerHand, error: type[Exception], operation: Callable[[], object]) -> None:
    before = hand.history
    showdown = hand.showdown
    with pytest.raises(error):
        operation()
    assert hand.history == before
    assert hand.showdown is showdown
    assert hand.settlement is None or error is HandAlreadySettledError


def test_every_rejected_start_leaves_the_history_unchanged(
    stacked_hand: NewHand, new_hand: NewHand, river_hand: PokerHand
) -> None:
    unprepared = stacked_hand(HOLES, BOARD)
    assert_history_unchanged(unprepared, BettingNotInitializedError, lambda: start_showdown(unprepared))

    not_ready = new_hand()
    assert_history_unchanged(not_ready, ShowdownNotReadyError, lambda: start_showdown(not_ready))

    uncontested = new_hand()
    play(uncontested, (1, FOLD), (2, FOLD))
    assert_history_unchanged(uncontested, UncontestedHandError, lambda: start_showdown(uncontested))

    start_showdown(river_hand)
    assert_history_unchanged(river_hand, ShowdownAlreadyStartedError, lambda: start_showdown(river_hand))
    for seat in (2, 3, 1):
        apply_showdown_action(river_hand, seat, SHOW)
    settle_hand(river_hand)
    assert_history_unchanged(river_hand, HandAlreadySettledError, lambda: start_showdown(river_hand))


def test_every_rejected_decision_leaves_the_history_unchanged(river_hand: PokerHand, all_in_hand: PokerHand) -> None:
    assert_history_unchanged(river_hand, ShowdownNotStartedError, lambda: apply_showdown_action(river_hand, 2, SHOW))
    start_showdown(river_hand)
    assert_history_unchanged(river_hand, NotShowdownTurnError, lambda: apply_showdown_action(river_hand, 3, SHOW))
    assert_history_unchanged(river_hand, NotShowdownTurnError, lambda: apply_showdown_action(river_hand, 99, MUCK))
    assert_history_unchanged(
        river_hand,
        TypeError,
        lambda: apply_showdown_action(river_hand, 2, CALL),  # type: ignore[arg-type]
    )
    assert_history_unchanged(
        river_hand,
        TypeError,
        lambda: apply_showdown_action(river_hand, 2, "show"),  # type: ignore[arg-type]
    )

    start_showdown(all_in_hand)
    for seat in (2, 3, 1):  # an all-in showdown is complete from the start: no decision is ever accepted
        assert_history_unchanged(
            all_in_hand, NotShowdownTurnError, lambda seat=seat: apply_showdown_action(all_in_hand, seat, SHOW)
        )

    for seat, decision in ((2, SHOW), (3, SHOW), (1, SHOW)):
        apply_showdown_action(river_hand, seat, decision)
    assert_history_unchanged(river_hand, NotShowdownTurnError, lambda: apply_showdown_action(river_hand, 2, SHOW))
    settle_hand(river_hand)
    assert_history_unchanged(river_hand, HandAlreadySettledError, lambda: apply_showdown_action(river_hand, 2, SHOW))


def test_every_rejected_settlement_leaves_the_history_unchanged(
    stacked_hand: NewHand, new_hand: NewHand, river_hand: PokerHand, all_in_hand: PokerHand
) -> None:
    unprepared = stacked_hand(HOLES, BOARD)
    assert_history_unchanged(unprepared, BettingNotInitializedError, lambda: settle_hand(unprepared))

    not_ready = new_hand()
    call_preflop(not_ready)
    check_to(not_ready, Street.TURN)
    deal_next_street(not_ready)  # the river is dealt but its round is not started
    assert_history_unchanged(not_ready, ShowdownNotReadyError, lambda: settle_hand(not_ready))

    assert_history_unchanged(river_hand, ShowdownNotStartedError, lambda: settle_hand(river_hand))
    start_showdown(river_hand)
    assert_history_unchanged(river_hand, ShowdownIncompleteError, lambda: settle_hand(river_hand))

    # A contested all-in hand with an incomplete board is rejected before anything is built or recorded: never a lone
    # `ShowdownStarted`.
    assert_history_unchanged(all_in_hand, IncompleteBoardError, lambda: settle_hand(all_in_hand))
    assert not any(isinstance(event, ShowdownStarted) for event in all_in_hand.history.events)
    assert all_in_hand.showdown is None


def test_a_rejected_direct_settlement_after_the_board_is_dealt_records_no_lone_showdown_start(
    all_in_hand: PokerHand,
) -> None:
    """The rank check fails after the all-in showdown was built, so nothing at all is recorded or stored."""
    hand = all_in_hand
    deal_remaining_streets(hand)
    hand.players[2].hole_cards.pop()  # seat 3 is a shown seat in an all-in showdown, with one hole card
    before = hand.history

    with pytest.raises(InvalidHoleCardCountError):
        settle_hand(hand)

    assert hand.history == before
    assert hand.showdown is None and hand.settlement is None
    assert not any(isinstance(event, ShowdownStarted) for event in hand.history.events)


def test_a_settlement_invariant_violation_records_nothing(
    monkeypatch: pytest.MonkeyPatch, all_in_hand: PokerHand, river_hand: PokerHand
) -> None:
    """A pot invariant violation (an engine defect, forced here) rejects the settlement after the showdown was built:
    no showdown is stored and neither `ShowdownStarted` nor `HandSettled` is recorded, for a direct all-in settlement,
    an interactive one and an uncontested one."""

    def violated(*_args: object) -> object:
        raise SettlementInvariantError("forced")

    monkeypatch.setattr("go_poker.game.settlement._award_pots", violated)
    deal_remaining_streets(all_in_hand)
    assert_history_unchanged(all_in_hand, SettlementInvariantError, lambda: settle_hand(all_in_hand))
    assert all_in_hand.showdown is None and not all_in_hand.history.is_complete

    start_showdown(river_hand)
    for seat in (2, 3, 1):
        apply_showdown_action(river_hand, seat, SHOW)
    assert_history_unchanged(river_hand, SettlementInvariantError, lambda: settle_hand(river_hand))
    assert not river_hand.history.is_complete


def test_a_second_settlement_appends_nothing_on_every_kind_of_hand(
    new_hand: NewHand, all_in_hand: PokerHand, river_hand: PokerHand
) -> None:
    uncontested = new_hand()
    play(uncontested, (1, FOLD), (2, FOLD))
    settle_hand(uncontested)
    deal_remaining_streets(all_in_hand)
    settle_hand(all_in_hand)
    start_showdown(river_hand)
    for seat in (2, 3, 1):
        apply_showdown_action(river_hand, seat, SHOW)
    settle_hand(river_hand)

    for hand in (uncontested, all_in_hand, river_hand):
        before = hand.history
        with pytest.raises(HandAlreadySettledError):
            settle_hand(hand)
        assert hand.history == before
        assert sum(isinstance(event, HandSettled) for event in hand.history.events) == 1

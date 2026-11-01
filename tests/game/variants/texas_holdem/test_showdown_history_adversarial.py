"""QA validation of the showdown and settlement history (Milestone 6, Cycle 4): ordering, atomicity, completeness reads,
the independence of the replay harness, durability and the rule that no rule reads a history.

Hands are stacked with the shared `stacked_hand` fixture. Seats are the button (1), the small blind (2) and the big
blind (3), and a fourth seat (4) acts first preflop when it plays. Blinds are 5/10. On the default board seat 2 (Kd Kh)
makes three kings, seat 1 (Ah Ad) a pair of aces, seat 4 (Qd Qh) a pair of queens and seat 3 (3s 4s) king-high, so the
strength order is 2 > 1 > 4 > 3. Every expectation below is written out from the rules, never read from the engine.
"""

import copy
import dataclasses
import itertools
import random
from collections import Counter
from collections.abc import Callable
from enum import Enum
from typing import Any

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    ChipsReturned,
    HandHistory,
    HandSettled,
    HoleCardsDealt,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import HandAlreadySettledError, PokerHand
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.settlement import PotAward, Settlement
from go_poker.game.showdown import NotShowdownTurnError, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import InvalidHoleCardCountError, deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.showdown import (
    IncompleteBoardError,
    ShowdownAlreadyStartedError,
    ShowdownIncompleteError,
    ShowdownNotReadyError,
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
BOARD = "2c 7d 9h Jc Ks"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s", 4: "Qd Qh"}
STRENGTH_ORDER = (2, 1, 4, 3)  # best first, written from the cards above
STREETS = (Street.FLOP, Street.TURN, Street.RIVER)

type StackedHand = Callable[..., PokerHand]
type FoldHistory = Callable[[HandHistory], Any]
type ReplayFacts = Callable[[PokerHand], Any]
type OrderCheck = Callable[[HandHistory], None]


def holes(*seats: int) -> dict[int, str]:
    return {seat: HOLES[seat] for seat in seats}


def clockwise_after_button(seats: tuple[int, ...]) -> tuple[int, ...]:
    """The canonical order of seats given with the button first: left of the button first, the button last."""
    return (*seats[1:], *seats[:1])


def passive(hand: PokerHand) -> None:
    """The current actor calls or checks."""
    actor = current_actor(hand)
    assert actor is not None
    act(hand, actor, CALL if legal_actions(hand).can_call else CHECK)


def play_passively_to(hand: PokerHand, street: Street) -> None:
    """Check and call until the betting round of `street` is about to be played (its first actor is waiting)."""
    while hand.street is not street:
        passive(hand)


def shove(hand: PokerHand) -> None:
    """The current actor bets or raises everything."""
    actor = current_actor(hand)
    assert actor is not None
    legal = legal_actions(hand)
    assert legal.max_target is not None
    act(hand, actor, Action(ActionType.BET if legal.can_bet else ActionType.RAISE, legal.max_target))


def respond(hand: PokerHand, responses: tuple[str, ...]) -> None:
    for response in responses:
        actor = current_actor(hand)
        assert actor is not None
        act(hand, actor, CALL if response == "call" else FOLD)


# =============================================================================
# ORDERING: the orchestrated runout on every street, every table size
# =============================================================================


@pytest.mark.parametrize("street", [Street.PREFLOP, *STREETS])
@pytest.mark.parametrize(
    "responses", [("call",), ("call", "call"), ("fold", "call"), ("call", "fold")], ids=lambda r: "-".join(r)
)
def test_an_all_in_closes_the_hand_with_the_showdown_start_before_every_runout_street(
    stacked_hand: StackedHand,
    replay_facts: ReplayFacts,
    fold_history: FoldHistory,
    assert_orchestrated_order: OrderCheck,
    street: Street,
    responses: tuple[str, ...],
) -> None:
    """The first actor of `street` shoves its whole stack and each other seat calls all-in or folds. The betting closes
    in that very round, so the history ends `... BettingRoundCompleted(street) ShowdownStarted(ALL_IN, live seats) <the
    streets still to deal, with no round> HandSettled`, however many seats are live and whichever street it is (the
    river deals none)."""
    seats = (1, 2, 3)[: len(responses) + 1]
    hand = stacked_hand(holes(*seats), BOARD, stacks=dict.fromkeys(seats, 300))
    begin_hand(hand, STAKES)
    play_passively_to(hand, street)
    shove(hand)
    respond(hand, responses)

    assert hand.settlement is not None
    events = hand.history.events
    live = [seat for seat in clockwise_after_button(seats) if seat not in folded_seats(hand)]
    assert len(live) >= 2
    remaining = STREETS[STREETS.index(street) + 1 :] if street is not Street.PREFLOP else STREETS
    tail = events[-(2 + len(remaining) + 1) :]
    assert tail == (
        BettingRoundCompleted(street),
        ShowdownStarted(ShowdownKind.ALL_IN, tuple(live)),
        *(event for event in events if isinstance(event, StreetDealt) and event.street in remaining),
        events[-1],
    )
    assert isinstance(events[-1], HandSettled)
    assert [event.street for event in events if isinstance(event, StreetDealt)] == [
        street for street in STREETS
    ]  # the whole board is dealt exactly once
    assert not any(isinstance(event, ShowdownDecided) for event in events)
    runout_begin = events.index(ShowdownStarted(ShowdownKind.ALL_IN, tuple(live)))
    assert not any(isinstance(event, BettingRoundStarted) for event in events[runout_begin:])
    assert hand.history.is_complete
    replay_facts(hand)
    fold_history(hand.history)
    assert_orchestrated_order(hand.history)


def folded_seats(hand: PokerHand) -> set[int]:
    return {state.seat_number for state in hand.players if state.folded}


@pytest.mark.parametrize("street", [Street.PREFLOP, *STREETS])
@pytest.mark.parametrize("seat_count", [2, 3])
def test_everyone_folding_to_an_all_in_is_uncontested_on_every_street(
    stacked_hand: StackedHand,
    replay_facts: ReplayFacts,
    fold_history: FoldHistory,
    assert_orchestrated_order: OrderCheck,
    street: Street,
    seat_count: int,
) -> None:
    """The first actor shoves and every other seat folds: no showdown event at all, the uncalled shove is returned, the
    round completes and `HandSettled` follows, and the all-in winner is no longer all-in."""
    seats = (1, 2, 3)[:seat_count]
    hand = stacked_hand(holes(*seats), BOARD, stacks=dict.fromkeys(seats, 300))
    begin_hand(hand, STAKES)
    play_passively_to(hand, street)
    shover = current_actor(hand)
    assert shover is not None
    shove(hand)
    respond(hand, ("fold",) * (seat_count - 1))

    assert hand.settlement is not None
    events = hand.history.events
    assert not any(isinstance(event, ShowdownStarted | ShowdownDecided) for event in events)
    assert events[-1] == HandSettled(hand.settlement)
    assert events[-2] == BettingRoundCompleted(street)
    assert isinstance(events[-3], ChipsReturned) and events[-3].seat == shover
    assert set(hand.settlement.payouts) == {shover} and hand.settlement.showdown_ranks == ()
    assert not next(state for state in hand.players if state.seat_number == shover).all_in
    expected_streets = list(STREETS[: STREETS.index(street) + 1]) if street is not Street.PREFLOP else []
    assert [event.street for event in events if isinstance(event, StreetDealt)] == expected_streets
    replay_facts(hand)
    fold_history(hand.history)
    assert_orchestrated_order(hand.history)


def test_a_short_all_in_raised_over_and_folded_to_runs_out_with_the_folder_excluded(
    stacked_hand: StackedHand, replay_facts: ReplayFacts, assert_orchestrated_order: OrderCheck
) -> None:
    """Seat 2 is all-in for 40 on the turn, seat 3 raises it, seat 1 folds. Only seat 3 can still act and has nothing
    to call, so betting is closed: the all-in showdown lists the live seats 2 and 3 only, and the river follows."""
    hand = stacked_hand(holes(1, 2, 3), BOARD, stacks={1: 1000, 2: 50, 3: 1000})
    begin_hand(hand, STAKES)
    play_passively_to(hand, Street.TURN)
    act(hand, 2, Action(ActionType.BET, 40))
    act(hand, 3, Action(ActionType.RAISE, 100))
    act(hand, 1, FOLD)

    events = hand.history.events
    assert events[-6:-1] == (
        ActionTaken(1, FOLD, 0, False),
        ChipsReturned(3, 60),
        BettingRoundCompleted(Street.TURN),
        ShowdownStarted(ShowdownKind.ALL_IN, (2, 3)),
        events[-2],
    )
    assert isinstance(events[-2], StreetDealt) and events[-2].street is Street.RIVER
    assert isinstance(events[-1], HandSettled)
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


def test_blinds_that_leave_only_the_small_blind_all_in_still_start_the_showdown_after_the_hole_cards(
    stacked_hand: StackedHand,
    replay_facts: ReplayFacts,
    fold_history: FoldHistory,
    assert_orchestrated_order: OrderCheck,
) -> None:
    """The heads-up button posts a 3-chip small blind all-in against a covering big blind: the big blind's 7 extra chips
    go back and the round completes before the cards are dealt, so the showdown starts after `HoleCardsDealt`."""
    hand = stacked_hand(holes(1, 2), BOARD, stacks={1: 3, 2: 1000})
    begin_hand(hand, STAKES)

    events = hand.history.events
    kinds = [type(event).__name__ for event in events]
    assert kinds == [
        "HandStarted",
        "BlindsPosted",
        "ChipsReturned",
        "BettingRoundCompleted",
        "HoleCardsDealt",
        "ShowdownStarted",
        "StreetDealt",
        "StreetDealt",
        "StreetDealt",
        "HandSettled",
    ]
    assert events[2] == ChipsReturned(2, 7)
    assert events[5] == ShowdownStarted(ShowdownKind.ALL_IN, (2, 1))
    assert isinstance(events[4], HoleCardsDealt)
    assert hand.settlement is not None and hand.settlement.payouts == {2: 6}
    replay_facts(hand)
    fold_history(hand.history)
    assert_orchestrated_order(hand.history)


def test_a_big_blind_all_in_for_less_than_the_blind_is_called_and_runs_out(
    stacked_hand: StackedHand, replay_facts: ReplayFacts, assert_orchestrated_order: OrderCheck
) -> None:
    """The big blind posts 7 all-in; the heads-up button calls and its extra chips go back. This needs a decision, so
    it is the call, not the blinds, that completes the round."""
    hand = stacked_hand(holes(1, 2), BOARD, stacks={1: 1000, 2: 7})
    begin_hand(hand, STAKES)
    assert current_actor(hand) == 1
    act(hand, 1, CALL)

    kinds = [type(event).__name__ for event in hand.history.events]
    assert kinds[1:] == [
        "BlindsPosted",
        "HoleCardsDealt",
        "ActionTaken",
        "BettingRoundCompleted",
        "ShowdownStarted",
        "StreetDealt",
        "StreetDealt",
        "StreetDealt",
        "HandSettled",
    ]
    assert hand.history.events[3] == ActionTaken(1, CALL, 2, False)  # a call is capped at the all-in blind: no excess
    replay_facts(hand)
    assert_orchestrated_order(hand.history)


# =============================================================================
# DECISIONS: every SHOW/MUCK sequence of a four-way showdown, at both levels
# =============================================================================


def four_way_flow(stacked_hand: StackedHand) -> PokerHand:
    """A four-way hand called and checked down by the flow to the start of its interactive showdown."""
    hand = stacked_hand(HOLES, BOARD)
    begin_hand(hand, STAKES)
    while hand.betting is not None and hand.showdown is None:
        passive(hand)
    return hand


def four_way_low_level(stacked_hand: StackedHand) -> PokerHand:
    hand = stacked_hand(HOLES, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    while hand.betting is not None and not (hand.street is Street.RIVER and current_actor(hand) is None):
        assert hand.betting is not None
        actor = hand.betting.current_actor
        if actor is not None:
            apply_action(hand, actor, CALL if legal_actions(hand).can_call else CHECK)
        else:
            deal_next_street(hand)
            start_betting_round(hand)
    start_showdown(hand)
    return hand


def expected_decisions(
    decisions: tuple[ShowdownAction, ...], order: tuple[int, ...]
) -> list[tuple[int, ShowdownAction]]:
    """The decisions the engine may accept: seats ask in order until all decided or one contender remains."""
    contenders = set(order)
    accepted: list[tuple[int, ShowdownAction]] = []
    for seat, decision in zip(order, decisions, strict=False):
        if len(contenders) == 1:
            break
        accepted.append((seat, decision))
        if decision is MUCK:
            contenders.discard(seat)
    return accepted


@pytest.mark.parametrize(
    "decisions", list(itertools.product([SHOW, MUCK], repeat=4)), ids=lambda d: "".join(x.name[1] for x in d)
)
def test_every_decision_sequence_is_recorded_as_asked_and_ends_exactly_when_one_contender_remains(
    stacked_hand: StackedHand,
    replay_facts: ReplayFacts,
    fold_history: FoldHistory,
    assert_orchestrated_order: OrderCheck,
    decisions: tuple[ShowdownAction, ...],
) -> None:
    """Seats 2, 3, 4 and 1 decide in that order. The history holds one `ShowdownDecided` per accepted decision, none for
    a seat that is never asked, and `HandSettled` right after the last. The level of the calls changes nothing."""
    order = (2, 3, 4, 1)
    expected = expected_decisions(decisions, order)
    flow = four_way_flow(stacked_hand)
    low = four_way_low_level(stacked_hand)
    before = flow.history
    assert before.events[-1] == ShowdownStarted(ShowdownKind.INTERACTIVE, order)

    for seat, decision in expected:
        assert current_actor(flow) == seat
        act(flow, seat, decision)
        apply_showdown_action(low, seat, decision)
    settle_hand(low)
    assert flow.settlement is not None
    assert current_actor(flow) is None

    shown = {seat for seat, decision in expected if decision is SHOW}
    contenders = set(order) - {seat for seat, decision in expected if decision is MUCK}
    winner = (
        next(seat for seat in STRENGTH_ORDER if seat in contenders) if len(contenders) > 1 else next(iter(contenders))
    )
    assert flow.history.events == (
        *before.events,
        *(ShowdownDecided(seat, decision) for seat, decision in expected),
        HandSettled(flow.settlement),
    )
    assert flow.history == low.history
    assert flow.settlement.payouts == {winner: 40}
    assert [seat for seat, _ in flow.settlement.showdown_ranks] == sorted(shown)
    assert len(expected) == len(order) or len(contenders) == 1
    if len(contenders) == 1 and len(expected) < len(order):
        unasked = order[len(expected)]
        assert unasked in contenders and not any(
            isinstance(event, ShowdownDecided) and event.seat == unasked for event in flow.history.events
        )
    replay_facts(flow)
    replay_facts(low)
    fold_history(flow.history)
    assert_orchestrated_order(flow.history)
    if len(contenders) > 1:
        assert shown == contenders  # everyone left decided SHOW, so every contender is ranked


def test_the_last_contender_who_never_showed_is_unranked_even_though_it_won_a_contested_pot(
    stacked_hand: StackedHand, fold_history: FoldHistory
) -> None:
    hand = four_way_flow(stacked_hand)
    for seat in (2, 3, 4):
        act(hand, seat, MUCK)

    assert hand.settlement is not None
    assert hand.history.events[-2:] == (ShowdownDecided(4, MUCK), HandSettled(hand.settlement))
    assert hand.settlement.payouts == {1: 40} and hand.settlement.showdown_ranks == ()
    assert fold_history(hand.history).settlement == hand.settlement


# =============================================================================
# ATOMICITY: a rejection changes nothing but never partly
# =============================================================================


def world(hand: PokerHand) -> tuple[Any, ...]:
    """Everything a hand operation may touch."""
    return (
        hand.history,
        hand.showdown,
        hand.settlement,
        hand.street,
        list(hand.board),
        list(hand.burned_cards),
        len(hand.deck),
        copy.deepcopy(hand.betting),
        [
            (s.seat_number, s.player.stack, s.folded, s.all_in, s.street_contribution, s.total_contribution)
            for s in hand.players
        ],
        [list(s.hole_cards) for s in hand.players],
    )


def all_in_three(stacked_hand: StackedHand) -> PokerHand:
    hand = stacked_hand(holes(1, 2, 3), BOARD, stacks=dict.fromkeys((1, 2, 3), 100))
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    apply_action(hand, 1, Action(ActionType.RAISE, 100))
    apply_action(hand, 2, CALL)
    apply_action(hand, 3, CALL)
    return hand


def test_a_direct_all_in_settlement_rejected_for_a_hole_card_leaves_the_whole_hand_and_succeeds_once_repaired(
    stacked_hand: StackedHand, fold_history: FoldHistory, replay_facts: ReplayFacts
) -> None:
    """The rejection comes after the all-in showdown was built and before anything is paid, recorded or stored. Retrying
    after the missing card is back records exactly one `ShowdownStarted` and one `HandSettled`."""
    hand = all_in_three(stacked_hand)
    for _ in range(3):
        deal_next_street(hand)
    missing = hand.players[1].hole_cards.pop()
    before = world(hand)

    for _ in range(2):  # repeated rejection stays a no-op
        with pytest.raises(InvalidHoleCardCountError):
            settle_hand(hand)
        assert world(hand) == before
    assert not any(isinstance(event, ShowdownStarted) for event in hand.history.events)

    hand.players[1].hole_cards.append(missing)
    events_before = hand.history.events
    settle_hand(hand)

    assert hand.history.events[: len(events_before)] == events_before
    assert [type(event).__name__ for event in hand.history.events[len(events_before) :]] == [
        "ShowdownStarted",
        "HandSettled",
    ]
    replay_facts(hand)
    fold_history(hand.history)


def test_an_interactive_settlement_rejected_for_a_hole_card_keeps_every_decision_and_settles_once_repaired(
    stacked_hand: StackedHand,
) -> None:
    hand = four_way_low_level(stacked_hand)
    for seat in (2, 3, 4, 1):
        apply_showdown_action(hand, seat, SHOW)
    missing = hand.players[3].hole_cards.pop()  # seat 4 is shown
    before = world(hand)

    with pytest.raises(InvalidHoleCardCountError):
        settle_hand(hand)
    assert world(hand) == before

    hand.players[3].hole_cards.append(missing)
    settle_hand(hand)
    assert sum(isinstance(event, HandSettled) for event in hand.history.events) == 1
    assert sum(isinstance(event, ShowdownStarted) for event in hand.history.events) == 1


def test_a_hole_card_problem_of_a_mucked_seat_does_not_reject_the_settlement(stacked_hand: StackedHand) -> None:
    """Only shown seats are evaluated, so a mucked seat's missing card is not a rejection and is recorded as usual."""
    hand = four_way_low_level(stacked_hand)
    apply_showdown_action(hand, 2, MUCK)
    hand.players[1].hole_cards.clear()  # seat 2 mucked
    for seat in (3, 4, 1):
        apply_showdown_action(hand, seat, SHOW)

    settle_hand(hand)

    assert hand.settlement is not None and hand.settlement.payouts == {1: 40}
    assert hand.history.events[-1] == HandSettled(hand.settlement)


def test_every_rejected_operation_leaves_the_whole_hand_unchanged(stacked_hand: StackedHand) -> None:
    """Start, decision and settlement rejections of an in-hand and a settled hand, compared on the whole hand, not only
    its history: stacks, flags, board, deck, betting state and the showdown included."""
    hand = four_way_low_level(stacked_hand)
    cases: list[tuple[type[Exception], Callable[[], object]]] = [
        (ShowdownAlreadyStartedError, lambda: start_showdown(hand)),
        (NotShowdownTurnError, lambda: apply_showdown_action(hand, 1, SHOW)),
        (TypeError, lambda: apply_showdown_action(hand, 2, "show")),  # type: ignore[arg-type]
        (ShowdownIncompleteError, lambda: settle_hand(hand)),
    ]
    for error, operation in cases:
        before = world(hand)
        with pytest.raises(error):
            operation()
        assert world(hand) == before

    for seat in (2, 3, 4, 1):
        apply_showdown_action(hand, seat, SHOW)
    settle_hand(hand)
    for operation in (
        lambda: start_showdown(hand),
        lambda: apply_showdown_action(hand, 2, MUCK),
        lambda: settle_hand(hand),
        lambda: deal_next_street(hand),
        lambda: apply_action(hand, 2, CHECK),
        lambda: act(hand, 2, SHOW),
    ):
        before = world(hand)
        with pytest.raises(HandAlreadySettledError):
            operation()
        assert world(hand) == before


def test_a_not_ready_and_an_incomplete_board_settlement_never_leave_a_lone_showdown_start(
    stacked_hand: StackedHand,
) -> None:
    hand = all_in_three(stacked_hand)
    before = world(hand)
    with pytest.raises(IncompleteBoardError):
        settle_hand(hand)
    assert world(hand) == before

    # An explicit start is a successful operation of its own, so its event stays; the rejected settlement adds nothing.
    start_showdown(hand)
    started = world(hand)
    with pytest.raises(IncompleteBoardError):
        settle_hand(hand)
    assert world(hand) == started
    assert sum(isinstance(event, ShowdownStarted) for event in hand.history.events) == 1

    live = stacked_hand(holes(1, 2, 3), BOARD)
    initialize_betting(live, STAKES)
    deal_hole_cards(live)
    for error, operation in (
        (IncompleteBoardError, lambda: settle_hand(live)),
        (ShowdownNotReadyError, lambda: start_showdown(live)),
    ):
        before = world(live)
        with pytest.raises(error):
            operation()
        assert world(live) == before

    river_open = stacked_hand(holes(1, 2, 3), BOARD)
    initialize_betting(river_open, STAKES)
    deal_hole_cards(river_open)
    while river_open.street is not Street.RIVER:
        while river_open.betting is not None and river_open.betting.current_actor is not None:
            apply_action(
                river_open, river_open.betting.current_actor, CALL if legal_actions(river_open).can_call else CHECK
            )
        deal_next_street(river_open)
        if river_open.street is not Street.RIVER:
            start_betting_round(river_open)
    for operation in (
        lambda: settle_hand(river_open),
        lambda: start_showdown(river_open),
    ):  # river dealt, round not begun
        before = world(river_open)
        with pytest.raises(ShowdownNotReadyError):
            operation()
        assert world(river_open) == before


# =============================================================================
# FAITHFUL LOW-LEVEL ORDER
# =============================================================================


def test_every_low_level_order_of_the_all_in_showdown_records_each_start_once(stacked_hand: StackedHand) -> None:
    """Start before any street, between streets, after all of them or never explicitly: exactly one `ShowdownStarted`
    each time, placed where the call was made, and `HandSettled` last."""
    positions: list[int] = []
    for deal_before_start in range(4):
        hand = all_in_three(stacked_hand)
        for _ in range(deal_before_start):
            deal_next_street(hand)
        start_showdown(hand)
        while hand.street is not Street.RIVER:
            deal_next_street(hand)
        settle_hand(hand)
        events = hand.history.events
        kinds = [type(event).__name__ for event in events]
        assert kinds.count("ShowdownStarted") == 1 and kinds[-1] == "HandSettled"
        positions.append(kinds.index("ShowdownStarted"))
        assert kinds[positions[-1] - deal_before_start : positions[-1]] == ["StreetDealt"] * deal_before_start
    assert positions == [positions[0] + n for n in range(4)]

    direct = all_in_three(stacked_hand)
    while direct.street is not Street.RIVER:
        deal_next_street(direct)
    settle_hand(direct)
    assert [type(event).__name__ for event in direct.history.events[-5:]] == [
        "StreetDealt",
        "StreetDealt",
        "StreetDealt",
        "ShowdownStarted",
        "HandSettled",
    ]


def test_a_started_showdown_before_the_board_is_dealt_is_incomplete_history_until_settled(
    stacked_hand: StackedHand,
) -> None:
    hand = all_in_three(stacked_hand)
    start_showdown(hand)

    assert not hand.history.is_complete and hand.history.settlement is None
    assert hand.history.events[-1] == ShowdownStarted(ShowdownKind.ALL_IN, (2, 3, 1))


# =============================================================================
# MULTIWAY INTERACTIVE SHOWDOWNS, driven randomly and checked against the decision model
# =============================================================================


def passive_multiway_hand(rng: random.Random) -> PokerHand:
    """3 to 6 deep-stacked seats that mostly check and call, so many hands reach an interactive river showdown."""
    seats = tuple(sorted(rng.sample(range(1, 10), rng.randint(3, 6))))
    assignments = assign_hand_seats(seats, rng.choice(seats))
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat}", stack=rng.randint(800, 2000), status=PlayerStatus.READY),
            seat_number=seat,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat, assignment in assignments.items()
    )
    deck = Deck()
    deck.shuffle(_rng=random.Random(f"mw-deck-{rng.random()}"))
    return PokerHand(players=players, deck=deck, number=1)


def passive_choice(rng: random.Random, hand: PokerHand) -> Action | ShowdownAction:
    if hand.showdown is not None:
        return rng.choice([SHOW, MUCK])
    legal = legal_actions(hand)
    if hand.street is Street.RIVER and legal.can_bet and rng.random() < 0.35:
        assert legal.min_full_target is not None
        return Action(ActionType.BET, legal.min_full_target)
    if legal.can_check:
        return CHECK if rng.random() < 0.97 else FOLD
    return CALL if rng.random() < 0.9 else FOLD


@pytest.mark.parametrize("batch", range(4))
def test_random_multiway_showdowns_follow_the_decision_model_and_reach_every_shape(
    batch: int, replay_facts: ReplayFacts, fold_history: FoldHistory, assert_orchestrated_order: OrderCheck
) -> None:
    """Over many random 3 to 6 seat hands, each interactive showdown starts with the river's last bettor (else the
    first live seat left of the button), asks seats until all decided or one contender remains, and settles right after;
    and the seeds really reach a muck that leaves the showdown going, a show then a muck then more, and a river bet."""
    counters: Counter[str] = Counter()
    for seed in range(batch * 75, batch * 75 + 75):
        rng = random.Random(f"multiway-{seed}")
        hand = passive_multiway_hand(rng)
        play_out_with(hand, rng, passive_choice)
        history = hand.history
        replay_facts(hand)
        fold_history(history)
        assert_orchestrated_order(history)
        events = history.events
        starts = [event for event in events if isinstance(event, ShowdownStarted)]
        if not starts:
            continue
        assert starts[0].kind is ShowdownKind.INTERACTIVE or any(
            isinstance(event, ActionTaken) and event.all_in for event in events
        )
        if starts[0].kind is not ShowdownKind.INTERACTIVE:
            continue
        seats = [participant.seat for participant in history.participants]
        folded = {event.seat for event in events if isinstance(event, ActionTaken) and event.action == FOLD}
        live = [seat for seat in clockwise_after_button(tuple(seats)) if seat not in folded]
        last_deal = max(i for i, event in enumerate(events) if isinstance(event, StreetDealt))
        river_bettors = [
            event.seat
            for event in events[last_deal:]
            if isinstance(event, ActionTaken) and event.action.type in (ActionType.BET, ActionType.RAISE)
        ]
        first = live.index(river_bettors[-1]) if river_bettors else 0
        order = (*live[first:], *live[:first])
        assert starts[0].order == order
        decided = [(event.seat, event.action) for event in events if isinstance(event, ShowdownDecided)]
        asked = expected_decisions(tuple(action for _, action in decided), order)
        assert decided == asked and [seat for seat, _ in decided] == list(order[: len(decided)])
        contenders = set(order) - {seat for seat, action in decided if action is MUCK}
        assert (len(decided) == len(order)) or len(contenders) == 1
        actions = [action for _, action in decided]
        counters["interactive"] += 1
        counters["river_bet"] += bool(river_bettors)
        counters["muck_then_more"] += any(action is MUCK for action in actions[:-1])
        counters["show_muck_more"] += any(
            actions[i] is SHOW and actions[i + 1] is MUCK and i + 2 < len(actions) for i in range(len(actions) - 1)
        )
        counters["unasked_last"] += len(decided) < len(order)
        counters["three_plus_live"] += len(order) >= 3
    # About half of what the 75 seeds of one batch reach (72, 58, 48, 23, 14 and 58).
    needed = {
        "interactive": 36,
        "river_bet": 29,
        "muck_then_more": 24,
        "show_muck_more": 11,
        "unasked_last": 7,
        "three_plus_live": 29,
    }
    short = {key: (counters[key], need) for key, need in needed.items() if counters[key] < need}
    assert not short, f"the seeds no longer reach enough of {short} (got {dict(counters)})"


# =============================================================================
# COMPLETENESS READS over every prefix of random hands
# =============================================================================


def random_hand(rng: random.Random, cls: type[PokerHand] = PokerHand) -> PokerHand:
    seats = tuple(sorted(rng.sample(range(1, 10), rng.randint(2, 5))))
    assignments = assign_hand_seats(seats, rng.choice(seats))
    stack_range = rng.choice([(1, 40), (10, 300), (500, 1500)])
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat}", stack=rng.randint(*stack_range), status=PlayerStatus.READY),
            seat_number=seat,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat, assignment in assignments.items()
    )
    deck = Deck()
    deck.shuffle(_rng=random.Random(f"qa-deck-{rng.random()}"))
    return cls(players=players, deck=deck, number=1)


def random_action(rng: random.Random, hand: PokerHand) -> Action | ShowdownAction:
    if hand.showdown is not None:
        return rng.choice([SHOW, MUCK, SHOW])
    legal = legal_actions(hand)
    options = [FOLD]
    if legal.can_check:
        options += [CHECK] * 3
    if legal.can_call:
        options += [CALL] * 3
    kind = ActionType.BET if legal.can_bet else ActionType.RAISE
    if legal.short_all_in_target is not None:
        options.append(Action(kind, legal.short_all_in_target))
    elif legal.min_full_target is not None and legal.max_target is not None:
        options += [Action(kind, legal.min_full_target), Action(kind, legal.max_target)]
    return rng.choice(options)


def play_out_with(
    hand: PokerHand, rng: random.Random, choose: Callable[[random.Random, PokerHand], Action | ShowdownAction]
) -> None:
    begin_hand(hand, STAKES)
    for _ in range(500):
        seat = current_actor(hand)
        if seat is None:
            break
        act(hand, seat, choose(rng, hand))
    assert hand.settlement is not None


def play_out(hand: PokerHand, rng: random.Random) -> list[tuple[int, Action | ShowdownAction]]:
    """Play the hand through the flow with random choices; return the choices made, in order."""
    begin_hand(hand, STAKES)
    played: list[tuple[int, Action | ShowdownAction]] = []
    for _ in range(500):
        seat = current_actor(hand)
        if seat is None:
            break
        choice = random_action(rng, hand)
        act(hand, seat, choice)
        played.append((seat, choice))
    assert hand.settlement is not None
    return played


@pytest.mark.parametrize("seed", range(120))
def test_only_the_last_history_of_a_hand_is_complete_and_every_earlier_one_stays_incomplete(seed: int) -> None:
    rng = random.Random(f"complete-{seed}")
    hand = random_hand(rng)
    begin_hand(hand, STAKES)
    taken = [hand.history]
    for _ in range(500):
        seat = current_actor(hand)
        if seat is None:
            break
        act(hand, seat, random_action(rng, hand))
        taken.append(hand.history)
    final = hand.history
    assert final.is_complete and final.settlement == hand.settlement
    for earlier in taken[:-1]:
        assert earlier.is_complete == isinstance(earlier.events[-1], HandSettled)
        if not earlier.is_complete:
            assert earlier.settlement is None
        assert final.events[: len(earlier.events)] == earlier.events  # a prefix, never rewritten
    assert sum(history.is_complete for history in taken) == 1  # a settled hand never records another event


# =============================================================================
# THE HARNESS CANNOT PASS VACUOUSLY: tampered histories are rejected
# =============================================================================


def tampered(history: HandHistory, index: int, replacement: Any) -> HandHistory:
    events = list(history.events)
    events[index] = replacement
    return HandHistory(tuple(events))


def three_way_side_pot_hand(stacked_hand: StackedHand) -> PokerHand:
    """Seat 1 raises to 500; seats 2 and 3 call all-in for 100 and 200: three kings (seat 2) win the 300 main pot and
    seat 3's jacks the 200 side pot."""
    hand = stacked_hand({1: HOLES[1], 2: HOLES[2], 3: "Jd Jh"}, BOARD, stacks={1: 1000, 2: 100, 3: 200})
    begin_hand(hand, STAKES)
    act(hand, 1, Action(ActionType.RAISE, 500))
    act(hand, 2, CALL)
    act(hand, 3, CALL)
    assert hand.settlement is not None
    return hand


def test_the_fold_catches_a_wrong_winner_a_wrong_split_and_a_wrong_pot_without_the_live_hand(
    stacked_hand: StackedHand, fold_history: FoldHistory
) -> None:
    """Each tamper keeps every total consistent, so only the independent award, layering and rank checks can see it."""
    hand = three_way_side_pot_hand(stacked_hand)
    history = hand.history
    settled = history.events[-1]
    assert isinstance(settled, HandSettled)
    awards = settled.settlement.pot_awards
    assert [award.shares for award in awards] == [((2, 300),), ((3, 200),)]
    fold_history(history)  # the genuine history folds

    def with_awards(*new_awards: PotAward, ranks: Any = None) -> HandHistory:
        ranked = settled.settlement.showdown_ranks if ranks is None else ranks
        return tampered(history, len(history.events) - 1, HandSettled(Settlement(tuple(new_awards), ranked)))

    wrong_winner = dataclasses.replace(awards[0], shares=((1, 300),))  # a worse, eligible, shown hand takes the pot
    split_wrongly = dataclasses.replace(awards[1], shares=((3, 150), (1, 50)))  # sums to the pot, wrong split
    merged = PotAward(dataclasses.replace(awards[0].pot, amount=500), ((2, 500),))  # layers merged
    ineligible = dataclasses.replace(awards[1], shares=((2, 200),))  # seat 2 is not eligible for the side pot
    for bad in (
        with_awards(wrong_winner, awards[1]),
        with_awards(awards[0], split_wrongly),
        with_awards(merged),
        with_awards(awards[0], ineligible),
        with_awards(awards[1], awards[0]),  # layers in the wrong order
        with_awards(*awards, ranks=settled.settlement.showdown_ranks[:2]),  # a shown seat unranked
        with_awards(
            *awards,
            ranks=((1, settled.settlement.showdown_ranks[1][1]), *settled.settlement.showdown_ranks[1:]),
        ),
    ):
        with pytest.raises(AssertionError):
            fold_history(bad)


def test_the_fold_catches_dropped_returned_chips_a_dropped_decision_and_a_wrong_board(
    stacked_hand: StackedHand, fold_history: FoldHistory
) -> None:
    hand = four_way_flow(stacked_hand)
    for seat in (2, 3, 4, 1):
        act(hand, seat, SHOW)
    history = hand.history
    fold_history(history)
    events = history.events

    decided = [i for i, event in enumerate(events) if isinstance(event, ShowdownDecided)]
    dealt = [i for i, event in enumerate(events) if isinstance(event, StreetDealt)]
    river = events[dealt[-1]]
    assert isinstance(river, StreetDealt)
    swapped_river = dataclasses.replace(river, cards=(Card(Rank.FIVE, Suit.CLUBS),))  # a card nobody else uses
    for bad in (
        HandHistory(events[: decided[1]] + events[decided[1] + 1 :]),  # a decision removed: the showdown is incomplete
        tampered(history, decided[0], ShowdownDecided(2, MUCK)),  # seat 2 mucks, yet is ranked and paid
        tampered(history, dealt[-1], swapped_river),  # the ranks no longer follow from the board
        HandHistory(events[:-1] + (HandSettled(Settlement((), ())),)),  # an empty settlement
    ):
        with pytest.raises(AssertionError):
            fold_history(bad)


def reordered(history: HandHistory, move: int, to: int) -> HandHistory:
    events = list(history.events)
    events.insert(to, events.pop(move))
    return HandHistory(tuple(events))


def test_the_order_check_rejects_every_misordering_of_an_all_in_runout(
    stacked_hand: StackedHand, assert_orchestrated_order: OrderCheck
) -> None:
    """The genuine orchestrated history passes; the showdown start moved after a runout street, a runout street missing,
    duplicated or out of order, a betting round or decision inside the runout, a second start, and a settlement that is
    not last each fail."""
    flow = stacked_hand(holes(1, 2, 3), BOARD, stacks=dict.fromkeys((1, 2, 3), 100))
    begin_hand(flow, STAKES)
    act(flow, 1, Action(ActionType.RAISE, 100))
    act(flow, 2, CALL)
    act(flow, 3, CALL)
    history = flow.history
    assert_orchestrated_order(history)
    events = history.events
    start = next(i for i, event in enumerate(events) if isinstance(event, ShowdownStarted))
    streets = [i for i, event in enumerate(events) if isinstance(event, StreetDealt)]
    assert streets == [start + 1, start + 2, start + 3] and start + 4 == len(events) - 1

    bad_histories = [
        reordered(history, start, start + 1),  # the start after the flop
        reordered(history, start, start + 3),  # the start after the river
        HandHistory(events[: start + 1] + events[start + 2 :]),  # the flop missing
        HandHistory(events[: start + 3] + events[start + 4 :]),  # the river missing
        reordered(history, start + 1, start + 2),  # the flop and turn swapped
        HandHistory(events[: start + 2] + (events[start + 1],) + events[start + 2 :]),  # the flop twice
        HandHistory((*events[: start + 2], BettingRoundStarted(Street.FLOP), *events[start + 2 :])),
        HandHistory((*events[: start + 1], ShowdownDecided(2, SHOW), *events[start + 1 :])),
        HandHistory((*events[: start + 1], events[start], *events[start + 1 :])),  # two starts
        HandHistory((*events, events[-1])),  # two settlements
        HandHistory((*events[:-1], events[1], events[-1])),  # an event after the end: HandSettled not last
        HandHistory((events[0], *events[0:])),  # two HandStarted
    ]
    for bad in bad_histories:
        with pytest.raises(AssertionError):
            assert_orchestrated_order(bad)


def test_the_order_check_rejects_every_misordering_of_an_interactive_showdown(
    stacked_hand: StackedHand, assert_orchestrated_order: OrderCheck
) -> None:
    hand = four_way_flow(stacked_hand)
    for seat in (2, 3):
        act(hand, seat, SHOW)
    act(hand, 4, MUCK)
    act(hand, 1, SHOW)
    history = hand.history
    assert_orchestrated_order(history)
    events = history.events
    start = next(i for i, event in enumerate(events) if isinstance(event, ShowdownStarted))
    assert events[start - 1] == BettingRoundCompleted(Street.RIVER)

    bad_histories = [
        reordered(history, start, start - 1),  # the start before the river round completed
        reordered(history, start + 1, start + 2),  # decisions out of order
        tampered(history, start - 1, BettingRoundCompleted(Street.TURN)),  # not right after the river round
        HandHistory((*events[:start], ChipsReturned(2, 1), *events[start:])),  # something between them
        HandHistory((*events[: start + 1], StreetDealt(Street.RIVER, (), ()), *events[start + 1 :])),
        HandHistory((*events[: start + 1], BettingRoundStarted(Street.RIVER), *events[start + 1 :])),
        HandHistory((*events[:start], *events[start + 1 :])),  # decisions without a start
        HandHistory((*events[: start + 2], events[-1], *events[start + 2 : -1])),  # the settlement mid-decisions
    ]
    for bad in bad_histories:
        with pytest.raises(AssertionError):
            assert_orchestrated_order(bad)

    uncontested = stacked_hand(holes(1, 2, 3), BOARD)
    begin_hand(uncontested, STAKES)
    act(uncontested, 1, FOLD)
    act(uncontested, 2, FOLD)
    assert_orchestrated_order(uncontested.history)
    with pytest.raises(AssertionError):  # an uncontested hand with a showdown start
        assert_orchestrated_order(
            HandHistory(
                (
                    *uncontested.history.events[:-1],
                    ShowdownStarted(ShowdownKind.ALL_IN, (3,)),
                    uncontested.history.events[-1],
                )
            )
        )


def test_the_live_hand_replay_catches_a_history_that_is_not_the_hands(
    stacked_hand: StackedHand, replay_facts: ReplayFacts
) -> None:
    hand = three_way_side_pot_hand(stacked_hand)
    replay_facts(hand)
    other = four_way_flow(stacked_hand)
    other_history = other.history
    hand.history = other_history
    with pytest.raises(AssertionError):
        replay_facts(hand)


# =============================================================================
# DURABILITY: a completed history is a pure value
# =============================================================================


def assert_pure_value(value: object, path: str = "history") -> None:
    """Only immutable values anywhere in a history: scalars, enums, tuples, frozensets and frozen dataclasses."""
    if value is None or isinstance(value, bool | int | str | Enum):
        return
    if isinstance(value, tuple | frozenset):
        for index, item in enumerate(value):
            assert_pure_value(item, f"{path}[{index}]")
        return
    assert dataclasses.is_dataclass(value) and not isinstance(value, type), f"{path} holds {type(value).__name__}"
    assert type(value).__dataclass_params__.frozen, f"{path} holds an unfrozen {type(value).__name__}"  # type: ignore[attr-defined]
    for field in dataclasses.fields(value):
        assert_pure_value(getattr(value, field.name), f"{path}.{field.name}")


@pytest.mark.parametrize("seed", range(60))
def test_a_completed_history_is_a_pure_value_that_later_changes_to_the_live_hand_and_players_cannot_reach(
    seed: int, fold_history: FoldHistory
) -> None:
    rng = random.Random(f"durable-{seed}")
    hand = random_hand(rng)
    play_out(hand, rng)
    history = hand.history
    assert_pure_value(history)
    snapshot = copy.deepcopy(history)
    facts = fold_history(history)
    settlement = history.settlement
    assert settlement is not None

    for state in hand.players:  # the live objects move on in every way a later hand or table churn could
        state.player.stack = rng.randint(0, 5000)
        state.player.status = PlayerStatus.SITTING_OUT
        state.hole_cards.clear()
        state.folded = not state.folded
        state.all_in = not state.all_in
    hand.board.clear()
    hand.burned_cards.clear()

    assert history == snapshot and history.settlement == settlement
    assert fold_history(history) == facts
    assert fold_history(snapshot) == facts


# =============================================================================
# BOUNDARY: no rule reads the history
# =============================================================================


class DiscardedHistoryHand(PokerHand):
    """A hand whose history keeps only its first value and silently drops every later write, so any rule that read the
    history to decide something would see a hand that never recorded anything."""

    @property  # type: ignore[override]
    def history(self) -> HandHistory:
        return self._frozen_history  # type: ignore[no-any-return]

    @history.setter
    def history(self, value: HandHistory) -> None:
        if "_frozen_history" not in self.__dict__:
            self._frozen_history = value


def live_state(hand: PokerHand) -> tuple[Any, ...]:
    return (
        hand.street,
        hand.board,
        hand.burned_cards,
        hand.betting,
        hand.settlement,
        hand.showdown,
        [
            (
                s.seat_number,
                s.player.stack,
                s.folded,
                s.all_in,
                s.street_contribution,
                s.total_contribution,
                s.hole_cards,
            )
            for s in hand.players
        ],
    )


@pytest.mark.parametrize("seed", range(150))
def test_poker_behavior_is_identical_when_every_history_write_is_discarded(seed: int) -> None:
    """The same random hand and the same choices, once with a real history and once with one that records nothing, ends
    in the same stacks, showdown, settlement and betting state: the history is written, never read, by the rules."""
    recorded = random_hand(random.Random(f"null-{seed}"))
    played = play_out(recorded, random.Random(f"null-choices-{seed}"))

    blank = random_hand(random.Random(f"null-{seed}"), DiscardedHistoryHand)
    begin_hand(blank, STAKES)
    for seat, choice in played:
        assert current_actor(blank) == seat
        act(blank, seat, choice)

    assert blank.history.events == blank.history.events[:1] and not blank.history.is_complete
    assert live_state(blank) == live_state(recorded)
    assert recorded.history.is_complete and blank.settlement is not None


def test_the_flow_and_the_game_neither_record_nor_read_the_history() -> None:
    """The orchestration modules import no history type or recorder and never touch a `history` attribute (comments and
    docstrings aside)."""
    import ast
    from pathlib import Path

    import go_poker.game.variants.texas_holdem.game as game_module
    import go_poker.game.variants.texas_holdem.hand_flow as flow_module

    for module in (flow_module, game_module):
        tree = ast.parse(Path(module.__file__ or "").read_text())
        imported = {
            alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) for alias in node.names
        } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        assert not any("hand_history" in name or name == "_appended" for name in imported), module.__name__
        assert not any(isinstance(node, ast.Attribute) and node.attr == "history" for node in ast.walk(tree))

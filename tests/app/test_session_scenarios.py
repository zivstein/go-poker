"""Scripted multi-user `TableSession` scenarios on stacked decks: hands one after another, a leaving player's automatic
actions, boundary intents, waiting and resuming, the engine-generation reset, and the views at every transition.

Every accepted result goes through `ok`, which checks the revisions are consecutive, that each member's last view equals
the live one and the engine's own projection, and that no view leaks a card or a user id (`assert_view_clean`).
Seats follow the join order: alice 1 (host), bob 2, carol 3, dave 4, erin 5; the first button is seat 1.
"""

from collections.abc import Callable, Iterator
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from typing import Any

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.results import Accepted, CommandResult, Rejected, RejectionCode, TransitionCause
from go_poker.app.session import TableSession
from go_poker.app.views import TablePhase, TableView
from go_poker.core.card import Card, Rank, Suit
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.player import Player
from go_poker.game.position import Position
from go_poker.game.showdown import ShowdownAction
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.view import HandView, OccupantStatus, OccupantView, holdem_view
from go_poker.game.visibility import ActionTakenView, HandStartedView, HoleCardsDealtView, ShowdownDecidedView

type DrawOrder = Callable[..., list[Card]]
type QueueDecks = Callable[..., Any]
type MakeSession = Callable[..., TableSession]

NAMES = ("alice", "bob", "carol", "dave", "erin", "frank")
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 4d 7h 9s Jc"
COMMAND = TransitionCause.COMMAND
AUTO = TransitionCause.LEAVE_AUTO_ACTION
BOUNDARY = TransitionCause.HAND_BOUNDARY
RESUME = TransitionCause.RESUME


def uid(name: str) -> UserId:
    return UserId(f"uid-{name}-7f3a")  # the convention of conftest's `_user_id`


def dname(name: str) -> DisplayName:
    return DisplayName(name.capitalize())  # the convention of conftest's `_display_name`


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def cards(text: str) -> tuple[Card, ...]:
    ranks = {"2": Rank.TWO, "3": Rank.THREE, "4": Rank.FOUR, "7": Rank.SEVEN, "9": Rank.NINE}
    ranks |= {"J": Rank.JACK, "K": Rank.KING, "A": Rank.ACE}
    suits = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}
    return tuple(Card(ranks[token[0]], suits[token[1]]) for token in text.split())


def deck(draw_order: DrawOrder, seats: tuple[int, ...], button: int) -> list[Card]:
    return draw_order({seat: HOLES[seat] for seat in seats}, BOARD, button)


# --- view checks ---


def _walk(value: object) -> Iterator[object]:
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from _walk(getattr(value, field.name))
    elif isinstance(value, tuple | list | frozenset | set):
        for item in value:
            yield from _walk(item)


def assert_view_clean(view: TableView) -> None:
    """No user id or engine player in the view, and no hole card other than the viewer's own and the shown ones."""
    for item in _walk(view):
        assert not isinstance(item, UserId | Player | Table), item
        assert not (isinstance(item, str) and "uid-" in item), item
        assert not isinstance(item, Enum) or "uid-" not in str(item.value)
    hand = view.game.hand
    if hand is None:
        return
    shown = set(hand.showdown.shown) if hand.showdown is not None else set()
    own = next((p.hole_cards for p in hand.participants if p.seat == view.you.seat), None)
    for participant in hand.participants:
        if participant.seat not in shown and participant.seat != view.you.seat:
            assert participant.hole_cards is None and participant.strength is None
    for event in hand.log:
        if isinstance(event, HoleCardsDealtView):
            assert event.own_cards == own


def ok(session: TableSession, result: CommandResult) -> Accepted:
    assert isinstance(result, Accepted), result
    revision = result.transitions[0].revision if result.transitions else session.revision
    for transition in result.transitions:
        assert transition.revision == revision
        revision += 1
        for member_view in transition.views.values():
            assert member_view.revision == transition.revision
            assert_view_clean(member_view)
    if result.transitions:
        assert result.transitions[-1].revision == session.revision
    for name in NAMES:
        view = session.view_for(uid(name))
        assert (view is None) == (not session.is_member(uid(name)))
        if view is None:
            continue
        assert_view_clean(view)
        if result.transitions:
            assert result.transitions[-1].views[uid(name)] == view
        engine = (session._table, session._game.hand)  # noqa: SLF001 - the one place a test reads the engine
        assert view.game == holdem_view(*engine, view.you.seat)
    return result


def causes(result: Accepted) -> list[TransitionCause]:
    return [transition.cause for transition in result.transitions]


def act(session: TableSession, name: str, action: Action | ShowdownAction) -> Accepted:
    return ok(session, session.act(uid(name), session.revision, action))


def advance(session: TableSession) -> Accepted:
    return ok(session, session.advance_hand(session.revision))


def start(session: TableSession) -> Accepted:
    return ok(session, session.start_game(uid("alice"), session.revision))


def join(session: TableSession, name: str, seat: int) -> Accepted:
    return ok(session, session.join(uid(name), session.revision, dname(name), seat))


def leave(session: TableSession, name: str) -> Accepted:
    return ok(session, session.leave(uid(name), session.revision))


def sit_out(session: TableSession, name: str) -> Accepted:
    return ok(session, session.sit_out(uid(name), session.revision))


def sit_back(session: TableSession, name: str) -> Accepted:
    return ok(session, session.sit_back(uid(name), session.revision))


def hand_of(session: TableSession, name: str) -> HandView:
    view = session.view_for(uid(name))
    assert view is not None and view.game.hand is not None
    return view.game.hand


def stacks(session: TableSession, name: str) -> dict[int, int]:
    view = session.view_for(uid(name))
    assert view is not None
    return {seat.number: seat.occupant.stack for seat in view.game.seats if seat.occupant is not None}


def logged_actions(session: TableSession, name: str) -> list[tuple[int, ActionType]]:
    return [
        (event.seat, event.action.type) for event in hand_of(session, name).log if isinstance(event, ActionTakenView)
    ]


# --- consecutive hands ---


def test_hands_follow_one_another_through_advance_hand_with_continuing_stacks_and_revisions(
    make_session: MakeSession, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    queue_decks(*(deck(draw_order, (1, 2, 3), button) for button in (1, 2, 3)))
    session = make_session(3)
    start(session)
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)  # carol wins the small blind
    assert session.phase is TablePhase.HAND_COMPLETE and hand_of(session, "alice").settlement is not None
    assert stacks(session, "alice") == {1: 1000, 2: 995, 3: 1005}

    result = advance(session)
    assert causes(result) == [BOUNDARY] and result.view is None
    second = hand_of(session, "alice")
    assert (second.number, second.turn.seat if second.turn else None) == (2, 2)  # the button moved to seat 2
    assert {p.seat: p.position for p in second.participants}[2] is Position.BTN
    assert stacks(session, "alice") == {1: 990, 2: 995, 3: 1000}  # blinds posted from the carried-over stacks
    assert hand_of(session, "alice").participants[0].hole_cards is None  # alice is not the button now
    own = [p.hole_cards for p in second.participants if p.seat == 1]
    assert own == [cards("Ah Ad")]

    act(session, "bob", FOLD)
    act(session, "carol", FOLD)  # alice wins the blinds
    advance(session)
    assert (hand_of(session, "alice").number, session.phase) == (3, TablePhase.HAND_IN_PROGRESS)
    assert session.revision == 10  # create, 2 joins, start, 2 folds, boundary, 2 folds, boundary


# --- a leaving player's automatic actions ---


def test_a_leaver_checks_folds_and_mucks_automatically_each_in_its_own_transition(
    make_session: MakeSession, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    queue_decks(deck(draw_order, (1, 2, 3), 1), deck(draw_order, (1, 2), 2))
    session = make_session(3)
    start(session)
    act(session, "alice", CALL)
    act(session, "bob", CALL)

    # Carol (big blind) is on turn and may check: the request is a private pending leave, then an automatic check.
    revision = session.revision
    result = ok(session, session.leave(uid("carol"), revision))
    assert causes(result) == [AUTO] and session.revision == revision + 1
    assert result.view is not None and result.view.you.pending_leave and session.is_member(uid("carol"))
    assert (3, ActionType.CHECK) in logged_actions(session, "alice")
    assert hand_of(session, "alice").street.name == "FLOP"

    # Every later turn of carol's is played for her, as a transition of its own right after the move that gave her
    # the turn (after the flop she acts between bob and alice).
    for _street in ("FLOP", "TURN", "RIVER"):
        result = act(session, "bob", CHECK)
        assert causes(result) == [COMMAND, AUTO]
        assert result.transitions[1].revision == result.transitions[0].revision + 1
        act(session, "alice", CHECK)
    showdown_causes = []
    while session.phase is TablePhase.HAND_IN_PROGRESS:
        turn = hand_of(session, "bob").turn
        assert turn is not None and turn.seat != 3  # carol never waits for a decision
        showdown_causes += causes(act(session, NAMES[turn.seat - 1], SHOW))
    assert AUTO in showdown_causes  # carol's MUCK

    log = hand_of(session, "alice").log
    assert any(isinstance(e, ShowdownDecidedView) and (e.seat, e.action) == (3, ShowdownAction.MUCK) for e in log)
    # Carol's mucked cards stay hidden from the others and visible to her; the shown ones are visible to all.
    assert [p.hole_cards for p in hand_of(session, "bob").participants if p.seat == 3] == [None]
    carol = [p.hole_cards for p in hand_of(session, "carol").participants if p.seat == 3]
    assert carol == [cards("3s 4s")]
    assert [p.hole_cards for p in hand_of(session, "bob").participants if p.seat == 1] == [cards("Ah Ad")]

    # A leave is pending until the boundary: repeating it is NO_CHANGE, sitting out or back is LEAVE_PENDING.
    revision = session.revision
    for code, rejected in (
        (RejectionCode.NO_CHANGE, session.leave(uid("carol"), revision)),
        (RejectionCode.LEAVE_PENDING, session.sit_out(uid("carol"), revision)),
        (RejectionCode.LEAVE_PENDING, session.sit_back(uid("carol"), revision)),
    ):
        assert isinstance(rejected, Rejected) and rejected.code is code
    assert session.revision == revision

    result = advance(session)  # the boundary applies the leave, then starts the next hand without carol
    assert causes(result) == [BOUNDARY] and not session.is_member(uid("carol"))
    assert [p.seat for p in hand_of(session, "alice").participants] == [2, 1]
    view = session.view_for(uid("alice"))
    assert view is not None and view.seats[2].display_name is None and view.game.seats[2].occupant is None
    rejected_join = session.join(uid("carol"), session.revision, dname("carol"), 3)
    assert isinstance(rejected_join, Rejected) and rejected_join.code is RejectionCode.LEFT_TABLE
    # the display name is free again
    assert isinstance(session.join(UserId("someone-new"), session.revision, DisplayName("CAROL"), 3), Accepted)


def test_a_leaver_on_turn_folds_when_chips_are_owed(make_session: MakeSession) -> None:
    session = make_session(3)
    start(session)
    act(session, "alice", raise_to(30))
    result = ok(session, session.leave(uid("bob"), session.revision))
    assert causes(result) == [AUTO]
    assert (2, ActionType.FOLD) in logged_actions(session, "carol")
    assert hand_of(session, "carol").turn is not None and hand_of(session, "carol").turn.seat == 3  # type: ignore[union-attr]


def test_a_leave_requested_off_turn_is_private_and_acts_when_the_turn_arrives(make_session: MakeSession) -> None:
    session = make_session(3)
    start(session)
    act(session, "alice", raise_to(30))
    revision = session.revision
    pending = ok(session, session.leave(uid("carol"), revision))
    assert pending.transitions == () and session.revision == revision  # carol is not on turn: nothing shared changed
    assert session.view_for(uid("bob")).you.pending_leave is False  # type: ignore[union-attr]

    result = act(session, "bob", CALL)  # carol is next, with chips owed
    assert causes(result) == [COMMAND, AUTO]
    assert [t.revision for t in result.transitions] == [revision + 1, revision + 2]
    assert (3, ActionType.FOLD) in logged_actions(session, "alice")
    assert result.transitions[0].views[uid("carol")].you.pending_leave  # reconciled before the first view
    assert not result.transitions[0].views[uid("alice")].you.pending_leave


# --- hand-boundary intents ---


def test_a_pending_sit_out_applies_at_the_boundary_and_a_sit_back_cancels_it(
    make_session: MakeSession, queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    queue_decks(deck(draw_order, (1, 2, 3), 1), deck(draw_order, (1, 3), 3))
    session = make_session(3)
    start(session)
    ok(session, session.sit_out(uid("bob"), session.revision))
    ok(session, session.sit_back(uid("bob"), session.revision))  # cancelled
    assert not session.view_for(uid("bob")).you.pending_sit_out  # type: ignore[union-attr]
    ok(session, session.sit_out(uid("bob"), session.revision))
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)  # a pending sit-out plays the current hand normally
    assert session.view_for(uid("bob")).game.seats[1].occupant.status is None  # type: ignore[union-attr]

    stale = session.revision
    result = advance(session)
    assert causes(result) == [BOUNDARY]
    view = session.view_for(uid("bob"))
    assert view is not None and not view.you.pending_sit_out
    assert view.game.seats[1].occupant == OccupantView(995, OccupantStatus.SITTING_OUT)
    assert [p.seat for p in hand_of(session, "alice").participants] == [3, 1]  # heads-up without bob
    rejected = session.sit_back(uid("bob"), stale)
    assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.STALE_REVISION

    back = sit_back(session, "bob")  # the hand is in progress and bob is not in it: applied at once
    assert causes(back) == [COMMAND]
    assert back.view is not None and back.view.game.seats[1].occupant == OccupantView(
        995, OccupantStatus.WAITING_TO_JOIN
    )


# --- waiting and resuming ---


def waiting_table(make_session: MakeSession) -> TableSession:
    """Alice and bob; bob wins hand 1, sits out, and the boundary leaves the table waiting with alice alone."""
    session = make_session(2)
    start(session)
    act(session, "alice", FOLD)
    sit_out(session, "bob")
    result = advance(session)
    assert causes(result) == [BOUNDARY] and session.phase is TablePhase.WAITING_FOR_PLAYERS
    return session


def test_a_waiting_table_resumes_when_a_user_joins(make_session: MakeSession) -> None:
    session = waiting_table(make_session)
    revision = session.revision
    result = join(session, "carol", 3)
    assert causes(result) == [COMMAND, RESUME]
    assert [t.revision for t in result.transitions] == [revision + 1, revision + 2]
    assert result.transitions[0].views[uid("alice")].phase is TablePhase.WAITING_FOR_PLAYERS
    assert result.transitions[1].views[uid("alice")].phase is TablePhase.HAND_IN_PROGRESS
    assert result.view is not None and result.view == session.view_for(uid("carol"))
    assert result.view.game.hand is not None and result.view.game.hand.number == 2  # the same generation continues


def test_a_waiting_table_resumes_when_a_user_sits_back(make_session: MakeSession) -> None:
    session = waiting_table(make_session)
    result = sit_back(session, "bob")
    assert causes(result) == [COMMAND, RESUME] and session.phase is TablePhase.HAND_IN_PROGRESS


def test_a_resume_attempt_that_changes_nothing_produces_no_transition(make_session: MakeSession) -> None:
    session = waiting_table(make_session)
    result = leave(session, "bob")  # bob was sitting out: alice is still alone
    assert causes(result) == [COMMAND] and session.phase is TablePhase.WAITING_FOR_PLAYERS
    result = join(session, "carol", 3)  # alice and carol can play
    assert causes(result) == [COMMAND, RESUME]


# --- the engine-generation reset ---


def test_the_generation_is_replaced_when_everyone_sits_out_and_play_resumes_with_the_same_stacks(
    make_session: MakeSession,
) -> None:
    session = make_session(2)
    start(session)
    act(session, "alice", FOLD)  # bob wins: alice 995, bob 1005
    sit_out(session, "alice")
    sit_out(session, "bob")
    before = session.revision
    host_view = session.view_for(uid("alice"))
    assert host_view is not None

    result = advance(session)  # no READY player is left: a fresh generation, which cannot start
    assert causes(result) == [BOUNDARY] and session.revision == before + 1
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    view = session.view_for(uid("alice"))
    assert view is not None and view.game.hand is None  # hand numbers restart in the new generation
    assert [seat.occupant for seat in view.game.seats[:2]] == [
        OccupantView(995, OccupantStatus.SITTING_OUT),
        OccupantView(1005, OccupantStatus.SITTING_OUT),
    ]
    assert (view.table_id, view.code, view.you.seat, view.you.is_host) == ("table-1", "ABCD", 1, True)
    assert [s.display_name for s in view.seats[:2]] == [DisplayName("Alice"), DisplayName("Bob")]
    assert session._table.get_seat(2).player.player_id == uid("bob").value  # type: ignore[union-attr]  # noqa: SLF001

    result = sit_back(session, "alice")  # one player is not enough: no hand, no resume transition
    assert causes(result) == [COMMAND]
    result = sit_back(session, "bob")
    assert causes(result) == [COMMAND, RESUME]
    hand = hand_of(session, "alice")
    assert hand.number == 1 and session.phase is TablePhase.HAND_IN_PROGRESS
    started = next(e for e in hand.log if isinstance(e, HandStartedView))
    assert {p.seat: p.starting_stack for p in started.participants} == {1: 995, 2: 1005}


def test_leaves_applied_at_the_boundary_reset_the_generation_and_pass_the_host_on(make_session: MakeSession) -> None:
    session = make_session(2)
    start(session)
    join(session, "dave", 4)  # seated during the hand: waiting, not a participant
    assert causes(leave(session, "alice")) == [AUTO]  # alice's turn: automatic fold, bob wins
    assert session.phase is TablePhase.HAND_COMPLETE
    assert causes(leave(session, "bob")) == [COMMAND]  # no longer in a hand in progress: applied at once
    assert session.view_for(uid("alice")).you.is_host  # type: ignore[union-attr]

    before = session.revision
    result = advance(session)  # alice's pending leave applies; only dave remains, in a fresh generation
    assert causes(result) == [BOUNDARY] and session.revision == before + 1
    assert [uid(n) in result.transitions[0].views for n in ("alice", "bob", "dave")] == [False, False, True]
    dave = result.transitions[0].views[uid("dave")]
    assert dave.you.is_host and dave.phase is TablePhase.WAITING_FOR_PLAYERS and dave.game.hand is None
    assert dave.game.seats[3].occupant == OccupantView(1000, OccupantStatus.WAITING_TO_JOIN)
    assert session._table.get_seat(4).player.player_id == uid("dave").value  # type: ignore[union-attr]  # noqa: SLF001

    result = join(session, "erin", 5)
    assert causes(result) == [COMMAND, RESUME]
    assert hand_of(session, "dave").number == 1


# --- the view checks themselves ---


def test_the_view_checks_detect_a_leaked_card_and_a_leaked_user_id(make_session: MakeSession) -> None:
    session = make_session(3)
    start(session)
    view = session.view_for(uid("bob"))
    assert view is not None and view.game.hand is not None
    assert_view_clean(view)
    leaked_card = tuple(
        replace(p, hole_cards=cards("As Ad")) if p.seat == 1 else p for p in view.game.hand.participants
    )
    leaked_hand = replace(view.game.hand, participants=leaked_card)
    with pytest.raises(AssertionError):
        assert_view_clean(replace(view, game=replace(view.game, hand=leaked_hand)))
    with pytest.raises(AssertionError):
        assert_view_clean(replace(view, table_id=uid("alice").value))
    with pytest.raises(AssertionError):
        assert_view_clean(replace(view, code=repr(uid("alice"))))  # a whole UserId in a view

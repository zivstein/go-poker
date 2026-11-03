"""Adversarial `TableSession` validation: rejection atomicity in every phase (revision, every view, the engine and the
session's own state), the shared-versus-private revision rules, the hand boundary and generation reset, the leaving
player's automatic actions across several leavers, waiting and resuming, and identity edge cases.

Seats follow the join order: alice 1 (host), bob 2, carol 3, dave 4, erin 5, frank 6; the first button is seat 1. With
three players seat 1 acts first before the flop, then seat 2 (small blind), then seat 3 (big blind).
"""

import unicodedata
from collections.abc import Callable
from dataclasses import fields, is_dataclass, replace
from enum import Enum

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.results import Accepted, CommandResult, Rejected, RejectionCode, TransitionCause
from go_poker.app.session import TableSession
from go_poker.app.views import TablePhase, TableView
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.showdown import ShowdownAction
from go_poker.game.variants.texas_holdem.view import HandView

type MakeSession = Callable[..., TableSession]
type Attempt = tuple[RejectionCode | None, Callable[[], CommandResult]]

NAMES = ("alice", "bob", "carol", "dave", "erin", "frank", "zed")
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
COMMAND = TransitionCause.COMMAND
AUTO = TransitionCause.LEAVE_AUTO_ACTION
BOUNDARY = TransitionCause.HAND_BOUNDARY
RESUME = TransitionCause.RESUME


def uid(name: str) -> UserId:
    return UserId(f"uid-{name}-7f3a")  # the convention of conftest's `_user_id`


def dname(name: str) -> DisplayName:
    return DisplayName(name.capitalize())  # the convention of conftest's `_display_name`


def ok(result: CommandResult) -> Accepted:
    assert isinstance(result, Accepted), result
    return result


def causes(result: Accepted) -> list[TransitionCause]:
    return [transition.cause for transition in result.transitions]


def act(session: TableSession, name: str, action: Action | ShowdownAction) -> Accepted:
    return ok(session.act(uid(name), session.revision, action))


def leave(session: TableSession, name: str) -> Accepted:
    return ok(session.leave(uid(name), session.revision))


def sit_out(session: TableSession, name: str) -> Accepted:
    return ok(session.sit_out(uid(name), session.revision))


def sit_back(session: TableSession, name: str) -> Accepted:
    return ok(session.sit_back(uid(name), session.revision))


def advance(session: TableSession) -> Accepted:
    return ok(session.advance_hand(session.revision))


def join(session: TableSession, name: str, seat: int) -> Accepted:
    return ok(session.join(uid(name), session.revision, dname(name), seat))


def started(make_session: MakeSession, joined: int = 3) -> TableSession:
    session = make_session(joined)
    ok(session.start_game(uid("alice"), session.revision))
    return session


def hand_of(session: TableSession, name: str) -> HandView:
    view = session.view_for(uid(name))
    assert view is not None and view.game.hand is not None
    return view.game.hand


def view_of(session: TableSession, name: str) -> TableView:
    view = session.view_for(uid(name))
    assert view is not None
    return view


def turn_name(session: TableSession) -> str:
    """The user whose turn it is (betting or showdown)."""
    member = next(name for name in NAMES if session.is_member(uid(name)))
    turn = hand_of(session, member).turn
    assert turn is not None
    return NAMES[turn.seat - 1]


def stack_total(session: TableSession) -> int:
    """Chips at the seats plus chips in front, as seen by any member."""
    member = next(name for name in NAMES if session.is_member(uid(name)))
    view = view_of(session, member)
    seated = sum(seat.occupant.stack for seat in view.game.seats if seat.occupant is not None)
    in_front = sum(p.in_front for p in view.game.hand.participants) if view.game.hand is not None else 0
    return seated + in_front


def fingerprint(session: TableSession) -> tuple[object, ...]:
    """Everything observable through the public API plus the engine and the session's own state."""
    table, game = session._table, session._game  # noqa: SLF001 - the one place a test reads the engine
    seats = tuple(
        (number, None if (p := table.get_seat(number).player) is None else (p.player_id, p.stack, p.status))
        for number in range(1, 7)
    )
    members = tuple(
        (m.user_id.value, m.display_name, m.seat, m.pending_leave, m.pending_sit_out)
        for m in session._members.values()  # noqa: SLF001
    )
    views = tuple(session.view_for(uid(name)) for name in NAMES)
    return (
        session.revision,
        session.phase,
        views,
        (id(table), id(game), id(game.hand), repr(game.hand), seats, table.button_seat_number),
        (members, session._host, frozenset(session._departed), session._waiting),  # noqa: SLF001
    )


def assert_clean(view: TableView) -> None:
    """No user id, `player_id` or engine object in the view."""
    text = repr(view)
    assert "uid-" not in text and "player_id" not in text
    stack = [view]
    while stack:
        item = stack.pop()
        assert not isinstance(item, UserId)
        if is_dataclass(item) and not isinstance(item, type):
            assert all(field.name not in ("user_id", "player_id") for field in fields(item))
            stack.extend(getattr(item, field.name) for field in fields(item))
        elif isinstance(item, tuple | list | frozenset):
            stack.extend(item)
        elif isinstance(item, Enum):
            assert "uid-" not in str(item.value)


# --- phases ---


def not_started(make_session: MakeSession) -> TableSession:
    return make_session(3)


def in_progress(make_session: MakeSession) -> TableSession:
    return started(make_session)


def hand_complete(make_session: MakeSession) -> TableSession:
    session = started(make_session)
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE
    return session


def waiting(make_session: MakeSession) -> TableSession:
    session = started(make_session, 2)
    act(session, "alice", FOLD)
    sit_out(session, "bob")
    advance(session)
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    return session


def pending_leave(make_session: MakeSession) -> TableSession:
    """A hand in progress where carol (big blind, off turn) has a pending leave and bob a pending sit-out."""
    session = started(make_session)
    assert leave(session, "carol").transitions == ()
    assert sit_out(session, "bob").transitions == ()
    return session


PHASES = {
    "not_started": not_started,
    "in_progress": in_progress,
    "hand_complete": hand_complete,
    "waiting": waiting,
    "pending_intents": pending_leave,
}


def attempts(session: TableSession, phase: str) -> list[Attempt]:
    """Commands that must all be rejected in this phase, each with its expected code (None: only that it is)."""
    rev = session.revision
    result: list[Attempt] = [
        # Stale revisions come first, before membership, host and the engine.
        (RejectionCode.STALE_REVISION, lambda: session.join(uid("zed"), rev + 1, dname("zed"), 5)),
        (RejectionCode.STALE_REVISION, lambda: session.join(uid("alice"), rev - 1, dname("alice"), 5)),
        (RejectionCode.STALE_REVISION, lambda: session.leave(uid("zed"), rev + 1)),
        (RejectionCode.STALE_REVISION, lambda: session.sit_out(uid("alice"), rev - 1)),
        (RejectionCode.STALE_REVISION, lambda: session.sit_back(uid("alice"), 0)),
        (RejectionCode.STALE_REVISION, lambda: session.start_game(uid("bob"), rev + 1)),
        (RejectionCode.STALE_REVISION, lambda: session.act(uid("zed"), rev - 1, FOLD)),
        (RejectionCode.STALE_REVISION, lambda: session.act(uid("alice"), rev + 5, CALL)),
        (RejectionCode.STALE_REVISION, lambda: session.advance_hand(rev + 1)),
        (RejectionCode.STALE_REVISION, lambda: session.advance_hand(rev - 1)),
        # Membership.
        (RejectionCode.NOT_A_MEMBER, lambda: session.leave(uid("zed"), rev)),
        (RejectionCode.NOT_A_MEMBER, lambda: session.sit_out(uid("zed"), rev)),
        (RejectionCode.NOT_A_MEMBER, lambda: session.sit_back(uid("zed"), rev)),
        (RejectionCode.NOT_A_MEMBER, lambda: session.start_game(uid("zed"), rev)),
        (RejectionCode.NOT_A_MEMBER, lambda: session.act(uid("zed"), rev, FOLD)),
        # join: duplicate id, display name collisions (case, normalization), seats.
        (RejectionCode.ALREADY_MEMBER, lambda: session.join(uid("alice"), rev, dname("alice"), 5)),
        (RejectionCode.ALREADY_MEMBER, lambda: session.join(uid("alice"), rev, DisplayName("Fresh"), 5)),
        (RejectionCode.DISPLAY_NAME_TAKEN, lambda: session.join(UserId("n1"), rev, DisplayName("ALICE"), 5)),
        (RejectionCode.DISPLAY_NAME_TAKEN, lambda: session.join(UserId("n2"), rev, DisplayName(" alice "), 5)),
        (RejectionCode.SEAT_TAKEN, lambda: session.join(uid("zed"), rev, dname("zed"), 1)),
        (RejectionCode.INVALID_SEAT, lambda: session.join(uid("zed"), rev, dname("zed"), 0)),
        (RejectionCode.INVALID_SEAT, lambda: session.join(uid("zed"), rev, dname("zed"), 7)),
        (RejectionCode.INVALID_SEAT, lambda: session.join(uid("zed"), rev, dname("zed"), -1)),
        # Host only (bob is a member and not the host).
        (RejectionCode.NOT_HOST, lambda: session.start_game(uid("bob"), rev)),
    ]
    if phase not in ("waiting", "pending_intents"):  # no carol, or carol has a pending leave
        result.append((RejectionCode.NO_CHANGE, lambda: session.sit_back(uid("carol"), rev)))
    if phase == "not_started":
        result += [
            (RejectionCode.NO_HAND_IN_PROGRESS, lambda: session.act(uid("alice"), rev, FOLD)),
            (RejectionCode.NOT_AT_HAND_BOUNDARY, lambda: session.advance_hand(rev)),
        ]
    if phase in ("in_progress", "pending_intents"):
        result += [
            (RejectionCode.GAME_ALREADY_STARTED, lambda: session.start_game(uid("alice"), rev)),
            (RejectionCode.NOT_YOUR_TURN, lambda: session.act(uid("bob"), rev, CALL)),
            (RejectionCode.NOT_YOUR_TURN, lambda: session.act(uid("carol"), rev, FOLD)),
            (RejectionCode.ILLEGAL_ACTION, lambda: session.act(uid("alice"), rev, CHECK)),
            (RejectionCode.ILLEGAL_ACTION, lambda: session.act(uid("alice"), rev, Action(ActionType.RAISE, 15))),
            (RejectionCode.ILLEGAL_ACTION, lambda: session.act(uid("alice"), rev, Action(ActionType.BET, 20))),
            (RejectionCode.ILLEGAL_ACTION, lambda: session.act(uid("alice"), rev, Action(ActionType.RAISE, 5000))),
            (None, lambda: session.act(uid("alice"), rev, ShowdownAction.SHOW)),
            (RejectionCode.NOT_AT_HAND_BOUNDARY, lambda: session.advance_hand(rev)),
        ]
    if phase == "pending_intents":
        result += [
            (RejectionCode.NO_CHANGE, lambda: session.leave(uid("carol"), rev)),
            (RejectionCode.LEAVE_PENDING, lambda: session.sit_out(uid("carol"), rev)),
            (RejectionCode.LEAVE_PENDING, lambda: session.sit_back(uid("carol"), rev)),
            (RejectionCode.NO_CHANGE, lambda: session.sit_out(uid("bob"), rev)),  # already pending
            (
                RejectionCode.SEAT_TAKEN,
                lambda: session.join(uid("zed"), rev, dname("zed"), 3),
            ),  # carol still owns the seat
            (RejectionCode.DISPLAY_NAME_TAKEN, lambda: session.join(UserId("n3"), rev, DisplayName("carol"), 5)),
        ]
    if phase in ("hand_complete", "waiting"):
        result += [
            (RejectionCode.NO_HAND_IN_PROGRESS, lambda: session.act(uid("alice"), rev, FOLD)),
            (RejectionCode.NO_HAND_IN_PROGRESS, lambda: session.act(uid("bob"), rev, ShowdownAction.MUCK)),
            (RejectionCode.GAME_ALREADY_STARTED, lambda: session.start_game(uid("alice"), rev)),
        ]
    if phase == "waiting":
        result += [
            (RejectionCode.NO_CHANGE, lambda: session.sit_out(uid("bob"), rev)),
            (RejectionCode.NO_CHANGE, lambda: session.sit_back(uid("alice"), rev)),
            (RejectionCode.NOT_AT_HAND_BOUNDARY, lambda: session.advance_hand(rev)),
        ]
    if phase == "hand_complete":
        result.append((RejectionCode.NO_CHANGE, lambda: session.sit_back(uid("bob"), rev)))
    return result


@pytest.mark.parametrize("phase", list(PHASES))
def test_every_rejection_in_every_phase_leaves_the_session_and_the_engine_untouched(
    make_session: MakeSession, phase: str
) -> None:
    session = PHASES[phase](make_session)
    before = fingerprint(session)
    for expected, call in attempts(session, phase):
        result = call()
        assert isinstance(result, Rejected), (phase, expected, result)
        if expected is not None:
            assert result.code is expected, (phase, expected, result)
        assert result.message
        assert fingerprint(session) == before, (phase, expected)
    # And the session still works afterwards.
    assert all(view_of(session, name).revision == session.revision for name in NAMES if session.is_member(uid(name)))


def test_start_game_with_one_member_is_rejected_atomically(make_session: MakeSession) -> None:
    session = make_session(1)
    before = fingerprint(session)
    result = session.start_game(uid("alice"), session.revision)
    assert isinstance(result, Rejected) and result.code is RejectionCode.NOT_ENOUGH_PLAYERS
    assert fingerprint(session) == before
    assert not session.is_member(uid("bob"))


def test_start_game_with_one_player_who_can_play_is_rejected_atomically(make_session: MakeSession) -> None:
    session = make_session(2)
    sit_out(session, "bob")
    before = fingerprint(session)
    result = session.start_game(uid("alice"), session.revision)
    assert isinstance(result, Rejected) and result.code is RejectionCode.NOT_ENOUGH_PLAYERS
    assert fingerprint(session) == before


def test_a_departed_user_is_rejected_with_the_right_code_by_every_command(make_session: MakeSession) -> None:
    session = make_session(3)
    leave(session, "bob")
    before = fingerprint(session)
    rev = session.revision
    for expected, result in (
        (RejectionCode.LEFT_TABLE, session.join(uid("bob"), rev, dname("bob"), 2)),
        (RejectionCode.LEFT_TABLE, session.join(uid("bob"), rev, DisplayName("Other"), 4)),
        (RejectionCode.NOT_A_MEMBER, session.leave(uid("bob"), rev)),
        (RejectionCode.NOT_A_MEMBER, session.act(uid("bob"), rev, FOLD)),
        (RejectionCode.NOT_A_MEMBER, session.sit_back(uid("bob"), rev)),
        (
            RejectionCode.STALE_REVISION,
            session.join(uid("bob"), rev - 1, dname("bob"), 2),
        ),  # the revision is checked first
    ):
        assert isinstance(result, Rejected) and result.code is expected, (expected, result)
    assert fingerprint(session) == before


def test_a_stale_command_never_reaches_membership_or_the_engine(
    make_session: MakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = started(make_session)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the engine or table was reached by a stale command")

    for owner, names in ((session._game, ("act", "start", "next_hand")), (session._table, ("sit_in", "stand_up"))):  # noqa: SLF001
        for name in names:
            monkeypatch.setattr(owner, name, boom)
    rev = session.revision
    stale = rev - 1
    for result in (
        session.join(uid("zed"), stale, dname("zed"), 4),
        session.leave(uid("alice"), stale),
        session.leave(uid("zed"), stale),
        session.sit_out(uid("carol"), stale),
        session.sit_back(uid("carol"), stale),
        session.start_game(uid("alice"), stale),
        session.act(uid("alice"), stale, FOLD),
        session.advance_hand(stale),
    ):
        assert isinstance(result, Rejected) and result.code is RejectionCode.STALE_REVISION
    assert session.revision == rev


# --- shared versus private revision ---


def test_a_private_intent_bumps_nothing_changes_only_its_owners_you_and_does_not_stale_the_next_command(
    make_session: MakeSession,
) -> None:
    session = started(make_session)
    revision = session.revision
    before = {name: view_of(session, name) for name in NAMES[:3]}

    result = sit_out(session, "bob")
    assert result.transitions == () and session.revision == revision
    assert result.view == view_of(session, "bob") and result.view is not None
    assert result.view == replace(before["bob"], you=replace(before["bob"].you, pending_sit_out=True))
    assert view_of(session, "alice") == before["alice"] and view_of(session, "carol") == before["carol"]

    result = leave(session, "carol")  # a second private intent, with the revision the client already had
    assert result.transitions == () and session.revision == revision
    assert view_of(session, "carol").you.pending_leave and not view_of(session, "bob").you.pending_leave
    assert view_of(session, "alice") == before["alice"]

    result = ok(session.sit_back(uid("bob"), revision))  # cancelling is private too, and not stale
    assert result.transitions == () and session.revision == revision and view_of(session, "bob") == before["bob"]


def test_advance_hand_accepts_the_revision_the_hand_ended_at_after_private_intents(make_session: MakeSession) -> None:
    session = started(make_session)
    leave(session, "carol")  # pending (off turn)
    sit_out(session, "bob")  # pending
    act(session, "alice", FOLD)
    assert causes(act(session, "bob", FOLD)) == [COMMAND]  # carol wins; her pending leave never acted
    revision = session.revision
    sit_back(session, "bob")  # cancelled again in HAND_COMPLETE: private
    assert session.revision == revision
    result = ok(session.advance_hand(revision))
    assert causes(result) == [BOUNDARY] and result.view is None
    assert not session.is_member(uid("carol")) and session.is_member(uid("bob"))


def test_a_cascade_is_consecutive_and_its_pre_cascade_revision_is_stale_afterwards(make_session: MakeSession) -> None:
    session = started(make_session, 4)  # dave is first to act, then alice, bob, carol
    leave(session, "alice")
    leave(session, "bob")
    revision = session.revision
    result = act(session, "dave", CALL)  # alice and bob fold in turn
    assert causes(result) == [COMMAND, AUTO, AUTO]
    assert (
        [t.revision for t in result.transitions]
        == [revision + 1, revision + 2, revision + 3]
        == [
            session.revision - 2,
            session.revision - 1,
            session.revision,
        ]
    )
    for transition in result.transitions:
        assert set(transition.views) == {uid(n) for n in NAMES[:4]}
        assert all(v.revision == transition.revision for v in transition.views.values())
    assert result.view is not None and result.view.revision == session.revision
    # The first transition already shows the pending flags and the hand before the leavers folded; the last the folds.
    assert result.transitions[0].views[uid("alice")].game.hand is not None
    assert not any(p.folded for p in result.transitions[0].views[uid("carol")].game.hand.participants)  # type: ignore[union-attr]
    assert sum(p.folded for p in result.transitions[-1].views[uid("carol")].game.hand.participants) == 2  # type: ignore[union-attr]
    before = fingerprint(session)
    for stale in (revision, revision + 1, revision + 2):
        assert isinstance(session.act(uid("carol"), stale, CHECK), Rejected)
        assert isinstance(session.sit_out(uid("dave"), stale), Rejected)
    assert fingerprint(session) == before


def test_every_shared_command_bumps_exactly_once_per_transition(make_session: MakeSession) -> None:
    session = make_session(3)
    for call, bumps in (
        (lambda: session.sit_out(uid("carol"), session.revision), 1),
        (lambda: session.sit_back(uid("carol"), session.revision), 1),
        (lambda: session.join(uid("dave"), session.revision, dname("dave"), 4), 1),
        (lambda: session.start_game(uid("alice"), session.revision), 1),
        (lambda: session.join(uid("erin"), session.revision, dname("erin"), 5), 1),  # a hand is running: no resume
        (lambda: session.sit_out(uid("erin"), session.revision), 1),  # erin is not a participant: applies at once
        (lambda: session.leave(uid("erin"), session.revision), 1),
    ):
        before = session.revision
        result = ok(call())
        assert session.revision == before + bumps and len(result.transitions) == bumps
        assert (
            result.transitions[0].revision == session.revision
            and result.view is not None
            or not session.is_member(uid("erin"))
        )


# --- the hand boundary: order, reset and conservation ---


def test_the_boundary_applies_leaves_and_sit_outs_before_the_next_hand_starts(make_session: MakeSession) -> None:
    session = started(make_session, 5)  # button 1; dave (4) is first to act
    leave(session, "bob")  # SB, off turn
    sit_out(session, "carol")  # BB, off turn
    for name in ("dave", "erin", "alice"):
        act(session, name, FOLD)  # bob folds automatically, carol wins the blinds
    assert session.phase is TablePhase.HAND_COMPLETE
    total = stack_total(session)
    revision = session.revision
    advance(session)
    assert session.revision == revision + 1
    assert not session.is_member(uid("bob"))
    hand = hand_of(session, "alice")
    assert hand.number == 2 and sorted(p.seat for p in hand.participants) == [1, 4, 5]  # no bob (2), no carol (3)
    assert view_of(session, "carol").game.seats[2].occupant.status.name == "SITTING_OUT"  # type: ignore[union-attr]
    assert not view_of(session, "carol").you.pending_sit_out
    assert stack_total(session) < total  # bob's chips left with him
    assert view_of(session, "alice").seats[1].display_name is None


def test_all_members_with_pending_leaves_empty_the_table_and_the_next_joiner_hosts(make_session: MakeSession) -> None:
    session = started(make_session)
    leave(session, "bob")  # off turn
    leave(session, "carol")  # off turn
    result = leave(session, "alice")  # alice is on turn: folds, bob folds, carol wins by default
    assert causes(result) == [AUTO, AUTO] and session.phase is TablePhase.HAND_COMPLETE
    assert all(view_of(session, n).you.pending_leave for n in NAMES[:3])
    revision = session.revision
    result = advance(session)
    assert causes(result) == [BOUNDARY] and result.transitions[0].views == {} and result.view is None
    assert session.revision == revision + 1 and session.phase is TablePhase.WAITING_FOR_PLAYERS
    assert not any(session.is_member(uid(n)) for n in NAMES)
    assert all(
        isinstance(session.join(uid(n), session.revision, dname(n), 1), Rejected) for n in NAMES[:3]
    )  # LEFT_TABLE

    result = join(session, "dave", 2)
    assert causes(result) == [COMMAND] and result.view is not None and result.view.you.is_host
    result = join(session, "erin", 1)
    assert causes(result) == [COMMAND, RESUME]
    hand = hand_of(session, "dave")
    assert hand.number == 1 and sorted(p.seat for p in hand.participants) == [1, 2]
    assert view_of(session, "erin").you.is_host is False


def test_a_leaver_whose_turn_never_comes_keeps_the_pending_intent_and_leaves_with_their_chips_at_the_boundary(
    make_session: MakeSession,
) -> None:
    session = started(make_session)
    assert leave(session, "carol").transitions == ()  # the big blind
    act(session, "alice", FOLD)
    result = act(session, "bob", FOLD)
    assert causes(result) == [COMMAND] and session.phase is TablePhase.HAND_COMPLETE
    assert view_of(session, "carol").you.pending_leave and session.is_member(uid("carol"))
    assert [s.occupant.stack for s in view_of(session, "bob").game.seats[:3] if s.occupant] == [1000, 995, 1005]
    advance(session)
    assert not session.is_member(uid("carol"))
    hand = hand_of(session, "alice")
    assert hand.number == 2 and sorted(p.seat for p in hand.participants) == [1, 2]
    assert stack_total(session) == 1000 + 995 + 0  # blinds are in front: alice and bob hold 1995 between them


def test_a_host_with_a_pending_leave_stays_host_until_the_boundary(make_session: MakeSession) -> None:
    session = started(make_session)
    assert causes(leave(session, "alice")) == [AUTO]  # on turn: the automatic fold
    assert all(v.seats[0].is_host for v in (view_of(session, "bob"), view_of(session, "carol")))
    rejected = session.start_game(uid("bob"), session.revision)
    assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.NOT_HOST
    act(session, "bob", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE and view_of(session, "alice").you.is_host
    advance(session)
    bob = view_of(session, "bob")
    assert bob.you.is_host and [s.is_host for s in bob.seats[:3]] == [False, True, False]
    assert not view_of(session, "carol").you.is_host


def test_several_leavers_in_one_showdown_muck_in_turn_each_as_its_own_transition(make_session: MakeSession) -> None:
    session = started(make_session)
    act(session, "alice", CALL)
    act(session, "bob", CALL)
    act(session, "carol", CHECK)
    while hand_of(session, "alice").turn.kind.name == "BETTING":  # type: ignore[union-attr]
        view = view_of(session, turn_name(session))
        assert view.game.hand is not None and view.game.hand.legal_actions is not None
        act(session, turn_name(session), CHECK)
    decider = turn_name(session)
    others = [n for n in NAMES[:3] if n != decider]
    for name in others:
        assert leave(session, name).transitions == ()  # off turn: private
    revision = session.revision
    result = act(session, decider, ShowdownAction.SHOW)
    assert causes(result) == [COMMAND, AUTO, AUTO]
    assert [t.revision for t in result.transitions] == [revision + 1, revision + 2, revision + 3]
    assert session.phase is TablePhase.HAND_COMPLETE and session.revision == revision + 3
    log = hand_of(session, decider).log
    assert sum(1 for e in log if type(e).__name__ == "ShowdownDecidedView") == 3


def test_a_leaver_with_a_check_option_checks_and_does_not_fold(make_session: MakeSession) -> None:
    session = started(make_session)
    act(session, "alice", CALL)
    act(session, "bob", CALL)
    result = leave(session, "carol")  # big blind with the option: CHECK, not FOLD
    assert causes(result) == [AUTO]
    carol = next(p for p in hand_of(session, "alice").participants if p.seat == 3)
    assert not carol.folded and hand_of(session, "alice").street.name == "FLOP"
    # On the flop the first to act is bob; carol, a leaver, then checks automatically behind him each street.
    result = act(session, "bob", CHECK)
    assert causes(result) == [COMMAND, AUTO]
    assert not next(p for p in hand_of(session, "alice").participants if p.seat == 3).folded
    # Facing a bet she folds.
    act(session, "alice", Action(ActionType.BET, 20))
    assert session.phase is TablePhase.HAND_IN_PROGRESS and turn_name(session) == "bob"
    act(session, "bob", CALL)
    assert next(p for p in hand_of(session, "alice").participants if p.seat == 3).folded


# --- waiting and resuming ---


def test_a_leave_while_waiting_that_resets_the_generation_is_two_transitions_and_later_joins_resume(
    make_session: MakeSession,
) -> None:
    session = make_session(3)
    ok(session.start_game(uid("alice"), session.revision))
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)  # carol wins: 1000 / 995 / 1005
    sit_out(session, "bob")
    sit_out(session, "carol")
    advance(session)  # only alice can play: waiting, same generation
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    assert hand_of(session, "alice").number == 1  # the old generation's settled hand

    revision = session.revision
    assert causes(leave(session, "bob")) == [COMMAND]  # nothing can resume: no extra transition
    assert session.revision == revision + 1 and hand_of(session, "alice").number == 1

    result = leave(session, "alice")  # the last READY player leaves: carol alone, in a fresh generation
    assert causes(result) == [COMMAND, RESUME] and session.revision == revision + 3
    assert result.view is None and session.phase is TablePhase.WAITING_FOR_PLAYERS
    carol = view_of(session, "carol")
    assert carol.game.hand is None and carol.you.is_host and carol.revision == session.revision
    assert carol.game.seats[2].occupant is not None and carol.game.seats[2].occupant.stack == 1005
    assert carol.game.seats[2].occupant.status.name == "SITTING_OUT"

    # A join that still cannot start a hand is one transition; the sit-back that completes the pair resumes.
    assert causes(join(session, "dave", 4)) == [COMMAND]
    assert causes(sit_back(session, "carol")) == [COMMAND, RESUME]
    assert hand_of(session, "carol").number == 1 and session.phase is TablePhase.HAND_IN_PROGRESS
    assert stack_total(session) == 1005 + 1000


def test_a_sit_back_while_waiting_can_replace_the_generation_before_a_hand_can_start(make_session: MakeSession) -> None:
    session = make_session(3)
    ok(session.start_game(uid("alice"), session.revision))
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)
    sit_out(session, "bob")
    sit_out(session, "carol")
    advance(session)
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    # A sit-out applied while waiting is a plain transition; the table keeps waiting.
    assert causes(sit_out(session, "alice")) == [COMMAND]
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    # Nobody is READY now, so the first sit-back replaces the generation (a RESUME transition) without starting a hand;
    # the second starts hand 1 of the new generation.
    assert causes(sit_back(session, "alice")) == [COMMAND, RESUME]
    assert view_of(session, "alice").game.hand is None and session.phase is TablePhase.WAITING_FOR_PLAYERS
    result = sit_back(session, "bob")
    assert causes(result) == [COMMAND, RESUME] and session.phase is TablePhase.HAND_IN_PROGRESS
    # carol stayed out of the hand she did not sit back for.
    assert sorted(p.seat for p in hand_of(session, "alice").participants) == [1, 2]


def test_chips_are_conserved_across_hands_and_a_reset_for_the_remaining_members(make_session: MakeSession) -> None:
    session = make_session(3)
    ok(session.start_game(uid("alice"), session.revision))
    act(session, "alice", Action(ActionType.RAISE, 40))
    act(session, "bob", FOLD)
    act(session, "carol", CALL)
    while session.phase is TablePhase.HAND_IN_PROGRESS:
        name = turn_name(session)
        hand = hand_of(session, name)
        if hand.turn is not None and hand.turn.kind.name == "SHOWDOWN":
            act(session, name, ShowdownAction.SHOW)
        else:
            act(session, name, CHECK)
    assert stack_total(session) == 3000
    sit_out(session, "alice")
    sit_out(session, "carol")
    bob_stack = next(s.occupant.stack for s in view_of(session, "bob").game.seats if s.number == 2 and s.occupant)
    assert bob_stack == 995
    leave(session, "bob")  # bob's chips go with him
    kept = stack_total(session)
    assert kept == 3000 - bob_stack
    revision = session.revision
    result = advance(session)  # nobody READY is left: generation reset
    assert causes(result) == [BOUNDARY] and session.revision == revision + 1
    assert stack_total(session) == kept and view_of(session, "alice").game.hand is None
    assert causes(sit_back(session, "alice")) == [COMMAND]
    result = sit_back(session, "carol")
    assert causes(result) == [COMMAND, RESUME]
    assert stack_total(session) == kept and hand_of(session, "alice").number == 1


# --- identity ---


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("Alice", "ALICE"),
        ("alice", "  alice\t"),
        ("Straße", "STRASSE"),  # casefold, not lower
        ("Café", "Café"),  # NFC versus NFD
        ("CAFÉ", "café"),
        ("İstanbul", "i̇stanbul"),
    ],
)
def test_display_name_conflict_keys_collide_by_case_normalization_and_trim(first: str, second: str) -> None:
    assert DisplayName(first).conflict_key == DisplayName(second).conflict_key
    assert len({DisplayName(first).conflict_key, DisplayName(second).conflict_key}) == 1


def test_display_name_collision_is_a_join_rejection_and_the_name_is_free_only_after_the_leave_applies(
    make_session: MakeSession,
) -> None:
    session = started(make_session)
    twin_id, twin_name = UserId("twin"), DisplayName("CAROL")
    assert isinstance(ok(session.join(UserId("w"), session.revision, DisplayName("Eve"), 5)), Accepted)
    leave(session, "carol")  # pending: carol is still a member and owns the name
    rejected = session.join(twin_id, session.revision, twin_name, 6)
    assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.DISPLAY_NAME_TAKEN
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)
    rejected = session.join(twin_id, session.revision, twin_name, 6)
    assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.DISPLAY_NAME_TAKEN  # still pending
    advance(session)
    result = ok(session.join(twin_id, session.revision, twin_name, 3))  # applied: free, and the seat is free too
    assert result.view is not None and result.view.seats[2].display_name == DisplayName("CAROL")
    assert result.view.seats[2].display_name is not None and result.view.seats[2].display_name.value == "CAROL"
    again = session.join(uid("carol"), session.revision, dname("carol"), 4)  # the original id is still barred
    assert isinstance(again, Rejected) and again.code is RejectionCode.LEFT_TABLE


@pytest.mark.parametrize("codepoint", [0x1F0, 0x390, 0x3B0, 0x1E96, 0x1F50, 0x1FB6, 0x1FE4, 0x1FF7])
def test_conflict_key_is_renormalized_after_casefold(codepoint: int) -> None:
    # These characters casefold to a decomposed sequence that has a precomposed NFC form.
    text = chr(codepoint)
    assert unicodedata.normalize("NFC", text.casefold()) != text.casefold()
    key = DisplayName(text).conflict_key
    assert key == unicodedata.normalize("NFC", key)
    assert DisplayName(text).conflict_key == DisplayName(unicodedata.normalize("NFD", text)).conflict_key


def test_join_check_order_is_revision_then_left_table_then_already_member_then_name_then_seat(
    make_session: MakeSession,
) -> None:
    session = make_session(3)
    leave(session, "carol")  # carol is departed; alice and bob are members; dave is a stranger
    rev = session.revision

    def code(result: CommandResult) -> RejectionCode:
        assert isinstance(result, Rejected)
        return result.code

    alice_name, bob_name, carol_name = dname("alice"), dname("bob"), dname("carol")
    before = fingerprint(session)
    # A stale revision beats everything, including a departed id and a taken name.
    assert code(session.join(uid("carol"), rev - 1, carol_name, 1)) is RejectionCode.STALE_REVISION
    assert code(session.join(uid("dave"), rev + 1, DisplayName("ALICE"), 1)) is RejectionCode.STALE_REVISION
    # A departed id is LEFT_TABLE even when it asks for a member's name (case-changed) and a taken or invalid seat.
    assert code(session.join(uid("carol"), rev, DisplayName("ALICE"), 1)) is RejectionCode.LEFT_TABLE
    assert code(session.join(uid("carol"), rev, DisplayName("bOB"), 99)) is RejectionCode.LEFT_TABLE
    # An existing member is ALREADY_MEMBER even when the name is its own or another member's.
    assert code(session.join(uid("alice"), rev, alice_name, 1)) is RejectionCode.ALREADY_MEMBER
    assert code(session.join(uid("alice"), rev, DisplayName("BOB"), 1)) is RejectionCode.ALREADY_MEMBER
    assert code(session.join(uid("bob"), rev, DisplayName("ALICE"), 99)) is RejectionCode.ALREADY_MEMBER
    # A taken name (including the host's) beats a taken or invalid seat.
    assert code(session.join(uid("dave"), rev, DisplayName("aLiCe"), 1)) is RejectionCode.DISPLAY_NAME_TAKEN
    assert code(session.join(uid("dave"), rev, bob_name, 99)) is RejectionCode.DISPLAY_NAME_TAKEN
    # The departed member's name is free, so only the seat is judged.
    assert code(session.join(uid("dave"), rev, DisplayName("CAROL"), 1)) is RejectionCode.SEAT_TAKEN
    assert code(session.join(uid("dave"), rev, DisplayName("CAROL"), 99)) is RejectionCode.INVALID_SEAT
    assert fingerprint(session) == before


def test_a_name_rejected_as_taken_leaves_the_seat_and_the_user_free(make_session: MakeSession) -> None:
    session = make_session(2)
    rejected = session.join(uid("dave"), session.revision, DisplayName("BOB"), 4)
    assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.DISPLAY_NAME_TAKEN
    assert not session.is_member(uid("dave")) and view_of(session, "alice").seats[3].display_name is None
    result = ok(session.join(uid("dave"), session.revision, DisplayName("Dave"), 4))  # the same id, seat and a new name
    assert result.view is not None and result.view.seats[3].display_name == DisplayName("Dave")


def test_the_hosts_name_is_held_until_the_host_leaves_and_then_free(make_session: MakeSession) -> None:
    session = make_session(3)
    taken = session.join(uid("dave"), session.revision, DisplayName("ALICE"), 4)
    assert isinstance(taken, Rejected) and taken.code is RejectionCode.DISPLAY_NAME_TAKEN
    leave(session, "alice")  # the host leaves; bob becomes host
    assert view_of(session, "bob").you.is_host
    result = ok(session.join(uid("dave"), session.revision, DisplayName("ALICE"), 1))
    assert result.view is not None and result.view.seats[0].display_name == DisplayName("ALICE")
    assert result.view.seats[0].display_name is not None and result.view.seats[0].display_name.value == "ALICE"
    again = session.join(uid("alice"), session.revision, DisplayName("Alice"), 5)
    assert isinstance(again, Rejected) and again.code is RejectionCode.LEFT_TABLE


def test_every_view_shows_the_name_with_the_casing_the_joiner_gave(make_session: MakeSession) -> None:
    session = make_session(2)
    result = ok(session.join(uid("carol"), session.revision, DisplayName("  cArOl  "), 3))
    transition = result.transitions[0]
    assert set(transition.views) == {uid("alice"), uid("bob"), uid("carol")}
    for view in transition.views.values():
        assert_clean(view)
        names = [seat.display_name for seat in view.seats]
        assert names[:3] == [DisplayName("Alice"), DisplayName("Bob"), DisplayName("cArOl")]
        assert [n.value for n in names if n is not None] == ["Alice", "Bob", "cArOl"]


def test_names_that_only_look_alike_without_case_equivalence_do_not_collide(make_session: MakeSession) -> None:
    session = make_session(2)
    # Dotless i and dotted capital I are different letters under casefold; "e" with a combining mark is not "e".
    ok(session.join(uid("carol"), session.revision, DisplayName("ı"), 3))
    ok(session.join(uid("dave"), session.revision, DisplayName("I"), 4))
    ok(session.join(uid("erin"), session.revision, DisplayName("Ali"), 5))
    ok(session.join(uid("frank"), session.revision, DisplayName("Alicé"), 6))  # "Alicé" is not "Alice"
    assert len({seat.display_name for seat in view_of(session, "alice").seats}) == 6


@pytest.mark.parametrize("text", ["", "   ", "\t", "a\nb", "a​b", "\u0007", "x" * 21, "\ud800"])
def test_invalid_display_names_raise(text: str) -> None:
    with pytest.raises(ValueError):
        DisplayName(text)


def test_display_name_length_is_counted_after_nfc_and_trim() -> None:
    assert DisplayName("x" * 20).value == "x" * 20
    assert DisplayName(" " + "x" * 20 + " ").value == "x" * 20
    decomposed = "é" * 20  # 40 code points, 20 after NFC
    assert DisplayName(decomposed).value == unicodedata.normalize("NFC", decomposed)
    with pytest.raises(ValueError):
        DisplayName("é" * 21)
    assert DisplayName("a b").value == "a b"  # inner spaces are allowed


def test_user_ids_are_case_sensitive_opaque_and_never_in_any_view(make_session: MakeSession) -> None:
    session = make_session(3)
    assert UserId("Bob") != UserId("bob")
    twin = UserId("UID-ALICE-7F3A")  # an id that differs from alice's only by case
    assert isinstance(ok(session.join(twin, session.revision, DisplayName("Twin"), 4)), Accepted)
    ok(session.start_game(uid("alice"), session.revision))
    result = ok(session.act(twin, session.revision, FOLD))  # the twin is first to act
    for transition in result.transitions:
        for view in transition.views.values():
            assert_clean(view)
    for name in NAMES[:4]:
        if name == "dave":
            continue
        assert_clean(view_of(session, name))
    assert session.view_for(UserId("UID-ALICE-7F3A")) is not None and session.view_for(UserId("uid-alice")) is None
    with pytest.raises(ValueError):
        UserId("")

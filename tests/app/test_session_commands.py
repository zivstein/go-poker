"""`TableSession` commands: each command's happy path and each rejection code.

Every rejection is checked to leave the revision and every member's view unchanged. Seats follow the join order:
alice 1 (host), bob 2, carol 3, ...; the button is seat 1. With three players seat 1 acts first before the flop.
"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.results import Accepted, CommandResult, Rejected, RejectionCode, TransitionCause
from go_poker.app.session import TableSession
from go_poker.app.views import TablePhase, TableSettings, TableView, YouView
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.stakes import Stakes
from go_poker.game.showdown import ShowdownAction
from go_poker.game.table import InvalidSeatNumber
from go_poker.game.variants.texas_holdem.game import HoldemGame
from go_poker.game.variants.texas_holdem.view import OccupantStatus, OccupantView

type MakeSession = Callable[..., TableSession]

NAMES = ("alice", "bob", "carol", "dave", "erin", "frank", "zed")
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def uid(name: str) -> UserId:
    return UserId(f"uid-{name}-7f3a")  # the convention of conftest's `_user_id`


def dname(name: str) -> DisplayName:
    return DisplayName(name.capitalize())  # the convention of conftest's `_display_name`


def ok(result: CommandResult) -> Accepted:
    assert isinstance(result, Accepted), result
    return result


def snapshot(session: TableSession) -> tuple[object, ...]:
    return (session.revision, session.phase, tuple(session.view_for(uid(name)) for name in NAMES))


def rejection_leaves_everything_unchanged(
    session: TableSession, code: RejectionCode, call: Callable[[], object]
) -> None:
    before = snapshot(session)
    result = call()
    assert isinstance(result, Rejected), result
    assert result.code is code
    assert result.message
    assert snapshot(session) == before


def act(session: TableSession, name: str, action: Action | ShowdownAction) -> Accepted:
    return ok(session.act(uid(name), session.revision, action))


def started(make_session: MakeSession, joined: int = 3) -> TableSession:
    session = make_session(joined)
    ok(session.start_game(uid("alice"), session.revision))
    return session


def fold_out(session: TableSession) -> None:
    """Seat 1 and seat 2 fold, so seat 3 (big blind) wins the blinds and the hand is complete."""
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE


def occupant(view: TableView, seat: int) -> OccupantView | None:
    return view.game.seats[seat - 1].occupant


# --- create ---


def test_create_seats_the_host_as_a_waiting_player_at_revision_one(make_session: MakeSession) -> None:
    session = make_session(1)
    view = session.view_for(uid("alice"))
    assert view is not None
    assert (session.revision, view.revision, session.phase) == (1, 1, TablePhase.NOT_STARTED)
    assert (view.table_id, view.code, view.phase) == ("table-1", "ABCD", TablePhase.NOT_STARTED)
    assert view.settings == TableSettings(Stakes(5, 10), 1000, 6)
    assert view.you == YouView(seat=1, is_host=True, pending_leave=False, pending_sit_out=False)
    assert occupant(view, 1) == OccupantView(stack=1000, status=OccupantStatus.WAITING_TO_JOIN)
    assert view.game.hand is None
    assert [(s.number, s.display_name, s.is_host) for s in view.seats] == [(1, DisplayName("Alice"), True)] + [
        (n, None, False) for n in range(2, 7)
    ]
    assert session.is_member(uid("alice"))
    assert not session.is_member(uid("bob"))
    assert session.view_for(uid("bob")) is None


@pytest.mark.parametrize(
    ("table_id", "code", "buy_in", "max_seats", "seat", "error"),
    [
        ("", "ABCD", 1000, 6, 1, ValueError),
        ("t", "", 1000, 6, 1, ValueError),
        ("t", "ABCD", 0, 6, 1, ValueError),
        ("t", "ABCD", -5, 6, 1, ValueError),
        ("t", "ABCD", True, 6, 1, ValueError),
        ("t", "ABCD", 1000, 1, 1, ValueError),
        ("t", "ABCD", 1000, 10, 1, ValueError),
        ("t", "ABCD", 1000, 6, 0, InvalidSeatNumber),
        ("t", "ABCD", 1000, 6, 7, InvalidSeatNumber),
    ],
)
def test_create_raises_on_invalid_input(
    table_id: str, code: str, buy_in: int, max_seats: int, seat: int, error: type[Exception]
) -> None:
    with pytest.raises(error):
        settings = TableSettings(Stakes(5, 10), buy_in, max_seats)
        TableSession.create(
            table_id, code, settings, uid("alice"), dname("alice"), seat, choose_button=lambda seats: seats[0]
        )


# --- join ---


def test_join_seats_the_user_as_waiting_with_the_buy_in_in_one_transition(make_session: MakeSession) -> None:
    session = make_session(1)
    result = ok(session.join(uid("bob"), 1, dname("bob"), 2))
    (transition,) = result.transitions
    assert (transition.revision, transition.cause, session.revision) == (2, TransitionCause.COMMAND, 2)
    assert set(transition.views) == {uid("alice"), uid("bob")}
    assert result.view == transition.views[uid("bob")] == session.view_for(uid("bob"))
    assert result.view is not None
    assert result.view.you == YouView(seat=2, is_host=False, pending_leave=False, pending_sit_out=False)
    assert occupant(result.view, 2) == OccupantView(1000, OccupantStatus.WAITING_TO_JOIN)
    assert transition.views[uid("alice")].seats[1].display_name == DisplayName("Bob")
    with pytest.raises(TypeError):
        transition.views[uid("zed")] = result.view  # type: ignore[index]


@pytest.mark.parametrize(
    ("code", "call"),
    [
        (RejectionCode.STALE_REVISION, lambda s: s.join(uid("bob"), s.revision + 1, dname("bob"), 2)),
        (
            RejectionCode.STALE_REVISION,
            lambda s: s.join(uid("alice"), 99, dname("alice"), 1),
        ),  # the revision is checked first
        (RejectionCode.ALREADY_MEMBER, lambda s: s.join(uid("alice"), s.revision, dname("alice"), 3)),
        (RejectionCode.ALREADY_MEMBER, lambda s: s.join(uid("alice"), s.revision, DisplayName("Other"), 3)),
        (RejectionCode.DISPLAY_NAME_TAKEN, lambda s: s.join(UserId("other"), s.revision, DisplayName("  ALICE "), 3)),
        (RejectionCode.SEAT_TAKEN, lambda s: s.join(uid("bob"), s.revision, dname("bob"), 1)),
        (RejectionCode.INVALID_SEAT, lambda s: s.join(uid("bob"), s.revision, dname("bob"), 0)),
        (RejectionCode.INVALID_SEAT, lambda s: s.join(uid("bob"), s.revision, dname("bob"), 7)),
    ],
)
def test_join_rejections(
    make_session: MakeSession, code: RejectionCode, call: Callable[[TableSession], CommandResult]
) -> None:
    session = make_session(1)
    rejection_leaves_everything_unchanged(session, code, lambda: call(session))


def test_a_user_who_left_cannot_join_again_but_their_display_name_is_free(make_session: MakeSession) -> None:
    session = make_session(2)
    ok(session.leave(uid("bob"), session.revision))
    rejection_leaves_everything_unchanged(
        session, RejectionCode.LEFT_TABLE, lambda: session.join(uid("bob"), session.revision, dname("bob"), 2)
    )
    rejection_leaves_everything_unchanged(
        session,
        RejectionCode.LEFT_TABLE,
        lambda: session.join(uid("bob"), session.revision, DisplayName("Robert"), 2),
    )
    result = ok(session.join(UserId("someone-else"), session.revision, DisplayName("BOB"), 2))
    assert result.view is not None and result.view.you.seat == 2


@pytest.mark.parametrize(
    "taken,attempt",
    [
        ("Bob", "bob"),
        ("Bob", "  BOB "),
        ("Straße", "STRASSE"),
        ("Café", "CAFÉ"),  # NFD versus NFC, upper case
    ],
)
def test_a_display_name_differing_only_by_case_or_normalization_is_taken_until_its_member_leaves(
    make_session: MakeSession, taken: str, attempt: str
) -> None:
    session = make_session(1)
    ok(session.join(UserId("bob-id"), session.revision, DisplayName(taken), 2))
    rejection_leaves_everything_unchanged(
        session,
        RejectionCode.DISPLAY_NAME_TAKEN,
        lambda: session.join(UserId("newcomer"), session.revision, DisplayName(attempt), 3),
    )
    ok(session.leave(UserId("bob-id"), session.revision))  # no hand: applies at once
    result = ok(session.join(UserId("newcomer"), session.revision, DisplayName(attempt), 3))
    assert result.view is not None and result.view.seats[2].display_name == DisplayName(attempt)


# --- leave, and the host ---


def test_leave_with_no_hand_applies_at_once_and_removes_the_member(make_session: MakeSession) -> None:
    session = make_session(3)
    result = ok(session.leave(uid("bob"), session.revision))
    (transition,) = result.transitions
    assert (transition.cause, transition.revision, session.revision) == (TransitionCause.COMMAND, 4, 4)
    assert result.view is None
    assert set(transition.views) == {uid("alice"), uid("carol")}
    assert not session.is_member(uid("bob")) and session.view_for(uid("bob")) is None
    alice = transition.views[uid("alice")]
    assert occupant(alice, 2) is None and alice.seats[1].display_name is None


def test_the_earliest_joined_remaining_member_becomes_host_and_the_next_joiner_when_empty(
    make_session: MakeSession,
) -> None:
    session = make_session(3)
    result = ok(session.leave(uid("alice"), session.revision))  # the host leaves: bob joined before carol
    (transition,) = result.transitions
    assert transition.views[uid("bob")].you.is_host and not transition.views[uid("carol")].you.is_host
    assert [seat.is_host for seat in transition.views[uid("carol")].seats] == [False, True, False, False, False, False]
    ok(session.leave(uid("bob"), session.revision))
    ok(session.leave(uid("carol"), session.revision))
    assert session.revision == 6
    newcomer = ok(session.join(uid("dave"), session.revision, dname("dave"), 4))
    assert newcomer.view is not None and newcomer.view.you.is_host
    second = ok(session.join(uid("erin"), session.revision, dname("erin"), 5))
    assert second.view is not None and not second.view.you.is_host


# --- sit out and sit back ---


def test_sit_out_and_sit_back_apply_at_once_without_a_hand(make_session: MakeSession) -> None:
    session = make_session(2)
    out = ok(session.sit_out(uid("bob"), session.revision))
    assert [(t.cause, t.revision) for t in out.transitions] == [(TransitionCause.COMMAND, 3)]
    assert out.view is not None and occupant(out.view, 2) == OccupantView(1000, OccupantStatus.SITTING_OUT)
    back = ok(session.sit_back(uid("bob"), session.revision))
    assert [t.revision for t in back.transitions] == [4]
    assert back.view is not None and occupant(back.view, 2) == OccupantView(1000, OccupantStatus.WAITING_TO_JOIN)
    assert session.phase is TablePhase.NOT_STARTED  # nothing to resume before the game starts


def test_repeating_what_is_already_in_effect_is_no_change(make_session: MakeSession) -> None:
    session = make_session(2)
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NO_CHANGE, lambda: session.sit_back(uid("bob"), session.revision)
    )
    ok(session.sit_out(uid("bob"), session.revision))
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NO_CHANGE, lambda: session.sit_out(uid("bob"), session.revision)
    )


# --- start_game ---


def test_start_game_by_the_host_starts_the_first_hand(make_session: MakeSession) -> None:
    session = make_session(3)
    result = ok(session.start_game(uid("alice"), session.revision))
    (transition,) = result.transitions
    assert (transition.cause, transition.revision, session.phase) == (
        TransitionCause.COMMAND,
        4,
        TablePhase.HAND_IN_PROGRESS,
    )
    assert result.view is not None and result.view.game.hand is not None
    hand = result.view.game.hand
    assert hand.number == 1 and hand.turn is not None and hand.turn.seat == 1
    assert [occupant(result.view, seat) for seat in (1, 2, 3)] == [
        OccupantView(1000, None),
        OccupantView(995, None),
        OccupantView(990, None),
    ]


@pytest.mark.parametrize(
    ("code", "call"),
    [
        (RejectionCode.STALE_REVISION, lambda s: s.start_game(uid("alice"), s.revision - 1)),
        (RejectionCode.NOT_A_MEMBER, lambda s: s.start_game(uid("zed"), s.revision)),
        (RejectionCode.NOT_HOST, lambda s: s.start_game(uid("bob"), s.revision)),
    ],
)
def test_start_game_rejections(
    make_session: MakeSession, code: RejectionCode, call: Callable[[TableSession], CommandResult]
) -> None:
    session = make_session(3)
    rejection_leaves_everything_unchanged(session, code, lambda: call(session))


def test_start_game_needs_two_players_who_can_play_and_starts_only_once(make_session: MakeSession) -> None:
    alone = make_session(1)
    rejection_leaves_everything_unchanged(
        alone, RejectionCode.NOT_ENOUGH_PLAYERS, lambda: alone.start_game(uid("alice"), alone.revision)
    )
    session = make_session(2)
    ok(session.sit_out(uid("bob"), session.revision))
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NOT_ENOUGH_PLAYERS, lambda: session.start_game(uid("alice"), session.revision)
    )
    ok(session.sit_back(uid("bob"), session.revision))
    ok(session.start_game(uid("alice"), session.revision))
    rejection_leaves_everything_unchanged(
        session, RejectionCode.GAME_ALREADY_STARTED, lambda: session.start_game(uid("alice"), session.revision)
    )


# --- act ---


def test_act_passes_the_action_to_the_engine_and_is_one_transition(make_session: MakeSession) -> None:
    session = started(make_session)
    revision = session.revision
    result = act(session, "alice", CALL)
    (transition,) = result.transitions
    assert (transition.cause, transition.revision, session.revision) == (
        TransitionCause.COMMAND,
        revision + 1,
        revision + 1,
    )
    assert result.view is not None and result.view.game.hand is not None
    assert result.view.game.hand.turn is not None and result.view.game.hand.turn.seat == 2
    assert result.view.game.hand.legal_actions is None  # alice is no longer the actor
    bob = transition.views[uid("bob")].game.hand
    assert bob is not None and bob.legal_actions is not None  # the new actor sees their own legal actions


def test_act_rejections_map_the_engine_errors(make_session: MakeSession) -> None:
    session = started(make_session)
    for code, call in [
        (RejectionCode.STALE_REVISION, lambda: session.act(uid("alice"), session.revision - 1, CALL)),
        (RejectionCode.NOT_A_MEMBER, lambda: session.act(uid("zed"), session.revision, CALL)),
        (RejectionCode.NOT_YOUR_TURN, lambda: session.act(uid("bob"), session.revision, CALL)),
        (RejectionCode.NOT_YOUR_TURN, lambda: session.act(uid("alice"), session.revision, ShowdownAction.SHOW)),
        (RejectionCode.ILLEGAL_ACTION, lambda: session.act(uid("alice"), session.revision, CHECK)),
        (RejectionCode.ILLEGAL_ACTION, lambda: session.act(uid("alice"), session.revision, Action(ActionType.BET, 50))),
        (
            RejectionCode.ILLEGAL_ACTION,
            lambda: session.act(uid("alice"), session.revision, Action(ActionType.RAISE, 11)),
        ),
    ]:
        rejection_leaves_everything_unchanged(session, code, call)


def test_act_without_a_hand_in_progress_is_rejected(make_session: MakeSession) -> None:
    session = make_session(3)
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NO_HAND_IN_PROGRESS, lambda: session.act(uid("alice"), session.revision, CALL)
    )
    ok(session.start_game(uid("alice"), session.revision))
    fold_out(session)
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NO_HAND_IN_PROGRESS, lambda: session.act(uid("carol"), session.revision, CHECK)
    )


def test_a_stale_act_is_rejected_before_the_engine_is_called(
    make_session: MakeSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = started(make_session)

    def engine_must_not_be_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("the engine was called")

    monkeypatch.setattr(HoldemGame, "act", engine_must_not_be_called)
    result = session.act(uid("alice"), session.revision - 1, CALL)
    assert isinstance(result, Rejected) and result.code is RejectionCode.STALE_REVISION


def test_an_unmapped_engine_error_propagates_and_changes_nothing(make_session: MakeSession) -> None:
    session = started(make_session)
    before = snapshot(session)
    with pytest.raises(TypeError):
        session.act(uid("alice"), session.revision, "fold")  # type: ignore[arg-type]
    assert snapshot(session) == before


# --- advance_hand ---


def test_advance_hand_is_accepted_only_when_the_hand_is_complete(make_session: MakeSession) -> None:
    session = make_session(3)
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NOT_AT_HAND_BOUNDARY, lambda: session.advance_hand(session.revision)
    )
    ok(session.start_game(uid("alice"), session.revision))
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NOT_AT_HAND_BOUNDARY, lambda: session.advance_hand(session.revision)
    )
    fold_out(session)
    rejection_leaves_everything_unchanged(
        session, RejectionCode.STALE_REVISION, lambda: session.advance_hand(session.revision - 1)
    )
    result = ok(session.advance_hand(session.revision))
    assert result.view is None
    (transition,) = result.transitions
    assert transition.cause is TransitionCause.HAND_BOUNDARY and transition.revision == session.revision
    assert session.phase is TablePhase.HAND_IN_PROGRESS
    view = transition.views[uid("alice")].game.hand
    assert view is not None and view.number == 2


# --- commands of a non-member ---


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.leave(uid("zed"), s.revision),
        lambda s: s.sit_out(uid("zed"), s.revision),
        lambda s: s.sit_back(uid("zed"), s.revision),
        lambda s: s.start_game(uid("zed"), s.revision),
        lambda s: s.act(uid("zed"), s.revision, FOLD),
    ],
)
def test_a_command_from_a_non_member_is_rejected(
    make_session: MakeSession, call: Callable[[TableSession], CommandResult]
) -> None:
    session = make_session(2)
    rejection_leaves_everything_unchanged(session, RejectionCode.NOT_A_MEMBER, lambda: call(session))


@pytest.mark.parametrize(
    "call",
    [
        lambda s: s.leave(uid("bob"), s.revision + 1),
        lambda s: s.sit_out(uid("bob"), s.revision + 1),
        lambda s: s.sit_back(uid("bob"), s.revision + 1),
        lambda s: s.start_game(uid("alice"), s.revision + 1),
        lambda s: s.act(uid("bob"), s.revision + 1, FOLD),
        lambda s: s.advance_hand(s.revision + 1),
        lambda s: s.leave(uid("zed"), s.revision + 1),  # the revision is checked before membership
    ],
)
def test_every_state_changing_command_is_rejected_on_a_stale_revision(
    make_session: MakeSession, call: Callable[[TableSession], CommandResult]
) -> None:
    session = make_session(2)
    rejection_leaves_everything_unchanged(session, RejectionCode.STALE_REVISION, lambda: call(session))


# --- private intents ---


def test_a_participants_sit_out_is_a_private_intent_that_a_sit_back_cancels(make_session: MakeSession) -> None:
    session = started(make_session)
    before = {name: session.view_for(uid(name)) for name in ("alice", "bob", "carol")}
    revision = session.revision

    pending = ok(session.sit_out(uid("bob"), revision))
    assert pending.transitions == () and session.revision == revision
    assert pending.view is not None and pending.view.you.pending_sit_out
    assert session.view_for(uid("alice")) == before["alice"] and session.view_for(uid("carol")) == before["carol"]
    bob_before = before["bob"]
    assert bob_before is not None
    assert replace(pending.view, you=bob_before.you) == bob_before  # only bob's own intents differ
    assert occupant(pending.view, 2) == occupant(bob_before, 2)  # the engine status is untouched

    rejection_leaves_everything_unchanged(
        session, RejectionCode.NO_CHANGE, lambda: session.sit_out(uid("bob"), session.revision)
    )
    cancelled = ok(session.sit_back(uid("bob"), revision))
    assert cancelled.transitions == () and cancelled.view == before["bob"] and session.revision == revision
    rejection_leaves_everything_unchanged(
        session, RejectionCode.NO_CHANGE, lambda: session.sit_back(uid("bob"), session.revision)
    )


def test_a_pending_leave_blocks_sit_out_and_sit_back_and_cannot_be_repeated_or_cancelled(
    make_session: MakeSession,
) -> None:
    session = started(make_session)
    ok(session.sit_out(uid("bob"), session.revision))
    revision = session.revision
    result = ok(session.leave(uid("bob"), revision))  # not bob's turn: private
    assert result.transitions == () and session.revision == revision
    assert result.view is not None and result.view.you.pending_leave and not result.view.you.pending_sit_out
    codes = [
        session.sit_out(uid("bob"), session.revision),
        session.sit_back(uid("bob"), session.revision),
        session.leave(uid("bob"), session.revision),
    ]
    assert [r.code for r in codes if isinstance(r, Rejected)] == [
        RejectionCode.LEAVE_PENDING,
        RejectionCode.LEAVE_PENDING,
        RejectionCode.NO_CHANGE,
    ]
    assert session.revision == revision


def test_private_intents_are_rejected_on_a_stale_revision_and_reads_change_nothing(make_session: MakeSession) -> None:
    session = started(make_session)
    for call in (
        lambda: session.sit_out(uid("bob"), session.revision - 1),
        lambda: session.leave(uid("bob"), session.revision + 3),
    ):
        rejection_leaves_everything_unchanged(session, RejectionCode.STALE_REVISION, call)
    before = snapshot(session)
    for name in NAMES:
        session.view_for(uid(name))
        session.is_member(uid(name))
    _ = (session.revision, session.phase)
    assert snapshot(session) == before


def test_a_non_participant_during_a_hand_changes_status_and_leaves_at_once(make_session: MakeSession) -> None:
    session = started(make_session, joined=3)
    ok(
        session.join(uid("dave"), session.revision, dname("dave"), 4)
    )  # seated during the hand: a WAITING non-participant
    revision = session.revision
    out = ok(session.sit_out(uid("dave"), revision))
    assert [t.revision for t in out.transitions] == [revision + 1]
    assert out.view is not None and occupant(out.view, 4) == OccupantView(1000, OccupantStatus.SITTING_OUT)
    back = ok(session.sit_back(uid("dave"), session.revision))
    assert [t.cause for t in back.transitions] == [TransitionCause.COMMAND]
    left = ok(session.leave(uid("dave"), session.revision))
    assert left.view is None and [t.cause for t in left.transitions] == [TransitionCause.COMMAND]
    assert session.phase is TablePhase.HAND_IN_PROGRESS and not session.is_member(uid("dave"))

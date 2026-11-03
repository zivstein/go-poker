"""Pre-actions on `TableSession`: the options per obligation, the private select and clear commands, every rejection,
the reconciliation of selections inside each shared transition, and their execution when the turn arrives.

Seats follow the join order: alice 1, bob 2, carol 3, dave 4. The first button is seat 1, so three-handed the preflop
order is alice, bob, carol and every later street starts with bob; four-handed the preflop order is dave, alice, bob,
carol. Blinds are 5 and 10.
"""

from collections.abc import Callable
from dataclasses import replace
from typing import Any

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.app.results import Accepted, CommandResult, Rejected, RejectionCode, TransitionCause
from go_poker.app.session import TableSession, _pre_action_to_action  # noqa: PLC2701
from go_poker.app.views import TablePhase, TableView
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street

type MakeSession = Callable[..., TableSession]

NAMES = ("alice", "bob", "carol", "dave", "erin", "frank")
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
COMMAND = TransitionCause.COMMAND
AUTO = TransitionCause.LEAVE_AUTO_ACTION
PRE = TransitionCause.PRE_ACTION

PA_CHECK = PreAction(PreActionKind.CHECK)
PA_CHECK_OR_FOLD = PreAction(PreActionKind.CHECK_OR_FOLD)
PA_FOLD = PreAction(PreActionKind.FOLD)


def pa_call(amount: int) -> PreAction:
    return PreAction(PreActionKind.CALL_CURRENT, amount)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def bet(amount: int) -> Action:
    return Action(ActionType.BET, amount)


def uid(name: str) -> UserId:
    return UserId(f"uid-{name}-7f3a")  # the convention of conftest's `_user_id`


# --- helpers ---


def ok(result: CommandResult) -> Accepted:
    assert isinstance(result, Accepted), result
    return result


def view(session: TableSession, name: str) -> TableView:
    found = session.view_for(uid(name))
    assert found is not None
    return found


def snapshot(session: TableSession) -> tuple[object, ...]:
    """The revision, phase and every view, and each member's stored selection: what a rejection must not change."""
    members = tuple((m.user_id, m.pre_action, m.consumed) for m in session._members.values())  # noqa: SLF001
    return (session.revision, session.phase, tuple(session.view_for(uid(name)) for name in NAMES), members)


def act(session: TableSession, name: str, action: Action | ShowdownAction) -> Accepted:
    result = ok(session.act(uid(name), session.revision, action))
    revisions = [t.revision for t in result.transitions]
    assert revisions == list(range(revisions[0], revisions[0] + len(revisions)))  # consecutive
    assert revisions[-1] == session.revision
    return result


def select(session: TableSession, name: str, pre_action: PreAction) -> Accepted:
    revision = session.revision
    result = ok(session.select_pre_action(uid(name), revision, pre_action))
    assert result.transitions == () and session.revision == revision
    assert result.view == view(session, name) and result.view is not None and result.view.revision == revision
    return result


def clear(session: TableSession, name: str) -> Accepted:
    revision = session.revision
    result = ok(session.clear_pre_action(uid(name), revision))
    assert result.transitions == () and session.revision == revision
    assert result.view == view(session, name)
    return result


def causes(result: Accepted) -> list[TransitionCause]:
    return [transition.cause for transition in result.transitions]


def you_of(table_view: TableView) -> tuple[PreAction | None, tuple[PreAction, ...]]:
    return table_view.you.pre_action, table_view.you.pre_action_options


def selected(session: TableSession, name: str) -> PreAction | None:
    return view(session, name).you.pre_action


def options(session: TableSession, name: str) -> tuple[PreAction, ...]:
    return view(session, name).you.pre_action_options


def turn_seat(session: TableSession) -> int | None:
    turn = view(session, "alice").game.hand.turn if view(session, "alice").game.hand else None  # type: ignore[union-attr]
    return None if turn is None else turn.seat


def started(make_session: MakeSession, joined: int = 3) -> TableSession:
    session = make_session(joined)
    ok(session.start_game(uid("alice"), session.revision))
    return session


def to_flop(session: TableSession) -> None:
    """Three-handed preflop, called around: the flop starts with bob to act."""
    act(session, "alice", CALL)
    act(session, "bob", CALL)
    act(session, "carol", CHECK)
    assert (view(session, "bob").game.hand.street, turn_seat(session)) == (Street.FLOP, 2)  # type: ignore[union-attr]


# --- the values ---


@pytest.mark.parametrize(
    "kind, amount",
    [
        (PreActionKind.CHECK, 5),
        (PreActionKind.CHECK_OR_FOLD, 1),
        (PreActionKind.FOLD, 0),
        (PreActionKind.CALL_CURRENT, None),
        (PreActionKind.CALL_CURRENT, 0),
        (PreActionKind.CALL_CURRENT, -5),
        (PreActionKind.CALL_CURRENT, True),
        (PreActionKind.CALL_CURRENT, 2.5),
        ("check", None),
    ],
)
def test_an_invalid_pre_action_cannot_be_constructed(kind: Any, amount: Any) -> None:
    with pytest.raises(ValueError):
        PreAction(kind, amount)


def test_a_valid_pre_action_has_value_equality() -> None:
    assert PreAction(PreActionKind.CHECK) == PA_CHECK and PA_CHECK != PA_FOLD
    assert pa_call(20) == PreAction(PreActionKind.CALL_CURRENT, 20) and pa_call(20) != pa_call(10)


# --- options ---


def test_options_follow_what_each_seat_owes_and_are_empty_on_its_own_turn(make_session: MakeSession) -> None:
    session = make_session(3)
    assert [options(session, name) for name in ("alice", "bob")] == [(), ()]  # the game has not started
    ok(session.start_game(uid("alice"), session.revision))

    assert options(session, "alice") == ()  # alice is on turn
    assert options(session, "bob") == (PA_FOLD, pa_call(5))  # the small blind owes the rest of the blind
    assert options(session, "carol") == (PA_CHECK, PA_CHECK_OR_FOLD)  # the big blind owes nothing yet
    assert all(selected(session, name) is None for name in ("alice", "bob", "carol"))

    act(session, "alice", CALL)
    assert options(session, "alice") == (PA_CHECK, PA_CHECK_OR_FOLD)  # called the blind: owes nothing
    assert options(session, "bob") == ()
    assert options(session, "carol") == (PA_CHECK, PA_CHECK_OR_FOLD)


def test_options_follow_a_raise(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    act(session, "alice", raise_to(40))
    assert options(session, "bob") == ()
    assert options(session, "carol") == (PA_FOLD, pa_call(30))
    act(session, "bob", raise_to(100))
    assert options(session, "bob") == (PA_CHECK, PA_CHECK_OR_FOLD)  # the raiser owes nothing until re-raised
    assert options(session, "alice") == (PA_FOLD, pa_call(60))
    assert options(session, "carol") == ()


def test_options_exist_only_for_participants_and_while_a_round_is_open(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    ok(session.join(uid("dave"), session.revision, DisplayName("Dave"), 4))  # type: ignore[union-attr]
    assert options(session, "dave") == ()  # seated mid-hand, not a participant
    act(session, "alice", FOLD)
    assert options(session, "alice") == ()  # folded
    act(session, "bob", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE
    assert all(options(session, name) == () for name in ("alice", "bob", "carol", "dave"))  # settled


# --- select and clear ---


def test_select_and_clear_are_private_and_return_the_owners_view_at_the_unchanged_revision(
    make_session: MakeSession,
) -> None:
    session = started(make_session, 3)
    revision = session.revision
    before = {name: view(session, name) for name in ("alice", "bob", "carol")}

    result = select(session, "carol", PA_CHECK)
    assert you_of(view(session, "carol")) == (PA_CHECK, (PA_CHECK, PA_CHECK_OR_FOLD))
    assert result.view is not None and result.view.revision == revision
    assert view(session, "alice") == before["alice"] and view(session, "bob") == before["bob"]
    # the only difference for carol is her own private selection
    assert replace(view(session, "carol"), you=replace(view(session, "carol").you, pre_action=None)) == before["carol"]

    select(session, "carol", PA_CHECK_OR_FOLD)  # last write wins
    assert selected(session, "carol") == PA_CHECK_OR_FOLD
    assert view(session, "alice") == before["alice"] and view(session, "bob") == before["bob"]

    clear(session, "carol")
    assert selected(session, "carol") is None
    assert {name: view(session, name) for name in before} == before


def test_selecting_what_is_presented_or_clearing_nothing_is_no_change(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    select(session, "carol", PA_CHECK)
    for call, code in (
        (lambda: session.select_pre_action(uid("carol"), session.revision, PA_CHECK), RejectionCode.NO_CHANGE),
        (lambda: session.clear_pre_action(uid("bob"), session.revision), RejectionCode.NO_CHANGE),
    ):
        before = snapshot(session)
        result = call()
        assert isinstance(result, Rejected) and result.code is code and result.message
        assert snapshot(session) == before
    clear(session, "carol")
    before = snapshot(session)
    result = session.clear_pre_action(uid("carol"), session.revision)
    assert isinstance(result, Rejected) and result.code is RejectionCode.NO_CHANGE and snapshot(session) == before


def test_check_or_fold_presenting_as_fold_makes_selecting_fold_no_change(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    select(session, "carol", PA_CHECK_OR_FOLD)
    act(session, "alice", raise_to(30))
    assert you_of(view(session, "carol")) == (PA_FOLD, (PA_FOLD, pa_call(20)))
    assert session._members[uid("carol")].pre_action.intent == PA_CHECK_OR_FOLD  # type: ignore[union-attr]  # noqa: SLF001

    for pre_action, code in (
        (PA_FOLD, RejectionCode.NO_CHANGE),  # it already presents as FOLD
        (PA_CHECK_OR_FOLD, RejectionCode.PRE_ACTION_UNAVAILABLE),  # no longer offered
    ):
        before = snapshot(session)
        result = session.select_pre_action(uid("carol"), session.revision, pre_action)
        assert isinstance(result, Rejected) and result.code is code
        assert snapshot(session) == before

    select(session, "carol", pa_call(20))  # replaces it
    assert selected(session, "carol") == pa_call(20)
    clear(session, "carol")


def _no_hand(make_session: MakeSession) -> tuple[TableSession, str]:
    return make_session(3), "carol"


def _own_turn(make_session: MakeSession) -> tuple[TableSession, str]:
    return started(make_session, 3), "alice"


def _wrong_amount(make_session: MakeSession) -> tuple[TableSession, str]:
    session = started(make_session, 3)
    act(session, "alice", raise_to(30))
    return session, "carol"


def _other_row(make_session: MakeSession) -> tuple[TableSession, str]:
    return started(make_session, 3), "bob"  # bob owes: the check row is not offered


def _settled(make_session: MakeSession) -> tuple[TableSession, str]:
    session = started(make_session, 3)
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)
    return session, "carol"


def _folded(make_session: MakeSession) -> tuple[TableSession, str]:
    session = started(make_session, 3)
    act(session, "alice", FOLD)
    return session, "alice"


def _all_in(make_session: MakeSession) -> tuple[TableSession, str]:
    session = started(make_session, 3)
    act(session, "alice", raise_to(1000))
    return session, "alice"


def _not_a_participant(make_session: MakeSession) -> tuple[TableSession, str]:
    session = started(make_session, 3)
    ok(session.join(uid("dave"), session.revision, DisplayName("Dave"), 4))  # type: ignore[union-attr]
    return session, "dave"


def _showdown(make_session: MakeSession) -> tuple[TableSession, str]:
    session = started(make_session, 3)
    to_flop(session)
    for _street in range(3):
        for name in ("bob", "carol", "alice"):
            act(session, name, CHECK)
    assert view(session, "bob").game.hand.showdown_actions is not None  # type: ignore[union-attr]
    return session, "carol"


@pytest.mark.parametrize(
    "setup",
    [
        _no_hand,
        _own_turn,
        _wrong_amount,
        _other_row,
        _settled,
        _folded,
        _all_in,
        _not_a_participant,
        _showdown,
    ],
)
def test_an_unavailable_pre_action_is_rejected_and_changes_nothing(
    setup: Callable[[MakeSession], tuple[TableSession, str]], make_session: MakeSession
) -> None:
    session, name = setup(make_session)
    candidates = (PA_CHECK, PA_CHECK_OR_FOLD, PA_FOLD, pa_call(5), pa_call(20), pa_call(990))
    unavailable = [pre_action for pre_action in candidates if pre_action not in options(session, name)]
    assert unavailable
    for pre_action in unavailable:
        before = snapshot(session)
        result = session.select_pre_action(uid(name), session.revision, pre_action)
        assert isinstance(result, Rejected) and result.code is RejectionCode.PRE_ACTION_UNAVAILABLE and result.message
        assert snapshot(session) == before


def test_the_command_checks_run_in_order_revision_membership_leave_then_availability(
    make_session: MakeSession,
) -> None:
    session = started(make_session, 3)
    stale = session.revision - 1
    stranger = UserId("stranger")
    for command in (
        lambda who, revision: session.select_pre_action(who, revision, PA_CHECK),
        lambda who, revision: session.clear_pre_action(who, revision),
    ):
        # a stale revision comes before everything, including membership
        assert isinstance(r := command(stranger, stale), Rejected) and r.code is RejectionCode.STALE_REVISION
        assert isinstance(r := command(uid("carol"), stale), Rejected) and r.code is RejectionCode.STALE_REVISION
        assert isinstance(r := command(stranger, session.revision), Rejected) and r.code is RejectionCode.NOT_A_MEMBER

    ok(session.leave(uid("bob"), session.revision))  # bob's leave is pending
    for result in (
        session.select_pre_action(uid("bob"), session.revision, PA_CHECK),  # unavailable too, but the leave comes first
        session.select_pre_action(uid("bob"), session.revision, pa_call(5)),
        session.clear_pre_action(uid("bob"), session.revision),
    ):
        assert isinstance(result, Rejected) and result.code is RejectionCode.LEAVE_PENDING
    assert options(session, "bob") == ()


# --- reconciliation ---


def test_a_check_selection_is_cleared_by_a_bet_in_that_transition(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    to_flop(session)
    select(session, "carol", PA_CHECK)
    select(session, "alice", PA_CHECK)
    result = act(session, "bob", bet(20))
    views = result.transitions[0].views  # cleared inside the transition, before its views were captured
    assert you_of(views[uid("alice")]) == (None, (PA_FOLD, pa_call(20)))
    assert you_of(views[uid("carol")]) == (None, ())  # carol is on turn, with her full legal actions
    assert views[uid("carol")].game.hand.legal_actions.can_call  # type: ignore[union-attr]
    assert causes(result) == [COMMAND]  # her cleared check never executes


def test_a_call_current_selection_survives_a_matching_amount_and_is_cleared_by_a_raise(
    make_session: MakeSession,
) -> None:
    session = started(make_session, 4)  # dave, alice, bob, carol
    act(session, "dave", raise_to(30))
    select(session, "carol", pa_call(20))
    select(session, "bob", pa_call(25))
    result = act(session, "alice", CALL)  # nothing changes for carol and bob
    assert you_of(result.transitions[0].views[uid("carol")]) == (pa_call(20), (PA_FOLD, pa_call(20)))
    assert you_of(result.transitions[0].views[uid("bob")])[0] is None  # bob is on turn: consumed
    # bob's call executes as his own transition, then carol's, which ends the round
    assert causes(result) == [COMMAND, PRE, PRE]
    assert view(session, "alice").game.hand.street is Street.FLOP  # type: ignore[union-attr]

    session = started(make_session, 4)
    act(session, "dave", raise_to(30))
    select(session, "carol", pa_call(20))
    result = act(session, "alice", raise_to(60))  # carol now owes 50
    assert you_of(result.transitions[0].views[uid("carol")]) == (None, (PA_FOLD, pa_call(50)))
    assert causes(result) == [COMMAND]


def test_check_or_fold_survives_a_bet_showing_fold(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    to_flop(session)
    select(session, "alice", PA_CHECK_OR_FOLD)
    result = act(session, "bob", bet(20))
    assert you_of(result.transitions[0].views[uid("alice")]) == (PA_FOLD, (PA_FOLD, pa_call(20)))
    assert you_of(view(session, "alice")) == (PA_FOLD, (PA_FOLD, pa_call(20)))
    assert session._members[uid("alice")].pre_action.intent == PA_CHECK_OR_FOLD  # type: ignore[union-attr]  # noqa: SLF001


def test_a_selection_is_cleared_when_the_street_ends_and_never_executes_later(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    to_flop(session)
    act(session, "bob", bet(20))
    select(session, "bob", PA_CHECK)  # the bettor owes nothing and may pre-select
    assert selected(session, "bob") == PA_CHECK
    act(session, "carol", FOLD)
    result = act(session, "alice", CALL)  # the flop round ends: the turn starts with bob on turn
    assert causes(result) == [COMMAND]
    assert view(session, "bob").game.hand.street is Street.TURN  # type: ignore[union-attr]
    assert you_of(result.transitions[0].views[uid("bob")]) == (None, ())
    assert turn_seat(session) == 2  # bob keeps the turn with his full legal actions
    assert view(session, "bob").game.hand.legal_actions.can_check  # type: ignore[union-attr]


def test_a_selection_is_cleared_when_the_hand_settles(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    select(session, "carol", PA_CHECK)
    act(session, "alice", FOLD)
    assert selected(session, "carol") == PA_CHECK  # still owed nothing
    result = act(session, "bob", FOLD)  # carol wins the blinds
    assert causes(result) == [COMMAND] and session.phase is TablePhase.HAND_COMPLETE
    assert you_of(result.transitions[0].views[uid("carol")]) == (None, ())
    assert you_of(view(session, "carol")) == (None, ())


def test_requesting_a_leave_clears_the_selection_privately(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    select(session, "carol", PA_CHECK)
    revision = session.revision
    others = {name: view(session, name) for name in ("alice", "bob")}
    result = ok(session.leave(uid("carol"), revision))
    assert result.transitions == () and session.revision == revision
    assert result.view is not None and result.view.you.pending_leave
    assert you_of(result.view) == (None, ())
    assert {name: view(session, name) for name in others} == others


# --- execution ---


def test_check_executes_as_its_own_transition_when_the_turn_arrives(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    to_flop(session)
    select(session, "alice", PA_CHECK)
    act(session, "bob", CHECK)
    revision = session.revision
    result = act(session, "carol", CHECK)
    assert causes(result) == [COMMAND, PRE]
    assert [t.revision for t in result.transitions] == [revision + 1, revision + 2]
    first, second = result.transitions
    # in the transition that gave alice the turn she holds no selection and has her full legal actions
    assert you_of(first.views[uid("alice")]) == (None, ())
    assert first.views[uid("alice")].game.hand.legal_actions.can_check  # type: ignore[union-attr]
    assert first.views[uid("alice")].game.hand.turn.seat == 1  # type: ignore[union-attr]
    assert second.views[uid("alice")].game.hand.street is Street.TURN  # her check ended the flop
    assert selected(session, "alice") is None and result.view is not None  # carol's own view
    assert (1, ActionType.CHECK) in [
        (e.seat, e.action.type)
        for e in view(session, "bob").game.hand.log
        if hasattr(e, "action")  # type: ignore[union-attr]
    ]


def test_check_or_fold_checks_when_nothing_is_owed_and_folds_otherwise(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    to_flop(session)
    select(session, "alice", PA_CHECK_OR_FOLD)
    act(session, "bob", CHECK)
    result = act(session, "carol", CHECK)
    assert causes(result) == [COMMAND, PRE]
    alice = [p for p in view(session, "bob").game.hand.participants if p.seat == 1][0]  # type: ignore[union-attr]
    assert not alice.folded  # she checked

    session = started(make_session, 3)
    to_flop(session)
    select(session, "alice", PA_CHECK_OR_FOLD)
    act(session, "bob", bet(20))
    result = act(session, "carol", CALL)
    assert causes(result) == [COMMAND, PRE]
    alice = [p for p in view(session, "bob").game.hand.participants if p.seat == 1][0]  # type: ignore[union-attr]
    assert alice.folded  # chips were owed


def test_fold_and_call_current_execute_as_their_own_transitions(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    select(session, "bob", PA_FOLD)
    result = act(session, "alice", raise_to(30))
    assert causes(result) == [COMMAND, PRE]
    assert turn_seat(session) == 3  # bob folded for himself
    assert you_of(view(session, "bob")) == (None, ())

    session = started(make_session, 3)
    act(session, "alice", raise_to(30))
    select(session, "carol", pa_call(20))
    result = act(session, "bob", CALL)
    assert causes(result) == [COMMAND, PRE]
    assert view(session, "alice").game.hand.street is Street.FLOP  # type: ignore[union-attr]
    assert view(session, "alice").game.hand.pots[0].amount == 90  # type: ignore[union-attr]


def test_a_call_current_that_goes_all_in_ends_the_players_options(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    act(session, "alice", raise_to(1000))
    select(session, "carol", pa_call(990))
    assert selected(session, "carol") == pa_call(990)
    result = act(session, "bob", FOLD)
    assert causes(result) == [COMMAND, PRE]
    assert you_of(view(session, "carol")) == (None, ())
    assert session.phase is not TablePhase.HAND_IN_PROGRESS or turn_seat(session) is None
    result = session.select_pre_action(uid("carol"), session.revision, PA_CHECK)
    assert isinstance(result, Rejected) and result.code is RejectionCode.PRE_ACTION_UNAVAILABLE


def test_translation_follows_the_engines_legal_actions() -> None:
    def legal(*, can_check: bool, can_call: bool, owed: int) -> LegalActions:
        return LegalActions(
            can_fold=True,
            can_check=can_check,
            can_call=can_call,
            amount_owed=owed,
            call_amount=owed,
            call_is_all_in=False,
            can_bet=False,
            can_raise=False,
            min_full_target=None,
            max_target=None,
            short_all_in_target=None,
        )

    free, owing = legal(can_check=True, can_call=False, owed=0), legal(can_check=False, can_call=True, owed=20)
    assert _pre_action_to_action(PA_CHECK, free) == CHECK
    assert _pre_action_to_action(PA_CHECK, owing) is None
    assert _pre_action_to_action(PA_CHECK_OR_FOLD, free) == CHECK
    assert _pre_action_to_action(PA_CHECK_OR_FOLD, owing) == FOLD
    assert _pre_action_to_action(PA_FOLD, free) == FOLD and _pre_action_to_action(PA_FOLD, owing) == FOLD
    assert _pre_action_to_action(pa_call(20), owing) == CALL
    assert _pre_action_to_action(pa_call(10), owing) is None
    assert _pre_action_to_action(pa_call(20), free) is None


# --- cascades ---


def test_pre_actions_cascade_each_as_its_own_transition_with_the_others_reconciled(make_session: MakeSession) -> None:
    session = started(make_session, 4)  # dave, alice, bob, carol
    select(session, "alice", PA_FOLD)
    select(session, "bob", PA_FOLD)
    select(session, "carol", PA_CHECK_OR_FOLD)
    revision = session.revision

    result = act(session, "dave", raise_to(30))
    assert causes(result) == [COMMAND, PRE, PRE, PRE]
    assert [t.revision for t in result.transitions] == [revision + 1, revision + 2, revision + 3, revision + 4]
    t1, t2, t3, t4 = result.transitions
    # T1: the raise. Alice is on turn (consumed); bob's fold and carol's check-or-fold stand, carol's as FOLD.
    assert you_of(t1.views[uid("alice")]) == (None, ())
    assert you_of(t1.views[uid("bob")]) == (PA_FOLD, (PA_FOLD, pa_call(25)))
    assert you_of(t1.views[uid("carol")]) == (PA_FOLD, (PA_FOLD, pa_call(20)))
    assert t1.views[uid("alice")].game.hand.legal_actions.can_call  # type: ignore[union-attr]
    # T2: alice folded; bob is on turn, carol still stands.
    assert you_of(t2.views[uid("alice")]) == (None, ())
    assert you_of(t2.views[uid("bob")]) == (None, ())
    assert you_of(t2.views[uid("carol")]) == (PA_FOLD, (PA_FOLD, pa_call(20)))
    assert t2.views[uid("bob")].game.hand.legal_actions is not None  # type: ignore[union-attr]
    # T3: bob folded; carol is on turn. T4: carol folded and dave wins.
    assert you_of(t3.views[uid("carol")]) == (None, ())
    assert t3.views[uid("carol")].game.hand.legal_actions is not None  # type: ignore[union-attr]
    assert t4.views[uid("dave")].game.hand.settlement is not None  # type: ignore[union-attr]
    assert session.phase is TablePhase.HAND_COMPLETE
    assert all(you_of(view(session, name)) == (None, ()) for name in NAMES[:4])


def test_a_cascade_stops_at_a_player_without_a_pre_action(make_session: MakeSession) -> None:
    session = started(make_session, 4)
    select(session, "alice", PA_FOLD)
    select(session, "bob", PA_FOLD)
    result = act(session, "dave", raise_to(30))
    assert causes(result) == [COMMAND, PRE, PRE]
    assert turn_seat(session) == 3 and session.phase is TablePhase.HAND_IN_PROGRESS
    assert view(session, "carol").game.hand.legal_actions.can_call  # type: ignore[union-attr]


def test_a_cascade_mixes_pre_actions_and_a_leavers_automatic_action(make_session: MakeSession) -> None:
    session = started(make_session, 4)
    select(session, "alice", PA_FOLD)
    ok(session.leave(uid("bob"), session.revision))  # pending, off turn
    result = act(session, "dave", raise_to(30))
    assert causes(result) == [COMMAND, PRE, AUTO]
    assert turn_seat(session) == 3 and session.is_member(uid("bob"))

    session = started(make_session, 4)
    ok(session.leave(uid("alice"), session.revision))
    select(session, "bob", PA_FOLD)
    result = act(session, "dave", raise_to(30))
    assert causes(result) == [COMMAND, AUTO, PRE]
    assert turn_seat(session) == 3


def test_a_stale_revision_after_a_cascade_is_rejected_and_the_last_revision_works(make_session: MakeSession) -> None:
    session = started(make_session, 4)
    select(session, "alice", PA_FOLD)
    select(session, "bob", PA_FOLD)
    revision = session.revision
    result = act(session, "dave", raise_to(30))
    assert session.revision == revision + 3
    before = snapshot(session)
    for stale in (revision, revision + 1, revision + 2):
        rejected = session.act(uid("carol"), stale, CALL)
        assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.STALE_REVISION
        rejected = session.select_pre_action(uid("carol"), stale, PA_FOLD)
        assert isinstance(rejected, Rejected) and rejected.code is RejectionCode.STALE_REVISION
    assert snapshot(session) == before
    assert result.transitions[-1].revision == session.revision
    assert causes(act(session, "carol", CALL)) == [COMMAND]


def test_a_consumed_selection_never_carries_into_the_next_hand(make_session: MakeSession) -> None:
    session = started(make_session, 3)
    select(session, "bob", PA_FOLD)
    act(session, "alice", raise_to(30))  # bob folds for himself
    act(session, "carol", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE
    ok(session.advance_hand(session.revision))
    for name in ("alice", "bob", "carol"):
        assert selected(session, name) is None
    assert all(m.consumed is None and m.pre_action is None for m in session._members.values())  # noqa: SLF001
    assert session.phase is TablePhase.HAND_IN_PROGRESS  # a fresh hand, nothing executed

"""Adversarial validation of pre-actions: realistic multi-hand sequences with unequal stacks, heads-up shapes, the
interplay with leaves, sit-outs, joins and generation resets, rejections in every phase, and the privacy of selections
against a twin session that plays the same moves by hand.

Seats follow the join order: alice 1, bob 2, carol 3, dave 4. The first button is seat 1. Blinds are 5 and 10.
"""

from collections.abc import Callable
from dataclasses import replace

import pytest

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.app.results import Accepted, CommandResult, Rejected, RejectionCode, TransitionCause
from go_poker.app.session import TableSession
from go_poker.app.views import TablePhase, TableView
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.view import HandView

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


def uid(name: str) -> UserId:
    return UserId(f"uid-{name}-7f3a")


def ok(result: CommandResult) -> Accepted:
    assert isinstance(result, Accepted), result
    return result


def rejected(result: CommandResult, code: RejectionCode) -> None:
    assert isinstance(result, Rejected) and result.code is code and result.message, result


def view(session: TableSession, name: str) -> TableView:
    found = session.view_for(uid(name))
    assert found is not None
    return found


def hand_of(session: TableSession, name: str = "alice") -> HandView:
    hand = view(session, name).game.hand
    assert hand is not None
    return hand


def act(session: TableSession, name: str, action: Action) -> Accepted:
    result = ok(session.act(uid(name), session.revision, action))
    revisions = [t.revision for t in result.transitions]
    assert revisions == list(range(revisions[0], revisions[0] + len(revisions))) and revisions[-1] == session.revision
    assert result.view == session.view_for(uid(name))  # the requester's view after the whole cascade
    return result


def select(session: TableSession, name: str, pre_action: PreAction) -> Accepted:
    return ok(session.select_pre_action(uid(name), session.revision, pre_action))


def intents(session: TableSession, name: str) -> tuple[PreAction | None, tuple[PreAction, ...]]:
    you = view(session, name).you
    return you.pre_action, you.pre_action_options


def intents_of(table_view: TableView) -> tuple[PreAction | None, tuple[PreAction, ...]]:
    return table_view.you.pre_action, table_view.you.pre_action_options


def causes(result: Accepted) -> list[TransitionCause]:
    return [t.cause for t in result.transitions]


def everything(session: TableSession) -> tuple[object, ...]:
    """What a rejected or private command must not disturb in the shared state: the revision, phase and, per member,
    the whole game and table parts of the view."""
    return (
        session.revision,
        session.phase,
        tuple(
            (v.revision, v.phase, v.seats, v.game, v.you.seat, v.you.pending_leave, v.you.pending_sit_out)
            for v in (session.view_for(uid(n)) for n in NAMES)
            if v is not None
        ),
    )


def private_part(v: TableView) -> TableView:
    """A view with its private pre-action intents removed."""
    return replace(v, you=replace(v.you, pre_action=None, pre_action_options=()))


def four_with_a_short_stack(make_session: MakeSession) -> TableSession:
    """The start of hand 2 of four players, where the order is alice (first), bob (button), carol (small blind) and
    dave (big blind), with stacks alice 1710, bob 300, carol 990 and dave 1000. Bob lost 700 in hand 1: alice raised to
    700 before the flop, bob called, and bob folded to a flop bet."""
    session = make_session(4)
    ok(session.start_game(uid("alice"), session.revision))
    act(session, "dave", FOLD)
    act(session, "alice", raise_to(700))
    act(session, "bob", CALL)
    act(session, "carol", FOLD)
    assert hand_of(session).street is Street.FLOP
    act(session, "bob", CHECK)
    act(session, "alice", Action(ActionType.BET, 10))
    act(session, "bob", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE
    ok(session.advance_hand(session.revision))
    stacks = {seat.number: seat.occupant.stack for seat in view(session, "alice").game.seats if seat.occupant}
    in_front = {p.seat: p.in_front for p in hand_of(session).participants}
    assert {seat: stacks[seat] + in_front[seat] for seat in (1, 2, 3, 4)} == {1: 1710, 2: 300, 3: 990, 4: 1000}
    assert hand_of(session).turn is not None and hand_of(session).turn.seat == 1  # type: ignore[union-attr]
    return session


def test_a_short_stacks_all_in_call_leaves_the_others_selections_standing_and_they_execute(
    make_session: MakeSession,
) -> None:
    session = four_with_a_short_stack(make_session)
    select(session, "bob", pa_call(10))
    select(session, "carol", pa_call(5))
    select(session, "dave", PA_CHECK_OR_FOLD)
    result = act(session, "alice", raise_to(700))
    assert causes(result) == [COMMAND]
    views = result.transitions[0].views
    assert intents_of(views[uid("alice")]) == (None, (PA_CHECK, PA_CHECK_OR_FOLD))  # the raiser owes nothing
    assert intents_of(views[uid("bob")]) == (None, ())  # bob is on turn and his stale call of 10 is gone
    assert intents_of(views[uid("carol")]) == (None, (PA_FOLD, pa_call(695)))  # the amount changed: cleared
    assert intents_of(views[uid("dave")]) == (PA_FOLD, (PA_FOLD, pa_call(690)))  # check-or-fold survives, as a fold
    legal = hand_of(session, "bob").legal_actions
    assert legal is not None and (legal.amount_owed, legal.call_amount, legal.call_is_all_in) == (700, 300, True)

    select(session, "carol", pa_call(695))
    result = act(session, "bob", CALL)  # a short all-in call: nobody else's obligation changes
    assert causes(result) == [COMMAND, PRE, PRE]  # carol calls, dave folds
    first, second, third = result.transitions
    assert intents_of(first.views[uid("carol")]) == (None, ())  # on turn: consumed
    assert intents_of(first.views[uid("dave")]) == (PA_FOLD, (PA_FOLD, pa_call(690)))
    assert intents_of(second.views[uid("dave")]) == (None, ())
    assert intents_of(third.views[uid("alice")])[1] != ()  # the flop: alice off turn with options again
    assert intents_of(view(session, "bob")) == (None, ())  # all-in
    assert hand_of(session).street is Street.FLOP and hand_of(session).turn is not None
    assert hand_of(session).turn.seat == 3  # type: ignore[union-attr]  # carol, first after the button
    assert [p.folded for p in hand_of(session).participants if p.seat == 4] == [True]


def test_a_selection_made_before_a_raise_over_a_short_stack_never_executes_a_stale_call(
    make_session: MakeSession,
) -> None:
    """Dave selects CALL_CURRENT for the 10 the blinds owe; alice then raises, bob re-raises all-in for 300 and carol
    folds. Dave's call of 10 must be gone after the first raise and never become a call of 290 on his turn."""
    session = four_with_a_short_stack(make_session)
    select(session, "carol", pa_call(5))
    act(session, "alice", CALL)  # alice calls 10; bob is on turn
    select(session, "dave", PA_CHECK)
    result = act(session, "bob", raise_to(300))  # bob all-in; carol is on turn owing 295
    assert causes(result) == [COMMAND]
    assert intents_of(result.transitions[0].views[uid("carol")]) == (None, ())  # the stale call of 5 is gone
    assert intents_of(result.transitions[0].views[uid("dave")]) == (None, (PA_FOLD, pa_call(290)))  # check cleared
    assert intents_of(result.transitions[0].views[uid("alice")]) == (None, (PA_FOLD, pa_call(290)))
    result = act(session, "carol", FOLD)
    assert causes(result) == [COMMAND]  # nothing executes for dave: he keeps the turn with every legal action
    dave_legal = hand_of(session, "dave").legal_actions
    assert dave_legal is not None and dave_legal.can_call and dave_legal.can_fold and not dave_legal.can_check


# --- heads-up ---


def test_heads_up_the_big_blind_option_runs_a_selected_check_after_a_limp(make_session: MakeSession) -> None:
    session = make_session(2)  # alice is the button and small blind, and acts first; bob is the big blind
    ok(session.start_game(uid("alice"), session.revision))
    assert intents_of(view(session, "bob")) == (None, (PA_CHECK, PA_CHECK_OR_FOLD))
    select(session, "bob", PA_CHECK)
    result = act(session, "alice", CALL)  # the limp leaves bob his option
    assert causes(result) == [COMMAND, PRE]
    assert intents_of(result.transitions[0].views[uid("bob")]) == (None, ())  # on turn: consumed
    assert hand_of(session).street is Street.FLOP  # the check ended the round
    assert result.transitions[1].views[uid("bob")].game.hand.street is Street.FLOP  # type: ignore[union-attr]
    # post-flop the big blind acts first: bob is on turn with every legal action, nothing stale ran for him
    turn = hand_of(session).turn
    assert turn is not None and turn.seat == 2
    assert hand_of(session, "bob").legal_actions is not None


def test_heads_up_a_selected_check_or_fold_folds_to_a_raise_in_the_raises_cascade(make_session: MakeSession) -> None:
    session = make_session(2)
    ok(session.start_game(uid("alice"), session.revision))
    select(session, "bob", PA_CHECK_OR_FOLD)
    result = act(session, "alice", raise_to(30))
    assert causes(result) == [COMMAND, PRE]
    assert intents_of(result.transitions[0].views[uid("bob")]) == (None, ())  # bob is on turn the moment alice raises
    assert result.transitions[1].views[uid("bob")].game.hand.settlement is not None  # type: ignore[union-attr]
    assert session.phase is TablePhase.HAND_COMPLETE
    assert intents_of(view(session, "alice")) == (None, ()) and intents_of(view(session, "bob")) == (None, ())


# --- leaves, sit-outs, joins ---


def test_a_member_who_requests_a_leave_after_selecting_is_handled_by_the_leave_not_the_selection(
    make_session: MakeSession,
) -> None:
    session = four_with_a_short_stack(make_session)  # alice, bob, carol, dave
    select(session, "carol", pa_call(5))
    revision = session.revision
    result = ok(session.leave(uid("carol"), revision))
    assert result.transitions == () and session.revision == revision
    assert intents_of(view(session, "carol")) == (None, ())
    rejected(session.select_pre_action(uid("carol"), revision, pa_call(5)), RejectionCode.LEAVE_PENDING)
    rejected(session.clear_pre_action(uid("carol"), revision), RejectionCode.LEAVE_PENDING)
    result = act(session, "alice", CALL)
    assert causes(result) == [COMMAND]  # bob is on turn
    result = act(session, "bob", CALL)  # carol's turn arrives: the leave acts for her, not a pre-action
    assert causes(result) == [COMMAND, AUTO]
    assert session.is_member(uid("carol"))  # she leaves at the hand boundary


def test_a_selection_survives_shared_transitions_that_do_not_touch_the_hand(make_session: MakeSession) -> None:
    session = make_session(3)
    ok(session.start_game(uid("alice"), session.revision))
    select(session, "carol", PA_CHECK)
    select(session, "bob", pa_call(5))
    for step in (
        lambda: session.join(uid("dave"), session.revision, DisplayName("Dave"), 4),
        lambda: session.join(uid("erin"), session.revision, DisplayName("Erin"), 5),
        lambda: session.sit_out(uid("dave"), session.revision),  # a seated non-participant: applies at once
        lambda: session.leave(uid("erin"), session.revision),  # a non-participant leaves at once
        lambda: session.sit_back(uid("dave"), session.revision),
    ):
        revision = session.revision
        result = ok(step())
        assert len(result.transitions) == 1 and session.revision == revision + 1
        assert intents_of(result.transitions[0].views[uid("carol")]) == (PA_CHECK, (PA_CHECK, PA_CHECK_OR_FOLD))
        assert intents_of(result.transitions[0].views[uid("bob")])[0] == pa_call(5)
    assert intents_of(view(session, "carol"))[0] == PA_CHECK
    result = act(session, "alice", CALL)  # bob's call of 5 and carol's check still execute
    assert causes(result) == [COMMAND, PRE, PRE]


def test_a_pending_sit_out_neither_clears_nor_blocks_a_selection_that_then_executes(make_session: MakeSession) -> None:
    session = make_session(3)
    ok(session.start_game(uid("alice"), session.revision))
    select(session, "carol", PA_CHECK_OR_FOLD)
    result = ok(session.sit_out(uid("carol"), session.revision))
    assert result.transitions == () and result.view is not None and result.view.you.pending_sit_out
    assert intents_of(view(session, "carol")) == (PA_CHECK_OR_FOLD, (PA_CHECK, PA_CHECK_OR_FOLD))
    act(session, "alice", CALL)
    result = act(session, "bob", CALL)
    assert causes(result) == [COMMAND, PRE]  # carol's check-or-fold ran as a check
    assert hand_of(session).street is Street.FLOP
    # ... and the pending sit-out is still pending, and applies at the boundary
    assert view(session, "carol").you.pending_sit_out


# --- generation reset ---


def test_selections_never_cross_a_hand_boundary_or_an_engine_generation_reset(make_session: MakeSession) -> None:
    """Hand 1 of generation 1 ends while carol holds a check selection; both players still seated sit out, so the
    boundary replaces the engine, and generation 2 also starts at hand 1 on the same street."""
    session = make_session(3)
    ok(session.start_game(uid("alice"), session.revision))
    select(session, "carol", PA_CHECK)
    act(session, "alice", FOLD)
    act(session, "bob", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE
    assert intents_of(view(session, "carol")) == (None, ())  # cleared in the settling transition
    for name in ("alice", "bob", "carol"):
        ok(session.sit_out(uid(name), session.revision))
    old_engine = session._game  # noqa: SLF001
    ok(session.advance_hand(session.revision))
    assert session._game is not old_engine  # noqa: SLF001  # the generation was replaced
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    for name in ("alice", "bob"):
        select_result = session.select_pre_action(uid(name), session.revision, PA_CHECK)
        rejected(select_result, RejectionCode.PRE_ACTION_UNAVAILABLE)
    for name in ("alice", "bob"):
        ok(session.sit_back(uid(name), session.revision))  # the second one starts the first hand of the new engine
    assert session.phase is TablePhase.HAND_IN_PROGRESS
    assert hand_of(session).number == 1 and hand_of(session).street is Street.PREFLOP
    ok(session.sit_back(uid("carol"), session.revision))  # seated mid-hand: waits for the next one
    for name in ("alice", "bob", "carol"):
        assert view(session, name).you.pre_action is None
    assert intents_of(view(session, "carol")) == (None, ())
    # the new hand's selections work: heads-up, bob is the big blind and owes nothing while alice acts first
    assert intents_of(view(session, "bob")) == (None, (PA_CHECK, PA_CHECK_OR_FOLD))
    select(session, "bob", PA_CHECK)
    assert view(session, "bob").you.pre_action == PA_CHECK


# --- rejections ---


def test_select_and_clear_are_rejected_atomically_before_the_game_waiting_after_a_leave_and_for_strangers(
    make_session: MakeSession,
) -> None:
    session = make_session(3)
    stranger = UserId("stranger")
    before = everything(session)
    for result, code in (
        (session.select_pre_action(uid("alice"), session.revision, PA_CHECK), RejectionCode.PRE_ACTION_UNAVAILABLE),
        (session.clear_pre_action(uid("alice"), session.revision), RejectionCode.NO_CHANGE),
        (session.select_pre_action(stranger, session.revision, PA_CHECK), RejectionCode.NOT_A_MEMBER),
        (session.clear_pre_action(stranger, session.revision), RejectionCode.NOT_A_MEMBER),
        (session.select_pre_action(uid("alice"), session.revision + 1, PA_CHECK), RejectionCode.STALE_REVISION),
        (session.clear_pre_action(uid("alice"), session.revision - 1), RejectionCode.STALE_REVISION),
    ):
        rejected(result, code)
        assert everything(session) == before

    ok(session.start_game(uid("alice"), session.revision))
    ok(session.leave(uid("bob"), session.revision))  # pending
    assert causes(act(session, "alice", FOLD)) == [COMMAND, AUTO]  # bob's pending leave folds for him; carol wins
    assert session.phase is TablePhase.HAND_COMPLETE
    ok(session.advance_hand(session.revision))  # bob leaves at the boundary
    assert not session.is_member(uid("bob"))
    before = everything(session)
    rejected(session.select_pre_action(uid("bob"), session.revision, PA_CHECK), RejectionCode.NOT_A_MEMBER)
    rejected(session.clear_pre_action(uid("bob"), session.revision), RejectionCode.NOT_A_MEMBER)
    assert everything(session) == before


def test_a_waiting_table_and_a_completed_hand_offer_nothing_and_reject_without_changes(
    make_session: MakeSession,
) -> None:
    session = make_session(2)
    ok(session.start_game(uid("alice"), session.revision))
    act(session, "alice", FOLD)
    assert session.phase is TablePhase.HAND_COMPLETE
    ok(session.sit_out(uid("bob"), session.revision))  # applies at once: the hand is complete
    ok(session.advance_hand(session.revision))
    assert session.phase is TablePhase.WAITING_FOR_PLAYERS
    before = everything(session)
    for name in ("alice", "bob"):
        assert intents_of(view(session, name)) == (None, ())
        for pre_action in (PA_CHECK, PA_CHECK_OR_FOLD, PA_FOLD, pa_call(5)):
            rejected(
                session.select_pre_action(uid(name), session.revision, pre_action),
                RejectionCode.PRE_ACTION_UNAVAILABLE,
            )
        rejected(session.clear_pre_action(uid(name), session.revision), RejectionCode.NO_CHANGE)
    assert everything(session) == before


# --- privacy ---


@pytest.mark.parametrize("name", ["bob", "carol", "dave"])
def test_a_selection_or_clear_changes_nothing_in_any_other_members_view(make_session: MakeSession, name: str) -> None:
    session = four_with_a_short_stack(make_session)
    owner_options = intents_of(view(session, name))[1]
    assert owner_options
    others = [n for n in NAMES[:4] if n != name]
    before = {n: view(session, n) for n in NAMES[:4]}
    for pre_action in owner_options:
        select(session, name, pre_action)
        assert {n: view(session, n) for n in others} == {n: before[n] for n in others}
        assert private_part(view(session, name)) == private_part(before[name])
    ok(session.clear_pre_action(uid(name), session.revision))
    assert {n: view(session, n) for n in NAMES[:4]} == before


def test_pre_actions_are_indistinguishable_from_manual_acts_for_everyone_else(
    make_session: MakeSession, queue_decks: Callable[..., object], draw_order: Callable[..., list]
) -> None:
    """Two tables with the same cards: in one, bob and carol pre-select and the cascade acts for them; in the other the
    same actions are played by hand. At every revision, every game view of every member and every private-free view of
    alice and dave is identical, so a selection reveals nothing about who selected."""
    holes = {1: "As Ad", 2: "7c 2d", 3: "Kh Qs", 4: "9d 9c"}
    deck = draw_order(holes, "2h 5s 9h Jd 3c", 1)
    queue_decks(deck, deck)
    manual, selected = make_session(4), make_session(4)
    for session in (manual, selected):
        ok(session.start_game(uid("alice"), session.revision))
    for session in (manual, selected):
        act(session, "dave", raise_to(30))
    select(selected, "bob", PA_FOLD)
    select(selected, "carol", pa_call(20))
    assert private_part(view(selected, "alice")) == private_part(view(manual, "alice"))
    assert view(selected, "dave") == view(manual, "dave")

    cascade = act(selected, "alice", CALL)  # bob folds and carol calls by themselves
    assert causes(cascade) == [COMMAND, PRE, PRE]
    steps = [act(manual, "alice", CALL), act(manual, "bob", FOLD), act(manual, "carol", CALL)]
    manual_transitions = [t for step in steps for t in step.transitions]
    assert len(manual_transitions) == len(cascade.transitions)
    for t_selected, t_manual in zip(cascade.transitions, manual_transitions, strict=True):
        assert t_selected.revision == t_manual.revision
        for name in NAMES[:4]:
            assert t_selected.views[uid(name)].game == t_manual.views[uid(name)].game
        for name in ("alice", "dave"):
            assert private_part(t_selected.views[uid(name)]) == private_part(t_manual.views[uid(name)])
    assert everything(selected) == everything(manual)

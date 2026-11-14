"""Command outcomes and private updates, against the canonical fixtures of `pre_action_private` (ADR 0009 §8, §9).

The flow is replayed over a real `TableSession` from that scenario's `setup`: Alice creates the table, Bob joins,
Alice starts the hand, Bob selects, clears and re-selects a pre-action at the unchanged revision, and Alice's call
then lets the selection execute as its own transition.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import pytest

from go_poker.app.identity import UserId
from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.app.results import Accepted, CommandResult, Rejected
from go_poker.app.session import TableSession
from go_poker.app.views import TableView
from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.server import dto, mapping


def _without_message(message: Mapping[str, Any]) -> dict[str, Any]:
    """A message without its diagnostic `message` field, which conformance ignores (ADR 0009 §15)."""
    return {key: value for key, value in message.items() if key != "message"}


@pytest.fixture
def table(
    scenario_setup: Callable[[str], Mapping[str, Any]],
    parse_cards: Callable[[Iterable[str]], list[Card]],
    queue_decks: Callable[..., Any],
    make_table: Callable[[Mapping[str, Any], str], tuple[TableSession, Any]],
    join_table: Callable[[TableSession, str, int], Accepted],
    accepted: Callable[[CommandResult], Accepted],
    member_user_id: Callable[[str], UserId],
) -> tuple[TableSession, Mapping[str, UserId], Accepted]:
    """The `pre_action_private` table with the hand started: revision 3, Alice to act."""
    setup = scenario_setup("pre_action_private")
    queue_decks(parse_cards(setup["hands"][0]["draw_order"]))
    session, _ = make_table(setup, "alice")
    ids = {name: member_user_id(name) for name in ("alice", "bob")}
    join_table(session, "bob", 2)
    started = accepted(session.start_game(ids["alice"], session.revision))
    return session, ids, started


def _requester_view(result: Accepted) -> TableView:
    assert result.view is not None
    return result.view


def test_a_shared_command_is_accepted_at_the_revision_it_produced(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
) -> None:
    session, _, started = table
    assert session.revision == 3
    assert mapping.accepted("a-01", started) == dto.Accepted(type="accepted", request_id="a-01", revision=3)


def test_a_private_command_is_accepted_at_the_unchanged_revision(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
    fixture_json: Callable[[str], Any],
    accepted: Callable[[CommandResult], Accepted],
) -> None:
    session, ids, _ = table
    accepted(session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK)))
    accepted(session.clear_pre_action(ids["bob"], 3))
    selected = accepted(session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK_OR_FOLD)))

    assert selected.transitions == ()
    assert session.revision == 3
    outcome = mapping.accepted("b-03", selected)
    assert outcome.model_dump(mode="json") == fixture_json("messages/server/accepted.private.json")


def test_the_private_snapshot_of_a_selected_pre_action_matches_its_fixture(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
    fixture_json: Callable[[str], Any],
    accepted: Callable[[CommandResult], Accepted],
) -> None:
    session, ids, _ = table
    selected = accepted(session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK_OR_FOLD)))
    view = _requester_view(selected)

    snapshot = mapping.snapshot(view.revision, "private", view)
    assert snapshot.model_dump(mode="json") == fixture_json("messages/server/snapshot.private.pre_action_selected.json")


def test_an_executed_pre_action_is_its_own_transition_with_its_own_cause(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
    fixture_json: Callable[[str], Any],
    accepted: Callable[[CommandResult], Accepted],
) -> None:
    session, ids, _ = table
    accepted(session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK_OR_FOLD)))
    called = accepted(session.act(ids["alice"], 3, Action(ActionType.CALL)))

    causes = [mapping.snapshot_cause(transition.cause) for transition in called.transitions]
    assert causes == ["command", "pre_action"]
    executed = called.transitions[-1]
    snapshot = mapping.snapshot(executed.revision, mapping.snapshot_cause(executed.cause), executed.views[ids["bob"]])
    assert snapshot.model_dump(mode="json") == fixture_json("messages/server/snapshot.pre_action_executed.json")


def test_a_rejection_maps_its_code_and_passes_its_message_through_verbatim(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
    fixture_json: Callable[[str], Any],
    accepted: Callable[[CommandResult], Accepted],
) -> None:
    session, ids, _ = table
    accepted(session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK_OR_FOLD)))
    repeated = session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK_OR_FOLD))
    assert isinstance(repeated, Rejected)

    outcome = mapping.rejected("b-04", repeated)
    expected = fixture_json("messages/server/rejected.no_change.json")
    assert _without_message(outcome.model_dump(mode="json")) == _without_message(expected)
    assert outcome.message == repeated.message


def test_no_snapshot_of_this_flow_leaks_a_card_or_an_identity(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
    scenario_setup: Callable[[str], Mapping[str, Any]],
    identity_texts: Callable[[Mapping[str, Any]], list[str]],
    leak_check: Callable[[Mapping[str, Any], Sequence[str]], None],
    accepted: Callable[[CommandResult], Accepted],
) -> None:
    session, ids, started = table
    forbidden = identity_texts(scenario_setup("pre_action_private"))
    selected = accepted(session.select_pre_action(ids["bob"], 3, PreAction(PreActionKind.CHECK_OR_FOLD)))
    called = accepted(session.act(ids["alice"], 3, Action(ActionType.CALL)))

    private = _requester_view(selected)
    snapshots = [mapping.snapshot(private.revision, "private", private)]
    snapshots += [
        mapping.snapshot(transition.revision, mapping.snapshot_cause(transition.cause), view)
        for transition in (*started.transitions, *called.transitions)
        for view in transition.views.values()
    ]
    assert len(snapshots) == 7
    for snapshot in snapshots:
        leak_check(snapshot.model_dump(mode="json"), forbidden)


def test_a_rejection_the_wire_has_no_code_for_is_a_defect(
    table: tuple[TableSession, Mapping[str, UserId], Accepted],
) -> None:
    """`NOT_AT_HAND_BOUNDARY` answers the server's own `advance_hand`, so it never reaches a client (ADR 0009 §12)."""
    session, _, _ = table
    rejected = session.advance_hand(session.revision)
    assert isinstance(rejected, Rejected)

    with pytest.raises(ValueError, match="NOT_AT_HAND_BOUNDARY"):
        mapping.rejected("a-02", rejected)

"""`TableRuntime` delivery: order, causes, outcomes, departures and the next-hand call (ADR 0009 §8, §9).

Every test drives a real `TableSession` over the real engine through the runtime and reads the connections' outboxes.
There is no socket and no double: `Connection` is the production value, and the only injected seams are the
scenarios' own (the ids, the button chooser, the stacked deck and the next-hand scheduler).
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

import pytest

from go_poker.app.views import TablePhase
from go_poker.core.card import Card
from go_poker.server import decode
from go_poker.server.runtime import CLOSE_LEFT_TABLE, CLOSE_SUPERSEDED, Connection

type Harness = Any  # `RuntimeHarness` from conftest, which a test module cannot import


def _kinds(messages: Iterable[Mapping[str, Any]]) -> list[tuple[str, int | None, str | None]]:
    """Each message as its type, revision and cause: what ADR 0009 §9 orders per connection."""
    return [(message["type"], message.get("revision"), message.get("cause")) for message in messages]


def _expected_receives(scenario: Mapping[str, Any], connection: str, without_messages: Callable[[Any], Any]) -> Any:
    """Exactly the messages a scenario says this connection receives, in order (the fixtures' normative order)."""
    return [
        without_messages(step["message"])
        for step in scenario["steps"]
        if step["op"] == "receive" and step["connection"] == connection
    ]


def _expected_close(scenario: Mapping[str, Any], connection: str) -> int | None:
    return next(
        (
            step["code"]
            for step in scenario["steps"]
            if step["op"] == "server_close" and step["connection"] == connection
        ),
        None,
    )


@pytest.fixture
def heads_up(
    make_runtime: Callable[..., Harness],
    scenario_setup: Callable[[str], Mapping[str, Any]],
    parse_cards: Callable[[Iterable[str]], list[Card]],
    queue_decks: Callable[..., Any],
) -> tuple[Harness, Connection, Connection]:
    """The `heads_up_hand` table at revision 2: Alice and Bob members, both connected, nothing started."""
    setup = scenario_setup("heads_up_hand")
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    harness = make_runtime(setup, "alice")
    alice = harness.open("alice")
    harness.join("bob", 2)
    bob = harness.open("bob")
    alice.outbox.drain()
    bob.outbox.drain()
    return harness, alice, bob


def test_a_shared_command_delivers_one_snapshot_per_connection_then_the_outcome(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob = heads_up
    harness.execute(alice, decode.StartGame(request_id="a-02", expected_revision=2))

    assert _kinds(messages_of(alice)) == [("snapshot", 3, "command"), ("accepted", 3, None)]
    assert _kinds(messages_of(bob)) == [("snapshot", 3, "command")]
    assert harness.runtime.revision == 3


def test_a_join_tells_every_connected_member_and_nobody_else(
    make_runtime: Callable[..., Harness],
    scenario_setup: Callable[[str], Mapping[str, Any]],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    setup = scenario_setup("heads_up_hand")
    harness = make_runtime(setup, "alice")
    alice = harness.open("alice")
    alice.outbox.drain()

    joined = harness.join("bob", 2)

    assert _kinds(messages_of(alice)) == [("snapshot", 2, "command")]
    assert harness.runtime.authenticate(joined.credential) == joined.user_id
    assert joined.seat == 2


def test_a_private_command_answers_only_its_requester_at_the_unchanged_revision(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob = heads_up
    harness.execute(alice, decode.StartGame(request_id="a-02", expected_revision=2))
    messages_of(alice)
    messages_of(bob)

    harness.execute(bob, decode.SelectPreAction(request_id="b-01", expected_revision=3, kind="check", amount=None))

    assert _kinds(messages_of(bob)) == [("snapshot", 3, "private"), ("accepted", 3, None)]
    assert messages_of(alice) == []
    assert harness.runtime.revision == 3


def test_a_rejection_carries_no_snapshot_and_changes_nothing(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob = heads_up

    harness.execute(bob, decode.StartGame(request_id="b-01", expected_revision=2))

    rejected = messages_of(bob)
    assert _kinds(rejected) == [("rejected", None, None)]
    assert (rejected[0]["code"], rejected[0]["request_id"]) == ("NOT_HOST", "b-01")
    assert messages_of(alice) == []
    assert harness.runtime.revision == 2
    assert harness.runtime.phase is TablePhase.NOT_STARTED


@pytest.mark.parametrize(("case", "expected_revision"), [("older", 1), ("newer", 99)])
def test_the_expected_revision_passes_through_unchanged(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
    case: str,
    expected_revision: int,
) -> None:
    """The runtime never substitutes the current revision, so a mismatch in either direction is STALE_REVISION."""
    harness, alice, _ = heads_up

    harness.execute(alice, decode.StartGame(request_id="a-02", expected_revision=expected_revision))

    frames = alice.outbox.drain()
    rejected = [frame.message for frame in frames]
    assert [message.type for message in rejected] == ["rejected"]
    assert [message.code for message in rejected] == ["STALE_REVISION"]
    # The diagnostic text is not normative, but it shows which revision reached the session unchanged.
    assert f"Expected revision {expected_revision}" in rejected[0].message
    assert harness.runtime.revision == 2


def test_a_cascade_delivers_each_transitions_own_captured_view(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    """A pre-action executing on its owner's turn is a second transition, and its snapshot is the state at *that*
    revision: a re-read of the final state would make both snapshots equal and fail this test."""
    harness, alice, bob = heads_up
    harness.execute(alice, decode.StartGame(request_id="a-02", expected_revision=2))
    harness.execute(
        bob, decode.SelectPreAction(request_id="b-01", expected_revision=3, kind="check_or_fold", amount=None)
    )
    messages_of(alice)
    messages_of(bob)

    harness.execute(alice, decode.Act(request_id="a-03", expected_revision=3, action="call", target=None))

    for messages in (messages_of(alice), messages_of(bob)):
        kinds = _kinds(messages)
        assert kinds[:2] == [("snapshot", 4, "command"), ("snapshot", 5, "pre_action")]
        assert [message["view"]["hand"]["street"] for message in messages[:2]] == ["preflop", "flop"]
    assert harness.runtime.revision == 5


def test_the_requester_of_an_applied_leave_gets_its_outcome_then_left_table(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob = heads_up
    alice_credential = harness.credentials["alice"]

    harness.execute(alice, decode.Leave(request_id="a-02", expected_revision=2))

    frames = alice.outbox.drain()
    assert _kinds(frame.message.model_dump(mode="json") for frame in frames) == [
        ("accepted", 3, None),
        ("left_table", None, None),
    ]
    assert [frame.close_code for frame in frames] == [None, CLOSE_LEFT_TABLE]
    assert alice.stopped is True
    assert _kinds(messages_of(bob)) == [("snapshot", 3, "command")]
    assert harness.runtime.authenticate(alice_credential) is None
    assert harness.runtime.authenticate(harness.credentials["bob"]) == harness.user_ids["bob"]
    assert harness.runtime.connections == (bob,)


def test_supersede_and_the_first_connected_snapshot_are_one_step(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob = heads_up

    second = harness.open("alice")

    frames = alice.outbox.drain()
    assert _kinds(frame.message.model_dump(mode="json") for frame in frames) == [("superseded", None, None)]
    assert [frame.close_code for frame in frames] == [CLOSE_SUPERSEDED]
    assert alice.stopped is True
    assert _kinds(messages_of(second)) == [("snapshot", 2, "connected")]
    assert harness.runtime.connections == (bob, second), "the superseded connection is unregistered"
    assert messages_of(bob) == [], "another member learns nothing from a supersede"


def test_a_frame_of_a_superseded_connection_is_never_executed(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    """A command already in transit when the supersede happened must change nothing and produce no outcome."""
    harness, alice, bob = heads_up
    second = harness.open("alice")
    alice.outbox.drain()
    messages_of(second)
    messages_of(bob)

    harness.execute(alice, decode.StartGame(request_id="a-99", expected_revision=2))

    assert harness.runtime.revision == 2
    assert harness.runtime.phase is TablePhase.NOT_STARTED
    assert alice.outbox.drain() == []
    assert messages_of(second) == []
    assert messages_of(bob) == []


def test_a_disconnected_connection_is_unregistered_and_reads_nothing_more(
    heads_up: tuple[Harness, Connection, Connection],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob = heads_up

    harness.runtime.disconnect(bob)
    harness.execute(alice, decode.StartGame(request_id="a-02", expected_revision=2))

    assert bob.stopped is True
    assert harness.runtime.connections == (alice,)
    assert messages_of(bob) == []
    assert _kinds(messages_of(alice)) == [("snapshot", 3, "command"), ("accepted", 3, None)]


# --- The next-hand call ---


@pytest.fixture
def settled(
    make_runtime: Callable[..., Harness],
    fixture_json: Callable[[str], Any],
    parse_cards: Callable[[Iterable[str]], list[Card]],
    queue_decks: Callable[..., Any],
) -> tuple[Harness, Connection, Connection, Mapping[str, Any]]:
    """The `leave_and_sit_out` table driven to revision 4: the hand is complete and Alice's leave is pending."""
    scenario = fixture_json("scenarios/leave_and_sit_out.json")
    setup = scenario["setup"]
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    harness = make_runtime(setup, "alice")
    harness.join("bob", 2)
    alice = harness.open("alice")
    bob = harness.open("bob")
    harness.execute(alice, decode.StartGame(request_id="a-01", expected_revision=2))
    harness.execute(bob, decode.SitOut(request_id="b-01", expected_revision=3))
    harness.execute(bob, decode.SitBack(request_id="b-02", expected_revision=3))
    harness.execute(alice, decode.Leave(request_id="a-02", expected_revision=3))
    return harness, alice, bob, scenario


def test_the_leave_and_sit_out_scenario_delivers_exactly_its_canonical_messages(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
    without_messages: Callable[[Any], Any],
    leak_check: Callable[[Mapping[str, Any], Sequence[str]], None],
) -> None:
    """One scenario end to end at the runtime level: the private updates, the leave auto-action, the hand boundary,
    both departures and their close codes, compared with the fixture's per-connection message lists."""
    harness, alice, bob, scenario = settled

    harness.scheduler.fire()
    harness.execute(bob, decode.Leave(request_id="b-03", expected_revision=5))

    for connection, name in ((alice, "alice-1"), (bob, "bob-1")):
        frames = connection.outbox.drain()
        messages = [without_messages(frame.message.model_dump(mode="json")) for frame in frames]
        assert messages == _expected_receives(scenario, name, without_messages)
        assert [frame.close_code for frame in frames[:-1]] == [None] * (len(frames) - 1)
        assert frames[-1].close_code == _expected_close(scenario, name)
        revisions = [message["revision"] for message in messages if "revision" in message]
        assert revisions == sorted(revisions), "revisions never decrease on one connection"
        for message in messages:
            leak_check(message, harness.identity_texts())


def test_the_next_hand_call_is_armed_exactly_while_the_hand_is_complete(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
) -> None:
    harness, _, _, _ = settled
    assert harness.runtime.phase is TablePhase.HAND_COMPLETE
    assert harness.scheduler.is_armed
    assert harness.scheduler.delay == harness.config.next_hand_pause_seconds

    harness.scheduler.fire()

    assert harness.runtime.phase is TablePhase.WAITING_FOR_PLAYERS
    assert not harness.scheduler.is_armed


def test_firing_the_next_hand_call_produces_the_hand_boundary_transition(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob, _ = settled
    messages_of(alice)
    messages_of(bob)

    harness.scheduler.fire()

    assert _kinds(messages_of(bob)) == [("snapshot", 5, "hand_boundary")]
    assert _kinds(message for message in messages_of(alice)) == [("left_table", None, None)]
    assert harness.runtime.revision == 5


def test_a_stale_next_hand_call_does_nothing_at_all(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    """The revision the timer was armed at is what makes a firing that lost its race harmless."""
    harness, alice, bob, _ = settled
    stale = harness.scheduler.armed_call()
    harness.scheduler.fire()
    messages_of(alice)
    messages_of(bob)
    revision = harness.runtime.revision

    stale()

    assert harness.runtime.revision == revision
    assert messages_of(alice) == []
    assert messages_of(bob) == []
    assert not harness.scheduler.is_armed


def test_a_stale_call_does_nothing_even_while_the_hand_is_still_complete(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    """The sharper stale case: the phase is *still* `hand_complete`, so only the captured revision stops the firing.

    A timer that read the current revision when it fired instead of the revision it was armed at would advance the
    hand here, because `advance_hand` would pass its guard.
    """
    harness, alice, bob, _ = settled
    stale = harness.scheduler.armed_call()
    harness.execute(bob, decode.SitOut(request_id="b-04", expected_revision=4))
    assert harness.runtime.phase is TablePhase.HAND_COMPLETE, "the hand is still complete at the new revision"
    revision = harness.runtime.revision
    assert revision == 5
    messages_of(alice)
    messages_of(bob)

    stale()

    assert harness.runtime.revision == revision, "the firing armed at an older revision must do nothing"
    assert harness.runtime.phase is TablePhase.HAND_COMPLETE
    assert messages_of(alice) == []
    assert messages_of(bob) == []
    assert harness.scheduler.is_armed, "the call armed at the current revision is still pending"

    harness.scheduler.fire()

    assert harness.runtime.revision == 6
    assert _kinds(messages_of(bob)) == [("snapshot", 6, "hand_boundary")]


def test_a_transition_after_the_hand_completed_rearms_the_call_at_the_new_revision(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness, alice, bob, _ = settled
    harness.execute(bob, decode.SitOut(request_id="b-04", expected_revision=4))
    assert harness.runtime.revision == 5
    assert harness.runtime.phase is TablePhase.HAND_COMPLETE
    assert harness.scheduler.is_armed
    messages_of(alice)
    messages_of(bob)

    harness.scheduler.fire()

    assert _kinds(messages_of(bob)) == [("snapshot", 6, "hand_boundary")]
    assert harness.runtime.revision == 6


def test_a_member_who_departs_with_no_connection_open_loses_their_credential(
    settled: tuple[Harness, Connection, Connection, Mapping[str, Any]],
) -> None:
    harness, alice, _, _ = settled
    credential = harness.credentials["alice"]
    harness.runtime.disconnect(alice)

    harness.scheduler.fire()

    assert harness.runtime.authenticate(credential) is None
    assert harness.session.is_member(harness.user_ids["alice"]) is False

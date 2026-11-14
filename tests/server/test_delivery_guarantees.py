"""At most once, with no deduplication, and the revision guard (ADR 0009 §8, §9.4; Brief §5.10).

Four separate guarantees are attacked here, each on the real server:

- one executed command per read frame, in arrival order;
- a repeated `request_id` is a **new** command: the server never compares it with an earlier one;
- there is no outcome cache and no replay, so an outcome the connection missed is gone;
- `expected_revision` reaches `TableSession` unchanged, so both a lower and a higher revision are `STALE_REVISION`.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

JOIN_CODE = "K7Q2XM"
TABLE_ID = "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f"
REPEATED = "same-request-id"


@dataclass
class Table:
    """Alice (host, seat 1) and Bob (seat 2) at revision 2, with `heads_up_hand`'s deck stacked."""

    client: TestClient
    harness: Any
    credentials: dict[str, str]

    @property
    def path(self) -> str:
        return f"/ws/tables/{TABLE_ID}"

    @property
    def revision(self) -> int:
        runtime = self.harness.directory.get(TABLE_ID)
        assert runtime is not None
        return int(runtime.revision)

    def hello(self, session: WebSocketTestSession, member: str) -> Any:
        session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": self.credentials[member]})
        return session.receive_json()

    def command(self, session: WebSocketTestSession, request_id: str, revision: int, **rest: Any) -> None:
        session.send_json({"type": "command", "request_id": request_id, "expected_revision": revision, **rest})


@pytest.fixture
def table(
    make_app: Callable[..., Any],
    queue_decks: Callable[..., Any],
    parse_cards: Callable[..., Any],
    fixture_json: Callable[[str], Any],
) -> Iterator[Table]:
    setup = fixture_json("scenarios/heads_up_hand.json")["setup"]
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    harness = make_app(new_table_id=lambda: TABLE_ID, new_join_code=lambda: JOIN_CODE, choose_button=min)
    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": "Alice"}).json()
        joined = client.post(f"/tables/by-code/{JOIN_CODE}/members", json={"display_name": "Bob", "seat": 2}).json()
        credentials = {"alice": created["credential"], "bob": joined["credential"]}
        harness.credentials.extend(credentials.values())
        yield Table(client=client, harness=harness, credentials=credentials)


def _outcomes(messages: list[Any]) -> list[tuple[str, str | None, str | None]]:
    """The terminal outcomes among a connection's messages: type, `request_id` and code (ADR 0009 §8.3)."""
    return [
        (message["type"], message.get("request_id"), message.get("code"))
        for message in messages
        if message["type"] in {"accepted", "rejected", "error"}
    ]


# --- One executed command per read frame, in arrival order (§8.1) ---


def test_three_pipelined_frames_produce_three_outcomes_in_arrival_order(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")

        table.command(alice, "a-01", 2, name="start_game", args={})
        table.command(alice, "a-02", 3, name="act", args={"action": "call", "target": None})
        table.command(alice, "a-03", 4, name="act", args={"action": "check", "target": None})

        messages = drain_socket(table.client, alice)
        assert _outcomes(messages) == [
            ("accepted", "a-01", None),
            ("accepted", "a-02", None),
            ("rejected", "a-03", "NOT_YOUR_TURN"),
        ]
        assert table.revision == 4, "exactly two of the three frames changed the table"


def test_an_undecodable_frame_between_two_commands_does_not_reorder_their_outcomes(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    with table.client.websocket_connect(table.path) as alice:
        table.hello(alice, "alice")

        table.command(alice, "a-01", 2, name="sit_out", args={})
        alice.send_text("{not json")
        table.command(alice, "a-02", 3, name="sit_back", args={})

        assert _outcomes(drain_socket(table.client, alice)) == [
            ("accepted", "a-01", None),
            ("error", None, "MALFORMED_MESSAGE"),
            ("accepted", "a-02", None),
        ]
        assert table.revision == 4


# --- A repeated `request_id` is a new command (§8.2) ---


def test_a_repeated_request_id_is_executed_again_and_never_deduplicated(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    """The second command carries the same `request_id` and a *different* outcome, because it really ran."""
    with table.client.websocket_connect(table.path) as alice:
        table.hello(alice, "alice")

        table.command(alice, REPEATED, 2, name="sit_out", args={})
        table.command(alice, REPEATED, 3, name="sit_out", args={})

        assert _outcomes(drain_socket(table.client, alice)) == [
            ("accepted", REPEATED, None),
            ("rejected", REPEATED, "NO_CHANGE"),
        ]
        assert table.revision == 3


def test_the_identical_frame_sent_twice_is_executed_twice_and_applies_once(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    """Byte-identical frames: no outcome cache answers the second one, and the guard stops it from applying."""
    frame = {
        "type": "command",
        "request_id": REPEATED,
        "expected_revision": 2,
        "name": "start_game",
        "args": {},
    }
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")

        alice.send_json(frame)
        alice.send_json(frame)

        assert _outcomes(drain_socket(table.client, alice)) == [
            ("accepted", REPEATED, None),
            ("rejected", REPEATED, "STALE_REVISION"),
        ]
        snapshots = [message for message in drain_socket(table.client, bob) if message["type"] == "snapshot"]
        assert [snapshot["revision"] for snapshot in snapshots] == [3], "the hand started exactly once"
        assert table.revision == 3


def test_a_private_command_repeated_at_the_same_revision_answers_twice(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    """§8: `expected_revision` is no idempotency guarantee for a private command; both frames are executed."""
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")
        table.command(alice, "a-01", 2, name="start_game", args={})
        drain_socket(table.client, alice)
        drain_socket(table.client, bob)

        selection = {"pre_action": {"kind": "check_or_fold", "amount": None}}
        table.command(bob, REPEATED, 3, name="select_pre_action", args=selection)
        table.command(bob, REPEATED, 3, name="select_pre_action", args=selection)

        messages = drain_socket(table.client, bob)
        assert _outcomes(messages) == [
            ("accepted", REPEATED, None),
            ("rejected", REPEATED, "NO_CHANGE"),
        ]
        assert [message["revision"] for message in messages if message["type"] == "snapshot"] == [3]
        assert drain_socket(table.client, alice) == [], "a private command tells nobody else"
        assert table.revision == 3


# --- No outcome cache and no replay (§8, §13) ---


def test_an_outcome_the_connection_never_read_is_dropped_and_not_replayed(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    """ADR 0009 §8: an outcome arrives only while the connection stays open, and a reconnect gets a snapshot only."""
    with table.client.websocket_connect(table.path) as bob:
        table.hello(bob, "bob")

        with table.client.websocket_connect(table.path) as alice:
            table.hello(alice, "alice")
            table.command(alice, "a-01", 2, name="start_game", args={})
            # Alice reads nothing, then leaves. Bob's snapshot proves the command was executed.
            assert [message["revision"] for message in drain_socket(table.client, bob)] == [3]

        with table.client.websocket_connect(table.path) as again:
            snapshot = table.hello(again, "alice")
            assert (snapshot["type"], snapshot["cause"], snapshot["revision"]) == ("snapshot", "connected", 3)
            assert drain_socket(table.client, again) == [], "no outcome and no missed snapshot is replayed"


def test_a_table_that_fails_mid_command_delivers_no_outcome(
    table: Table,
    inject_defect: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§8.3: the one outcome of an executed command may be undelivered, and `table_failed` replaces it."""
    runtime = table.harness.directory.get(TABLE_ID)
    assert runtime is not None
    inject_defect(monkeypatch, runtime, "sit_out")

    with table.client.websocket_connect(table.path) as alice:
        table.hello(alice, "alice")

        table.command(alice, "a-01", 2, name="sit_out", args={})

        assert alice.receive_json() == {"type": "table_failed"}, "the outcome is replaced, not queued behind it"
        with pytest.raises(WebSocketDisconnect) as closed:
            alice.receive_json()
        assert closed.value.code == 4500


# --- The revision guard (§9.4) ---


@pytest.mark.parametrize(("case", "expected_revision"), [("lower", 1), ("higher", 3), ("far higher", 2**53 - 1)])
def test_a_revision_that_is_not_the_current_one_is_stale_in_either_direction(
    table: Table, drain_socket: Callable[..., list[Any]], case: str, expected_revision: int
) -> None:
    """ADR 0009 §9.4: a *higher* `expected_revision` is `STALE_REVISION` too, and nothing changes."""
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")

        table.command(alice, "a-01", expected_revision, name="start_game", args={})

        assert _outcomes(drain_socket(table.client, alice)) == [("rejected", "a-01", "STALE_REVISION")]
        assert drain_socket(table.client, bob) == [], "a rejection tells nobody and carries no snapshot"
        assert table.revision == 2

        # The same command at the current revision is accepted, so nothing was poisoned by the rejection.
        table.command(alice, "a-02", 2, name="start_game", args={})
        assert _outcomes(drain_socket(table.client, alice)) == [("accepted", "a-02", None)]
        assert table.revision == 3

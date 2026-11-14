"""The connection lifecycle and the concurrency rules, over the real server (ADR 0009 §5, §8, §12, §13).

Everything here drives the real app through `TestClient`, entered as a context manager so that every connection of a
client shares one event loop. No `sleep`-based assertion decides anything about table state: the timings that matter
are configured (a short hello timeout) or triggered (the next-hand call).
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

HELLO_TIMEOUT_SECONDS = 0.05
FRAME_LIMIT = 16384

# The commands of hand 1 of `heads_up_hand`, as the scenario sends them, for the ordering test.
HAND_ONE: tuple[tuple[str, dict[str, Any]], ...] = (
    ("alice", {"name": "act", "args": {"action": "call", "target": None}}),
    ("bob", {"name": "act", "args": {"action": "check", "target": None}}),
    ("bob", {"name": "act", "args": {"action": "bet", "target": 20}}),
    ("alice", {"name": "act", "args": {"action": "raise", "target": 60}}),
    ("bob", {"name": "act", "args": {"action": "call", "target": None}}),
)


@dataclass
class LiveTable:
    """A table over the real app, with its client, its identifiers and its members' credentials."""

    client: TestClient
    harness: Any
    table_id: str
    join_code: str
    credentials: dict[str, str]

    @property
    def path(self) -> str:
        return f"/ws/tables/{self.table_id}"

    @property
    def revision(self) -> int:
        runtime = self.harness.directory.get(self.table_id)
        assert runtime is not None
        return int(runtime.revision)

    def hello(self, session: WebSocketTestSession, member: str) -> Any:
        """Authenticate a connection and return its `connected` snapshot."""
        session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": self.credentials[member]})
        return session.receive_json()

    def command(self, session: WebSocketTestSession, request_id: str, revision: int, **command: Any) -> None:
        session.send_json({"type": "command", "request_id": request_id, "expected_revision": revision, **command})


def _table(harness: Any, client: TestClient, join_code: str) -> LiveTable:
    created = client.post("/tables", json={"display_name": "Alice"}).json()
    joined = client.post(f"/tables/by-code/{join_code}/members", json={"display_name": "Bob", "seat": 2}).json()
    credentials = {"alice": created["credential"], "bob": joined["credential"]}
    harness.credentials.extend(credentials.values())
    return LiveTable(
        client=client,
        harness=harness,
        table_id=created["table_id"],
        join_code=created["join_code"],
        credentials=credentials,
    )


@pytest.fixture
def table(
    make_app: Callable[..., Any],
    queue_decks: Callable[..., Any],
    parse_cards: Callable[..., Any],
    fixture_json: Callable[[str], Any],
) -> Iterator[LiveTable]:
    """Alice (host, seat 1) and Bob (seat 2) at revision 2, with `heads_up_hand`'s decks stacked."""
    setup = fixture_json("scenarios/heads_up_hand.json")["setup"]
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    harness = make_app(
        new_table_id=lambda: setup["ids"]["table_id"],
        new_join_code=lambda: setup["ids"]["join_code"],
        choose_button=min,
    )
    with TestClient(harness.app) as client:
        yield _table(harness, client, setup["ids"]["join_code"])


# --- The handshake ---


def test_a_connection_that_never_says_hello_times_out(make_app: Callable[..., Any]) -> None:
    harness = make_app(hello_timeout_seconds=HELLO_TIMEOUT_SECONDS)
    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": "Alice"}).json()
        with client.websocket_connect(f"/ws/tables/{created['table_id']}") as session:
            assert session.receive_json() == {
                "type": "error",
                "request_id": None,
                "code": "HELLO_TIMEOUT",
                "message": f"No hello within {HELLO_TIMEOUT_SECONDS} seconds",
            }
            with pytest.raises(WebSocketDisconnect) as closed:
                session.receive_json()
            assert closed.value.code == 4408


def test_a_revoked_credential_no_longer_authenticates(table: LiveTable, drain_socket: Callable[..., list[Any]]) -> None:
    with table.client.websocket_connect(table.path) as alice:
        table.hello(alice, "alice")
        table.command(alice, "a-01", 2, name="leave", args={})
        assert alice.receive_json()["type"] == "accepted"
        assert alice.receive_json() == {"type": "left_table"}
        with pytest.raises(WebSocketDisconnect) as closed:
            alice.receive_json()
        assert closed.value.code == 4410

    with table.client.websocket_connect(table.path) as reconnected:
        reconnected.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": table.credentials["alice"]})
        assert reconnected.receive_json()["code"] == "AUTH_FAILED"
        with pytest.raises(WebSocketDisconnect) as closed:
            reconnected.receive_json()
        assert closed.value.code == 4401


# --- Supersede and reconnection (ADR 0009 §5, §13) ---


def test_a_frame_sent_after_a_supersede_is_never_executed(
    table: LiveTable,
    drain_socket: Callable[..., list[Any]],
    assert_nothing_pending: Callable[..., None],
) -> None:
    with (
        table.client.websocket_connect(table.path) as bob,
        table.client.websocket_connect(table.path) as first,
    ):
        table.hello(bob, "bob")
        table.hello(first, "alice")

        with table.client.websocket_connect(table.path) as second:
            assert table.hello(second, "alice")["revision"] == 2
            assert first.receive_json() == {"type": "superseded"}
            with pytest.raises(WebSocketDisconnect) as closed:
                first.receive_json()
            assert closed.value.code == 4409

            table.command(first, "a-99", 2, name="start_game", args={})

            assert table.revision == 2, "a superseded connection's frame is never executed"
            assert_nothing_pending(table.client, {"alice-2": second, "bob-1": bob})


def test_a_reconnection_receives_only_the_current_snapshot(
    table: LiveTable, drain_socket: Callable[..., list[Any]]
) -> None:
    """Missed transitions are never replayed (ADR 0009 §13)."""
    with (
        table.client.websocket_connect(table.path) as bob,
        table.client.websocket_connect(table.path) as alice,
    ):
        table.hello(bob, "bob")
        table.hello(alice, "alice")
        table.command(alice, "a-01", 2, name="start_game", args={})
        table.command(alice, "a-02", 3, name="act", args={"action": "call", "target": None})
        drain_socket(table.client, alice)
        drain_socket(table.client, bob)

    # Alice is gone; Bob moves the table on without her.
    with table.client.websocket_connect(table.path) as bob_again:
        table.hello(bob_again, "bob")
        table.command(bob_again, "b-01", 4, name="act", args={"action": "check", "target": None})
        drain_socket(table.client, bob_again)
        revision = table.revision

        with table.client.websocket_connect(table.path) as alice_again:
            snapshot = table.hello(alice_again, "alice")
            assert (snapshot["type"], snapshot["cause"], snapshot["revision"]) == (
                "snapshot",
                "connected",
                revision,
            )
            assert drain_socket(table.client, alice_again) == [], "nothing of the missed transitions is replayed"


# --- The inbound frame limit (ADR 0009 §5, §12) ---


def _padded_command(byte_length: int) -> str:
    """A syntactically valid command frame of exactly `byte_length` UTF-8 bytes, with a multi-byte character.

    The extra `pad` field makes it an `INVALID_COMMAND` once decoded, which is how a test sees that it *was* decoded.
    The two-byte character makes a character-count limit disagree with the contract's byte count.
    """
    prefix = '{"type":"command","request_id":"a-01","expected_revision":2,"name":"start_game","args":{},"pad":"é'
    suffix = '"}'
    padding = byte_length - len((prefix + suffix).encode("utf-8"))
    assert padding > 0
    frame = prefix + "x" * padding + suffix
    assert len(frame.encode("utf-8")) == byte_length
    assert len(frame) == byte_length - 1, "the frame must have fewer characters than bytes"
    return frame


def test_a_frame_at_the_limit_is_decoded(table: LiveTable) -> None:
    with table.client.websocket_connect(table.path) as alice:
        table.hello(alice, "alice")

        alice.send_text(_padded_command(FRAME_LIMIT))

        answer = alice.receive_json()
        assert (answer["type"], answer["code"], answer["request_id"]) == ("error", "INVALID_COMMAND", "a-01")
        # The connection stays open and keeps working.
        table.command(alice, "a-02", 2, name="start_game", args={})
        assert [message["type"] for message in (alice.receive_json(), alice.receive_json())] == [
            "snapshot",
            "accepted",
        ]


def test_a_frame_over_the_limit_closes_the_connection_and_changes_nothing(
    table: LiveTable, assert_nothing_pending: Callable[..., None]
) -> None:
    with (
        table.client.websocket_connect(table.path) as bob,
        table.client.websocket_connect(table.path) as alice,
    ):
        table.hello(bob, "bob")
        table.hello(alice, "alice")

        alice.send_text(_padded_command(FRAME_LIMIT + 1))

        with pytest.raises(WebSocketDisconnect) as closed:
            alice.receive_json()
        assert closed.value.code == 1009, "an oversized frame closes 1009 with no error message"
        assert table.revision == 2
        assert_nothing_pending(table.client, {"bob-1": bob})


# --- Concurrency and delivery (Brief §6.6) ---


def test_two_commands_at_the_same_revision_give_one_accepted_and_one_stale(
    table: LiveTable, drain_socket: Callable[..., list[Any]]
) -> None:
    """`expected_revision` protects against duplicate shared transitions at one revision (ADR 0009 §8)."""
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")

        table.command(alice, "a-01", 2, name="sit_out", args={})
        table.command(bob, "b-01", 2, name="sit_out", args={})

        outcomes = []
        for session in (alice, bob):
            messages = drain_socket(table.client, session)
            own = [message for message in messages if message.get("request_id") is not None]
            assert len(own) == 1, messages
            outcomes.append((own[0]["type"], own[0].get("code")))
        assert sorted(outcomes) == [("accepted", None), ("rejected", "STALE_REVISION")]
        assert table.revision == 3, "exactly one of them produced a shared transition"


def test_revisions_never_decrease_on_one_connection_across_a_hand(
    table: LiveTable, drain_socket: Callable[..., list[Any]]
) -> None:
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        sessions = {"alice": alice, "bob": bob}
        received: dict[str, list[int]] = {"alice": [], "bob": []}
        latest: dict[str, int] = {}
        for member, session in sessions.items():
            latest[member] = table.hello(session, member)["revision"]

        def drive(actor: str, request_id: str, **command: Any) -> None:
            """Send as a real client does: with the revision of the latest snapshot this connection applied."""
            table.command(sessions[actor], request_id, latest[actor], **command)
            for member, session in sessions.items():
                for message in drain_socket(table.client, session):
                    if message["type"] == "snapshot":
                        received[member].append(message["revision"])
                        latest[member] = message["revision"]

        drive("alice", "a-01", name="start_game", args={})
        for index, (actor, command) in enumerate(HAND_ONE, start=2):
            drive(actor, f"r-{index}", **command)

        for member, revisions in received.items():
            assert revisions == sorted(revisions), f"{member} saw revisions out of order"
            assert revisions, f"{member} received no snapshot"
        assert table.revision == 8


def test_an_overflowing_connection_is_closed_and_leaves_the_others_alone(
    make_app: Callable[..., Any],
    queue_decks: Callable[..., Any],
    parse_cards: Callable[..., Any],
    fixture_json: Callable[[str], Any],
) -> None:
    """ADR 0009 §5: a connection that overflows its outbox is closed `4008`, and reconnects to the current snapshot.

    One phase-1 step puts a snapshot and then the outcome, so an outbox of one frame overflows on the first shared
    command. No production seam is involved: `outbox_size` is ordinary configuration.
    """
    setup = fixture_json("scenarios/heads_up_hand.json")["setup"]
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    harness = make_app(
        outbox_size=1,
        new_table_id=lambda: setup["ids"]["table_id"],
        new_join_code=lambda: setup["ids"]["join_code"],
        choose_button=min,
    )
    with TestClient(harness.app) as client:
        table = _table(harness, client, setup["ids"]["join_code"])
        with (
            client.websocket_connect(table.path) as alice,
            client.websocket_connect(table.path) as bob,
        ):
            table.hello(alice, "alice")
            table.hello(bob, "bob")

            table.command(alice, "a-01", 2, name="start_game", args={})

            with pytest.raises(WebSocketDisconnect) as closed:
                alice.receive_json()
            assert closed.value.code == 4008
            assert bob.receive_json()["revision"] == 3, "another connection of the table is unaffected"
            assert table.revision == 3

        with client.websocket_connect(table.path) as again:
            snapshot = table.hello(again, "alice")
            assert (snapshot["cause"], snapshot["revision"]) == ("connected", 3)


# --- Failure isolation over the socket (Brief §6.7) ---


def test_a_failed_table_takes_down_only_its_own_connections(
    make_app: Callable[..., Any],
    queue_decks: Callable[..., Any],
    parse_cards: Callable[..., Any],
    fixture_json: Callable[[str], Any],
    inject_defect: Callable[..., None],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup = fixture_json("scenarios/heads_up_hand.json")["setup"]
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    ids = iter(["table-one", "table-two"])
    codes = iter(["AAAA22", "BBBB33"])
    harness = make_app(new_table_id=lambda: next(ids), new_join_code=lambda: next(codes), choose_button=min)

    with TestClient(harness.app) as client:
        broken = _table(harness, client, "AAAA22")
        healthy = _table(harness, client, "BBBB33")
        runtime = harness.directory.get(broken.table_id)
        assert runtime is not None
        inject_defect(monkeypatch, runtime, "start_game")

        with (
            client.websocket_connect(broken.path) as broken_alice,
            client.websocket_connect(broken.path) as broken_bob,
            client.websocket_connect(healthy.path) as healthy_alice,
        ):
            broken.hello(broken_alice, "alice")
            broken.hello(broken_bob, "bob")
            healthy.hello(healthy_alice, "alice")

            broken.command(broken_alice, "a-01", 2, name="start_game", args={})

            for session in (broken_alice, broken_bob):
                assert session.receive_json() == {"type": "table_failed"}
                with pytest.raises(WebSocketDisconnect) as closed:
                    session.receive_json()
                assert closed.value.code == 4500
            assert harness.directory.get(broken.table_id) is None
            assert harness.directory.by_code("AAAA22") is None

            healthy.command(healthy_alice, "a-01", 2, name="start_game", args={})
            assert [healthy_alice.receive_json()["type"] for _ in range(2)] == ["snapshot", "accepted"]
            assert healthy.revision == 3

        with client.websocket_connect(broken.path) as reconnected:
            reconnected.send_json(
                {"type": "hello", "protocol": "go-poker.v1", "credential": broken.credentials["alice"]}
            )
            assert reconnected.receive_json()["code"] == "AUTH_FAILED"
            with pytest.raises(WebSocketDisconnect) as closed:
                reconnected.receive_json()
            assert closed.value.code == 4401

        assert client.post("/tables/by-code/AAAA22/members", json={"display_name": "Carol", "seat": 3}).json() == {
            "error": {"code": "TABLE_NOT_FOUND", "message": "No open table has this code", "field": None}
        }


# --- The HTTP surface's own contract details ---


def test_the_health_probe_is_not_cached(make_app: Callable[..., Any]) -> None:
    harness = make_app()
    with TestClient(harness.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["cache-control"] == "no-store"


def test_a_join_code_is_matched_case_insensitively(table: LiveTable) -> None:
    joined = table.client.post(
        f"/tables/by-code/{table.join_code.lower()}/members", json={"display_name": "Carol", "seat": 3}
    )
    assert joined.status_code == 201
    assert joined.json()["table_id"] == table.table_id


def test_a_failed_join_stores_nothing(table: LiveTable) -> None:
    """Brief §5.7: no credential is minted and no membership created before an accepted join."""
    before = table.revision
    rejected = table.client.post(
        f"/tables/by-code/{table.join_code}/members", json={"display_name": "Carol", "seat": 2}
    )
    assert rejected.status_code == 409
    assert "credential" not in rejected.json()
    assert table.revision == before


def test_an_unknown_table_id_is_accepted_for_the_upgrade_and_answered_in_hello(table: LiveTable) -> None:
    """ADR 0009 §5: the upgrade succeeds for any table id, so a browser never learns which ids exist."""
    with table.client.websocket_connect("/ws/tables/no-such-table") as session:
        session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": table.credentials["alice"]})
        assert session.receive_json()["code"] == "AUTH_FAILED"
        with pytest.raises(WebSocketDisconnect) as closed:
            session.receive_json()
        assert closed.value.code == 4401


@pytest.mark.parametrize(
    ("case", "frame"),
    [
        ("not json", "{"),
        ("not an object", "[1, 2]"),
        ("a command", json.dumps({"type": "command", "request_id": "a-01", "expected_revision": 1})),
    ],
)
def test_a_first_frame_that_is_not_a_hello_closes_the_handshake(table: LiveTable, case: str, frame: str) -> None:
    with table.client.websocket_connect(table.path) as session:
        session.send_text(frame)
        assert session.receive_json()["code"] == "HELLO_REQUIRED"
        with pytest.raises(WebSocketDisconnect) as closed:
            session.receive_json()
        assert closed.value.code == 4400


def test_a_binary_frame_before_hello_closes_and_after_hello_does_not(table: LiveTable) -> None:
    with table.client.websocket_connect(table.path) as early:
        early.send_bytes(b'{"type": "hello", "protocol": "go-poker.v1", "credential": "x"}')
        assert early.receive_json()["code"] == "HELLO_REQUIRED"
        with pytest.raises(WebSocketDisconnect) as closed:
            early.receive_json()
        assert closed.value.code == 4400

    with table.client.websocket_connect(table.path) as alice:
        table.hello(alice, "alice")
        alice.send_bytes(b"not a text frame")
        answer = alice.receive_json()
        assert (answer["type"], answer["code"], answer["request_id"]) == ("error", "MALFORMED_MESSAGE", None)
        table.command(alice, "a-01", 2, name="start_game", args={})
        assert [alice.receive_json()["type"] for _ in range(2)] == ["snapshot", "accepted"]

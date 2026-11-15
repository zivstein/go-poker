"""A close that happens while the table is moving (ADR 0009 §5, §8, §12, §13).

The reader closes a connection itself for an oversized frame (`1009`), while that connection's writer may still hold
frames the table just produced. These are the realistic interleavings of the two:

- a shared transition and an oversized frame arriving together;
- an oversized frame from the member whose turn it is, followed by the table moving on without it.

In both, exactly one connection goes, the table keeps its state, every other connection is unaffected, and the closed
member gets the current snapshot when it reconnects.
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
FRAME_LIMIT = 16384
CLOSE_FRAME_TOO_BIG = 1009


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


def _oversized_command(byte_length: int) -> str:
    """A syntactically valid command frame of exactly `byte_length` UTF-8 bytes."""
    prefix = '{"type":"command","request_id":"b-99","expected_revision":2,"name":"start_game","args":{},"pad":"'
    suffix = '"}'
    padding = byte_length - len((prefix + suffix).encode("utf-8"))
    assert padding > 0
    frame = prefix + "x" * padding + suffix
    assert len(frame.encode("utf-8")) == byte_length
    return frame


def _read_until_close(session: WebSocketTestSession, limit: int = 8) -> tuple[list[str], int]:
    """Every message type a connection still receives, and the code it was closed with."""
    kinds: list[str] = []
    for _ in range(limit):
        try:
            kinds.append(session.receive_json()["type"])
        except WebSocketDisconnect as closed:
            return kinds, closed.code
    raise AssertionError(f"the connection was never closed; it received {kinds}")


def test_an_oversized_frame_sent_while_the_table_moves_closes_only_its_own_connection(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    """Bob's oversized frame and Alice's `start_game` are in flight together.

    Whether Bob's writer gets the transition snapshot out before the reader closes him is an interleaving the contract
    does not fix, so both are accepted. What is fixed: only `snapshot`s may precede the close, the close is `1009`,
    the transition still happened exactly once, and Alice saw her whole outcome.
    """
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")

        table.command(alice, "a-01", 2, name="start_game", args={})
        bob.send_text(_oversized_command(FRAME_LIMIT + 1))

        kinds, code = _read_until_close(bob)
        assert code == CLOSE_FRAME_TOO_BIG
        assert set(kinds) <= {"snapshot"}, f"Bob received {kinds}, which an oversized frame may not produce"
        assert [message["type"] for message in drain_socket(table.client, alice)] == ["snapshot", "accepted"]
        assert table.revision == 3, "the oversized frame was not executed and the command was executed once"

        # Alice's connection is untouched and the table keeps working for her.
        table.command(alice, "a-02", 3, name="act", args={"action": "call", "target": None})
        assert [message["type"] for message in drain_socket(table.client, alice)] == ["snapshot", "accepted"]
        assert table.revision == 4

    with table.client.websocket_connect(table.path) as again:
        snapshot = table.hello(again, "bob")
        assert (snapshot["cause"], snapshot["revision"]) == ("connected", 4), "a reconnect gets the current state"


def test_no_frame_of_a_superseded_connection_is_read_not_even_an_oversized_one(
    table: Table, drain_socket: Callable[..., list[Any]], assert_nothing_pending: Callable[..., None]
) -> None:
    """ADR 0009 §5: from the supersede on, the server reads **no** further frame of that connection.

    An oversized frame is the one frame whose handling would act on the socket itself, so a reader that kept reading
    a superseded connection would close an already closed socket here. Nothing may happen instead.
    """
    with table.client.websocket_connect(table.path) as first:
        table.hello(first, "alice")

        with table.client.websocket_connect(table.path) as second:
            assert table.hello(second, "alice")["cause"] == "connected"
            assert first.receive_json() == {"type": "superseded"}
            with pytest.raises(WebSocketDisconnect) as closed:
                first.receive_json()
            assert closed.value.code == 4409

            first.send_text(_oversized_command(FRAME_LIMIT + 1))
            first.send_text(_oversized_command(FRAME_LIMIT + 1))
            table.command(first, "a-99", 2, name="start_game", args={})

            assert table.revision == 2, "no frame of the superseded connection was executed"
            assert_nothing_pending(table.client, {"alice-2": second})

            # The live connection still works, which a defect inside the superseded reader would have broken.
            table.command(second, "a-01", 2, name="start_game", args={})
            assert [message["type"] for message in drain_socket(table.client, second)] == ["snapshot", "accepted"]
            assert table.revision == 3


def test_the_table_moves_on_after_a_members_connection_closed_itself(
    table: Table, drain_socket: Callable[..., list[Any]]
) -> None:
    """Bob loses his connection to the frame limit on his own turn; Alice's later command still applies."""
    with (
        table.client.websocket_connect(table.path) as alice,
        table.client.websocket_connect(table.path) as bob,
    ):
        table.hello(alice, "alice")
        table.hello(bob, "bob")
        table.command(alice, "a-01", 2, name="start_game", args={})
        drain_socket(table.client, alice)
        drain_socket(table.client, bob)

        bob.send_text(_oversized_command(FRAME_LIMIT + 1))
        kinds, code = _read_until_close(bob)
        assert (kinds, code) == ([], CLOSE_FRAME_TOO_BIG)

        table.command(alice, "a-02", 3, name="act", args={"action": "call", "target": None})
        assert [message["type"] for message in drain_socket(table.client, alice)] == ["snapshot", "accepted"]
        assert table.revision == 4

        runtime = table.harness.directory.get(TABLE_ID)
        assert runtime is not None
        assert [connection.user_id for connection in runtime.connections] == [
            runtime.authenticate(table.credentials["alice"])
        ], "the closed connection is unregistered and the live one is not"

"""Every canonical invalid frame answered by the real server, not only by the decoder (Brief §6.3, ADR 0009 §12).

`test_decode.py` proves the decoder classifies each `invalid/client_to_server.json` case. This module proves the
WebSocket turns that classification into the stated wire error, with the stated close code, and that an authenticated
connection survives every `MALFORMED_MESSAGE` and `INVALID_COMMAND` and changes nothing (ADR 0009 §1.5).
"""

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-wire-protocol-v1"
INVALID = json.loads((FIXTURE_ROOT / "invalid" / "client_to_server.json").read_text(encoding="utf-8"))
AFTER_HELLO: list[dict[str, Any]] = INVALID["after_hello"]
FIRST_FRAME: list[dict[str, Any]] = INVALID["first_frame"]

JOIN_CODE = "K7Q2XM"
TABLE_ID = "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f"
FRAME_LIMIT = 16384
CLOSE_FRAME_TOO_BIG = 1009


@dataclass
class Live:
    """One table with two members, over the real application."""

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


@pytest.fixture
def live(make_app: Callable[..., Any]) -> Iterator[Live]:
    harness = make_app(new_table_id=lambda: TABLE_ID, new_join_code=lambda: JOIN_CODE, choose_button=min)
    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": "Alice"}).json()
        joined = client.post(f"/tables/by-code/{JOIN_CODE}/members", json={"display_name": "Bob", "seat": 2}).json()
        credentials = {"alice": created["credential"], "bob": joined["credential"]}
        harness.credentials.extend(credentials.values())
        yield Live(client=client, harness=harness, credentials=credentials)


def _send(session: WebSocketTestSession, case: dict[str, Any]) -> None:
    """Send a fixture case's frame: `raw` as is, otherwise its `message` as JSON."""
    if "raw" in case:
        session.send_text(case["raw"])
    else:
        session.send_json(case["message"])


@pytest.mark.parametrize("case", AFTER_HELLO, ids=[case["case"] for case in AFTER_HELLO])
def test_an_invalid_frame_of_an_authenticated_connection_earns_its_error_and_keeps_the_connection(
    live: Live, case: dict[str, Any]
) -> None:
    expected = case["expect"]
    with live.client.websocket_connect(live.path) as alice:
        live.hello(alice, "alice")

        _send(alice, case)

        answer = alice.receive_json()
        assert (answer["type"], answer["code"], answer["request_id"]) == (
            expected["type"],
            expected["code"],
            expected["request_id"],
        )
        assert answer["message"], "every error carries a diagnostic message"
        assert set(answer) == {"type", "request_id", "code", "message"}
        assert live.revision == 2, "an undecodable frame changes nothing"

        # The connection stays open and the next command is executed normally (ADR 0009 §1.5, §12).
        alice.send_json(
            {"type": "command", "request_id": "a-99", "expected_revision": 2, "name": "start_game", "args": {}}
        )
        assert [alice.receive_json()["type"] for _ in range(2)] == ["snapshot", "accepted"]
        assert live.revision == 3


@pytest.mark.parametrize("case", FIRST_FRAME, ids=[case["case"] for case in FIRST_FRAME])
def test_a_first_frame_the_contract_rejects_closes_with_its_code(live: Live, case: dict[str, Any]) -> None:
    expected = case["expect"]
    with live.client.websocket_connect(live.path) as session:
        _send(session, case)

        answer = session.receive_json()
        assert (answer["type"], answer["code"], answer["request_id"]) == (
            expected["type"],
            expected["code"],
            expected["request_id"],
        )
        with pytest.raises(WebSocketDisconnect) as closed:
            session.receive_json()
        assert closed.value.code == expected["close"]
    assert live.revision == 2


def test_the_fixture_cases_cover_both_authenticated_error_codes_and_all_three_handshake_codes() -> None:
    """A fixture list that lost its cases would make the two tests above vacuous."""
    assert {case["expect"]["code"] for case in AFTER_HELLO} == {"MALFORMED_MESSAGE", "INVALID_COMMAND"}
    assert {case["expect"]["code"] for case in FIRST_FRAME} == {
        "HELLO_REQUIRED",
        "PROTOCOL_MISMATCH",
        "AUTH_FAILED",
    }
    assert {case["expect"]["close"] for case in FIRST_FRAME} == {4400, 4401}


def test_a_credential_of_another_table_is_auth_failed(make_app: Callable[..., Any]) -> None:
    """ADR 0009 §5: a foreign credential and an unknown one are not distinguished."""
    codes = iter([JOIN_CODE, "AAAA22"])
    ids = iter([TABLE_ID, "11111111-2222-3333-4444-555555555555"])
    harness = make_app(new_table_id=lambda: next(ids), new_join_code=lambda: next(codes))
    with TestClient(harness.app) as client:
        first = client.post("/tables", json={"display_name": "Alice"}).json()
        second = client.post("/tables", json={"display_name": "Bob"}).json()
        harness.credentials.extend([first["credential"], second["credential"]])

        with client.websocket_connect(f"/ws/tables/{second['table_id']}") as session:
            session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": first["credential"]})
            assert session.receive_json()["code"] == "AUTH_FAILED"
            with pytest.raises(WebSocketDisconnect) as closed:
                session.receive_json()
            assert closed.value.code == 4401


def test_a_second_hello_is_malformed_and_does_not_reauthenticate(live: Live) -> None:
    """§12: a second `hello` is `MALFORMED_MESSAGE` with no `request_id`, and the connection stays open."""
    with live.client.websocket_connect(live.path) as alice:
        live.hello(alice, "alice")

        alice.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": live.credentials["bob"]})

        answer = alice.receive_json()
        assert (answer["type"], answer["code"], answer["request_id"]) == ("error", "MALFORMED_MESSAGE", None)
        alice.send_json(
            {"type": "command", "request_id": "a-01", "expected_revision": 2, "name": "start_game", "args": {}}
        )
        assert [alice.receive_json()["type"] for _ in range(2)] == ["snapshot", "accepted"]


def _oversized_hello(byte_length: int) -> str:
    """A well-formed `hello` padded to exactly `byte_length` UTF-8 bytes through its credential."""
    prefix = '{"type":"hello","protocol":"go-poker.v1","credential":"'
    suffix = '"}'
    padding = byte_length - len((prefix + suffix).encode("utf-8"))
    assert padding > 0
    frame = prefix + "x" * padding + suffix
    assert len(frame.encode("utf-8")) == byte_length
    return frame


def test_an_oversized_first_frame_closes_with_1009_and_never_authenticates(live: Live) -> None:
    """The inbound limit is checked before the frame is decoded, the first frame included (ADR 0009 §5)."""
    with live.client.websocket_connect(live.path) as session:
        session.send_text(_oversized_hello(FRAME_LIMIT + 1))

        with pytest.raises(WebSocketDisconnect) as closed:
            session.receive_json()
        assert closed.value.code == CLOSE_FRAME_TOO_BIG, "no error message: 1009 carries no code (ADR 0009 §12)"
    assert live.revision == 2
    runtime = live.harness.directory.get(TABLE_ID)
    assert runtime is not None
    assert runtime.connections == (), "an oversized first frame registers no connection"


def test_a_first_frame_at_the_limit_is_decoded_and_answered_by_authentication(live: Live) -> None:
    """One byte less is decoded: its credential is 16 KiB of padding, so it answers `AUTH_FAILED`."""
    with live.client.websocket_connect(live.path) as session:
        session.send_text(_oversized_hello(FRAME_LIMIT))

        assert session.receive_json()["code"] == "AUTH_FAILED"
        with pytest.raises(WebSocketDisconnect) as closed:
            session.receive_json()
        assert closed.value.code == 4401

"""Every canonical server message parses with the wire models in strict mode and re-serializes unchanged.

This covers every snapshot shape of the contract before the runtime exists, the nine-seat, side-pot, odd-chip,
waiting, reset, resume and terminal ones included. The fixture paths are globbed at collection time, so they are read
here rather than through the `fixture_json` fixture.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from go_poker.server import dto
from go_poker.server.dto import wire_schema

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-wire-protocol-v1"
SERVER_MESSAGES = sorted((FIXTURE_ROOT / "messages" / "server").glob("*.json"))
HTTP_EXCHANGES = sorted((FIXTURE_ROOT / "messages" / "http").glob("*.json"))

SERVER_MESSAGE: TypeAdapter[dto.ServerMessage] = TypeAdapter(dto.ServerMessage)

MESSAGE_TYPES = frozenset({"snapshot", "accepted", "rejected", "error", "superseded", "left_table", "table_failed"})


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_the_canonical_fixtures_are_where_this_test_expects_them() -> None:
    assert len(SERVER_MESSAGES) >= 30, f"no server message fixtures under {FIXTURE_ROOT}"
    assert len(HTTP_EXCHANGES) == 5


@pytest.mark.parametrize("path", SERVER_MESSAGES, ids=lambda path: path.name)
def test_a_server_message_fixture_parses_strictly_and_re_serializes_to_the_same_json(path: Path) -> None:
    message = _load(path)
    assert SERVER_MESSAGE.dump_python(SERVER_MESSAGE.validate_python(message), mode="json") == message


@pytest.mark.parametrize("path", HTTP_EXCHANGES, ids=lambda path: path.name)
def test_an_http_exchange_fixture_parses_strictly_and_re_serializes_to_the_same_json(path: Path) -> None:
    exchange = _load(path)
    request = exchange["request"]
    response = exchange["response"]
    request_model: dto.WireModel = (
        dto.CreateTableRequest.model_validate(request["body"])
        if request["path"] == "/tables"
        else dto.JoinTableRequest.model_validate(request["body"])
    )
    assert request_model.model_dump(mode="json") == request["body"]

    body = response["body"]
    if "error" in body:
        response_model: dto.WireModel = dto.ErrorBody.model_validate(body)
    elif "join_code" in body:
        response_model = dto.CreateTableResponse.model_validate(body)
    else:
        response_model = dto.JoinTableResponse.model_validate(body)
    assert response_model.model_dump(mode="json") == body


def test_every_server_message_type_has_a_fixture_and_a_model() -> None:
    parsed = [SERVER_MESSAGE.validate_python(_load(path)) for path in SERVER_MESSAGES]
    assert {message.type for message in parsed} == MESSAGE_TYPES


def test_the_wire_schema_names_every_server_message_type() -> None:
    schema = wire_schema()
    definitions: dict[str, Any] = schema["$defs"]  # type: ignore[assignment]
    tagged = {
        definition["properties"]["type"]["const"]
        for definition in definitions.values()
        if "type" in definition.get("properties", {})
    }
    assert tagged == MESSAGE_TYPES
    assert set(schema["discriminator"]["mapping"]) == MESSAGE_TYPES  # type: ignore[index]


@pytest.mark.parametrize(
    ("case", "message"),
    [
        ("unknown type", {"type": "chat", "text": "hi"}),
        ("extra field", {"type": "accepted", "request_id": "a-01", "revision": 3, "extra": 1}),
        ("missing field", {"type": "accepted", "request_id": "a-01"}),
        ("a boolean is not an integer", {"type": "accepted", "request_id": "a-01", "revision": True}),
        ("a float is not an integer", {"type": "accepted", "request_id": "a-01", "revision": 3.0}),
        ("an integer is not a string", {"type": "accepted", "request_id": 1, "revision": 3}),
        ("unknown code", {"type": "error", "request_id": None, "code": "WHAT", "message": "x"}),
        ("a terminal message carries nothing else", {"type": "superseded", "revision": 3}),
    ],
)
def test_a_defective_server_message_is_rejected(case: str, message: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        SERVER_MESSAGE.validate_python(message)


def test_a_wire_model_is_frozen() -> None:
    message = dto.Accepted(type="accepted", request_id="a-01", revision=3)
    with pytest.raises(ValidationError):
        message.revision = 4  # type: ignore[misc]

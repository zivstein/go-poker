"""A server defect in `POST /tables` is the contract's `500 INTERNAL_ERROR`, and the order of checks is pinned.

ADR 0009 §4: every non-2xx response of the two endpoints is the contract's error body, a server defect included
(`500 | INTERNAL_ERROR | null`), and every response carries `Cache-Control: no-store`. A defect must still reach
the server's log, so the handler answers the client without swallowing the exception.
"""

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from go_poker.server import decode
from go_poker.server.directory import JoinCodeUnavailableError

INTERNAL_ERROR = {"error": {"code": "INTERNAL_ERROR", "message": "The server hit a defect", "field": None}}


def _always(value: str) -> Callable[[], str]:
    return lambda: value


def _raises_after(count: int, value: str) -> Callable[[], str]:
    """A generator that hands out `count` values and then fails, as a broken one might."""
    calls = iter(range(count + 1))

    def next_value() -> str:
        if next(calls) == count:
            raise RuntimeError("an injected generator defect")
        return value

    return next_value


def test_a_join_code_collision_at_create_is_the_contracts_internal_error(make_app: Callable[..., Any]) -> None:
    harness = make_app(new_join_code=_always("K7Q2XM"))
    # The defect re-raises after its response is sent (that is what keeps it in the server's log), so this client
    # must not re-raise it, or the test could not read the response.
    with TestClient(harness.app, raise_server_exceptions=False) as client:
        assert client.post("/tables", json={"display_name": "Alice"}).status_code == 201

        response = client.post("/tables", json={"display_name": "Bob"})

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == INTERNAL_ERROR
    assert len(harness.directory.table_ids) == 1


def test_a_credential_generator_defect_at_create_adds_no_table(make_app: Callable[..., Any]) -> None:
    harness = make_app(new_credential=_raises_after(1, "a-credential"))
    # As above: the client must not re-raise the defect to let the test read the response.
    with TestClient(harness.app, raise_server_exceptions=False) as client:
        assert client.post("/tables", json={"display_name": "Alice"}).status_code == 201

        response = client.post("/tables", json={"display_name": "Bob"})

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == INTERNAL_ERROR
    assert len(harness.directory.table_ids) == 1, "a failed create stores nothing"


def test_the_defect_is_not_swallowed(make_app: Callable[..., Any]) -> None:
    """With the default client, the original exception still propagates out of the application."""
    harness = make_app(new_join_code=_always("K7Q2XM"))
    with TestClient(harness.app) as client:
        client.post("/tables", json={"display_name": "Alice"})

        with pytest.raises(JoinCodeUnavailableError):
            client.post("/tables", json={"display_name": "Bob"})


def test_an_invalid_display_name_is_answered_before_the_code_lookup(make_app: Callable[..., Any]) -> None:
    """ADR 0009 §4: an invalid display name is a body-validation failure, which comes before the code lookup."""
    harness = make_app()
    with TestClient(harness.app) as client:
        response = client.post("/tables/by-code/ZZZZZZ/members", json={"display_name": "   ", "seat": 2})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    assert response.json()["error"]["field"] == "display_name"


def test_a_defect_in_the_join_endpoint_is_the_contracts_internal_error(
    make_app: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second endpoint too: a defect outside `TableRuntime.join` reaches the app-wide handler, and the body
    never carries the exception's own text."""
    harness = make_app(new_join_code=_always("K7Q2XM"))

    def defect(*arguments: object, **keywords: object) -> None:
        raise RuntimeError("SECRET-internal-detail")

    with TestClient(harness.app, raise_server_exceptions=False) as client:
        created = client.post("/tables", json={"display_name": "Alice"})
        assert created.status_code == 201
        runtime = harness.directory.get(created.json()["table_id"])
        assert runtime is not None
        revision = runtime.revision
        monkeypatch.setattr(harness.directory, "by_code", defect)

        response = client.post("/tables/by-code/K7Q2XM/members", json={"display_name": "Bob", "seat": 2})

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/json"
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == INTERNAL_ERROR
    assert "SECRET" not in response.text
    assert runtime.revision == revision, "the failed join seated nobody"


def test_a_defect_escaping_the_websocket_is_not_turned_into_an_http_answer(
    make_app: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The `Exception` handler is app-wide, but Starlette's ServerErrorMiddleware handles only `http` scopes.

    A defect escaping the WebSocket endpoint still propagates as itself, the connection receives no error frame
    first, and another connection of the same table keeps working.
    """
    harness = make_app(new_join_code=_always("K7Q2XM"))

    def defect(*arguments: object, **keywords: object) -> None:
        raise RuntimeError("an injected decoder defect")

    with TestClient(harness.app, raise_server_exceptions=False) as client:
        created = client.post("/tables", json={"display_name": "Alice"}).json()
        hello = {"type": "hello", "protocol": "go-poker.v1", "credential": created["credential"]}
        path = f"/ws/tables/{created['table_id']}"

        with pytest.raises(RuntimeError, match="an injected decoder defect"):
            with client.websocket_connect(path) as broken:
                broken.send_json(hello)
                assert broken.receive_json()["cause"] == "connected"
                with monkeypatch.context() as patch:
                    patch.setattr(decode, "decode_command", defect)
                    broken.send_json({"type": "command"})
                    broken.receive_json()

        with client.websocket_connect(path) as healthy:
            healthy.send_json(hello)
            assert healthy.receive_json()["cause"] == "connected"
            healthy.send_json(
                {"type": "command", "request_id": "a-01", "expected_revision": 1, "name": "sit_out", "args": {}}
            )
            assert [healthy.receive_json()["type"] for _ in range(2)] == ["snapshot", "accepted"]

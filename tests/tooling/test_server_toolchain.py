"""The development environment installs the server stack that C6.4 builds on (C6.3 plan D2 and D5).

A throwaway app inside each test exercises the locked FastAPI, Starlette test client and uvicorn transport. No
production server code exists yet; the Backend Cycle adds it under `src/go_poker/server/`.
"""

import pytest
import uvicorn
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


def throwaway_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/echo")
    async def echo(websocket: WebSocket) -> None:
        await websocket.accept()
        await websocket.send_text(await websocket.receive_text())
        await websocket.close(code=4400)

    return app


def test_the_test_client_drives_http_and_websockets_with_application_close_codes() -> None:
    with TestClient(throwaway_app()) as client:
        assert client.get("/health").json() == {"status": "ok"}
        with client.websocket_connect("/echo") as websocket:
            websocket.send_text("ping")
            assert websocket.receive_text() == "ping"
            with pytest.raises(WebSocketDisconnect) as closed:
                websocket.receive_text()

    assert closed.value.code == 4400


def test_uvicorn_accepts_the_dev_command_websocket_transport_options() -> None:
    # The options of the C6.3 plan D5 dev command: --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20
    # --ws-max-size 16384. Loading the configuration imports the chosen websockets implementation.
    config = uvicorn.Config(
        throwaway_app(), ws="websockets", ws_ping_interval=20, ws_ping_timeout=20, ws_max_size=16384
    )

    config.load()

    assert config.ws_protocol_class is not None
    assert config.ws_protocol_class.__module__ == "uvicorn.protocols.websockets.websockets_impl"

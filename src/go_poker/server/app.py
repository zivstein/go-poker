"""The application factory (C6.4 Brief §2.1).

    uv run uvicorn go_poker.server.app:create_app --factory --host 127.0.0.1 --port 8000 \
        --ws websockets --ws-ping-interval 20 --ws-ping-timeout 20 --ws-max-size 16384

The WebSocket options are set explicitly because they are *transport* behavior: ping, pong and uvicorn's own frame
limit are not run by FastAPI's `TestClient`, so the application's own 16 KiB limit (`ws.py`) is what the tests check,
and ping is verified by hand in the demonstration. See `README.md`.

The factory builds one `TableDirectory` for the process and puts it, with the configuration, on `app.state`.
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from go_poker.server import http, ws
from go_poker.server.config import ServerConfig
from go_poker.server.directory import TableDirectory

WEBSOCKET_PATH = "/ws/tables/{table_id}"


def create_app(config: ServerConfig | None = None) -> FastAPI:
    """The FastAPI application: the HTTP endpoints, the WebSocket route, and one in-memory table directory.

    `config` defaults to `ServerConfig()`, whose every field is the production behavior.
    """
    settings = config if config is not None else ServerConfig()
    app = FastAPI(title="Go! Poker", version="go-poker.v1")
    app.state.config = settings
    app.state.directory = TableDirectory(settings)

    app.include_router(http.router)
    app.add_api_websocket_route(WEBSOCKET_PATH, ws.table_socket)
    app.add_exception_handler(RequestValidationError, http.handle_validation_error)
    app.add_exception_handler(http.ApiError, http.handle_api_error)
    # A handler for `Exception` runs in Starlette's ServerErrorMiddleware, outside `no_store` below, so it sets the
    # `Cache-Control` header itself.
    app.add_exception_handler(Exception, http.handle_server_defect)

    @app.middleware("http")
    async def no_store(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        """Every HTTP response carries `Cache-Control: no-store` (ADR 0009 §4), `/health` included."""
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    return app

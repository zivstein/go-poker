"""The WebSocket endpoint: the handshake, the inbound limit, and phase 2 (ADR 0009 §5, §8, §12; ADR 0008 §4, §5).

The upgrade is accepted for any `table_id`; authorization happens only in `hello`, so a browser never learns which
table ids exist.

**Phase 2 lives here and nowhere else.** Per connection there are exactly two tasks: a reader that decodes frames and
hands commands to `TableRuntime.execute` (phase 1, synchronous), and a writer that drains that connection's outbox.
The reader never sends a message: every message a client receives after the handshake is queued on the outbox, so
one writer keeps the per-connection order the contract requires. The reader's one direct action on the socket is the
`1009` close of an oversized frame, which carries no message. The handshake's own errors are sent directly, because
no connection exists yet.

**The inbound limit is the application's** (ADR 0009 §5): the UTF-8 byte length of every received text frame, the
first one included, is checked before it is decoded, and an oversized frame closes `1009` with no error message,
because §12 gives `1009` no code. Ping, pong and a transport's own frame limit are uvicorn settings of the dev
command, which `TestClient` does not run (see README.md).
"""

import asyncio
import contextlib

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect

from go_poker.server import decode, dto
from go_poker.server.config import ServerConfig
from go_poker.server.directory import TableDirectory
from go_poker.server.runtime import CLOSE_OUTBOX_OVERFLOW, Connection, Frame, TableRuntime

# The close codes the handshake and the frame limit decide (ADR 0009 §12).
CLOSE_HANDSHAKE_FAILED = 4400
CLOSE_AUTH_FAILED = 4401
CLOSE_HELLO_TIMEOUT = 4408
CLOSE_FRAME_TOO_BIG = 1009

AUTH_FAILED_MESSAGE = "The credential is not valid for this table"


def _error(request_id: str | None, code: dto.ErrorCode, message: str) -> dto.ErrorMessage:
    return dto.ErrorMessage(type="error", request_id=request_id, code=code, message=message)


def _is_too_large(text: str, config: ServerConfig) -> bool:
    """Whether a text frame is over the inbound limit, measured in UTF-8 bytes (ADR 0009 §5)."""
    return len(text.encode("utf-8")) > config.max_inbound_frame_bytes


async def _fail_handshake(websocket: WebSocket, code: dto.ErrorCode, message: str, close_code: int) -> None:
    """Send one handshake error and close. Nothing is registered, so nothing else can be queued for this socket."""
    await websocket.send_text(_error(None, code, message).model_dump_json())
    await websocket.close(close_code)


async def _handshake(
    websocket: WebSocket, directory: TableDirectory, config: ServerConfig, table_id: str
) -> tuple[TableRuntime, Connection] | None:
    """Run the `hello` exchange. Returns the registered connection, or None when the socket was closed.

    The checks are in the contract's order (ADR 0009 §5): a well-formed `hello`, then the protocol, then the
    credential. An unknown table and a foreign, revoked or unknown credential are not distinguished, which is also
    what a failed table answers, because it has left the directory.
    """
    try:
        message = await asyncio.wait_for(websocket.receive(), config.hello_timeout_seconds)
    except TimeoutError:
        await _fail_handshake(
            websocket,
            "HELLO_TIMEOUT",
            f"No hello within {config.hello_timeout_seconds} seconds",
            CLOSE_HELLO_TIMEOUT,
        )
        return None
    if message["type"] == "websocket.disconnect":
        return None

    text = message.get("text")
    if text is None:  # A binary frame is not a well-formed hello.
        await _fail_handshake(
            websocket, "HELLO_REQUIRED", "The first frame must be a text hello", CLOSE_HANDSHAKE_FAILED
        )
        return None
    if _is_too_large(text, config):
        await websocket.close(CLOSE_FRAME_TOO_BIG)
        return None

    match decode.decode_hello(text):
        case decode.HelloRequired(message=problem):
            await _fail_handshake(websocket, "HELLO_REQUIRED", problem, CLOSE_HANDSHAKE_FAILED)
            return None
        case decode.ProtocolMismatch(message=problem):
            await _fail_handshake(websocket, "PROTOCOL_MISMATCH", problem, CLOSE_HANDSHAKE_FAILED)
            return None
        case decode.Hello(credential=credential):
            runtime = directory.get(table_id)
            user_id = None if runtime is None else runtime.authenticate(credential)
            if runtime is None or user_id is None:
                await _fail_handshake(websocket, "AUTH_FAILED", AUTH_FAILED_MESSAGE, CLOSE_AUTH_FAILED)
                return None
            connection = runtime.new_connection(credential, user_id)
            runtime.connect(connection)
            return runtime, connection


async def _write(websocket: WebSocket, connection: Connection) -> None:
    """The one writer of one connection: drain its outbox in order, and close on a terminal frame or an overflow.

    The event is cleared before draining, so a put that races the clear is either taken by this drain or sets the
    event again for the next round.
    """
    while True:
        await connection.ready.wait()
        connection.ready.clear()
        for frame in connection.outbox.drain():
            await websocket.send_text(frame.message.model_dump_json())
            if frame.close_code is not None:
                await websocket.close(frame.close_code)
                return
        if connection.outbox.overflowed:
            await websocket.close(CLOSE_OUTBOX_OVERFLOW)
            return


async def _read(websocket: WebSocket, runtime: TableRuntime, connection: Connection, config: ServerConfig) -> None:
    """Read this connection's frames and execute at most one command per frame (ADR 0009 §8.1).

    A stopped connection is read no further and executes nothing: that is what makes a frame already in transit when
    a supersede happened never execute.
    """
    while True:
        try:
            message = await websocket.receive()
        except WebSocketDisconnect:
            return
        if message["type"] == "websocket.disconnect":
            return
        if connection.stopped:
            return

        text = message.get("text")
        if text is None:
            connection.deliver(Frame(_error(None, "MALFORMED_MESSAGE", "A binary frame is not a message")))
            continue
        if _is_too_large(text, config):
            # Nothing is executed, and no error message: close code 1009 carries no code (ADR 0009 §12). The outbox
            # is not used, so this close cannot cross a queued frame of the writer.
            connection.stopped = True
            await websocket.close(CLOSE_FRAME_TOO_BIG)
            return

        match decode.decode_command(text):
            case decode.Malformed(message=problem):
                connection.deliver(Frame(_error(None, "MALFORMED_MESSAGE", problem)))
            case decode.InvalidCommand(request_id=request_id, message=problem):
                # This is that command's one outcome (ADR 0009 §8.3), so it carries the request_id.
                connection.deliver(Frame(_error(request_id, "INVALID_COMMAND", problem)))
            case command:
                runtime.execute(command, connection)


async def table_socket(websocket: WebSocket, table_id: str) -> None:
    """One client connection of one table: the handshake, then the reader and the writer until either ends."""
    config = websocket.app.state.config
    directory = websocket.app.state.directory
    assert isinstance(config, ServerConfig)
    assert isinstance(directory, TableDirectory)

    await websocket.accept()
    registered = await _handshake(websocket, directory, config, table_id)
    if registered is None:
        return
    runtime, connection = registered
    try:
        tasks = {
            asyncio.create_task(_read(websocket, runtime, connection, config)),
            asyncio.create_task(_write(websocket, connection)),
        }
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for task in done:
            task.result()  # surface a defect instead of swallowing it
    finally:
        runtime.disconnect(connection)

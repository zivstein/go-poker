"""A minimal local development bot for Go! Poker. A developer tool, not a product feature.

It plays one seat at a table of a locally running server, over the same public `go-poker.v1` surface as the Web client
(ADR 0009): HTTP join, then one WebSocket. It imports no poker code and decides nothing about rules. It acts only when
the server hands it a legal action, in this order of preference:

- betting: Check, otherwise Call, otherwise Fold. It never bets or raises;
- showdown: Show, otherwise Muck.

Usage, from the repository root (the server must already be running, see `src/go_poker/server/README.md`):

    uv run scripts/dev_bot.py join CODE                 # join table CODE at the first free seat and play until Ctrl+C
    uv run scripts/dev_bot.py join CODE --name "Bot 2" --seat 3 --base-url http://127.0.0.1:8000
    uv run scripts/dev_bot.py smoke                     # two bots play three hands on a throwaway local server

Typical session: start the server, open the Web client, create a table, run `join` with the table's code, then Start
game in the Web client. A joined bot is never the host, so the human starts the game. (`smoke` creates its own table
and has its host bot start the game.)

Delivery rules the bot keeps (ADR 0009 §8):

- every command carries a fresh `request_id` and `expected_revision`, the revision of the newest snapshot applied;
- one command is in flight at a time, and the bot decides again only on a snapshot newer than the last command it sent;
- a command that was not answered, because the connection dropped or 10 s passed, has an uncertain outcome. It is never
  sent again. The bot reconnects and decides afresh from the `connected` snapshot, with a new `request_id`. That is not
  a retry: a shared command always advances the revision, so a snapshot that still shows the same revision proves the
  earlier command had no effect, and any other revision proves it was superseded by newer state.

Stopping (Ctrl+C or SIGTERM) first asks the server to Leave, so the seat is released instead of stalling the table:

- the Leave goes out only when no other command is in flight, as a new command with its own `request_id` and the
  current revision, and never twice for one revision. The whole attempt is bounded by 3 s;
- during a hand the server holds the Leave as pending, folds for the bot when its turn comes and removes it at the
  end of the hand, so the bot may exit as soon as the Leave is accepted;
- a bot that has no connection when stopped, because it is connecting or waiting to reconnect, exits at once without
  sending anything. A Leave is never sent because a connection dropped;
- a second Ctrl+C abandons the attempt. SIGKILL or a crash cannot run any of this, so the seat then stays occupied.

The bot reads only the actions the server offers it (`legal_actions`, `showdown_actions`), the seat occupancy of the
public view and its own `is_host` flag. It never looks at any hole card, its own or an opponent's. Its credential is
kept in memory and never printed. An HTTP join has no idempotency key, so a join whose response was lost is reported
and not repeated.
"""

import argparse
import asyncio
import json
import random
import signal
import sys
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, WebSocketException

PROTOCOL = "go-poker.v1"
DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_NAME = "Dev Bot"
MAX_SEAT = 9  # the product range of ADR 0009 §4; a table's `max_seats` may be lower
JOIN_CODE_ALPHABET = frozenset("23456789ABCDEFGHJKMNPQRSTUVWXYZ")
HTTP_TIMEOUT_SECONDS = 10.0
OUTCOME_TIMEOUT_SECONDS = 10.0  # ADR 0009 §8: a command's own timeout is client behavior; C6.2 provisionally says 10 s
SHUTDOWN_DEADLINE_SECONDS = (
    3.0  # the whole graceful leave: wait for a pending outcome, send Leave, wait for its outcome
)
CLOSE_TIMEOUT_SECONDS = 2.0  # the WebSocket closing handshake, so a dead server cannot hold the exit
BACKOFF_INITIAL_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 8.0
# Close codes after which reconnecting cannot help (ADR 0009 §12); every other close is reconnected.
TERMINAL_CLOSE_CODES = {
    4400: "protocol failure",
    4401: "authentication failed (the table or this membership is gone)",
    4409: "superseded by another connection",
    4410: "left the table",
    4500: "the table failed",
}
HELLO_ERROR_CODES = frozenset({"HELLO_REQUIRED", "PROTOCOL_MISMATCH", "AUTH_FAILED", "HELLO_TIMEOUT"})

type Log = Callable[[str], None]
type Command = tuple[str, dict[str, Any]]


class ProtocolError(Exception):
    """The server sent something `go-poker.v1` does not allow, or reported a failure the bot cannot continue after."""


class JoinError(Exception):
    """The HTTP join (or create) did not produce a membership."""


# --- Decisions ------------------------------------------------------------------------------------------------------


def choose_command(view: Mapping[str, Any]) -> Command | None:
    """The command the bot wants in this view, or None when it has nothing to do.

    The only inputs are the actions the server offers this member: `hand.showdown_actions` (set only for the current
    showdown decider) and `hand.legal_actions` (set only for the member who must bet now). Nothing else of the view,
    and no card, takes part.
    """
    hand = view.get("hand")
    if not isinstance(hand, Mapping):
        return None
    showdown = hand.get("showdown_actions")
    if isinstance(showdown, list):
        for decision in ("show", "muck"):
            if decision in showdown:
                return "showdown_decision", {"decision": decision}
        return None
    legal = hand.get("legal_actions")
    if isinstance(legal, Mapping):
        for action in ("check", "call", "fold"):
            if legal.get(f"can_{action}") is True:
                return "act", {"action": action, "target": None}
    return None


def wants_to_start_game(view: Mapping[str, Any]) -> bool:
    """True for the host of a table that has not started, once at least two seats are occupied."""
    you = view.get("you")
    seats = view.get("seats")
    if view.get("phase") != "not_started" or not isinstance(you, Mapping) or not isinstance(seats, list):
        return False
    occupied = sum(1 for seat in seats if isinstance(seat, Mapping) and seat.get("occupant") is not None)
    return you.get("is_host") is True and occupied >= 2


# --- The protocol state machine (no I/O) ----------------------------------------------------------------------------


@dataclass(frozen=True)
class _InFlight:
    request_id: str
    name: str
    expected_revision: int


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Brain:
    """One bot's protocol state, without any I/O: server frames in, at most one command frame out.

    `receive` takes a raw server text frame and returns the command frame to send in answer, or None. The runner owns
    the socket, so everything here is testable with plain values.
    """

    def __init__(
        self,
        *,
        start_game: bool = False,
        new_request_id: Callable[[], str] = lambda: uuid.uuid4().hex,
        log: Log = lambda message: None,
        on_settled: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self._start_game = start_game
        self._new_request_id = new_request_id
        self._log = log
        self._on_settled = on_settled
        self.view: Mapping[str, Any] | None = None
        self.revision: int | None = None
        self.terminal: str | None = None
        self.settled_hands = 0
        self.problems: list[str] = []  # every rejection and error outcome, as "CODE" strings, for inspection
        self._in_flight: _InFlight | None = None
        self._last_sent_revision: int | None = None
        self._was_settled: bool | None = None
        self._leaving = False
        self._last_leave_revision: int | None = None
        # How a requested Leave ended: "left" (accepted, or the server removed the member), "already" (a leave was
        # already pending or the member was already gone), "refused: CODE", or None while it is unanswered.
        self.leave_result: str | None = None

    @property
    def in_flight(self) -> bool:
        return self._in_flight is not None

    def start_connection(self) -> None:
        """A new WebSocket connection begins: nothing from the old one carries over except what it already counted.

        A command still unanswered is uncertain. It is dropped, never sent again; the next decision comes from the
        `connected` snapshot of the new connection.
        """
        if self._in_flight is not None:
            self._log(
                f"outcome of {self._in_flight.name} (request {self._in_flight.request_id}) is uncertain; "
                "it will not be sent again"
            )
        self.view = None
        self.revision = None
        self._in_flight = None
        self._last_sent_revision = None
        self._was_settled = None

    def begin_shutdown(self) -> str | None:
        """The user asked the bot to stop: from now on its only command is one Leave.

        Returns the Leave frame when it can go out at once. Otherwise it goes out from `receive`: after the outcome of a
        command still in flight, or after the first snapshot when none has arrived yet. It is never sent while another
        command is in flight, and at most once per revision.
        """
        self._leaving = True
        return self._next_command()

    def receive(self, raw: str) -> str | None:
        """Apply one server frame. Returns the command frame (JSON text) to send next, or None."""
        try:
            message = json.loads(raw)
        except ValueError as error:
            raise ProtocolError(f"the server sent a frame that is not JSON: {error}") from error
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            raise ProtocolError("the server sent a frame that is not a typed JSON object")
        kind = message["type"]
        if kind == "snapshot":
            self._apply_snapshot(message)
        elif kind in ("accepted", "rejected", "error"):
            self._apply_outcome(kind, message)
        elif kind in ("superseded", "left_table", "table_failed"):
            self.terminal = kind.replace("_", " ")
            if kind == "left_table" and self._leaving:
                self.leave_result = "left"
            self._log(f"the server ended this connection: {self.terminal}")
        else:
            raise ProtocolError(f"the server sent an unknown message type {kind!r}")
        return self._next_command()

    # -- applying frames --

    def _apply_snapshot(self, message: Mapping[str, Any]) -> None:
        revision = message.get("revision")
        view = message.get("view")
        if not _is_int(revision) or revision < 1 or not isinstance(view, dict):
            raise ProtocolError("the server sent a malformed snapshot")
        if self.revision is not None and revision < self.revision:
            return  # an older snapshot is ignored (ADR 0009 §9.3)
        self.revision = revision
        self.view = view
        hand = view.get("hand")
        settled = isinstance(hand, Mapping) and hand.get("settlement") is not None
        if self._was_settled is False and settled:
            self.settled_hands += 1
            self._log(f"hand {hand.get('number') if isinstance(hand, Mapping) else '?'} settled")
            if self._on_settled is not None:
                self._on_settled(view)
        self._was_settled = settled

    def _apply_outcome(self, kind: str, message: Mapping[str, Any]) -> None:
        request_id = message.get("request_id")
        code = message.get("code")
        if kind == "error" and request_id is None:
            # A protocol failure of the connection (a hello error, or a frame the bot should never have sent).
            self.terminal = f"server error {code}"
            self._log(f"server error {code}: {message.get('message')}")
            return
        pending = self._in_flight
        if pending is None or request_id != pending.request_id:
            self._log(f"ignoring an outcome for an unknown request {request_id!r}")
            return
        self._in_flight = None
        if kind == "accepted":
            self._log(f"accepted {pending.name} (request {request_id}, revision {message.get('revision')})")
            if pending.name == "leave":
                self.leave_result = "left"
            return
        self._log(f"{kind} {pending.name} (request {request_id}): {code}: {message.get('message')}")
        if pending.name == "leave" and code in ("NO_CHANGE", "NOT_A_MEMBER"):
            self.leave_result = "already"  # a leave was already pending, or the member is already gone
            return
        if pending.name == "leave" and code == "STALE_REVISION":
            return  # nothing was applied; the next snapshot lets a new Leave go out
        if pending.name == "leave":
            self.leave_result = f"refused: {code}"
        self.problems.append(str(code))

    # -- deciding --

    def _next_command(self) -> str | None:
        if self.terminal is not None or self._in_flight is not None or self.view is None or self.revision is None:
            return None
        if self._leaving:
            # The only command of a stopping bot, at most once per revision. After a stale rejection, which proved that
            # nothing was applied, newer state lets it go out again as a new command; any other outcome ends it.
            if self.leave_result is not None or (
                self._last_leave_revision is not None and self.revision <= self._last_leave_revision
            ):
                return None
            decision: Command | None = ("leave", {})
            self._last_leave_revision = self.revision
        else:
            # One command per revision: after a rejection nothing is sent until newer state arrives.
            if self._last_sent_revision is not None and self.revision <= self._last_sent_revision:
                return None
            decision = choose_command(self.view)
        if decision is None and self._start_game and wants_to_start_game(self.view):
            decision = ("start_game", {})
        if decision is None:
            return None
        name, args = decision
        request_id = self._new_request_id()
        self._in_flight = _InFlight(request_id, name, self.revision)
        self._last_sent_revision = self.revision
        choice = args.get("action") or args.get("decision")
        label = f"{name} {choice}" if choice else name
        self._log(f"sending {label} (request {request_id}, expected revision {self.revision})")
        return json.dumps(
            {
                "type": "command",
                "request_id": request_id,
                "expected_revision": self.revision,
                "name": name,
                "args": args,
            }
        )


# --- HTTP: create and join ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Membership:
    """What a create or a join returns. The credential is a bearer secret: it has no repr and is never logged."""

    table_id: str
    seat: int
    credential: str = field(repr=False)
    join_code: str | None = None
    display_name: str = ""


def _post_json(url: str, body: Mapping[str, Any]) -> tuple[int, Any]:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.load(error)
        except ValueError:
            return error.code, None
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        if isinstance(getattr(error, "reason", None), ConnectionRefusedError):
            # Nothing was listening, so nothing was sent: the request definitely had no effect.
            raise JoinError(f"nothing is listening at {url}: start the server first (see README)") from error
        raise JoinError(
            f"could not reach {url}: {error}. The request is not repeated: its outcome is unknown"
        ) from error


def _error_code(payload: Any) -> str:
    error = payload.get("error") if isinstance(payload, dict) else None
    return str(error.get("code")) if isinstance(error, dict) else "UNKNOWN"


def valid_join_code(code: str) -> bool:
    return len(code) == 6 and all(character in JOIN_CODE_ALPHABET for character in code)


def _membership(payload: Any, *, display_name: str, join_code: str | None) -> Membership:
    if not isinstance(payload, dict) or not isinstance(payload.get("table_id"), str):
        raise JoinError("the server's answer is not a membership")
    seat, credential = payload.get("seat"), payload.get("credential")
    if not _is_int(seat) or not isinstance(credential, str):
        raise JoinError("the server's answer is not a membership")
    return Membership(payload["table_id"], seat, credential, payload.get("join_code", join_code), display_name)


def create_table(base_url: str, display_name: str) -> Membership:
    """Create a table and sit as its host (used by the smoke test; the bot's own entry point is `join_table`)."""
    status, payload = _post_json(f"{base_url}/tables", {"display_name": display_name})
    if status != 201:
        raise JoinError(f"creating a table failed: {status} {_error_code(payload)}")
    return _membership(payload, display_name=display_name, join_code=None)


def join_table(base_url: str, join_code: str, display_name: str, seat: int | None, log: Log) -> Membership:
    """Join the table with this code. Without `seat`, take the lowest free seat.

    A failed request stores nothing (ADR 0009 §4), so after a definite `SEAT_TAKEN` the next seat is a fresh request.
    A request whose outcome is unknown is never repeated.
    """
    code = join_code.strip().upper()
    if not valid_join_code(code):
        raise JoinError(f"{join_code!r} is not a join code (six characters from {''.join(sorted(JOIN_CODE_ALPHABET))})")
    candidates = [seat] if seat is not None else list(range(1, MAX_SEAT + 1))
    for candidate in candidates:
        status, payload = _post_json(
            f"{base_url}/tables/by-code/{quote(code)}/members", {"display_name": display_name, "seat": candidate}
        )
        if status == 201:
            return _membership(payload, display_name=display_name, join_code=code)
        reason = _error_code(payload)
        if seat is None and reason == "SEAT_TAKEN":
            log(f"seat {candidate} is taken")
            continue
        if seat is None and reason == "INVALID_SEAT":
            break  # every seat the table has is taken
        raise JoinError(
            f"joining failed: {status} {reason}"
            + (" (choose another --name)" if reason == "DISPLAY_NAME_TAKEN" else "")
        )
    raise JoinError("joining failed: no free seat")


# --- The connection loop --------------------------------------------------------------------------------------------


def websocket_url(base_url: str, table_id: str) -> str:
    parts = urlsplit(base_url)
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, f"/ws/tables/{quote(table_id)}", "", ""))


def backoff_delay(attempt: int, rng: Callable[[], float] = random.random) -> float:
    """Exponential backoff with equal jitter, as the Web client does: 0.5 s rising to an 8 s cap."""
    base = min(BACKOFF_INITIAL_SECONDS * 2**attempt, BACKOFF_CAP_SECONDS)
    return base / 2 + rng() * base / 2


async def _until_stop[T](awaitable: Awaitable[T], stop: asyncio.Event | None) -> tuple[T | None, bool]:
    """Await `awaitable` unless `stop` is set first. Returns `(value, False)`, or `(None, True)` after cancelling it."""
    if stop is None:
        return await awaitable, False
    work = asyncio.ensure_future(awaitable)
    waiter = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait({work, waiter}, return_when=asyncio.FIRST_COMPLETED)
        if work.done():
            return work.result(), False
        return None, True
    finally:
        waiter.cancel()
        if not work.done():
            work.cancel()
            await asyncio.gather(work, waiter, return_exceptions=True)


async def _leave_and_wait(socket: Any, brain: Brain, log: Log, deadline: float) -> None:
    """Best-effort graceful leave on the live connection, within `deadline` seconds in all.

    Sends Leave once the bot has no command in flight (waiting for that command's outcome first), then waits for the
    Leave's outcome. Nothing is sent again after a lost connection, a protocol failure or the deadline: the Leave's
    outcome is then simply unknown. A Leave that is accepted while the bot's hand is running is pending on the server,
    which folds for the bot and removes it at the hand boundary, so the bot need not stay connected for that.
    """
    log("stopping: leaving the table")
    try:
        async with asyncio.timeout(deadline):
            frame = brain.begin_shutdown()
            while True:
                if frame is not None:
                    await socket.send(frame)
                if brain.leave_result is not None or brain.terminal is not None:
                    break
                raw = await socket.recv()
                if not isinstance(raw, str):
                    raise ProtocolError("the server sent a binary frame")
                frame = brain.receive(raw)
    except TimeoutError:
        log(f"no answer within {deadline:g} s: the leave may or may not have been applied, and is not sent again")
        return
    except ConnectionClosed:
        log("connection lost before the leave was answered: it may or may not have been applied, and is not sent again")
        return
    except ProtocolError as error:
        log(f"stopping without a confirmed leave: {error}")
        return
    result = brain.leave_result
    if result == "left":
        log("left the table; the seat is released (or will be at the end of the current hand)")
    elif result == "already":
        log("the bot was already leaving the table")
    elif result is not None:
        log(f"the server refused the leave ({result}); the seat may stay occupied")
    else:
        log(f"the server ended the connection ({brain.terminal}) before the leave was answered")


async def run_bot(
    membership: Membership,
    base_url: str,
    brain: Brain,
    log: Log,
    *,
    outcome_timeout: float = OUTCOME_TIMEOUT_SECONDS,
    sleep: Callable[[float], Any] = asyncio.sleep,
    stop: asyncio.Event | None = None,
    shutdown_deadline: float = SHUTDOWN_DEADLINE_SECONDS,
) -> int:
    """Play until the server ends the membership (exit code 1), `stop` is set (exit code 0) or the task is cancelled.

    A lost connection is reconnected with backoff. A terminal close code or a protocol failure ends the run.

    When `stop` is set on a live connection the bot tries to leave the table first (`_leave_and_wait`), within
    `shutdown_deadline` seconds. When it is set while there is no connection (connecting, or waiting to reconnect) the
    bot exits at once and sends nothing. A Leave is sent only because of `stop`, never because a connection was lost.
    """
    url = websocket_url(base_url, membership.table_id)
    hello = json.dumps({"type": "hello", "protocol": PROTOCOL, "credential": membership.credential})
    attempt = 0
    while True:
        if stop is not None and stop.is_set():
            log("stopped: no connection, so there is nothing to leave")
            return 0
        brain.start_connection()
        try:
            socket, stopped = await _until_stop(
                connect(url, open_timeout=HTTP_TIMEOUT_SECONDS, close_timeout=CLOSE_TIMEOUT_SECONDS), stop
            )
            if stopped or socket is None:
                log("stopped: not connected yet, so there is nothing to leave")
                return 0
            try:
                await socket.send(hello)
                while True:
                    timeout = outcome_timeout if brain.in_flight else None
                    try:
                        raw, stopped = await _until_stop(asyncio.wait_for(socket.recv(), timeout), stop)
                    except TimeoutError:
                        log(f"no outcome within {outcome_timeout:g} s; reconnecting")
                        break
                    if stopped:
                        await _leave_and_wait(socket, brain, log, shutdown_deadline)
                        return 0
                    if not isinstance(raw, str):
                        raise ProtocolError("the server sent a binary frame")
                    reply = brain.receive(raw)
                    if brain.revision is not None:
                        attempt = 0
                    if brain.terminal is not None:
                        log(f"stopping: {brain.terminal}")
                        return 1
                    if reply is not None:
                        await socket.send(reply)
            finally:
                await socket.close()
        except ConnectionClosed as closed:
            code = closed.rcvd.code if closed.rcvd is not None else 1006
            if code in TERMINAL_CLOSE_CODES:
                log(f"stopping: {TERMINAL_CLOSE_CODES[code]} (close {code})")
                return 1
            log(f"connection closed ({code}); reconnecting")
        except ProtocolError as error:
            log(f"stopping: {error}")
            return 1
        except (OSError, WebSocketException, TimeoutError) as error:
            log(f"connection failed ({type(error).__name__}: {error}); reconnecting")
        delay = backoff_delay(attempt)
        attempt += 1
        log(f"reconnecting in {delay:.1f} s")
        _, stopped = await _until_stop(sleep(delay), stop)
        if stopped:
            log("stopped: waiting to reconnect, so there is nothing to leave")
            return 0


# --- CLI ------------------------------------------------------------------------------------------------------------


def make_log(label: str) -> Log:
    def log(message: str) -> None:
        print(f"{time.strftime('%H:%M:%S')} [{label}] {message}", flush=True)

    return log


async def run_join(arguments: argparse.Namespace) -> int:
    log = make_log(arguments.name)
    base_url = arguments.base_url.rstrip("/")
    try:
        membership = await asyncio.to_thread(join_table, base_url, arguments.code, arguments.name, arguments.seat, log)
    except JoinError as error:
        log(str(error))
        return 1
    log(f"joined table {membership.table_id} (code {membership.join_code}) at seat {membership.seat}; Ctrl+C stops")
    brain = Brain(log=log)
    stop = asyncio.Event()
    task = asyncio.create_task(run_bot(membership, base_url, brain, log, stop=stop))

    def on_signal() -> None:
        # The first Ctrl+C or SIGTERM asks the bot to leave the table; a second one abandons that and stops at once.
        if stop.is_set():
            task.cancel()
        else:
            stop.set()

    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, on_signal)
    try:
        return await task
    except asyncio.CancelledError:
        log("stopped without leaving the table")
        return 0


@asynccontextmanager
async def local_server(config: Any) -> AsyncIterator[str]:
    """A real server on a free loopback port for the duration of the block; yields its base URL."""
    # Imported here so `join` works from any checkout that has the server running elsewhere.
    import uvicorn

    from go_poker.server.app import create_app

    server = uvicorn.Server(uvicorn.Config(create_app(config), host="127.0.0.1", port=0, log_level="warning"))
    serving = asyncio.create_task(server.serve())
    try:
        while not server.started:
            if serving.done():
                serving.result()
                raise RuntimeError("the local server stopped before it started")
            await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{server.servers[0].sockets[0].getsockname()[1]}"
    finally:
        server.should_exit = True
        await serving


async def run_smoke(hands: int, timeout: float, *, verbose: bool = False) -> int:
    """Two bots play `hands` hands against a real server on a free local port, then the verdict is printed.

    Passes only when every hand settled, no command was rejected, and the chips stayed conserved at every settlement.
    The bots' own log lines are shown only with `verbose`.
    """
    from go_poker.server.config import ServerConfig

    def make_label_log(label: str) -> Log:
        return make_log(label) if verbose else (lambda message: None)

    config = ServerConfig(next_hand_pause_seconds=0.2)
    tasks: list[asyncio.Task[int]] = []
    failures: list[str] = []
    try:
        async with local_server(config) as base_url:

            def conserved(view: Mapping[str, Any]) -> None:
                stacks = [seat["occupant"]["stack"] for seat in view["seats"] if seat["occupant"] is not None]
                if sum(stacks) != len(stacks) * config.buy_in:
                    failures.append(f"chips not conserved after a hand: stacks {stacks}")

            host = await asyncio.to_thread(create_table, base_url, "Smoke Host")
            guest = await asyncio.to_thread(
                join_table, base_url, host.join_code or "", "Smoke Guest", None, make_label_log("guest")
            )
            brains = [
                Brain(start_game=True, log=make_label_log("host"), on_settled=conserved),
                Brain(log=make_label_log("guest")),
            ]
            for membership, brain, label in ((host, brains[0], "host"), (guest, brains[1], "guest")):
                tasks.append(asyncio.create_task(run_bot(membership, base_url, brain, make_label_log(label))))
            try:
                async with asyncio.timeout(timeout):
                    while not (
                        all(brain.settled_hands >= hands for brain in brains) or any(task.done() for task in tasks)
                    ):
                        await asyncio.sleep(0.05)
                for task in tasks:
                    if task.done():
                        failures.append(f"a bot stopped early with exit code {task.result()}")
                for brain in brains:
                    failures.extend(f"a command was refused: {problem}" for problem in brain.problems)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except TimeoutError:
        failures.append(f"fewer than {hands} hands settled within {timeout:g} s")
    except (JoinError, RuntimeError) as error:
        failures.append(str(error))
    if failures:
        print("SMOKE: FAIL\n  " + "\n  ".join(failures))
        return 1
    print(f"SMOKE: PASS ({hands} hands played by two bots)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A local development bot for Go! Poker.")
    commands = parser.add_subparsers(dest="command", required=True)
    join = commands.add_parser("join", help="join a table by its code and play until stopped")
    join.add_argument("code", help="the table's six-character join code")
    join.add_argument(
        "--name", default=DEFAULT_NAME, help=f"display name, unique at the table (default: {DEFAULT_NAME!r})"
    )
    join.add_argument(
        "--seat", type=int, choices=range(1, MAX_SEAT + 1), help="seat to take (default: the lowest free one)"
    )
    join.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"the server (default: {DEFAULT_BASE_URL})")
    smoke = commands.add_parser("smoke", help="two bots play a few hands on a throwaway local server")
    smoke.add_argument("--hands", type=int, default=3, help="hands to play (default: 3)")
    smoke.add_argument("--verbose", action="store_true", help="show every line the bots log")
    smoke.add_argument("--timeout", type=float, default=60.0, help="seconds before the smoke test fails (default: 60)")
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    if arguments.command == "join":
        return asyncio.run(run_join(arguments))
    return asyncio.run(run_smoke(arguments.hands, arguments.timeout, verbose=arguments.verbose))


if __name__ == "__main__":
    sys.exit(main())

"""`TableRuntime`: the single authoritative writer for one table (ADR 0008 §4, ADR 0009 §8, §9; C6.4 Brief §2.4).

**Phase 1 is this module, and it is synchronous.** Every mutation of a table happens in one of its operations
(`connect`, `disconnect`, `execute`, `join`, `fire_next_hand`), each of which runs the `TableSession` call, maps every
captured view, puts the resulting frames on their recipients' outboxes and updates the registry, with **no `await`
anywhere**. No lock is held across a send, and a slow client cannot delay another
(`tests/server/test_runtime_isolation.py` checks the absence of `await` on the source).

**Phase 2 is not here.** The runtime knows outboxes and never a socket: one writer task per connection drains its
outbox and closes it with the frame's close code. That keeps this module transport-free and means its tests need no
double of a transport at all.

Ordering is the contract's (ADR 0009 §8.4): a command's transition snapshots, then a `private` snapshot when there
was no transition, then the outcome, then `left_table` for a member whose departure was applied. A rejection carries
no snapshot and changes nothing.
"""

import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import assert_never

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.results import CommandResult, Rejected, Transition
from go_poker.app.session import TableSession
from go_poker.app.views import TablePhase, TableView
from go_poker.server import decode, dto, mapping
from go_poker.server.config import ServerConfig

# The close codes this runtime decides (ADR 0009 §12). The handshake's codes belong to the WebSocket.
CLOSE_SUPERSEDED = 4409
CLOSE_LEFT_TABLE = 4410
CLOSE_TABLE_FAILED = 4500
CLOSE_OUTBOX_OVERFLOW = 4008


@dataclass(frozen=True)
class Frame:
    """One outgoing frame: the message to send, and the code to close the connection with afterwards.

    A frame with a `close_code` is terminal: the writer sends the message, then closes (ADR 0009 §7).
    """

    message: dto.ServerMessage
    close_code: int | None = None


class Outbox:
    """One connection's bounded FIFO of outgoing frames (ADR 0009 §5).

    A connection that cannot keep up overflows: the queue is dropped, `overflowed` is set, and nothing more is
    queued, because the writer is about to close it with `CLOSE_OUTBOX_OVERFLOW` and the client will get the current
    snapshot when it reconnects. A terminal frame ignores the capacity and never overflows the outbox: it is never
    dropped for capacity, and it does not clear the frames already queued. A frame queued with `put` has no such
    guarantee, so an outcome put on an outbox already at capacity is dropped and only the terminal frame after it
    survives, which ADR 0009 §8.3 permits (an outcome may be undelivered).
    """

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("An outbox needs a capacity of at least one frame")
        self._capacity = capacity
        self._frames: list[Frame] = []
        self._overflowed = False

    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def overflowed(self) -> bool:
        return self._overflowed

    def put(self, frame: Frame) -> None:
        if self._overflowed:
            return
        if len(self._frames) >= self._capacity:
            self._overflowed = True
            self._frames.clear()
            return
        self._frames.append(frame)

    def put_terminal(self, frame: Frame) -> None:
        """Queue a terminal frame, whatever the capacity: a terminal message is never dropped for a slow client."""
        self._frames.append(frame)

    def drain(self) -> list[Frame]:
        """Every queued frame, in order, leaving the outbox empty."""
        frames = list(self._frames)
        self._frames.clear()
        return frames

    def __len__(self) -> int:
        return len(self._frames)


@dataclass(eq=False)
class Connection:
    """One client connection of one table, as phase 1 sees it: an identity, an outbox and a stop flag.

    `stopped` means **no further frame of this connection is read or executed** (ADR 0009 §5, §8.1). It is set when
    the connection is superseded, when any terminal message is queued, and when the transport reports it gone.

    `ready` wakes the writer task. `asyncio.Event.set` is synchronous, so phase 1 may call it. Connections compare by
    identity (`eq=False`), because two connections of one member are different connections.
    """

    credential: str
    user_id: UserId
    outbox: Outbox
    stopped: bool = False
    ready: asyncio.Event = field(default_factory=asyncio.Event)

    def deliver(self, frame: Frame) -> None:
        """Queue a frame, unless this connection is stopped: an outcome that cannot be delivered is dropped."""
        if self.stopped:
            return
        self.outbox.put(frame)
        self.ready.set()

    def deliver_terminal(self, frame: Frame) -> None:
        """Queue a terminal frame and stop the connection, in one step."""
        self.outbox.put_terminal(frame)
        self.stopped = True
        self.ready.set()


@dataclass(frozen=True)
class JoinedMember:
    """What an accepted HTTP join produced: the membership's identity, its bearer credential and its seat."""

    user_id: UserId
    credential: str
    seat: int


class TableRuntime:
    """The one writer of one table. Every operation below is a complete phase-1 step."""

    def __init__(
        self,
        session: TableSession,
        config: ServerConfig,
        credentials: Mapping[str, UserId],
        *,
        table_id: str,
        join_code: str,
        on_failed: Callable[[], None],
    ) -> None:
        """Take over a freshly created session.

        `credentials` are the memberships that already exist, normally just the host's. `table_id` and `join_code` are
        the identifiers the session was created with: the directory generated them and keys this runtime by them.
        `on_failed` is called once if the table hits a defect, so the directory can drop it without this module
        importing the directory.
        """
        views = (session.view_for(user_id) for user_id in credentials.values())
        known = next(view for view in views if view is not None)
        assert (known.table_id, known.code) == (table_id, join_code), (
            "a runtime's identifiers must be the ones its session was created with"
        )
        self._session = session
        self._config = config
        self._table_id = table_id
        self._join_code = join_code
        self._on_failed = on_failed
        self._scheduler = config.new_next_hand_scheduler()
        self._credentials: dict[str, UserId] = dict(credentials)
        self._connections: list[Connection] = []
        self._failed = False

    # --- Reads: none of these changes anything ---

    @property
    def table_id(self) -> str:
        return self._table_id

    @property
    def join_code(self) -> str:
        return self._join_code

    @property
    def revision(self) -> int:
        return self._session.revision

    @property
    def phase(self) -> TablePhase:
        return self._session.phase

    @property
    def failed(self) -> bool:
        return self._failed

    @property
    def connections(self) -> tuple[Connection, ...]:
        """The live connections, in registration order."""
        return tuple(self._connections)

    def view_for(self, user_id: UserId) -> TableView | None:
        return self._session.view_for(user_id)

    def authenticate(self, credential: str) -> UserId | None:
        """The membership a credential bears at this table, or None when it is unknown or revoked (ADR 0009 §5).

        An unknown and a revoked credential are not distinguished.
        """
        return self._credentials.get(credential)

    def new_connection(self, credential: str, user_id: UserId) -> Connection:
        """A connection value with this table's configured outbox size. It is live only once `connect` registers it."""
        return Connection(credential=credential, user_id=user_id, outbox=Outbox(self._config.outbox_size))

    # --- Phase 1 ---

    def connect(self, connection: Connection) -> None:
        """Register an authenticated connection, superseding any live one of the same credential.

        Supersede and the first `connected` snapshot are one step, with nothing in between, so no frame of the
        superseded connection can be executed after it (ADR 0009 §5, Brief §5.4).
        """
        if self._failed:
            return
        try:
            for live in list(self._connections):
                if live.credential == connection.credential:
                    live.deliver_terminal(Frame(dto.Superseded(type="superseded"), CLOSE_SUPERSEDED))
                    self._connections.remove(live)
            self._connections.append(connection)
            view = self._session.view_for(connection.user_id)
            assert view is not None, "an authenticated connection belongs to a member"
            connection.deliver(Frame(mapping.snapshot(view.revision, mapping.CONNECTED, view)))
        except Exception:
            self._fail()

    def disconnect(self, connection: Connection) -> None:
        """The connection is gone. It is stopped and unregistered, so nothing more is sent to or read from it."""
        connection.stopped = True
        if connection in self._connections:
            self._connections.remove(connection)

    def execute(self, command: decode.Command, connection: Connection) -> None:
        """Execute one decoded command of one connection: the table's only state-changing path for a client.

        `expected_revision` passes through to `TableSession` unchanged (Brief §5.6). A frame of a stopped connection
        is never executed, and a failed table executes nothing.
        """
        if self._failed or connection.stopped:
            return
        try:
            connected_members = self._connected_members()
            result = self._apply(command, connection.user_id)
            if isinstance(result, Rejected):
                connection.deliver(Frame(mapping.rejected(command.request_id, result)))
                return
            self._deliver_transitions(result.transitions)
            if not result.transitions and self._session.is_member(connection.user_id):
                private = self._session.view_for(connection.user_id)
                assert private is not None
                connection.deliver(Frame(mapping.snapshot(private.revision, mapping.PRIVATE, private)))
            connection.deliver(Frame(mapping.accepted(command.request_id, result)))
            self._apply_departures(connected_members)
            self._rearm()
        except Exception:
            self._fail()

    def join(self, display_name: DisplayName, seat: int) -> JoinedMember | Rejected | None:
        """The HTTP join's phase-1 step: seat a new member and tell the connected members.

        The current revision goes to `TableSession.join`, so a join is never `STALE_REVISION` (C6.1 E4). A rejected
        join stores nothing: the credential is minted only after it is accepted (Brief §5.7). None means the table
        has failed and no result exists.
        """
        if self._failed:
            return None
        try:
            connected_members = self._connected_members()
            user_id = self._config.new_user_id()
            result = self._session.join(user_id, self._session.revision, display_name, seat)
            if isinstance(result, Rejected):
                return result
            credential = self._config.new_credential()
            self._credentials[credential] = user_id
            self._deliver_transitions(result.transitions)
            self._apply_departures(connected_members)  # a join removes nobody; the step is the same everywhere
            self._rearm()
            return JoinedMember(user_id=user_id, credential=credential, seat=seat)
        except Exception:
            self._fail()
            return None

    def fire_next_hand(self, expected_revision: int) -> None:
        """The next-hand pause elapsed: advance the hand at the revision the timer was armed at (ADR 0005 §10).

        There is no requester and no outcome. A stale timer does nothing at all: `advance_hand` answers
        `STALE_REVISION` or `NOT_AT_HAND_BOUNDARY`, both server-internal, and no message goes anywhere.
        """
        if self._failed:
            return
        try:
            connected_members = self._connected_members()
            result = self._session.advance_hand(expected_revision)
            if isinstance(result, Rejected):
                return
            self._deliver_transitions(result.transitions)
            self._apply_departures(connected_members)
            self._rearm()
        except Exception:
            self._fail()

    # --- Phase-1 steps ---

    def _apply(self, command: decode.Command, user_id: UserId) -> CommandResult:
        """Call the one `TableSession` command this value names. The match is exhaustive over the closed set."""
        session = self._session
        revision = command.expected_revision
        match command:
            case decode.StartGame():
                return session.start_game(user_id, revision)
            case decode.Act(action=action, target=target):
                return session.act(user_id, revision, mapping.betting_action(action, target))
            case decode.ShowdownDecision(decision=decision):
                return session.act(user_id, revision, mapping.showdown_decision(decision))
            case decode.SitOut():
                return session.sit_out(user_id, revision)
            case decode.SitBack():
                return session.sit_back(user_id, revision)
            case decode.Leave():
                return session.leave(user_id, revision)
            case decode.SelectPreAction(kind=kind, amount=amount):
                return session.select_pre_action(user_id, revision, mapping.selected_pre_action(kind, amount))
            case decode.ClearPreAction():
                return session.clear_pre_action(user_id, revision)
            case _:
                assert_never(command)

    def _deliver_transitions(self, transitions: tuple[Transition, ...]) -> None:
        """One snapshot per transition per connected member, each mapped from that transition's captured view.

        A member a transition removed has no view in it and receives nothing for it: `_apply_departures` sends that
        member `left_table` instead (ADR 0009 §8.5).
        """
        for transition in transitions:
            cause = mapping.snapshot_cause(transition.cause)
            for connection in list(self._connections):
                view = transition.views.get(connection.user_id)
                if view is None:
                    continue
                connection.deliver(Frame(mapping.snapshot(transition.revision, cause, view)))

    def _connected_members(self) -> frozenset[UserId]:
        """The users of the live connections that are members right now, read before the session call."""
        return frozenset(
            connection.user_id for connection in self._connections if self._session.is_member(connection.user_id)
        )

    def _apply_departures(self, connected_members: frozenset[UserId]) -> None:
        """Depart every member the operation removed, and revoke their credentials: one atomic step (Brief §5.4).

        A departed member with no connection open is covered too, because revocation is decided by membership, not by
        the connections.
        """
        for connection in list(self._connections):
            if connection.user_id in connected_members and not self._session.is_member(connection.user_id):
                connection.deliver_terminal(Frame(dto.LeftTable(type="left_table"), CLOSE_LEFT_TABLE))
                self._connections.remove(connection)
        for credential, user_id in list(self._credentials.items()):
            if not self._session.is_member(user_id):
                del self._credentials[credential]

    def _rearm(self) -> None:
        """Arm the next-hand call while the hand is complete, capturing the revision it is armed at; else cancel.

        Every transition therefore re-arms, and the captured revision is what makes a stale firing harmless.
        """
        if self._session.phase is TablePhase.HAND_COMPLETE:
            armed_revision = self._session.revision
            self._scheduler.arm(self._config.next_hand_pause_seconds, lambda: self.fire_next_hand(armed_revision))
        else:
            self._scheduler.cancel()

    def _fail(self) -> None:
        """A defect inside a phase-1 operation: this table is gone, and no other table is affected (Brief §2.9).

        Every live connection receives `table_failed` and close `4500`; the credentials and connections are dropped,
        so nothing authenticates and nothing is executed afterwards; `on_failed` lets the directory forget the table
        and its join code. The exception is not re-raised and the operation returns no result.
        """
        if self._failed:
            return
        self._failed = True
        self._scheduler.cancel()
        for connection in list(self._connections):
            connection.deliver_terminal(Frame(dto.TableFailed(type="table_failed"), CLOSE_TABLE_FAILED))
        self._connections.clear()
        self._credentials.clear()
        self._on_failed()

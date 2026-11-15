/**
 * The connection lifecycle of C6.2 plan §2.4: `hello`; the first `connected`
 * snapshot as "live"; command correlation by `request_id`; the
 * uncertain-outcome rule (ADR 0009 §8); reconnect with backoff and jitter;
 * the terminal states keyed by ADR 0009 §12's close codes.
 *
 * This module has no React and no DOM dependency beyond `Transport` itself.
 */

import { decodeServerMessage, ProtocolDecodeError, parseWireJson } from "../protocol/decode";
import { encodeCommand, encodeHello, newRequestId, toWireText } from "../protocol/encode";
import type {
  AcceptedMessage,
  CommandName,
  CommandPayload,
  ErrorMessage,
  RejectedMessage,
  RejectionCode,
  ServerMessage,
  SnapshotCause,
  TableView,
} from "../protocol/types";
import { computeBackoffDelayMs } from "./backoff";
import type { ClosedReason } from "./closeCodes";
import { closeDisposition } from "./closeCodes";
import type { Transport, TransportCloseEvent } from "./Transport";

export interface ConnectionStatus {
  phase: "idle" | "connecting" | "live" | "reconnecting" | "closed";
  /** A command is in flight; its outcome is not yet known, but not uncertain. */
  pending: boolean;
  /** The uncertain-outcome lock (ADR 0009 §8): every action stays disabled
   * until the next `connected` snapshot, across any reconnect. */
  reconciling: boolean;
  /** Meaningful only while `phase === "reconnecting"`. */
  attempt: number;
  /** Meaningful only while `phase === "closed"`. */
  reason: ClosedReason | null;
}

export interface SnapshotEvent {
  revision: number;
  cause: SnapshotCause;
  view: TableView;
}

export type OutcomeEvent =
  | { kind: "accepted"; requestId: string; revision: number }
  | { kind: "rejected"; requestId: string; code: RejectionCode; message: string }
  | { kind: "invalid"; requestId: string; code: "INVALID_COMMAND"; message: string };

export interface ConnectionControllerOptions {
  tableId: string;
  credential: string;
  wsUrlBase?: string;
  requestIdFactory?: () => string;
  commandTimeoutMs?: number;
  random?: () => number;
}

const INITIAL_STATUS: ConnectionStatus = {
  phase: "idle",
  pending: false,
  reconciling: false,
  attempt: 0,
  reason: null,
};

export class ConnectionController {
  private readonly transport: Transport;
  private readonly options: ConnectionControllerOptions;

  private status: ConnectionStatus = INITIAL_STATUS;
  private revision = 0;
  private inFlight: { requestId: string; commandName: CommandName } | null = null;
  private timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  private reconnectHandle: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempt = 0;
  private closedForGood = false;
  private lastCommandName: CommandName | null = null;

  private readonly statusListeners = new Set<(status: ConnectionStatus) => void>();
  private readonly snapshotListeners = new Set<(event: SnapshotEvent) => void>();
  private readonly outcomeListeners = new Set<(event: OutcomeEvent) => void>();

  constructor(transport: Transport, options: ConnectionControllerOptions) {
    this.transport = transport;
    this.options = options;
    transport.onOpen(() => this.handleOpen());
    transport.onMessage((text) => this.handleMessage(text));
    transport.onClose((event) => this.handleClose(event));
  }

  get currentStatus(): ConnectionStatus {
    return this.status;
  }

  get currentRevision(): number {
    return this.revision;
  }

  /** Whether the last command this client sent was `leave` (ADR 0009 §8.4). */
  get wasLeaving(): boolean {
    return this.lastCommandName === "leave";
  }

  onStatusChange(callback: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(callback);
    return () => this.statusListeners.delete(callback);
  }

  onSnapshot(callback: (event: SnapshotEvent) => void): () => void {
    this.snapshotListeners.add(callback);
    return () => this.snapshotListeners.delete(callback);
  }

  onOutcome(callback: (event: OutcomeEvent) => void): () => void {
    this.outcomeListeners.add(callback);
    return () => this.outcomeListeners.delete(callback);
  }

  /** Opens a new connection (the first connect, a reconnect, or "Use here"). */
  connect(): void {
    if (this.closedForGood) return;
    this.setStatus({ ...this.status, phase: "connecting" });
    const base = this.options.wsUrlBase ?? "/ws/tables";
    this.transport.open(`${base}/${this.options.tableId}`);
  }

  /**
   * Sends a new poker command. Returns its `request_id`, or `null` when one
   * command is already in flight, the connection is not live, or actions are
   * disabled by the uncertain-outcome lock.
   */
  sendCommand(payload: CommandPayload): string | null {
    if (this.status.phase !== "live" || this.status.pending || this.status.reconciling) return null;
    const requestId = (this.options.requestIdFactory ?? newRequestId)();
    const message = encodeCommand(requestId, this.revision, payload);
    this.inFlight = { requestId, commandName: payload.name };
    this.lastCommandName = payload.name;
    this.transport.send(toWireText(message));
    this.setStatus({ ...this.status, pending: true });
    this.timeoutHandle = setTimeout(
      () => this.handleUncertain(),
      this.options.commandTimeoutMs ?? 10_000,
    );
    return requestId;
  }

  /** A user-initiated close (leaving the screen, choosing a terminal action). */
  disconnect(): void {
    this.closedForGood = true;
    this.clearInFlightTimer();
    this.clearReconnectTimer();
    this.transport.close();
  }

  private handleOpen(): void {
    this.transport.send(toWireText(encodeHello(this.options.credential)));
  }

  private clearInFlightTimer(): void {
    if (this.timeoutHandle !== null) {
      clearTimeout(this.timeoutHandle);
      this.timeoutHandle = null;
    }
  }

  private clearReconnectTimer(): void {
    if (this.reconnectHandle !== null) {
      clearTimeout(this.reconnectHandle);
      this.reconnectHandle = null;
    }
  }

  /** The 10 s command timeout: the outcome is uncertain (ADR 0009 §8.4). */
  private handleUncertain(): void {
    this.clearInFlightTimer();
    this.inFlight = null;
    this.setStatus({ ...this.status, pending: false, reconciling: true });
    // The uncertain command is never retransmitted. Force a reconnect so the
    // client reconciles with a fresh `connected` snapshot.
    this.transport.close();
  }

  private handleOutcome(message: AcceptedMessage | RejectedMessage | ErrorMessage): void {
    const requestId = message.request_id;
    if (requestId === null || this.inFlight === null || requestId !== this.inFlight.requestId) {
      return; // unmatched: never complete a command except by its own correlated outcome
    }
    this.clearInFlightTimer();
    this.inFlight = null;
    this.setStatus({ ...this.status, pending: false });
    if (message.type === "accepted") {
      this.emitOutcome({ kind: "accepted", requestId, revision: message.revision });
    } else if (message.type === "rejected") {
      this.emitOutcome({
        kind: "rejected",
        requestId,
        code: message.code,
        message: message.message,
      });
    } else {
      this.emitOutcome({
        kind: "invalid",
        requestId,
        code: "INVALID_COMMAND",
        message: message.message,
      });
    }
  }

  private emitOutcome(event: OutcomeEvent): void {
    this.outcomeListeners.forEach((callback) => {
      callback(event);
    });
  }

  private handleMessage(text: string): void {
    let decoded: ServerMessage;
    try {
      decoded = decodeServerMessage(parseWireJson(text));
    } catch (error) {
      if (!(error instanceof ProtocolDecodeError) && !(error instanceof SyntaxError)) throw error;
      // An undecodable server message - whether malformed JSON (a plain
      // `SyntaxError` from `JSON.parse`) or JSON that fails the protocol
      // decoder - is terminal: "Please reload" (ADR 0009 §1.4).
      this.terminal("protocol_mismatch");
      this.transport.close();
      return;
    }
    switch (decoded.type) {
      case "snapshot":
        this.handleSnapshot(decoded.revision, decoded.cause, decoded.view);
        return;
      case "accepted":
      case "rejected":
        this.handleOutcome(decoded);
        return;
      case "error":
        this.handleError(decoded);
        return;
      case "superseded":
        this.terminal("superseded");
        return;
      case "left_table":
        this.terminal("left_table");
        return;
      case "table_failed":
        this.terminal("table_failed");
        return;
    }
  }

  private handleSnapshot(revision: number, cause: SnapshotCause, view: TableView): void {
    if (revision < this.revision) return; // older than the current state: ignored
    this.revision = revision;
    if (cause === "connected") {
      this.reconnectAttempt = 0;
      this.setStatus({
        phase: "live",
        pending: false,
        reconciling: false,
        attempt: 0,
        reason: null,
      });
    } else if (this.status.phase !== "live") {
      this.setStatus({ ...this.status, phase: "live" });
    }
    this.snapshotListeners.forEach((callback) => {
      callback({ revision, cause, view });
    });
  }

  private handleError(message: ErrorMessage): void {
    switch (message.code) {
      case "INVALID_COMMAND":
        this.handleOutcome(message);
        return;
      case "AUTH_FAILED":
        this.terminal("auth_failed");
        return;
      case "PROTOCOL_MISMATCH":
      case "HELLO_REQUIRED":
        this.terminal("protocol_mismatch");
        return;
      case "MALFORMED_MESSAGE":
      case "HELLO_TIMEOUT":
        // The connection stays open (MALFORMED_MESSAGE), or the matching
        // close event (4408) arrives and `handleClose` reconnects.
        return;
    }
  }

  private handleClose(event: TransportCloseEvent): void {
    // Already terminal, or closed by the user via `disconnect()`: the close
    // event of that socket may arrive late and must never schedule a reconnect.
    if (this.closedForGood || this.status.phase === "closed") return;
    const disposition = closeDisposition(event.code);
    if (disposition.kind === "terminal") {
      this.terminal(disposition.reason);
      return;
    }
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    const hadInFlight = this.inFlight !== null;
    if (hadInFlight) {
      this.clearInFlightTimer();
      this.inFlight = null;
    }
    const reconciling = this.status.reconciling || hadInFlight;
    const attempt = this.reconnectAttempt;
    this.setStatus({ phase: "reconnecting", pending: false, reconciling, attempt, reason: null });
    const delay = computeBackoffDelayMs(attempt, this.options.random);
    this.reconnectHandle = setTimeout(() => {
      this.reconnectAttempt = attempt + 1;
      this.connect();
    }, delay);
  }

  private terminal(reason: ClosedReason): void {
    if (this.status.phase === "closed") return;
    this.closedForGood = true;
    this.clearInFlightTimer();
    this.clearReconnectTimer();
    this.setStatus({ phase: "closed", pending: false, reconciling: false, attempt: 0, reason });
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    this.statusListeners.forEach((callback) => {
      callback(status);
    });
  }
}

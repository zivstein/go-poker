/**
 * The authoritative store (C6.2 plan §2.2, §2.3): the latest server
 * snapshot, connection status, the in-flight command and the last
 * rejection. One minimal, immutable external store per table connection,
 * read with `useSyncExternalStore` (W7): `getSnapshot` returns the same
 * cached reference until a message actually changes the state.
 */

import type {
  ConnectionStatus,
  OutcomeEvent,
  SnapshotEvent,
} from "../connection/ConnectionController";
import type { RejectionCode, SnapshotCause, TableView } from "../protocol/types";

export interface LastRejection {
  code: RejectionCode | "INVALID_COMMAND";
  message: string;
}

export interface TableState {
  status: ConnectionStatus;
  revision: number;
  cause: SnapshotCause | null;
  view: TableView | null;
  lastRejection: LastRejection | null;
}

const INITIAL_STATE: TableState = {
  status: { phase: "idle", pending: false, reconciling: false, attempt: 0, reason: null },
  revision: 0,
  cause: null,
  view: null,
  lastRejection: null,
};

export class TableStore {
  private state: TableState = INITIAL_STATE;
  private readonly listeners = new Set<() => void>();

  getSnapshot = (): TableState => this.state;

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  applyStatus(status: ConnectionStatus): void {
    this.setState({ ...this.state, status });
  }

  /** Revision ordering (ADR 0009 §9.3): applies a snapshot whose revision is
   * ≥ the current one (equal revision replaces with the private update),
   * ignores an older one. */
  applySnapshot(event: SnapshotEvent): void {
    if (this.state.view !== null && event.revision < this.state.revision) return;
    // A newer shared state supersedes the last rejection (A1): it described a
    // decision that no longer exists. A STALE_REVISION rejection arrives after
    // the newer snapshot it refers to (ADR 0009 §9.4), so it still shows.
    const newer = this.state.view !== null && event.revision > this.state.revision;
    this.setState({
      ...this.state,
      revision: event.revision,
      cause: event.cause,
      view: event.view,
      lastRejection: newer ? null : this.state.lastRejection,
    });
  }

  applyOutcome(event: OutcomeEvent): void {
    if (event.kind === "accepted") {
      this.setState({ ...this.state, lastRejection: null });
      return;
    }
    this.setState({ ...this.state, lastRejection: { code: event.code, message: event.message } });
  }

  dismissRejection(): void {
    if (this.state.lastRejection === null) return;
    this.setState({ ...this.state, lastRejection: null });
  }

  private setState(next: TableState): void {
    this.state = next;
    this.listeners.forEach((listener) => {
      listener();
    });
  }
}

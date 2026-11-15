/**
 * Terminal states keyed by ADR 0009 §12's close codes, whichever the client
 * sees first: the close event, or the `error` / terminal message that
 * precedes it.
 */

export type ClosedReason =
  | "protocol_mismatch" // 4400: "Please reload"
  | "auth_failed" // 4401: back to entry; drop the stored credential
  | "superseded" // 4409: "Use here"
  | "left_table" // 4410: back to entry; drop the stored credential
  | "table_failed"; // 4500: error screen

export type CloseDisposition = { kind: "terminal"; reason: ClosedReason } | { kind: "reconnect" };

const TERMINAL_CLOSE_CODES: Record<number, ClosedReason> = {
  4400: "protocol_mismatch",
  4401: "auth_failed",
  4409: "superseded",
  4410: "left_table",
  4500: "table_failed",
};

/**
 * Maps a close code to the client's reaction. `4008` (outbox overflow) and
 * `4408` (`HELLO_TIMEOUT`) reconnect; `1009` (oversized frame, never
 * executed) reconnects; every other code (`1001`, `1006`, `1011`, …)
 * reconnects with backoff.
 */
export function closeDisposition(code: number): CloseDisposition {
  const reason = TERMINAL_CLOSE_CODES[code];
  if (reason !== undefined) return { kind: "terminal", reason };
  return { kind: "reconnect" };
}

/**
 * The credential kept in `sessionStorage`, keyed by `table_id` (ADR 0009 §4,
 * C6.2 plan §2.5). `4401` (`AUTH_FAILED`) and `4410` (`left_table`) delete it.
 *
 * Next to it, the tab records which table it is currently in, so a refresh
 * can resume: storage "only lets a tab resume after a refresh" (§2.5). The
 * credential never goes into a URL.
 *
 * Storage can be blocked (privacy modes, disabled site data): every access
 * here is guarded. A failed read means "nothing stored"; a failed write is a
 * no-op, so the live session works but cannot be resumed after a refresh.
 */

const KEY_PREFIX = "go-poker:credential:";
const CURRENT_TABLE_KEY = "go-poker:current-table";

export interface StoredSession {
  tableId: string;
  credential: string;
}

function guard<T>(fallback: T, action: () => T): T {
  try {
    return action();
  } catch {
    return fallback;
  }
}

export function storeCredential(tableId: string, credential: string): void {
  guard(undefined, () => sessionStorage.setItem(KEY_PREFIX + tableId, credential));
}

export function readCredential(tableId: string): string | null {
  return guard(null, () => sessionStorage.getItem(KEY_PREFIX + tableId));
}

/** Forgets the credential, and the current-table marker if it names this table. */
export function clearCredential(tableId: string): void {
  guard(undefined, () => sessionStorage.removeItem(KEY_PREFIX + tableId));
  if (guard(null, () => sessionStorage.getItem(CURRENT_TABLE_KEY)) === tableId) {
    clearCurrentTable();
  }
}

/** Records a successful Create or Join: the credential and the tab's current table. */
export function storeSession(tableId: string, credential: string): void {
  storeCredential(tableId, credential);
  guard(undefined, () => sessionStorage.setItem(CURRENT_TABLE_KEY, tableId));
}

export function clearCurrentTable(): void {
  guard(undefined, () => sessionStorage.removeItem(CURRENT_TABLE_KEY));
}

/** The tab's session to resume, or `null` when the marker is missing or has no credential. */
export function readStoredSession(): StoredSession | null {
  const tableId = guard(null, () => sessionStorage.getItem(CURRENT_TABLE_KEY));
  if (tableId === null) return null;
  const credential = readCredential(tableId);
  if (credential === null) return null;
  return { tableId, credential };
}

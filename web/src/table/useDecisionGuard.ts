/**
 * Accidental-action guards for the Action Dock (A1, AM3).
 *
 * Both guards only ever DROP an activation. Neither queues, delays or
 * replays one, so a guard can never send a command late or twice.
 */

import { useCallback, useEffect, useRef, useState } from "react";

/** The provisional turn-arrival guard (AM3), subject to browser validation. */
export const GUARD_MS = 350;

/** How long an armed "Confirm fold" waits for its second press. */
export const FOLD_CONFIRM_WINDOW_MS = 4000;

/**
 * Whether newly actionable decision controls should still ignore input.
 *
 * `armKey` identifies the current actionable decision (`null` while there is
 * none, or while the connection cannot act). Each change to a new non-null
 * key arms the guard for `guardMs`, from the very first render that shows the
 * decision, so there is no gap before an effect runs. A key that goes `null`
 * and back (a reconnect) arms it again; a pending command and its rejection
 * do not change the key, so a rejection never re-arms it.
 */
export function useArrivalGuard(armKey: string | null, guardMs: number = GUARD_MS): boolean {
  const [state, setState] = useState(() => ({
    key: armKey,
    armed: armKey !== null && guardMs > 0,
  }));
  let current = state;
  if (state.key !== armKey) {
    current = { key: armKey, armed: armKey !== null && guardMs > 0 };
    setState(current);
  }
  useEffect(() => {
    if (armKey === null || guardMs <= 0) return;
    const timer = setTimeout(() => {
      setState((s) => (s.key === armKey ? { key: armKey, armed: false } : s));
    }, guardMs);
    return () => clearTimeout(timer);
  }, [armKey, guardMs]);
  return current.armed;
}

export type FoldConfirmPhase = "idle" | "arming" | "ready";

export interface FoldConfirm {
  /** `arming`: armed, but a second press is still too soon to count.
   * `ready`: a second press folds. */
  phase: FoldConfirmPhase;
  arm: () => void;
  disarm: () => void;
}

/**
 * The two-press Fold confirmation while Check is free (D3). `arm` starts the
 * window; a second press counts only after `guardMs`, so a double-click never
 * folds. The window lapses after `windowMs` with no command.
 */
export function useFoldConfirm(
  guardMs: number = GUARD_MS,
  windowMs: number = FOLD_CONFIRM_WINDOW_MS,
): FoldConfirm {
  const [phase, setPhase] = useState<FoldConfirmPhase>("idle");
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clearTimers = useCallback(() => {
    for (const timer of timers.current) clearTimeout(timer);
    timers.current = [];
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const arm = useCallback(() => {
    clearTimers();
    if (guardMs > 0) {
      setPhase("arming");
      timers.current.push(setTimeout(() => setPhase("ready"), guardMs));
    } else {
      setPhase("ready");
    }
    timers.current.push(setTimeout(() => setPhase("idle"), windowMs));
  }, [clearTimers, guardMs, windowMs]);

  const disarm = useCallback(() => {
    clearTimers();
    setPhase("idle");
  }, [clearTimers]);

  return { phase, arm, disarm };
}

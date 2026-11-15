/**
 * Exponential backoff with jitter for reconnection (C6.2 plan §2.4): about
 * 0.5 s rising to an 8 s cap. Equal jitter: half of the computed base is
 * fixed, half is random, so the delay for a given attempt is always within
 * `[base / 2, base]`.
 */

const INITIAL_MS = 500;
const CAP_MS = 8000;

export function backoffBaseMs(attempt: number): number {
  return Math.min(INITIAL_MS * 2 ** attempt, CAP_MS);
}

export function computeBackoffDelayMs(attempt: number, random: () => number = Math.random): number {
  const base = backoffBaseMs(attempt);
  const half = base / 2;
  return half + random() * half;
}

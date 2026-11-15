/**
 * The one adapter from `legal_actions` to presentation data (C6.2 plan §5).
 * No poker rule lives here: every bound comes straight from the server.
 */

import type { LegalActions } from "../protocol/types";

export interface BetSizerRange {
  kind: "bet" | "raise";
  min: number;
  max: number;
  /** Set only when the actor's all-in target is below `min`; then the only
   * legal target, collapsing the sizer to one choice. */
  shortAllInTarget: number | null;
}

export function betSizerRange(legal: LegalActions): BetSizerRange | null {
  if (!legal.can_bet && !legal.can_raise) return null;
  const kind = legal.can_bet ? "bet" : "raise";
  const max = legal.max_target ?? 0;
  const min = legal.min_full_target ?? max;
  return { kind, min, max, shortAllInTarget: legal.short_all_in_target };
}

/** In `no_limit`, `max_target` is the actor's all-in target (ADR 0009 §11). */
export function isAllInTarget(legal: LegalActions, target: number): boolean {
  return legal.max_target !== null && target === legal.max_target;
}

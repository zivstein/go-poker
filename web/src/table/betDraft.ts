/**
 * The bet sizer's draft (A1, AM2): the raw text of the exact-amount field,
 * read against the server's `[min_full_target, max_target]` range. Pure, with
 * no React.
 *
 * Nothing here computes an amount (C6.2 §2.3 rule 7): a draft is either a
 * whole number the server's range already allows, sent exactly as typed, or
 * it is not committable. Out-of-range text is never clamped, on blur or on
 * submit; it stays invalid until the player corrects it or picks Min or Max.
 */

import { formatMoney } from "../format/money";

export interface DraftRange {
  min: number;
  max: number;
}

export type DraftStatus =
  | { kind: "ok"; target: number }
  | { kind: "empty" }
  | { kind: "invalid" }
  | { kind: "below" }
  | { kind: "above" };

const WHOLE_NUMBER = /^\d+$/;

/** Reads the draft text. Surrounding whitespace is ignored; anything else
 * that is not a whole number (`-5`, `1.5`, `1e3`, `$20`) is invalid. */
export function parseDraft(text: string, range: DraftRange): DraftStatus {
  const trimmed = text.trim();
  if (trimmed === "") return { kind: "empty" };
  if (!WHOLE_NUMBER.test(trimmed)) return { kind: "invalid" };
  const value = Number(trimmed);
  if (value < range.min) return { kind: "below" };
  if (value > range.max) return { kind: "above" };
  return { kind: "ok", target: value };
}

/** The canonical text of a committable draft ("0150" → "150"), or the text
 * itself when it is not committable: blur never changes an amount. */
export function normalizeDraftText(text: string, range: DraftRange): string {
  const status = parseDraft(text, range);
  return status.kind === "ok" ? String(status.target) : text;
}

export interface DraftHint {
  text: string;
  tone: "info" | "error";
}

/** The hint beside the sizer: the server's range, or why the draft cannot be
 * committed. */
export function draftHint(status: DraftStatus, range: DraftRange): DraftHint {
  const span = `${formatMoney(range.min)} to ${formatMoney(range.max)}`;
  switch (status.kind) {
    case "ok":
      return {
        text: `Min ${formatMoney(range.min)} · Max ${formatMoney(range.max)}`,
        tone: "info",
      };
    case "empty":
      return { text: `Enter an amount from ${span}`, tone: "info" };
    case "invalid":
      return { text: `Enter a whole-dollar amount from ${span}`, tone: "error" };
    case "below":
      return { text: `The minimum is ${formatMoney(range.min)}`, tone: "error" };
    case "above":
      return { text: `The maximum is ${formatMoney(range.max)}`, tone: "error" };
  }
}

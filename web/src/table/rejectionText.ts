import type { RejectionCode } from "../protocol/types";

/** A client table of ADR 0009 §12 rejection codes, with a generic fallback
 * (C6.2 plan §2.4). `message` is diagnostic only and never shown. */
const REJECTION_TEXT: Record<RejectionCode, string> = {
  STALE_REVISION: "Table updated.",
  NOT_A_MEMBER: "You are no longer seated at this table.",
  NOT_HOST: "Only the host can start the game.",
  GAME_ALREADY_STARTED: "The game has already started.",
  NOT_ENOUGH_PLAYERS: "Waiting for another player.",
  NO_HAND_IN_PROGRESS: "There is no hand in progress.",
  NOT_YOUR_TURN: "It isn't your turn.",
  ILLEGAL_ACTION: "That action isn't legal right now.",
  LEAVE_PENDING: "You have a pending leave.",
  NO_CHANGE: "Nothing to change.",
  PRE_ACTION_UNAVAILABLE: "That pre-action isn't available.",
};

const GENERIC_FALLBACK = "Something went wrong with that action.";
const INVALID_COMMAND_TEXT = "That action couldn't be sent.";

export function rejectionText(code: RejectionCode | "INVALID_COMMAND"): string {
  if (code === "INVALID_COMMAND") return INVALID_COMMAND_TEXT;
  return REJECTION_TEXT[code] ?? GENERIC_FALLBACK;
}

/** Whether a rejection is a quiet notice (ADR 0009 §9.4), not an error toast. */
export function isQuietRejection(code: RejectionCode | "INVALID_COMMAND"): boolean {
  return code === "STALE_REVISION";
}

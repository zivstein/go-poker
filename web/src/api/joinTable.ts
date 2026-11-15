import { decodeHttpErrorBody, decodeJoinTableResponse, parseWireJson } from "../protocol/decode";
import type { JoinTableResponseBody } from "../protocol/types";
import type { FieldError } from "./errors";
import { mapHttpError } from "./errors";

export type JoinTableResult =
  | { ok: true; data: JoinTableResponseBody }
  | { ok: false; error: FieldError };

/** Join codes are uppercased and stripped of whitespace before sending (Brief §2 item 3). */
export function normalizeJoinCode(code: string): string {
  return code.replace(/\s+/g, "").toUpperCase();
}

/** `POST /tables/by-code/{code}/members` (ADR 0009 §4). */
export async function joinTable(
  joinCode: string,
  displayName: string,
  seat: number,
): Promise<JoinTableResult> {
  const code = normalizeJoinCode(joinCode);
  const response = await fetch(`/tables/by-code/${code}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName, seat }),
  });
  const body = parseWireJson(await response.text());
  if (response.ok) {
    return { ok: true, data: decodeJoinTableResponse(body) };
  }
  return { ok: false, error: mapHttpError(decodeHttpErrorBody(body)) };
}

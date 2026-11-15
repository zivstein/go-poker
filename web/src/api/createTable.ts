import { decodeCreateTableResponse, decodeHttpErrorBody, parseWireJson } from "../protocol/decode";
import type { CreateTableResponseBody } from "../protocol/types";
import type { FieldError } from "./errors";
import { mapHttpError } from "./errors";

export type CreateTableResult =
  | { ok: true; data: CreateTableResponseBody }
  | { ok: false; error: FieldError };

/** `POST /tables` (ADR 0009 §4). */
export async function createTable(displayName: string): Promise<CreateTableResult> {
  const response = await fetch("/tables", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ display_name: displayName }),
  });
  const body = parseWireJson(await response.text());
  if (response.ok) {
    return { ok: true, data: decodeCreateTableResponse(body) };
  }
  return { ok: false, error: mapHttpError(decodeHttpErrorBody(body)) };
}

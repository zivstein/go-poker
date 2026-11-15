/**
 * Encoders for `hello` and every command (ADR 0009 §5, §6).
 */

import type {
  ActArgs,
  ClientMessage,
  CommandMessage,
  CommandPayload,
  HelloMessage,
  PreAction,
  ShowdownDecision,
} from "./types";
import { PROTOCOL_ID } from "./types";

export function encodeHello(credential: string): HelloMessage {
  return { type: "hello", protocol: PROTOCOL_ID, credential };
}

export function encodeCommand(
  requestId: string,
  expectedRevision: number,
  payload: CommandPayload,
): CommandMessage {
  return {
    type: "command",
    request_id: requestId,
    expected_revision: expectedRevision,
    ...payload,
  } as CommandMessage;
}

export function encodeStartGame(requestId: string, expectedRevision: number): CommandMessage {
  return encodeCommand(requestId, expectedRevision, { name: "start_game", args: {} });
}

export function encodeAct(
  requestId: string,
  expectedRevision: number,
  args: ActArgs,
): CommandMessage {
  return encodeCommand(requestId, expectedRevision, { name: "act", args });
}

export function encodeShowdownDecision(
  requestId: string,
  expectedRevision: number,
  decision: ShowdownDecision,
): CommandMessage {
  return encodeCommand(requestId, expectedRevision, {
    name: "showdown_decision",
    args: { decision },
  });
}

export function encodeSitOut(requestId: string, expectedRevision: number): CommandMessage {
  return encodeCommand(requestId, expectedRevision, { name: "sit_out", args: {} });
}

export function encodeSitBack(requestId: string, expectedRevision: number): CommandMessage {
  return encodeCommand(requestId, expectedRevision, { name: "sit_back", args: {} });
}

export function encodeLeave(requestId: string, expectedRevision: number): CommandMessage {
  return encodeCommand(requestId, expectedRevision, { name: "leave", args: {} });
}

export function encodeSelectPreAction(
  requestId: string,
  expectedRevision: number,
  preAction: PreAction,
): CommandMessage {
  return encodeCommand(requestId, expectedRevision, {
    name: "select_pre_action",
    args: { pre_action: preAction },
  });
}

export function encodeClearPreAction(requestId: string, expectedRevision: number): CommandMessage {
  return encodeCommand(requestId, expectedRevision, { name: "clear_pre_action", args: {} });
}

/** Serializes a client message to the WebSocket text frame. */
export function toWireText(message: ClientMessage): string {
  return JSON.stringify(message);
}

/** A correlation id for a new command (ADR 0009 §2). */
export function newRequestId(): string {
  return crypto.randomUUID();
}

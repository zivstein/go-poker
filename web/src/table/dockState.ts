/**
 * What the Action Dock shows (A1, `docs/design/ACTION_DOCK.md`): one state
 * derived from the displayed view (server-authoritative) and the connection
 * status (command lifecycle). Pure, with no React.
 *
 * Every control the dock offers still comes only from `legal_actions` and
 * `showdown_actions`; this module only chooses which frame and status text
 * the dock renders around them.
 */

import type { ConnectionStatus } from "../connection/ConnectionController";
import { formatMoney } from "../format/money";
import type { LegalActions, TableView, TurnKind } from "../protocol/types";

export type DockMode =
  | { kind: "betting"; legal: LegalActions }
  | { kind: "showdown" }
  | { kind: "waitingOther"; name: string; turnKind: TurnKind }
  | { kind: "notInHand" }
  | { kind: "notStarted"; isHost: boolean }
  | { kind: "waitingForPlayers" }
  | { kind: "handComplete" }
  | { kind: "idle" };

/** `live`: commands may be sent. `reconnecting`: the connection is down.
 * `reconciling`: a command's outcome is uncertain, so every action stays
 * disabled until a fresh `connected` snapshot (ADR 0009 §8). `closed`: a
 * terminal screen covers the table. */
export type DockConnection = "live" | "reconnecting" | "reconciling" | "closed";

export interface DockState {
  mode: DockMode;
  connection: DockConnection;
  /** A command is in flight (not uncertain). */
  pending: boolean;
  /** `you.pending_leave`: the server will apply the leave after this hand. */
  leavePending: boolean;
}

function seatName(view: TableView, seat: number): string {
  return view.seats.find((s) => s.seat === seat)?.occupant?.display_name ?? `Seat ${seat}`;
}

export function dockMode(view: TableView): DockMode {
  const hand = view.hand;
  if (hand?.legal_actions) return { kind: "betting", legal: hand.legal_actions };
  if (hand?.showdown_actions) return { kind: "showdown" };
  switch (view.phase) {
    case "not_started":
      return { kind: "notStarted", isHost: view.you.is_host };
    case "waiting_for_players":
      return { kind: "waitingForPlayers" };
    case "hand_complete":
      return { kind: "handComplete" };
    case "hand_in_progress":
      break;
  }
  if (hand === null) return { kind: "idle" };
  if (!hand.participants.some((p) => p.seat === view.you.seat)) return { kind: "notInHand" };
  const turn = hand.turn;
  if (turn !== null && turn.seat !== view.you.seat) {
    return { kind: "waitingOther", name: seatName(view, turn.seat), turnKind: turn.kind };
  }
  return { kind: "idle" };
}

export function dockConnection(status: ConnectionStatus): DockConnection {
  if (status.phase === "closed") return "closed";
  if (status.reconciling) return "reconciling";
  return status.phase === "live" ? "live" : "reconnecting";
}

export function dockState(view: TableView, status: ConnectionStatus): DockState {
  return {
    mode: dockMode(view),
    connection: dockConnection(status),
    pending: status.pending,
    leavePending: view.you.pending_leave,
  };
}

/** The status line for a mode, from server fields only. */
export function modeStatusText(mode: DockMode): string {
  switch (mode.kind) {
    case "betting":
      return mode.legal.can_call
        ? `Your turn · To call ${formatMoney(mode.legal.call_amount)}`
        : "Your turn";
    case "showdown":
      return "Your turn · Show or muck";
    case "waitingOther":
      return mode.turnKind === "showdown"
        ? `${mode.name} to show or muck`
        : `Waiting for ${mode.name}`;
    case "notInHand":
      return "Waiting for the next hand";
    case "notStarted":
      return mode.isHost ? "" : "Waiting for the host to start";
    case "waitingForPlayers":
      return "Waiting for players";
    case "handComplete":
      return "Hand complete · Next hand starting";
    case "idle":
      return "";
  }
}

/** The status line while the connection is not live, or `null` when live. */
export function connectionStatusText(connection: DockConnection): string | null {
  switch (connection) {
    case "reconnecting":
      return "Reconnecting… Actions are paused.";
    case "reconciling":
      return "No response — reconnecting. Your last action may or may not have counted.";
    case "live":
    case "closed":
      return null;
  }
}

/** Whether the mode is a decision the hero makes now. */
export function isDecision(mode: DockMode): boolean {
  return mode.kind === "betting" || mode.kind === "showdown";
}

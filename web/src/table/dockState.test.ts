import { describe, expect, it } from "vitest";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import {
  connectionStatusText,
  dockConnection,
  dockMode,
  dockState,
  modeStatusText,
} from "./dockState";

function view(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

const LIVE: ConnectionStatus = {
  phase: "live",
  pending: false,
  reconciling: false,
  attempt: 0,
  reason: null,
};

describe("dockMode from the canonical fixtures", () => {
  it("is a betting decision when the server sends legal_actions", () => {
    const mode = dockMode(view("snapshot.heads_up.preflop.actor.json"));
    expect(mode.kind).toBe("betting");
    expect(modeStatusText(mode)).toBe("Your turn · To call $5");
  });

  it("says nothing owed when calling is not legal", () => {
    const actor = view("snapshot.heads_up.preflop.actor.json");
    const hand = actor.hand;
    if (hand === null || hand.legal_actions === null) throw new Error("fixture has no decision");
    const mode = dockMode({
      ...actor,
      hand: {
        ...hand,
        legal_actions: { ...hand.legal_actions, can_call: false, can_check: true, call_amount: 0 },
      },
    });
    expect(modeStatusText(mode)).toBe("Your turn");
  });

  it("names the player being waited for", () => {
    const mode = dockMode(view("snapshot.heads_up.preflop.waiting.json"));
    expect(mode).toMatchObject({ kind: "waitingOther", turnKind: "betting" });
    expect(modeStatusText(mode)).toMatch(/^Waiting for \S/);
  });

  it("is a showdown decision when the server sends showdown_actions", () => {
    const mode = dockMode(view("snapshot.heads_up.showdown_decision.json"));
    expect(mode.kind).toBe("showdown");
    expect(modeStatusText(mode)).toBe("Your turn · Show or muck");
  });

  it("is hand complete once the hand is settled", () => {
    const mode = dockMode(view("snapshot.heads_up.settled.opponent_mucked.json"));
    expect(mode.kind).toBe("handComplete");
    expect(modeStatusText(mode)).toBe("Hand complete · Next hand starting");
  });

  it("distinguishes the host from a guest before the first hand", () => {
    const notStarted = view("snapshot.connected.not_started.json");
    expect(dockMode({ ...notStarted, you: { ...notStarted.you, is_host: true } })).toEqual({
      kind: "notStarted",
      isHost: true,
    });
    const guest = dockMode({ ...notStarted, you: { ...notStarted.you, is_host: false } });
    expect(modeStatusText(guest)).toBe("Waiting for the host to start");
  });

  it("waits for players, with or without a hand", () => {
    expect(dockMode(view("snapshot.waiting_for_players.json")).kind).toBe("waitingForPlayers");
    expect(dockMode(view("snapshot.reset.waiting_hand_null.json")).kind).toBe("waitingForPlayers");
  });

  it("is a betting decision at the nine-seat table", () => {
    expect(dockMode(view("snapshot.nine_seats.actor.json")).kind).toBe("betting");
  });

  it("is 'not in the hand' for a seated member who is not a participant", () => {
    const waiting = view("snapshot.heads_up.preflop.waiting.json");
    const hand = waiting.hand;
    if (hand === null) throw new Error("fixture has no hand");
    const outsider: TableView = {
      ...waiting,
      hand: { ...hand, participants: hand.participants.filter((p) => p.seat !== waiting.you.seat) },
    };
    expect(modeStatusText(dockMode(outsider))).toBe("Waiting for the next hand");
  });

  it("falls back to the seat number for a turn seat with no occupant", () => {
    const waiting = view("snapshot.heads_up.preflop.waiting.json");
    const turnSeat = waiting.hand?.turn?.seat;
    const emptied: TableView = {
      ...waiting,
      seats: waiting.seats.map((s) => (s.seat === turnSeat ? { ...s, occupant: null } : s)),
    };
    expect(modeStatusText(dockMode(emptied))).toBe(`Waiting for Seat ${turnSeat}`);
  });
});

describe("dockConnection", () => {
  it("is live only when live and not reconciling", () => {
    expect(dockConnection(LIVE)).toBe("live");
    expect(dockConnection({ ...LIVE, pending: true })).toBe("live");
    expect(dockConnection({ ...LIVE, reconciling: true })).toBe("reconciling");
    expect(dockConnection({ ...LIVE, phase: "reconnecting" })).toBe("reconnecting");
    expect(dockConnection({ ...LIVE, phase: "connecting" })).toBe("reconnecting");
    expect(dockConnection({ ...LIVE, phase: "reconnecting", reconciling: true })).toBe(
      "reconciling",
    );
    expect(dockConnection({ ...LIVE, phase: "closed" })).toBe("closed");
  });

  it("has a status line only when not live", () => {
    expect(connectionStatusText("live")).toBeNull();
    expect(connectionStatusText("reconnecting")).toBe("Reconnecting… Actions are paused.");
    expect(connectionStatusText("reconciling")).toBe(
      "No response — reconnecting. Your last action may or may not have counted.",
    );
  });
});

describe("dockState", () => {
  it("carries the pending command and the pending leave", () => {
    const v = view("snapshot.heads_up.preflop.waiting.json");
    const state = dockState(
      { ...v, you: { ...v.you, pending_leave: true } },
      {
        ...LIVE,
        pending: true,
      },
    );
    expect(state.pending).toBe(true);
    expect(state.leavePending).toBe(true);
    expect(state.connection).toBe("live");
  });
});

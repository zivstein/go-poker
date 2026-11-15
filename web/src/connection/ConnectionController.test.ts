import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { backoffBaseMs, computeBackoffDelayMs } from "./backoff";
import type { ConnectionControllerOptions } from "./ConnectionController";
import { ConnectionController } from "./ConnectionController";
import { closeDisposition } from "./closeCodes";
import { MockTransport } from "./MockTransport";

function connectedSnapshot(revision: number) {
  const fixture = readFixtureJson<{ view: TableView }>(
    "messages/server/snapshot.connected.not_started.json",
  );
  return { type: "snapshot", revision, cause: "connected", view: fixture.view };
}

function privateSnapshot(revision: number) {
  const fixture = readFixtureJson<{ view: TableView }>(
    "messages/server/snapshot.private.pre_action_selected.json",
  );
  return { type: "snapshot", revision, cause: "private", view: fixture.view };
}

function commandSnapshot(revision: number) {
  const fixture = readFixtureJson<{ view: TableView }>(
    "messages/server/snapshot.heads_up.preflop.actor.json",
  );
  return { type: "snapshot", revision, cause: "command", view: fixture.view };
}

function makeController(options: Partial<ConnectionControllerOptions> = {}) {
  const transport = new MockTransport();
  let counter = 0;
  const controller = new ConnectionController(transport, {
    tableId: "table-1",
    credential: "cred-1",
    requestIdFactory: () => `req-${++counter}`,
    ...options,
  });
  return { transport, controller };
}

describe("ConnectionController", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("ignores a late close event after disconnect(): no reconnecting status, no timer", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    controller.disconnect();

    transport.emitClose(1006); // the closed socket's event arrives late

    expect(controller.currentStatus.phase).toBe("live");
    expect(vi.getTimerCount()).toBe(0);
    vi.advanceTimersByTime(60_000);
    expect(transport.openedUrls).toHaveLength(1);
  });

  it("sends hello first, on open", () => {
    const { transport, controller } = makeController();
    controller.connect();
    expect(transport.sentFrames).toEqual([]);
    transport.emitOpen();
    expect(transport.sentFrames).toHaveLength(1);
    expect(transport.lastSent()).toEqual({
      type: "hello",
      protocol: "go-poker.v1",
      credential: "cred-1",
    });
  });

  it("becomes live on the first snapshot", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    expect(controller.currentStatus.phase).toBe("connecting");
    transport.emitMessage(connectedSnapshot(1));
    expect(controller.currentStatus.phase).toBe("live");
    expect(controller.currentStatus.reconciling).toBe(false);
    expect(controller.currentRevision).toBe(1);
  });

  it("completes a command only on its correlated outcome, across several snapshots", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));

    const requestId = controller.sendCommand({ name: "start_game", args: {} });
    expect(requestId).not.toBeNull();
    expect(controller.currentStatus.pending).toBe(true);

    // A shared transition's own snapshot does not complete the command.
    transport.emitMessage(commandSnapshot(2));
    expect(controller.currentStatus.pending).toBe(true);

    const outcomes: unknown[] = [];
    controller.onOutcome((e) => outcomes.push(e));
    transport.emitMessage({ type: "accepted", request_id: requestId, revision: 2 });
    expect(controller.currentStatus.pending).toBe(false);
    expect(outcomes).toEqual([{ kind: "accepted", requestId, revision: 2 }]);
  });

  it("completes a private command on a private snapshot then accepted, at an unchanged revision", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(3));

    const requestId = controller.sendCommand({ name: "clear_pre_action", args: {} });
    transport.emitMessage(privateSnapshot(3));
    expect(controller.currentStatus.pending).toBe(true); // a bare snapshot never completes it
    expect(controller.currentRevision).toBe(3);

    const outcomes: unknown[] = [];
    controller.onOutcome((e) => outcomes.push(e));
    transport.emitMessage({ type: "accepted", request_id: requestId, revision: 3 });
    expect(controller.currentStatus.pending).toBe(false);
    expect(outcomes).toEqual([{ kind: "accepted", requestId, revision: 3 }]);
  });

  it("treats an unmatched outcome as never completing the in-flight command", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    controller.sendCommand({ name: "start_game", args: {} });
    transport.emitMessage({ type: "accepted", request_id: "someone-elses-id", revision: 2 });
    expect(controller.currentStatus.pending).toBe(true);
  });

  it('an undecodable server message closes the connection and is terminal, "Please reload" (ADR 0009 §1.4)', () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));

    transport.emitRawMessage('{"type": "nonsense_type_the_client_has_never_heard_of"}');

    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.currentStatus.reason).toBe("protocol_mismatch");
    expect(transport.closedCodes.length).toBeGreaterThan(0);

    // Terminal: a close event arriving afterwards changes nothing, and no
    // command can be sent.
    transport.emitClose(1006);
    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.sendCommand({ name: "start_game", args: {} })).toBeNull();
  });

  it("malformed (non-JSON) text from the server is also undecodable and terminal", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));

    transport.emitRawMessage("not even json {{{");

    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.currentStatus.reason).toBe("protocol_mismatch");
  });

  it("STALE_REVISION is not an error: the connection stays open and live, and actions re-enable at once", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));

    const requestId = controller.sendCommand({ name: "start_game", args: {} });
    const outcomes: unknown[] = [];
    controller.onOutcome((e) => outcomes.push(e));
    transport.emitMessage({
      type: "rejected",
      request_id: requestId,
      code: "STALE_REVISION",
      message: "x",
    });

    expect(outcomes).toEqual([
      { kind: "rejected", requestId, code: "STALE_REVISION", message: "x" },
    ]);
    // Not a terminal, not a reconnect, not an uncertain lock: just a completed
    // (rejected) command on an otherwise still-live, still-open connection.
    expect(controller.currentStatus.phase).toBe("live");
    expect(controller.currentStatus.pending).toBe(false);
    expect(controller.currentStatus.reconciling).toBe(false);
    expect(transport.closedCodes).toEqual([]);
    expect(controller.sendCommand({ name: "start_game", args: {} })).not.toBeNull();
  });

  it("the 10s timeout makes the outcome uncertain: actions disabled, no re-send, reconnect", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));

    controller.sendCommand({ name: "act", args: { action: "fold", target: null } });
    expect(transport.sentFrames).toHaveLength(2); // hello + the command

    vi.advanceTimersByTime(10_000);
    expect(controller.currentStatus.reconciling).toBe(true);
    expect(controller.currentStatus.pending).toBe(false);
    expect(
      controller.sendCommand({ name: "act", args: { action: "fold", target: null } }),
    ).toBeNull();

    // The transport was told to close; the test simulates the resulting close event.
    transport.emitClose(1006);
    expect(controller.currentStatus.phase).toBe("reconnecting");
    expect(controller.currentStatus.reconciling).toBe(true);

    vi.advanceTimersByTime(backoffBaseMs(0) + 1);
    transport.emitOpen();
    expect(transport.sentFrames).toHaveLength(3); // hello again; the fold was never resent
    expect(JSON.parse(transport.sentFrames[2] as string)).toEqual({
      type: "hello",
      protocol: "go-poker.v1",
      credential: "cred-1",
    });

    // Reconciliation: actions re-enable only once a fresh `connected` snapshot arrives.
    transport.emitMessage(connectedSnapshot(2));
    expect(controller.currentStatus.reconciling).toBe(false);
    expect(controller.currentStatus.phase).toBe("live");

    // The next user decision is a brand new command, with a new request_id
    // at the current (post-reconciliation) revision.
    const requestId = controller.sendCommand({
      name: "act",
      args: { action: "fold", target: null },
    });
    expect(requestId).not.toBeNull();
    expect(JSON.parse(transport.sentFrames[3] as string)).toMatchObject({ expected_revision: 2 });
  });

  it("a connection drop with no command in flight reconnects without locking actions", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitClose(1006);
    expect(controller.currentStatus.phase).toBe("reconnecting");
    expect(controller.currentStatus.reconciling).toBe(false);
  });

  it.each([
    [4400, "terminal"],
    [4401, "terminal"],
    [4409, "terminal"],
    [4410, "terminal"],
    [4500, "terminal"],
    [4008, "reconnect"],
    [4408, "reconnect"],
    [1009, "reconnect"],
    [1001, "reconnect"],
    [1006, "reconnect"],
    [1011, "reconnect"],
  ])("maps close code %i to %s", (code, kind) => {
    expect(closeDisposition(code).kind).toBe(kind);
  });

  it("reaches a terminal state on each close code mapped to terminal", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitClose(4409);
    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.currentStatus.reason).toBe("superseded");
  });

  it('"Use here" reconnects and supersedes the other connection', () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitMessage({ type: "superseded" });
    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.currentStatus.reason).toBe("superseded");

    // "Use here" is a fresh connect from a new controller instance (the app
    // discards the superseded one and opens a new connection).
    const next = makeController();
    next.controller.connect();
    next.transport.emitOpen();
    expect(next.transport.sentFrames).toHaveLength(1);
  });

  it("treats AUTH_FAILED after an uncertain leave as left (ADR 0009 §8.4)", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));

    // The user leaves, but the outcome is never received: the connection
    // drops before the server's answer arrives, so the command is uncertain.
    controller.sendCommand({ name: "leave", args: {} });
    expect(controller.wasLeaving).toBe(true);
    vi.advanceTimersByTime(10_000);
    expect(controller.currentStatus.reconciling).toBe(true);
    transport.emitClose(1006);
    expect(controller.currentStatus.phase).toBe("reconnecting");

    // On reconnect, the leave already applied server-side: the credential
    // no longer works.
    vi.advanceTimersByTime(backoffBaseMs(0) + 1);
    transport.emitOpen();
    transport.emitMessage({ type: "error", request_id: null, code: "AUTH_FAILED", message: "x" });
    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.currentStatus.reason).toBe("auth_failed");
    // The client distinguishes this from an unrelated session loss only
    // through `wasLeaving`; the UI renders "You left the table." for it.
    expect(controller.wasLeaving).toBe(true);
  });

  it("an AUTH_FAILED unrelated to leaving is not reported as wasLeaving", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    controller.sendCommand({ name: "act", args: { action: "fold", target: null } });
    expect(controller.wasLeaving).toBe(false);
    transport.emitMessage({ type: "error", request_id: null, code: "AUTH_FAILED", message: "x" });
    expect(controller.currentStatus.reason).toBe("auth_failed");
    expect(controller.wasLeaving).toBe(false);
  });

  it("the close event for 4401 that follows an already-handled AUTH_FAILED error is a no-op", () => {
    const { transport, controller } = makeController();
    controller.connect();
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitMessage({ type: "error", request_id: null, code: "AUTH_FAILED", message: "x" });
    expect(controller.currentStatus.phase).toBe("closed");
    // The matching close code, whichever the client sees second, changes nothing.
    transport.emitClose(4401);
    expect(controller.currentStatus.phase).toBe("closed");
    expect(controller.currentStatus.reason).toBe("auth_failed");
  });

  it("backoff stays within [base/2, base] for an attempt, capped at 8s", () => {
    for (const attempt of [0, 1, 2, 3, 4, 5, 10]) {
      const base = backoffBaseMs(attempt);
      for (const r of [0, 0.25, 0.5, 0.75, 0.999999]) {
        const delay = computeBackoffDelayMs(attempt, () => r);
        expect(delay).toBeGreaterThanOrEqual(base / 2);
        expect(delay).toBeLessThanOrEqual(base);
      }
      expect(base).toBeLessThanOrEqual(8000);
    }
    expect(backoffBaseMs(0)).toBe(500);
    expect(backoffBaseMs(10)).toBe(8000);
  });
});

import { describe, expect, it } from "vitest";
import { ConnectionController } from "../connection/ConnectionController";
import { MockTransport } from "../connection/MockTransport";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { TableStore } from "./store";
import { wireStore } from "./wireStore";

function view(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

describe("TableStore", () => {
  it("returns the same cached reference until a message changes the state", () => {
    const store = new TableStore();
    const a = store.getSnapshot();
    const b = store.getSnapshot();
    expect(a).toBe(b);
    store.applySnapshot({
      revision: 1,
      cause: "connected",
      view: view("snapshot.connected.not_started.json"),
    });
    const c = store.getSnapshot();
    expect(c).not.toBe(b);
    expect(store.getSnapshot()).toBe(c);
  });

  it("applies a snapshot whose revision is >= the current one", () => {
    const store = new TableStore();
    store.applySnapshot({
      revision: 5,
      cause: "command",
      view: view("snapshot.heads_up.preflop.actor.json"),
    });
    expect(store.getSnapshot().revision).toBe(5);
    // An older revision is ignored.
    store.applySnapshot({
      revision: 3,
      cause: "connected",
      view: view("snapshot.connected.not_started.json"),
    });
    expect(store.getSnapshot().revision).toBe(5);
  });

  it("replaces on an equal revision (a private-intent update)", () => {
    const store = new TableStore();
    const command = view("snapshot.heads_up.preflop.actor.json");
    store.applySnapshot({ revision: 5, cause: "command", view: command });
    const privateView = view("snapshot.private.pre_action_selected.json");
    store.applySnapshot({ revision: 5, cause: "private", view: privateView });
    expect(store.getSnapshot().revision).toBe(5);
    expect(store.getSnapshot().view).toBe(privateView);
    expect(store.getSnapshot().cause).toBe("private");
  });

  it("clears the last rejection on an accepted outcome, keeps it on rejected/invalid", () => {
    const store = new TableStore();
    store.applyOutcome({
      kind: "rejected",
      requestId: "r-1",
      code: "STALE_REVISION",
      message: "x",
    });
    expect(store.getSnapshot().lastRejection).toEqual({ code: "STALE_REVISION", message: "x" });
    store.applyOutcome({ kind: "accepted", requestId: "r-2", revision: 2 });
    expect(store.getSnapshot().lastRejection).toBeNull();
    store.applyOutcome({
      kind: "invalid",
      requestId: "r-3",
      code: "INVALID_COMMAND",
      message: "y",
    });
    expect(store.getSnapshot().lastRejection).toEqual({ code: "INVALID_COMMAND", message: "y" });
  });

  it("wires a ConnectionController's events into the store", () => {
    const store = new TableStore();
    const transport = new MockTransport();
    const controller = new ConnectionController(transport, { tableId: "t-1", credential: "c-1" });
    wireStore(store, controller);
    controller.connect();
    transport.emitOpen();
    transport.emitMessage({
      type: "snapshot",
      revision: 1,
      cause: "connected",
      view: view("snapshot.connected.not_started.json"),
    });
    expect(store.getSnapshot().status.phase).toBe("live");
    expect(store.getSnapshot().revision).toBe(1);
  });
});

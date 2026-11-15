import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readCredential, readStoredSession, storeSession } from "../entry/credentialStorage";
import type { TableView } from "../protocol/types";
import { FakeWebSocket } from "../testing/fakeWebSocket";
import { readFixtureJson } from "../testing/fixtures";
import { App } from "./App";

// QA: resume-after-refresh edge cases beyond App.test.tsx (the M2 repair).

const TABLE_A = "table-a";
const TABLE_B = "table-b";

function connectedSnapshot(revision = 1) {
  return {
    type: "snapshot",
    revision,
    cause: "connected",
    view: readFixtureJson<{ view: TableView }>(
      "messages/server/snapshot.connected.not_started.json",
    ).view,
  };
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function mountApp() {
  return render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.install();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  sessionStorage.clear();
  window.history.replaceState({}, "", "/");
});

describe("App with blocked sessionStorage", () => {
  it("renders the entry screen instead of crashing when storage throws", async () => {
    const boom = () => {
      throw new DOMException("blocked", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(boom);

    mountApp();
    await advance(1);

    expect(screen.getByRole("button", { name: "Create" })).toBeDefined();
    expect(FakeWebSocket.instances).toHaveLength(0);
    vi.restoreAllMocks();
  });
});

describe("App resume: which table, which credential", () => {
  it("a marker for one table never borrows another table's credential", async () => {
    storeSession(TABLE_B, "cred-b");
    sessionStorage.setItem("go-poker:current-table", TABLE_A); // A has no credential of its own

    mountApp();
    await advance(1);

    expect(screen.getByRole("button", { name: "Create" })).toBeDefined();
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(readCredential(TABLE_B)).toBe("cred-b"); // untouched
  });

  it("resumes the marked table with its own credential when several are stored", async () => {
    storeSession(TABLE_A, "cred-a");
    storeSession(TABLE_B, "cred-b"); // the marker now names B
    mountApp();
    await advance(1);

    const live = FakeWebSocket.live();
    expect(live).toHaveLength(1);
    expect((live[0] as FakeWebSocket).url).toBe(`/ws/tables/${TABLE_B}`);
    expect((live[0] as FakeWebSocket).sentJson()[0]).toMatchObject({
      type: "hello",
      credential: "cred-b",
    });
  });

  it("a stale marker (the table is gone): AUTH_FAILED with no snapshot clears it, and a refresh shows entry", async () => {
    storeSession(TABLE_A, "cred-a");
    const first = mountApp();
    await advance(1);
    const socket = FakeWebSocket.live()[0] as FakeWebSocket;
    await act(async () => {
      socket.serverSend({ type: "error", request_id: null, code: "AUTH_FAILED", message: "x" });
      socket.serverClose(4401);
    });
    await advance(1);
    expect(screen.getByText("Your session ended.")).toBeDefined();
    expect(readStoredSession()).toBeNull();
    expect(readCredential(TABLE_A)).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Back to entry" }));
    expect(screen.getByRole("button", { name: "Create" })).toBeDefined();
    first.unmount();
    FakeWebSocket.instances.length = 0;

    mountApp();
    await advance(1);
    expect(screen.getByRole("button", { name: "Create" })).toBeDefined();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("a superseded tab still resumes after a refresh: the marker is kept for 'Use here'", async () => {
    storeSession(TABLE_A, "cred-a");
    const first = mountApp();
    await advance(1);
    const socket = FakeWebSocket.live()[0] as FakeWebSocket;
    await act(async () => {
      socket.serverSend(connectedSnapshot());
      socket.serverSend({ type: "superseded" });
      socket.serverClose(4409);
    });
    await advance(1);
    expect(readStoredSession()).toEqual({ tableId: TABLE_A, credential: "cred-a" });
    first.unmount();

    mountApp(); // the refresh
    await advance(1);
    const resumed = FakeWebSocket.live();
    expect(resumed).toHaveLength(1);
    expect((resumed[0] as FakeWebSocket).sentJson()[0]).toMatchObject({ credential: "cred-a" });
  });
});

describe("App resume: a duplicated tab (C6.2 plan §2.5)", () => {
  it("the copy reconnects as the same player and supersedes the original, which can take it back", async () => {
    storeSession(TABLE_A, "cred-a");

    // Tab 1 is the original.
    const tab1 = mountApp();
    await advance(1);
    const socket1 = FakeWebSocket.live()[0] as FakeWebSocket;
    await act(async () => {
      socket1.serverSend(connectedSnapshot(1));
    });

    // Tab 2 is a duplicate: it carries a copy of sessionStorage.
    const tab2 = mountApp();
    await advance(1);
    const socket2 = FakeWebSocket.live().find((s) => s !== socket1) as FakeWebSocket;
    expect(socket2.sentJson()[0]).toMatchObject({ type: "hello", credential: "cred-a" });
    // The server supersedes the older connection and welcomes the new one.
    await act(async () => {
      socket1.serverSend({ type: "superseded" });
      socket1.serverClose(4409);
      socket2.serverSend(connectedSnapshot(2));
    });
    await advance(1);

    expect(within(tab1.container).getByText("This table is open in another window.")).toBeDefined();
    expect(within(tab2.container).queryByText("This table is open in another window.")).toBeNull();
    expect(FakeWebSocket.live()).toEqual([socket2]);

    // The original takes the table back: a fresh hello, superseding the copy.
    fireEvent.click(within(tab1.container).getByRole("button", { name: "Use here" }));
    await advance(1);
    const socket3 = FakeWebSocket.live().find((s) => s !== socket2) as FakeWebSocket;
    expect(socket3.sentJson()[0]).toMatchObject({ type: "hello", credential: "cred-a" });
    await act(async () => {
      socket2.serverSend({ type: "superseded" });
      socket2.serverClose(4409);
      socket3.serverSend(connectedSnapshot(3));
    });
    await advance(1);

    expect(within(tab2.container).getByText("This table is open in another window.")).toBeDefined();
    expect(within(tab1.container).queryByText("This table is open in another window.")).toBeNull();
    expect(FakeWebSocket.live()).toEqual([socket3]);
    // Neither tab ever forgot the credential.
    expect(readStoredSession()).toEqual({ tableId: TABLE_A, credential: "cred-a" });
  });
});

describe("App resume: the dev mock mode keeps precedence", () => {
  it("a ?mock URL runs the scripted scenario and opens no real socket, whatever is stored", async () => {
    storeSession(TABLE_A, "cred-a");
    window.history.replaceState({}, "", "/?mock=heads_up_hand&connection=alice-1");

    mountApp();
    await advance(50);

    expect(screen.queryByRole("button", { name: "Create" })).toBeNull();
    expect(FakeWebSocket.instances).toHaveLength(0);
    expect(readStoredSession()).toEqual({ tableId: TABLE_A, credential: "cred-a" });
  });
});

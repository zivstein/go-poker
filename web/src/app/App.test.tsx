import { act, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { storeSession } from "../entry/credentialStorage";
import type { TableView } from "../protocol/types";
import { FakeWebSocket } from "../testing/fakeWebSocket";
import { readFixtureJson } from "../testing/fixtures";
import { App } from "./App";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("App", () => {
  it("shows the branded entry screen with Create and Join", () => {
    render(<App />);
    expect(screen.getByRole("img", { name: "Go! Poker" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Create" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Join" })).toBeDefined();
  });
});

describe("App resumes a stored session after a refresh (C6.2 plan §2.5)", () => {
  const TABLE_ID = "table-resume";
  const CREDENTIAL = "cred-resume";

  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.install();
  });

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

  function connectedSnapshot() {
    const fixture = readFixtureJson<{ view: TableView }>(
      "messages/server/snapshot.connected.not_started.json",
    );
    return { type: "snapshot", revision: 1, cause: "connected", view: fixture.view };
  }

  function expectEntryScreen() {
    expect(screen.getByRole("button", { name: "Create" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Join" })).toBeDefined();
  }

  it("resumes into the table: no entry screen, a socket to the table, hello with the stored credential", async () => {
    storeSession(TABLE_ID, CREDENTIAL);

    mountApp();
    await advance(1);

    expect(screen.queryByRole("button", { name: "Create" })).toBeNull();
    const live = FakeWebSocket.live();
    expect(live).toHaveLength(1);
    const socket = live[0] as FakeWebSocket;
    expect(socket.url).toBe(`/ws/tables/${TABLE_ID}`);
    expect(socket.sentJson()[0]).toMatchObject({ type: "hello", credential: CREDENTIAL });
  });

  it.each([
    [
      "AUTH_FAILED / 4401",
      4401,
      { type: "error", request_id: null, code: "AUTH_FAILED", message: "x" },
    ],
    ["left_table / 4410", 4410, { type: "left_table" }],
  ])("leaves nothing to resume after %s", async (_name, closeCode, message) => {
    storeSession(TABLE_ID, CREDENTIAL);
    const first = mountApp();
    await advance(1);
    const socket = FakeWebSocket.live()[0] as FakeWebSocket;
    await act(async () => {
      socket.serverSend(connectedSnapshot());
      socket.serverSend(message);
      socket.serverClose(closeCode);
    });
    await advance(1);
    first.unmount();
    FakeWebSocket.instances.length = 0;

    mountApp(); // the refresh
    await advance(1);

    expectEntryScreen();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("forgets the table when the user goes back to the entry screen from a terminal screen", async () => {
    storeSession(TABLE_ID, CREDENTIAL);
    const first = mountApp();
    await advance(1);
    const socket = FakeWebSocket.live()[0] as FakeWebSocket;
    await act(async () => {
      socket.serverSend(connectedSnapshot());
      socket.serverSend({ type: "table_failed" });
      socket.serverClose(4500);
    });
    await advance(1);

    fireEvent.click(screen.getByRole("button", { name: "Back to entry" }));
    expectEntryScreen();
    first.unmount();

    mountApp(); // the refresh
    expectEntryScreen();
  });

  it("shows the entry screen for a current-table marker without a credential", () => {
    sessionStorage.setItem("go-poker:current-table", TABLE_ID);

    mountApp();

    expectEntryScreen();
    expect(FakeWebSocket.instances).toHaveLength(0);
  });
});

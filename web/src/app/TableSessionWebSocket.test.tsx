import { act, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WebSocketTransport } from "../connection/WebSocketTransport";
import type { TableView } from "../protocol/types";
import { FakeWebSocket } from "../testing/fakeWebSocket";
import { readFixtureJson } from "../testing/fixtures";
import { TableSession } from "./TableSession";

// The real WebSocketTransport over a browser-like fake WebSocket, under
// StrictMode (setup, cleanup, setup): the C2 regression suite.

const TABLE_ID = "table-ws";
const CREDENTIAL = "cred-ws";

function connectedSnapshot(revision: number) {
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

function mount() {
  return render(
    <StrictMode>
      <TableSession
        tableId={TABLE_ID}
        credential={CREDENTIAL}
        createTransport={() => new WebSocketTransport()}
        onBackToEntry={() => {}}
      />
    </StrictMode>,
  );
}

/** The one live socket, asserting there is exactly one. */
function onlySocket(): FakeWebSocket {
  const live = FakeWebSocket.live();
  expect(live).toHaveLength(1);
  return live[0] as FakeWebSocket;
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.install();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("TableSession over the real WebSocketTransport, under StrictMode", () => {
  it("connects exactly one socket, sends hello first, and goes live on the connected snapshot", async () => {
    mount();
    await advance(1);

    const socket = onlySocket();
    expect(socket.everOpened).toBe(true);
    expect(socket.url).toBe(`/ws/tables/${TABLE_ID}`);
    const first = socket.sentJson()[0];
    expect(first?.type).toBe("hello");
    expect(first?.credential).toBe(CREDENTIAL);
    // StrictMode's discarded first setup never reached a server.
    expect(FakeWebSocket.instances.filter((s) => s !== socket && s.everOpened)).toEqual([]);

    await act(async () => {
      socket.serverSend(connectedSnapshot(1));
    });
    expect(screen.queryByText("Reconnecting…")).toBeNull();
    expect(screen.getByRole("button", { name: "Start game" })).toBeDefined();
  });

  it("closes every socket on unmount and leaves no reconnect timer behind", async () => {
    const { unmount } = render(
      <StrictMode>
        <TableSession
          tableId={TABLE_ID}
          credential={CREDENTIAL}
          createTransport={() => new WebSocketTransport()}
          onBackToEntry={() => {}}
        />
      </StrictMode>,
    );
    await advance(1);
    await act(async () => {
      onlySocket().serverSend(connectedSnapshot(1));
    });
    const opened = FakeWebSocket.instances.length;

    unmount();
    await advance(1); // the close events arrive late, after the unmount
    expect(FakeWebSocket.live()).toHaveLength(0);

    await advance(60_000); // well past the 8 s backoff cap
    expect(FakeWebSocket.instances).toHaveLength(opened);
    expect(FakeWebSocket.live()).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it('opens a fresh socket with hello after "Use here" following a supersede', async () => {
    mount();
    await advance(1);
    const first = onlySocket();
    await act(async () => {
      first.serverSend(connectedSnapshot(1));
      first.serverSend({ type: "superseded" });
      first.serverClose(4409);
    });
    await advance(1);
    expect(FakeWebSocket.live()).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Use here" }));
    await advance(1);

    const second = onlySocket();
    expect(second).not.toBe(first);
    expect(second.sentJson()[0]?.type).toBe("hello");
    expect(second.sentJson()[0]?.credential).toBe(CREDENTIAL);
  });

  it("still reconnects with backoff after an unexpected close", async () => {
    mount();
    await advance(1);
    const first = onlySocket();
    await act(async () => {
      first.serverSend(connectedSnapshot(1));
    });

    await act(async () => {
      first.serverClose(1006);
    });
    await advance(1);
    expect(FakeWebSocket.live()).toHaveLength(0); // waiting out the backoff
    expect(screen.getAllByText("Reconnecting…").length).toBeGreaterThan(0);

    await advance(8000); // past the first attempt's backoff
    const second = onlySocket();
    expect(second).not.toBe(first);
    expect(second.sentJson()[0]?.type).toBe("hello");
  });
});

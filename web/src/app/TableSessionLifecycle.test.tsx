import { act, fireEvent, render, screen } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MockTransport } from "../connection/MockTransport";
import { WebSocketTransport } from "../connection/WebSocketTransport";
import { readCredential, storeCredential } from "../entry/credentialStorage";
import type { TableView } from "../protocol/types";
import { FakeWebSocket } from "../testing/fakeWebSocket";
import { readFixtureJson } from "../testing/fixtures";
import { TableSession } from "./TableSession";

// QA: lifecycle holes around the C2 repair (a controller per effect setup,
// replaced by "Use here"), on the real WebSocketTransport under StrictMode
// unless a test needs a transport it can drive by hand.

const TABLE_ID = "table-qa";
const CREDENTIAL = "cred-qa";

function snapshotView(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

function connectedSnapshot(revision: number, fixture = "snapshot.connected.not_started.json") {
  return { type: "snapshot", revision, cause: "connected", view: snapshotView(fixture) };
}

async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

function mountReal(onBackToEntry: () => void = () => {}) {
  return render(
    <StrictMode>
      <TableSession
        tableId={TABLE_ID}
        credential={CREDENTIAL}
        createTransport={() => new WebSocketTransport()}
        onBackToEntry={onBackToEntry}
      />
    </StrictMode>,
  );
}

function onlySocket(): FakeWebSocket {
  const live = FakeWebSocket.live();
  expect(live).toHaveLength(1);
  return live[0] as FakeWebSocket;
}

async function goLive(): Promise<FakeWebSocket> {
  await advance(1);
  const socket = onlySocket();
  await act(async () => {
    socket.serverSend(connectedSnapshot(1));
  });
  return socket;
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeWebSocket.install();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("TableSession lifecycle: sockets, timers and stale controllers", () => {
  it('"Use here" clicked before the old socket\'s close arrives leaves exactly one live socket', async () => {
    mountReal();
    const first = await goLive();
    await act(async () => {
      first.serverSend({ type: "superseded" }); // terminal message; its close frame is still on the way
    });
    expect(screen.getByRole("button", { name: "Use here" })).toBeDefined();
    expect(first.readyState).toBe(1); // still open

    fireEvent.click(screen.getByRole("button", { name: "Use here" }));
    await advance(1);

    const second = onlySocket();
    expect(second).not.toBe(first);
    expect(first.readyState).toBe(3); // the old one was closed by the client
    expect(second.sentJson()[0]).toMatchObject({ type: "hello", credential: CREDENTIAL });
    expect(second.sentJson()).toHaveLength(1);
  });

  it("the closed old session's late events cannot disturb the new one", async () => {
    mountReal();
    const first = await goLive();
    await act(async () => {
      first.serverSend({ type: "superseded" });
      first.serverClose(4409);
    });
    await advance(1);
    fireEvent.click(screen.getByRole("button", { name: "Use here" }));
    await advance(1);
    const second = onlySocket();
    await act(async () => {
      second.serverSend(connectedSnapshot(2));
    });
    expect(screen.queryByText("Reconnecting…")).toBeNull();

    // Whatever the first socket's late events carry, the new session is untouched.
    await act(async () => {
      first.serverSend({ type: "left_table" });
    });
    await advance(10_000);

    expect(screen.queryByText("You left the table.")).toBeNull();
    expect(screen.queryByRole("button", { name: "Use here" })).toBeNull();
    expect(screen.queryByText("Reconnecting…")).toBeNull();
    expect(FakeWebSocket.live()).toEqual([second]);
  });

  it('two clicks on "Use here" in one batch still open a single socket', async () => {
    mountReal();
    const first = await goLive();
    await act(async () => {
      first.serverSend({ type: "superseded" });
      first.serverClose(4409);
    });
    await advance(1);

    const button = screen.getByRole("button", { name: "Use here" });
    const before = FakeWebSocket.instances.length;
    act(() => {
      button.click();
      button.click();
    });
    await advance(1);

    expect(FakeWebSocket.instances.length - before).toBe(1);
    onlySocket();
  });

  it("an old controller no longer wired to the store cannot clear the new session's credential", async () => {
    storeCredential(TABLE_ID, CREDENTIAL);
    const transports: MockTransport[] = [];
    render(
      <TableSession
        tableId={TABLE_ID}
        credential={CREDENTIAL}
        createTransport={() => {
          const transport = new MockTransport();
          transports.push(transport);
          return transport;
        }}
        onBackToEntry={() => {}}
      />,
    );
    const [oldTransport] = transports as [MockTransport];
    act(() => {
      oldTransport.emitOpen();
      oldTransport.emitMessage(connectedSnapshot(1));
      oldTransport.emitMessage({ type: "superseded" });
      oldTransport.emitClose(4409);
    });
    fireEvent.click(screen.getByRole("button", { name: "Use here" }));
    const newTransport = transports[1] as MockTransport;
    expect(newTransport).toBeDefined();
    expect(screen.getAllByText("Reconnecting…").length).toBeGreaterThan(0); // the new session is connecting

    // The old transport keeps talking: its frames must go nowhere. A
    // non-`connected` snapshot would flip a still-wired old controller to
    // "live", hiding the new session's banner; `left_table` would drop the credential.
    act(() => {
      oldTransport.emitMessage({
        type: "snapshot",
        revision: 99,
        cause: "command",
        view: snapshotView("snapshot.heads_up.preflop.actor.json"),
      });
      oldTransport.emitMessage({ type: "left_table" });
      oldTransport.emitClose(4410);
    });

    expect(readCredential(TABLE_ID)).toBe(CREDENTIAL);
    expect(screen.queryByText("You left the table.")).toBeNull();
    expect(screen.queryByRole("group", { name: "Actions" })).toBeNull(); // rev 99 never applied
    expect(screen.getAllByText("Reconnecting…").length).toBeGreaterThan(0); // still connecting

    act(() => {
      newTransport.emitOpen();
      newTransport.emitMessage(connectedSnapshot(2));
    });
    expect(screen.queryByText("Reconnecting…")).toBeNull();
    expect(screen.getByRole("button", { name: "Start game" })).toBeDefined();
  });

  it("unmounting during a reconnect backoff leaves no timer and opens no socket", async () => {
    const { unmount } = mountReal();
    const first = await goLive();
    await act(async () => {
      first.serverClose(1006);
    });
    await advance(1);
    expect(screen.getAllByText("Reconnecting…").length).toBeGreaterThan(0);
    const opened = FakeWebSocket.instances.length;

    unmount();
    await advance(60_000);

    expect(FakeWebSocket.instances).toHaveLength(opened);
    expect(FakeWebSocket.live()).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("unmounting with a command in flight clears its timeout and never reconnects", async () => {
    const { unmount } = mountReal();
    const socket = await goLive();
    fireEvent.click(screen.getByRole("button", { name: "Start game" }));
    expect(socket.sentJson().filter((frame) => frame.type === "command")).toHaveLength(1);
    expect(vi.getTimerCount()).toBeGreaterThan(0); // the 10 s command timeout
    const opened = FakeWebSocket.instances.length;

    unmount();
    await advance(60_000);

    expect(FakeWebSocket.instances).toHaveLength(opened);
    expect(FakeWebSocket.live()).toHaveLength(0);
    expect(vi.getTimerCount()).toBe(0);
  });

  it("re-renders and live snapshots never reconnect or reopen a socket", async () => {
    const { rerender } = mountReal();
    const socket = await goLive();
    const opened = FakeWebSocket.instances.length;

    for (let revision = 2; revision < 6; revision++) {
      await act(async () => {
        socket.serverSend({
          type: "snapshot",
          revision,
          cause: "command",
          view: snapshotView("snapshot.connected.not_started.json"),
        });
      });
      rerender(
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
    await advance(60_000);

    expect(FakeWebSocket.instances).toHaveLength(opened);
    expect(onlySocket()).toBe(socket);
    expect(socket.sentJson()).toHaveLength(1); // the hello, nothing else
  });

  it("a failed first connection is retried with a fresh hello, still under StrictMode", async () => {
    mountReal();
    // Both StrictMode setups made a socket; the surviving one fails before it opens.
    const survivor = FakeWebSocket.live()[0] as FakeWebSocket;
    expect(FakeWebSocket.live()).toHaveLength(1);
    await act(async () => {
      survivor.serverClose(1006);
    });
    await advance(1);
    expect(survivor.everOpened).toBe(false);
    expect(FakeWebSocket.live()).toHaveLength(0);
    expect(screen.getAllByText("Reconnecting…").length).toBeGreaterThan(0);

    await advance(8000);

    const retry = onlySocket();
    expect(retry).not.toBe(survivor);
    expect(retry.everOpened).toBe(true);
    expect(retry.sentJson()[0]).toMatchObject({ type: "hello", credential: CREDENTIAL });
    await act(async () => {
      retry.serverSend(connectedSnapshot(1));
    });
    expect(screen.queryByText("Reconnecting…")).toBeNull();
  });

  it("an unanswered command times out, reconnects with hello, and is never resent", async () => {
    mountReal();
    const first = await goLive();
    fireEvent.click(screen.getByRole("button", { name: "Start game" }));
    const commands = (socket: FakeWebSocket) =>
      socket.sentJson().filter((frame) => frame.type === "command");
    expect(commands(first)).toHaveLength(1);

    await advance(10_000); // the command timeout: outcome uncertain, the client closes
    await advance(1);
    expect(first.readyState).toBe(3);
    await advance(8000); // the reconnect backoff
    const second = onlySocket();
    expect(second).not.toBe(first);
    expect(second.sentJson()[0]).toMatchObject({ type: "hello" });

    // Until the connected snapshot reconciles, nothing can be sent.
    const start = screen.queryByRole("button", { name: "Start game" }) as HTMLButtonElement | null;
    if (start !== null) {
      expect(start.disabled).toBe(true);
      fireEvent.click(start);
    }
    expect(commands(second)).toHaveLength(0);

    await act(async () => {
      second.serverSend(connectedSnapshot(2));
    });
    await advance(30_000);
    expect(commands(second)).toHaveLength(0); // never retransmitted
    expect((screen.getByRole("button", { name: "Start game" }) as HTMLButtonElement).disabled).toBe(
      false,
    );
  });
});

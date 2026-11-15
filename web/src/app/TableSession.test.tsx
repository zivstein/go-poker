import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { MockTransport } from "../connection/MockTransport";
import { readCredential, storeCredential } from "../entry/credentialStorage";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { TableSession } from "./TableSession";

function view(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

function connectedSnapshot(revision: number) {
  return {
    type: "snapshot",
    revision,
    cause: "connected",
    view: view("snapshot.connected.not_started.json"),
  };
}

afterEach(() => {
  sessionStorage.clear();
});

describe("TableSession credential lifecycle (Brief §2 item 6: 4401 and 4410 delete it)", () => {
  it("drops the stored credential once the connection ends in left_table (4410)", async () => {
    const tableId = "table-left";
    storeCredential(tableId, "cred-1");
    const transport = new MockTransport();
    render(
      <TableSession
        tableId={tableId}
        credential="cred-1"
        createTransport={() => transport}
        onBackToEntry={() => {}}
      />,
    );
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    expect(readCredential(tableId)).toBe("cred-1");

    transport.emitMessage({ type: "left_table" });
    transport.emitClose(4410);

    expect(await screen.findByText("You left the table.")).toBeDefined();
    expect(readCredential(tableId)).toBeNull();
  });

  it("drops the stored credential on AUTH_FAILED (4401)", async () => {
    const tableId = "table-auth-failed";
    storeCredential(tableId, "cred-2");
    const transport = new MockTransport();
    render(
      <TableSession
        tableId={tableId}
        credential="cred-2"
        createTransport={() => transport}
        onBackToEntry={() => {}}
      />,
    );
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    expect(readCredential(tableId)).toBe("cred-2");

    transport.emitMessage({ type: "error", request_id: null, code: "AUTH_FAILED", message: "x" });
    transport.emitClose(4401);

    expect(await screen.findByText("Your session ended.")).toBeDefined();
    expect(readCredential(tableId)).toBeNull();
  });

  it("keeps the stored credential through a reconnect (not a terminal close)", () => {
    const tableId = "table-reconnect";
    storeCredential(tableId, "cred-3");
    const transport = new MockTransport();
    render(
      <TableSession
        tableId={tableId}
        credential="cred-3"
        createTransport={() => transport}
        onBackToEntry={() => {}}
      />,
    );
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitClose(1006); // an ordinary drop: reconnect, not terminal
    expect(readCredential(tableId)).toBe("cred-3");
  });

  it("does not drop the credential on supersede (4409): 'Use here' needs it", () => {
    const tableId = "table-superseded";
    storeCredential(tableId, "cred-4");
    const transport = new MockTransport();
    render(
      <TableSession
        tableId={tableId}
        credential="cred-4"
        createTransport={() => transport}
        onBackToEntry={() => {}}
      />,
    );
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitMessage({ type: "superseded" });
    transport.emitClose(4409);
    expect(readCredential(tableId)).toBe("cred-4");
  });

  it('"Use here" actually reopens the connection after a supersede (ADR 0009 §12: 4409 -> "Use here")', async () => {
    const tableId = "table-use-here";
    storeCredential(tableId, "cred-5");
    const transport = new MockTransport();
    render(
      <TableSession
        tableId={tableId}
        credential="cred-5"
        createTransport={() => transport}
        onBackToEntry={() => {}}
      />,
    );
    transport.emitOpen();
    transport.emitMessage(connectedSnapshot(1));
    transport.emitMessage({ type: "superseded" });
    transport.emitClose(4409);
    expect(await screen.findByRole("button", { name: "Use here" })).toBeDefined();
    expect(transport.openedUrls).toHaveLength(1); // only the original connect so far

    await userEvent.click(screen.getByRole("button", { name: "Use here" }));

    // Clicking "Use here" must open a new connection (a fresh `hello`), not
    // silently do nothing because the controller already latched terminal.
    expect(transport.openedUrls.length).toBeGreaterThan(1);
  });
});

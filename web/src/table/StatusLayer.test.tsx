import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ConnectionStatus } from "../connection/ConnectionController";
import { StatusLayer } from "./StatusLayer";

function status(overrides: Partial<ConnectionStatus>): ConnectionStatus {
  return {
    phase: "idle",
    pending: false,
    reconciling: false,
    attempt: 0,
    reason: null,
    ...overrides,
  };
}

function noop() {
  // intentionally empty
}

describe("StatusLayer terminal states (ADR 0009 §12)", () => {
  it('shows "Please reload." for a protocol mismatch, with no action', () => {
    render(
      <StatusLayer
        status={status({ phase: "closed", reason: "protocol_mismatch" })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByText("Please reload.")).toBeDefined();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it('offers "Use here" on supersede, which reconnects and supersedes the other connection', async () => {
    const onUseHere = vi.fn();
    render(
      <StatusLayer
        status={status({ phase: "closed", reason: "superseded" })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={onUseHere}
        onBackToEntry={noop}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Use here" }));
    expect(onUseHere).toHaveBeenCalledOnce();
  });

  it('shows "You left the table." for an explicit left_table close', () => {
    render(
      <StatusLayer
        status={status({ phase: "closed", reason: "left_table" })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByText("You left the table.")).toBeDefined();
  });

  it('treats AUTH_FAILED after an uncertain leave as left: "You left the table."', () => {
    render(
      <StatusLayer
        status={status({ phase: "closed", reason: "auth_failed" })}
        lastRejection={null}
        wasLeaving={true}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByText("You left the table.")).toBeDefined();
  });

  it('shows a different message for AUTH_FAILED unrelated to leaving: "Your session ended."', () => {
    render(
      <StatusLayer
        status={status({ phase: "closed", reason: "auth_failed" })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByText("Your session ended.")).toBeDefined();
    expect(screen.queryByText("You left the table.")).toBeNull();
  });

  it("shows an error screen for table_failed", () => {
    render(
      <StatusLayer
        status={status({ phase: "closed", reason: "table_failed" })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByText("This table has failed.")).toBeDefined();
  });

  it('every terminal screen except "Please reload" offers a way forward', () => {
    for (const reason of ["superseded", "left_table", "auth_failed", "table_failed"] as const) {
      const { unmount } = render(
        <StatusLayer
          status={status({ phase: "closed", reason })}
          lastRejection={null}
          wasLeaving={false}
          onDismissRejection={noop}
          onUseHere={noop}
          onBackToEntry={noop}
        />,
      );
      expect(screen.getByRole("button")).toBeDefined();
      unmount();
    }
  });
});

describe("StatusLayer live-phase banners and rejections", () => {
  it("shows a reconnecting banner while reconnecting", () => {
    render(
      <StatusLayer
        status={status({ phase: "reconnecting", attempt: 2 })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe("Reconnecting…");
  });

  it("shows a reconciling banner once live but still locked (the uncertain-outcome lock)", () => {
    render(
      <StatusLayer
        status={status({ phase: "live", reconciling: true })}
        lastRejection={null}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByRole("status").textContent).toBe("No response — reconnecting");
  });

  it("shows STALE_REVISION as a quiet status notice, not an alert", () => {
    render(
      <StatusLayer
        status={status({ phase: "live" })}
        lastRejection={{ code: "STALE_REVISION", message: "x" }}
        wasLeaving={false}
        onDismissRejection={noop}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByText("Table updated.")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows a non-stale rejection as an alert toast, dismissible", async () => {
    const onDismiss = vi.fn();
    render(
      <StatusLayer
        status={status({ phase: "live" })}
        lastRejection={{ code: "NOT_YOUR_TURN", message: "x" }}
        wasLeaving={false}
        onDismissRejection={onDismiss}
        onUseHere={noop}
        onBackToEntry={noop}
      />,
    );
    expect(screen.getByRole("alert").textContent).toContain("It isn't your turn.");
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MockTransport } from "../connection/MockTransport";
import type { TableView } from "../protocol/types";
import { actorView, fixtureView, laterDecision, unrelatedTransition } from "../table/testViews";
import { GUARD_MS } from "../table/useDecisionGuard";
import { TableSession } from "./TableSession";

// A1 review M1 end to end: real controller, store, presentation queue and
// dock. The shared revision changes for many reasons; only the game state
// decides what is a new decision.

function snapshot(revision: number, cause: string, view: TableView) {
  return { type: "snapshot", revision, cause, view };
}

function mount() {
  const transport = new MockTransport();
  render(
    <TableSession
      tableId="t1"
      credential="c1"
      createTransport={() => transport}
      onBackToEntry={() => {}}
    />,
  );
  act(() => {
    transport.emitOpen();
    transport.emitMessage(snapshot(3, "connected", actorView()));
  });
  act(() => vi.advanceTimersByTime(GUARD_MS));
  return transport;
}

const field = () => screen.getByRole("textbox", { name: "Bet amount (exact)" }) as HTMLInputElement;
const call = () => screen.getByRole("button", { name: "Call $5" }) as HTMLButtonElement;

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});

describe("TableSession: decision continuity across shared revisions", () => {
  it("a revision bump with an unchanged decision keeps the draft, focus and the released guard", () => {
    const transport = mount();
    const input = field();
    input.focus();
    fireEvent.change(input, { target: { value: "350" } });

    act(() => {
      transport.emitMessage(snapshot(4, "command", unrelatedTransition(actorView())));
    });
    expect(field()).toBe(input);
    expect(input.value).toBe("350");
    expect(document.activeElement).toBe(input);
    expect(input.disabled).toBe(false);
    expect(call().getAttribute("aria-disabled")).toBeNull();

    // A private update at an equal revision changes nothing either.
    act(() => {
      transport.emitMessage(snapshot(4, "private", unrelatedTransition(actorView())));
    });
    expect(field().value).toBe("350");
  });

  it("the command still carries the latest revision after such a bump", () => {
    const transport = mount();
    act(() => {
      transport.emitMessage(snapshot(4, "command", unrelatedTransition(actorView())));
    });
    fireEvent.change(field(), { target: { value: "350" } });
    fireEvent.click(screen.getByRole("button", { name: "Raise to $350" }));
    const sent = transport.lastSent<{ expected_revision: number; args: unknown }>();
    expect(sent.expected_revision).toBe(4);
    expect(sent.args).toEqual({ action: "raise", target: 350 });
  });

  it("the hero's turn returning with identical legal actions is a new decision", () => {
    const transport = mount();
    fireEvent.change(field(), { target: { value: "350" } });
    act(() => {
      transport.emitMessage(
        snapshot(4, "command", fixtureView("snapshot.heads_up.preflop.waiting.json")),
      );
    });
    act(() => {
      transport.emitMessage(snapshot(5, "command", laterDecision(actorView())));
    });
    expect(field().value).toBe("20");
    expect(call().getAttribute("aria-disabled")).toBe("true");
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(call().getAttribute("aria-disabled")).toBeNull();
  });

  it("a hand-boundary snapshot makes an otherwise identical decision a new one", () => {
    const transport = mount();
    fireEvent.change(field(), { target: { value: "350" } });
    act(() => {
      transport.emitMessage(snapshot(4, "hand_boundary", actorView()));
    });
    expect(field().value).toBe("20");
    expect(call().getAttribute("aria-disabled")).toBe("true");
  });

  it("a reconnect that delivers a newer revision over the same decision keeps the draft but guards again", () => {
    const transport = mount();
    const input = field();
    fireEvent.change(input, { target: { value: "350" } });
    act(() => {
      transport.emitClose(1006);
    });
    expect(field().disabled).toBe(true);
    act(() => vi.advanceTimersByTime(60_000)); // the backoff elapses and the controller reconnects
    act(() => {
      transport.emitOpen();
      transport.emitMessage(snapshot(7, "connected", unrelatedTransition(actorView())));
    });
    expect(field()).toBe(input);
    expect(input.value).toBe("350");
    expect(input.disabled).toBe(false);
    expect(call().getAttribute("aria-disabled")).toBe("true");
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(call().getAttribute("aria-disabled")).toBeNull();
  });

  it("controls are truly disabled while reconnecting: nothing is sent, pressed or pending", () => {
    const transport = mount();
    act(() => {
      transport.emitClose(1006);
    });
    const sentBefore = transport.sentFrames.length;
    fireEvent.click(call()); // truly disabled while reconnecting
    expect(transport.sentFrames.length).toBe(sentBefore);
    expect(screen.queryByText(/^Sending/)).toBeNull();
  });
});

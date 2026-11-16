import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { leaveCopy } from "./leaveCopy";
import { TableHeader } from "./TableHeader";

// jsdom implements <dialog> without showModal()/close() (jsdom 30): a local
// stand-in, so these tests check our logic. The native modal behavior (inert
// page, top layer, Esc) is validated in real browsers.
const proto = HTMLDialogElement.prototype as {
  showModal?: () => void;
  close?: (value?: string) => void;
};
const original = { showModal: proto.showModal, close: proto.close };
beforeEach(() => {
  proto.showModal = function (this: HTMLDialogElement) {
    this.setAttribute("open", "");
  };
  proto.close = function (this: HTMLDialogElement) {
    if (!this.hasAttribute("open")) return;
    this.removeAttribute("open");
    this.dispatchEvent(new Event("close"));
  };
});
afterEach(() => {
  proto.showModal = original.showModal;
  proto.close = original.close;
});

const LIVE: ConnectionStatus = {
  phase: "live",
  pending: false,
  reconciling: false,
  attempt: 0,
  reason: null,
};

function view(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

function header(v: TableView, onLeave = vi.fn(() => true), status: ConnectionStatus = LIVE) {
  return <TableHeader view={v} status={status} onLeave={onLeave} />;
}

function openLeave() {
  fireEvent.click(screen.getByRole("button", { name: /^Table/ }));
  fireEvent.click(screen.getByRole("button", { name: "Leave table…" }));
}

describe("Table menu", () => {
  it("is a disclosure: closed by default, toggled, closed by Esc with focus back on it", () => {
    render(header(view("snapshot.heads_up.preflop.waiting.json")));
    const trigger = screen.getByRole("button", { name: /^Table/ });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("button", { name: "Leave table…" })).toBeNull();
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    fireEvent.keyDown(screen.getByRole("button", { name: "Leave table…" }), { key: "Escape" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(trigger);
  });

  it("disables Leave while a leave is pending, and says so", () => {
    const v = view("snapshot.heads_up.preflop.waiting.json");
    render(header({ ...v, you: { ...v.you, pending_leave: true } }));
    fireEvent.click(screen.getByRole("button", { name: /^Table/ }));
    expect(
      (screen.getByRole("button", { name: "Leave pending" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    expect(screen.getByText("Leaving after this hand")).toBeDefined();
  });

  it("disables Leave while a command is in flight or the connection is not live", () => {
    const v = view("snapshot.heads_up.preflop.waiting.json");
    for (const status of [
      { ...LIVE, pending: true },
      { ...LIVE, reconciling: true },
      { ...LIVE, phase: "reconnecting" as const },
    ]) {
      const { unmount } = render(
        header(
          v,
          vi.fn(() => true),
          status,
        ),
      );
      fireEvent.click(screen.getByRole("button", { name: /^Table/ }));
      expect(
        (screen.getByRole("button", { name: "Leave table…" }) as HTMLButtonElement).disabled,
      ).toBe(true);
      unmount();
    }
  });
});

describe("Leave confirmation", () => {
  it("opens a modal dialog with Stay focused first", () => {
    render(header(view("snapshot.heads_up.preflop.waiting.json")));
    openLeave();
    const dialog = screen.getByRole("dialog", { name: "Leave this table?" });
    expect(dialog.hasAttribute("open")).toBe(true);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Stay" }));
  });

  it("Stay sends nothing and returns focus to the menu", () => {
    const onLeave = vi.fn();
    render(header(view("snapshot.heads_up.preflop.waiting.json"), onLeave));
    openLeave();
    fireEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onLeave).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /^Table/ }));
  });

  it("Esc (the dialog's cancel and close) counts as Stay", () => {
    const onLeave = vi.fn();
    render(header(view("snapshot.heads_up.preflop.waiting.json"), onLeave));
    openLeave();
    const dialog = screen.getByRole("dialog") as HTMLDialogElement;
    dialog.close(); // what the browser does on Esc after `cancel`
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(onLeave).not.toHaveBeenCalled();
  });

  it("Leave table sends exactly one leave, even when pressed repeatedly", () => {
    const onLeave = vi.fn(() => true);
    render(header(view("snapshot.heads_up.preflop.waiting.json"), onLeave));
    openLeave();
    const leave = screen.getByRole("button", { name: "Leave table" });
    fireEvent.click(leave);
    fireEvent.click(leave);
    expect(onLeave).toHaveBeenCalledOnce();
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("Leave confirmation: a refused or unavailable send (M4)", () => {
  const waiting = () => view("snapshot.heads_up.preflop.waiting.json");
  const UNAVAILABLE = /Can't leave right now/;
  const leaveButton = () => screen.getByRole("button", { name: "Leave table" });

  it("a refused send keeps the dialog open with an explicit message, and can be retried", () => {
    const onLeave = vi.fn(() => false);
    render(header(waiting(), onLeave));
    openLeave();
    fireEvent.click(leaveButton());
    expect(screen.getByRole("dialog")).toBeDefined();
    expect(screen.getByRole("alert").textContent).toMatch(UNAVAILABLE);
    expect(onLeave).toHaveBeenCalledOnce();
    // Nothing claims the player left, and the double-submit guard is not stuck.
    onLeave.mockReturnValue(true);
    const leave = leaveButton();
    fireEvent.click(leave);
    fireEvent.click(leave);
    expect(onLeave).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a connection lost while the dialog is open: confirming sends nothing and says why", () => {
    const onLeave = vi.fn(() => true);
    const v = waiting();
    const { rerender } = render(header(v, onLeave));
    openLeave();
    rerender(header(v, onLeave, { ...LIVE, phase: "reconnecting" }));
    expect(screen.getByRole("alert").textContent).toMatch(UNAVAILABLE);
    expect(leaveButton().getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(leaveButton());
    expect(onLeave).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it.each([
    ["a command in flight", { ...LIVE, pending: true }],
    ["an uncertain outcome", { ...LIVE, reconciling: true }],
  ])("%s while the dialog is open: confirming sends nothing", (_name, status) => {
    const onLeave = vi.fn(() => true);
    const v = waiting();
    const { rerender } = render(header(v, onLeave));
    openLeave();
    rerender(header(v, onLeave, status));
    fireEvent.click(leaveButton());
    expect(onLeave).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toBeDefined();
  });

  it("the message clears when the connection is usable again, and Leave then works once", () => {
    const onLeave = vi.fn(() => true);
    const v = waiting();
    const { rerender } = render(header(v, onLeave));
    openLeave();
    rerender(header(v, onLeave, { ...LIVE, phase: "reconnecting" }));
    expect(screen.queryByRole("alert")).not.toBeNull();
    rerender(header(v, onLeave));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(leaveButton().getAttribute("aria-disabled")).toBeNull();
    fireEvent.click(leaveButton());
    expect(onLeave).toHaveBeenCalledOnce();
  });

  it("keeps focus inside the dialog, and Stay and Esc still close it with focus back on the menu", () => {
    const v = waiting();
    const { rerender } = render(
      header(
        v,
        vi.fn(() => true),
      ),
    );
    openLeave();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Stay" }));
    rerender(
      header(
        v,
        vi.fn(() => true),
        { ...LIVE, phase: "reconnecting" },
      ),
    );
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Stay" }));
    (screen.getByRole("dialog") as HTMLDialogElement).close();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /^Table/ }));
  });
});

describe("Leave confirmation: our own closes do not depend on the native close event", () => {
  // Observed in a browser smoke test: `dialog.close()` from a click handler
  // did not deliver `close`, which left a closed dialog mounted and the next
  // "Leave table…" inert.
  beforeEach(() => {
    proto.close = function (this: HTMLDialogElement) {
      this.removeAttribute("open");
    };
  });

  it("Stay unmounts the dialog, returns focus to the menu, and the menu can reopen it", () => {
    render(header(view("snapshot.heads_up.preflop.waiting.json")));
    openLeave();
    fireEvent.click(screen.getByRole("button", { name: "Stay" }));
    expect(document.querySelector("dialog")).toBeNull(); // unmounted, not just closed
    expect(document.activeElement).toBe(screen.getByRole("button", { name: /^Table/ }));
    openLeave();
    expect(screen.getByRole("dialog").hasAttribute("open")).toBe(true);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Stay" }));
  });

  it("a sent leave unmounts the dialog once", () => {
    const onLeave = vi.fn(() => true);
    render(header(view("snapshot.heads_up.preflop.waiting.json"), onLeave));
    openLeave();
    fireEvent.click(screen.getByRole("button", { name: "Leave table" }));
    expect(onLeave).toHaveBeenCalledOnce();
    expect(document.querySelector("dialog")).toBeNull(); // unmounted, not just closed
  });
});

describe("leaveCopy", () => {
  it("with no hand: gives up the seat, cannot be undone", () => {
    const v = view("snapshot.connected.not_started.json");
    expect(leaveCopy({ ...v, you: { ...v.you, is_host: false } })).toEqual([
      `You'll give up seat ${v.you.seat}. Leaving can't be undone or cancelled.`,
    ]);
  });

  it("in the hand, not your turn: automatic check/fold and muck, then leave", () => {
    const lines = leaveCopy(view("snapshot.heads_up.preflop.waiting.json"));
    expect(lines.join(" ")).toContain("checks or folds for you on your turns");
    expect(lines.join(" ")).toContain("You'll leave when the hand ends.");
    expect(lines.join(" ")).not.toContain("It's your turn");
  });

  it("in the hand, your turn: checks if it can, otherwise folds, right away", () => {
    const lines = leaveCopy(view("snapshot.heads_up.preflop.actor.json"));
    expect(lines).toContain(
      "It's your turn: leaving now checks if you can, otherwise folds, right away.",
    );
  });

  it("at your showdown decision: mucks right away", () => {
    const lines = leaveCopy(view("snapshot.heads_up.showdown_decision.json"));
    expect(lines).toContain(
      "It's your turn to show or muck: leaving now mucks your cards right away.",
    );
  });

  it("folded: only leaves when the hand ends", () => {
    const v = view("snapshot.heads_up.preflop.waiting.json");
    const hand = v.hand;
    if (hand === null) throw new Error("fixture has no hand");
    const folded: TableView = {
      ...v,
      hand: {
        ...hand,
        participants: hand.participants.map((p) =>
          p.seat === v.you.seat ? { ...p, folded: true, has_live_cards: false } : p,
        ),
      },
    };
    expect(leaveCopy(folded)).toContain("You'll leave when this hand ends.");
  });

  it("a host with others seated: the host role passes on", () => {
    const v = view("snapshot.heads_up.preflop.waiting.json");
    expect(leaveCopy({ ...v, you: { ...v.you, is_host: true } })).toContain(
      "The host role passes to another player.",
    );
    expect(leaveCopy({ ...v, you: { ...v.you, is_host: false } })).not.toContain(
      "The host role passes to another player.",
    );
  });

  it("never promises a rejoin or mentions chips", () => {
    for (const fixture of [
      "snapshot.connected.not_started.json",
      "snapshot.heads_up.preflop.actor.json",
      "snapshot.heads_up.preflop.waiting.json",
    ]) {
      const text = leaveCopy(view(fixture)).join(" ").toLowerCase();
      expect(text).not.toMatch(/rejoin|come back|chips|wallet/);
    }
  });
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { ActArgs, LegalActions, ShowdownDecision, TableView } from "../protocol/types";
import type { LastRejection } from "../session/store";
import { readFixtureJson } from "../testing/fixtures";
import { ActionDock } from "./ActionDock";
import { laterDecision } from "./testViews";
import { GUARD_MS } from "./useDecisionGuard";

// snapshot.heads_up.preflop.actor: call $5, raise range 20 .. 1,000.

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

function actorView(): TableView {
  return view("snapshot.heads_up.preflop.actor.json");
}

/** The actor's decision with Check free (the big blind's option). */
function checkFreeView(): TableView {
  const v = actorView();
  const hand = v.hand;
  if (hand === null || hand.legal_actions === null) throw new Error("fixture has no decision");
  const legal: LegalActions = {
    ...hand.legal_actions,
    can_check: true,
    can_call: false,
    amount_owed: 0,
    call_amount: 0,
  };
  return { ...v, hand: { ...hand, legal_actions: legal } };
}

interface DockOptions {
  view?: TableView;
  status?: ConnectionStatus;
  lastRejection?: LastRejection | null;
  handEpoch?: number;
  guardMs?: number;
  onAct?: (args: ActArgs) => boolean;
  onShowdownDecision?: (decision: ShowdownDecision) => boolean;
  onStartGame?: () => boolean;
  onDismissRejection?: () => void;
}

function dock(options: DockOptions = {}) {
  return (
    <ActionDock
      view={options.view ?? actorView()}
      status={options.status ?? LIVE}
      lastRejection={options.lastRejection ?? null}
      handEpoch={options.handEpoch}
      guardMs={options.guardMs ?? 0}
      onAct={options.onAct ?? vi.fn(() => true)}
      onShowdownDecision={options.onShowdownDecision ?? vi.fn(() => true)}
      onStartGame={options.onStartGame ?? vi.fn(() => true)}
      onDismissRejection={options.onDismissRejection ?? vi.fn()}
    />
  );
}

function field(): HTMLInputElement {
  return screen.getByRole("textbox", { name: "Bet amount (exact)" }) as HTMLInputElement;
}

function button(name: string | RegExp): HTMLButtonElement {
  return screen.getByRole("button", { name }) as HTMLButtonElement;
}

afterEach(() => {
  vi.useRealTimers();
});

describe("ActionDock frame: one stable dock in every state", () => {
  it.each([
    ["snapshot.heads_up.preflop.actor.json", "Your turn · To call $5"],
    ["snapshot.heads_up.preflop.waiting.json", /^Waiting for /],
    ["snapshot.heads_up.showdown_decision.json", "Your turn · Show or muck"],
    ["snapshot.heads_up.settled.opponent_mucked.json", "Hand complete · Next hand starting"],
    ["snapshot.waiting_for_players.json", "Waiting for players"],
    ["snapshot.reset.waiting_hand_null.json", "Waiting for players"],
    ["snapshot.nine_seats.actor.json", /^Your turn/],
  ])("%s renders the same frame with its status line", (fixture, statusText) => {
    render(dock({ view: view(fixture) }));
    const frame = screen.getByRole("region", { name: "Action dock" });
    expect(frame.children).toHaveLength(2); // the status row and the controls row
    expect(screen.getByText(statusText)).toBeDefined();
  });

  it("offers Start game to the host only, and never inside the decision group", () => {
    const notStarted = view("snapshot.connected.not_started.json");
    const onStartGame = vi.fn();
    const { rerender } = render(
      dock({ view: { ...notStarted, you: { ...notStarted.you, is_host: true } }, onStartGame }),
    );
    fireEvent.click(button("Start game"));
    expect(onStartGame).toHaveBeenCalledOnce();
    expect(screen.queryByRole("group", { name: "Actions" })).toBeNull();
    rerender(dock({ view: { ...notStarted, you: { ...notStarted.you, is_host: false } } }));
    expect(screen.queryByRole("button", { name: "Start game" })).toBeNull();
    expect(screen.getByText("Waiting for the host to start")).toBeDefined();
  });

  it("shows the pending leave without offering anything to cancel it", () => {
    const v = view("snapshot.heads_up.preflop.waiting.json");
    render(dock({ view: { ...v, you: { ...v.you, pending_leave: true } } }));
    expect(screen.getByText("Leaving after this hand")).toBeDefined();
    expect(screen.queryByRole("button", { name: /cancel/i })).toBeNull();
  });
});

describe("ActionDock labels: what the label says is what is sent", () => {
  it("labels and sends Call, and an all-in call as all-in", () => {
    const onAct = vi.fn();
    const { unmount } = render(dock({ onAct }));
    fireEvent.click(button("Call $5"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "call", target: null });
    unmount();
    render(dock({ view: view("snapshot.call_is_all_in.decision.json") }));
    expect(button(/Call .*\(All-in\)/)).toBeDefined();
  });

  it("sends exactly the commit label's amount at min, mid and max", () => {
    const onAct = vi.fn();
    render(dock({ onAct }));
    for (const [text, label] of [
      ["20", "Raise to $20"],
      ["437", "Raise to $437"],
      ["1000", "All-in $1,000"],
    ] as const) {
      onAct.mockClear();
      fireEvent.change(field(), { target: { value: text } });
      fireEvent.click(button(label));
      expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: Number(text) });
    }
  });

  it("the slider drives the draft and the label", () => {
    const onAct = vi.fn();
    render(dock({ onAct }));
    fireEvent.change(screen.getByRole("slider", { name: "Bet amount" }), {
      target: { value: "300" },
    });
    expect(field().value).toBe("300");
    fireEvent.click(button("Raise to $300"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 300 });
  });

  it("the slider stays on the last valid amount while the field is invalid", () => {
    render(dock());
    const slider = screen.getByRole("slider", { name: "Bet amount" }) as HTMLInputElement;
    fireEvent.change(field(), { target: { value: "300" } });
    fireEvent.change(field(), { target: { value: "5000" } });
    expect(slider.value).toBe("300");
  });

  it("shows the server's range as a hint, tied to the field", () => {
    render(dock());
    const hint = screen.getByText("Min $20 · Max $1,000");
    expect(field().getAttribute("aria-describedby")).toBe(hint.id);
  });
});

describe("ActionDock Min and Max (D2): draft selectors only", () => {
  it("set the exact server bounds and never send a command", () => {
    const onAct = vi.fn();
    render(dock({ onAct }));
    fireEvent.click(button("Max"));
    expect(field().value).toBe("1000");
    expect(button("All-in $1,000")).toBeDefined();
    fireEvent.click(button("Min"));
    expect(field().value).toBe("20");
    expect(onAct).not.toHaveBeenCalled();
  });

  it("make an invalid draft valid again", () => {
    render(dock());
    fireEvent.change(field(), { target: { value: "5000" } });
    expect(button("Raise to").disabled).toBe(true);
    fireEvent.click(button("Max"));
    expect(button("All-in $1,000").disabled).toBe(false);
  });
});

describe("ActionDock keyboard", () => {
  it("Enter in the field commits a valid draft once, and an invalid one never", () => {
    const onAct = vi.fn();
    render(dock({ onAct }));
    fireEvent.change(field(), { target: { value: "150" } });
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 150 });
    onAct.mockClear();
    fireEvent.change(field(), { target: { value: "9" } });
    fireEvent.keyDown(field(), { key: "Enter" });
    expect(onAct).not.toHaveBeenCalled();
  });

  it("a held Enter (key repeat) never sends", () => {
    const onAct = vi.fn();
    render(dock({ onAct }));
    fireEvent.keyDown(field(), { key: "Enter", repeat: true });
    expect(onAct).not.toHaveBeenCalled();
    // On a button, a repeated Enter's default activation is cancelled.
    expect(fireEvent.keyDown(button("Call $5"), { key: "Enter", repeat: true })).toBe(false);
    expect(fireEvent.keyDown(button("Fold"), { key: " ", repeat: true })).toBe(false);
  });

  it("Esc in the field resets the draft to the minimum", () => {
    render(dock());
    fireEvent.change(field(), { target: { value: "5000" } });
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(field().value).toBe("20");
  });

  it("does not take focus when a turn arrives", () => {
    render(dock());
    expect(document.activeElement).toBe(document.body);
  });
});

describe("ActionDock turn-arrival guard (AM3)", () => {
  it("drops activations for 350 ms, never sends them later, then works", () => {
    vi.useFakeTimers();
    const onAct = vi.fn();
    render(dock({ onAct, guardMs: GUARD_MS }));
    fireEvent.click(button("Call $5"));
    act(() => vi.advanceTimersByTime(GUARD_MS - 1));
    fireEvent.click(button("Call $5"));
    fireEvent.keyDown(field(), { key: "Enter" });
    act(() => vi.advanceTimersByTime(5000));
    expect(onAct).not.toHaveBeenCalled();
    fireEvent.click(button("Call $5"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "call", target: null });
  });

  it("guards from the first render with aria-disabled, never native disabled", () => {
    vi.useFakeTimers();
    render(dock({ guardMs: GUARD_MS }));
    const call = button("Call $5");
    expect(call.disabled).toBe(false);
    expect(call.getAttribute("aria-disabled")).toBe("true");
    expect(screen.getByRole("region", { name: "Action dock" }).dataset.arming).toBe("true");
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(button("Call $5").getAttribute("aria-disabled")).toBeNull();
  });

  it("re-arms for a new decision and after a reconnect, but not after a rejection", () => {
    vi.useFakeTimers();
    const first = actorView();
    const { rerender } = render(dock({ guardMs: GUARD_MS, view: first }));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(button("Call $5").getAttribute("aria-disabled")).toBeNull();

    // A command and its rejection: same decision, no re-arm.
    rerender(dock({ guardMs: GUARD_MS, view: first, status: { ...LIVE, pending: true } }));
    rerender(
      dock({
        guardMs: GUARD_MS,
        view: first,
        lastRejection: { code: "ILLEGAL_ACTION", message: "x" },
      }),
    );
    expect(button("Call $5").getAttribute("aria-disabled")).toBeNull();

    // A reconnect: the same decision becomes actionable again.
    rerender(dock({ guardMs: GUARD_MS, view: first, status: { ...LIVE, phase: "reconnecting" } }));
    rerender(dock({ guardMs: GUARD_MS, view: first }));
    expect(button("Call $5").getAttribute("aria-disabled")).toBe("true");
    act(() => vi.advanceTimersByTime(GUARD_MS));

    // A new decision, even with identical legal actions.
    rerender(dock({ guardMs: GUARD_MS, view: laterDecision(first) }));
    expect(button("Call $5").getAttribute("aria-disabled")).toBe("true");
  });

  it("does not guard Start game", () => {
    vi.useFakeTimers();
    const notStarted = view("snapshot.connected.not_started.json");
    const onStartGame = vi.fn();
    render(
      dock({
        view: { ...notStarted, you: { ...notStarted.you, is_host: true } },
        guardMs: GUARD_MS,
        onStartGame,
      }),
    );
    fireEvent.click(button("Start game"));
    expect(onStartGame).toHaveBeenCalledOnce();
  });
});

describe("ActionDock Fold confirmation when Check is free (D3)", () => {
  it("facing a bet, Fold is one press", () => {
    const onAct = vi.fn();
    render(dock({ onAct }));
    fireEvent.click(button("Fold"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "fold", target: null });
  });

  it("with Check free, the first press arms and sends nothing; a later second press folds once", () => {
    vi.useFakeTimers();
    const onAct = vi.fn();
    render(dock({ view: checkFreeView(), onAct }));
    fireEvent.click(button("Fold"));
    expect(onAct).not.toHaveBeenCalled();
    const confirm = button("Confirm fold");
    expect(confirm.getAttribute("aria-describedby")).toBeTruthy();
    expect(
      screen.getByText(/Check is free\. Press Fold again to fold, or Esc to cancel\./),
    ).toBeDefined();
    act(() => vi.advanceTimersByTime(GUARD_MS));
    fireEvent.click(button("Confirm fold"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "fold", target: null });
  });

  it("a double- or triple-click never folds", () => {
    vi.useFakeTimers();
    const onAct = vi.fn();
    render(dock({ view: checkFreeView(), onAct }));
    fireEvent.click(button("Fold"));
    fireEvent.click(button("Confirm fold"));
    act(() => vi.advanceTimersByTime(100));
    fireEvent.click(button("Confirm fold"));
    expect(onAct).not.toHaveBeenCalled();
  });

  it("Esc, the window lapsing and another control each disarm it with no command", () => {
    vi.useFakeTimers();
    const onAct = vi.fn();
    render(dock({ view: checkFreeView(), onAct }));

    fireEvent.click(button("Fold"));
    fireEvent.keyDown(button("Confirm fold"), { key: "Escape" });
    expect(button("Fold")).toBeDefined();

    fireEvent.click(button("Fold"));
    act(() => vi.advanceTimersByTime(4000));
    expect(button("Fold")).toBeDefined();

    fireEvent.click(button("Fold"));
    fireEvent.click(button("Max"));
    expect(button("Fold")).toBeDefined();
    expect(onAct).not.toHaveBeenCalled();
  });

  it("Check while armed sends one check and disarms", () => {
    const onAct = vi.fn();
    render(dock({ view: checkFreeView(), onAct }));
    fireEvent.click(button("Fold"));
    fireEvent.click(button("Check"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "check", target: null });
    expect(button("Fold")).toBeDefined();
  });

  it("a held Space or Enter never confirms a fold", () => {
    vi.useFakeTimers();
    const onAct = vi.fn();
    render(dock({ view: checkFreeView(), onAct }));
    fireEvent.click(button("Fold"));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(fireEvent.keyDown(button("Confirm fold"), { key: "Enter", repeat: true })).toBe(false);
    expect(onAct).not.toHaveBeenCalled();
  });

  it("a new decision starts disarmed", () => {
    const { rerender } = render(dock({ view: checkFreeView() }));
    fireEvent.click(button("Fold"));
    expect(button("Confirm fold")).toBeDefined();
    rerender(dock({ view: laterDecision(checkFreeView()) }));
    expect(button("Fold")).toBeDefined();
  });
});

describe("ActionDock pending command", () => {
  it("disables every control at once and marks the pressed one busy, keeping its name", () => {
    const onAct = vi.fn(() => true);
    const { rerender } = render(dock({ onAct }));
    fireEvent.click(button("Raise to $20"));
    rerender(dock({ onAct, status: { ...LIVE, pending: true } }));
    const pressed = button("Raise to $20");
    expect(pressed.getAttribute("aria-busy")).toBe("true");
    expect(pressed.disabled).toBe(true);
    expect(button("Call $5").disabled).toBe(true);
    expect(field().disabled).toBe(true);
    expect(screen.getByText("Sending Raise to $20…")).toBeDefined();
    expect(screen.getByRole("region", { name: "Action dock" }).dataset.pending).toBe("true");
    fireEvent.click(pressed);
    expect(onAct).toHaveBeenCalledOnce();
  });

  it("keeps focus in the dock when the pressed control becomes disabled", () => {
    const { rerender } = render(dock());
    const call = button("Call $5");
    call.focus();
    fireEvent.click(call);
    rerender(dock({ status: { ...LIVE, pending: true } }));
    expect(document.activeElement).toBe(screen.getByRole("region", { name: "Action dock" }));
  });

  it("clears the busy state when the outcome arrives", () => {
    const { rerender } = render(dock());
    fireEvent.click(button("Call $5"));
    rerender(dock({ status: { ...LIVE, pending: true } }));
    rerender(dock());
    expect(button("Call $5").getAttribute("aria-busy")).toBeNull();
    expect(screen.queryByText(/^Sending/)).toBeNull();
  });
});

describe("ActionDock rejection", () => {
  it("shows a rejection inline as an alert, with the draft kept", async () => {
    const onDismissRejection = vi.fn();
    const { rerender } = render(dock());
    fireEvent.change(field(), { target: { value: "300" } });
    rerender(dock({ lastRejection: { code: "NOT_YOUR_TURN", message: "x" }, onDismissRejection }));
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("It isn't your turn.");
    expect(field().value).toBe("300");
    expect(button("Raise to $300").disabled).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismissRejection).toHaveBeenCalledOnce();
  });

  it("shows STALE_REVISION as a quiet status, not an alert", () => {
    render(dock({ lastRejection: { code: "STALE_REVISION", message: "x" } }));
    expect(screen.getByText("Table updated.")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("ActionDock reconnecting", () => {
  it("pauses every action in place and says so", () => {
    render(dock({ status: { ...LIVE, phase: "reconnecting" } }));
    expect(screen.getByText("Reconnecting… Actions are paused.")).toBeDefined();
    expect(button("Call $5").disabled).toBe(true);
    expect(field().disabled).toBe(true);
  });

  it("explains an uncertain outcome without claiming what happened", () => {
    const onAct = vi.fn();
    render(dock({ status: { ...LIVE, reconciling: true }, onAct }));
    expect(
      screen.getByText("No response — reconnecting. Your last action may or may not have counted."),
    ).toBeDefined();
    fireEvent.click(button("Call $5"));
    expect(onAct).not.toHaveBeenCalled();
  });
});

describe("ActionDock showdown decision", () => {
  it("sends Show or Muck once", () => {
    const onShowdownDecision = vi.fn();
    render(dock({ view: view("snapshot.heads_up.showdown_decision.json"), onShowdownDecision }));
    fireEvent.click(button("Muck"));
    expect(onShowdownDecision).toHaveBeenCalledExactlyOnceWith("muck");
  });
});

import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { ActArgs, ShowdownDecision, TableView } from "../protocol/types";
import type { LastRejection } from "../session/store";
import { ActionDock } from "./ActionDock";
import {
  actorView,
  checkFreeView,
  fixtureView,
  LIVE,
  laterDecision,
  unrelatedTransition,
  withLegal,
} from "./testViews";
import { GUARD_MS } from "./useDecisionGuard";

// A1 review: decision identity (M1), the guard's focus and accessibility (M2),
// the confirmed Fold (M3), refused sends (M5), the status line (M6) and held
// keys (M7).

interface Options {
  view?: TableView;
  status?: ConnectionStatus;
  lastRejection?: LastRejection | null;
  handEpoch?: number;
  guardMs?: number;
  onAct?: (args: ActArgs) => boolean;
  onShowdownDecision?: (decision: ShowdownDecision) => boolean;
  onStartGame?: () => boolean;
}

function dock(o: Options = {}) {
  return (
    <ActionDock
      view={o.view ?? actorView()}
      status={o.status ?? LIVE}
      lastRejection={o.lastRejection ?? null}
      handEpoch={o.handEpoch}
      guardMs={o.guardMs ?? 0}
      onAct={o.onAct ?? vi.fn(() => true)}
      onShowdownDecision={o.onShowdownDecision ?? vi.fn(() => true)}
      onStartGame={o.onStartGame ?? vi.fn(() => true)}
      onDismissRejection={vi.fn()}
    />
  );
}

const field = () => screen.getByRole("textbox", { name: "Bet amount (exact)" }) as HTMLInputElement;
const button = (name: string | RegExp) => screen.getByRole("button", { name }) as HTMLButtonElement;
const region = () => screen.getByRole("region", { name: "Action dock" });
const statusLineOf = (element: HTMLElement) =>
  document.getElementById(element.getAttribute("aria-describedby") ?? "")?.textContent ?? "";

afterEach(() => vi.useRealTimers());

describe("M1: a revision bump over the same decision changes nothing the player sees", () => {
  it("keeps the draft, the very same field element and its focus", () => {
    const v = actorView();
    const { rerender } = render(dock({ view: v }));
    const input = field();
    input.focus();
    fireEvent.change(input, { target: { value: "350" } });

    rerender(dock({ view: unrelatedTransition(v) })); // revision n+1: a host change
    rerender(dock({ view: unrelatedTransition(unrelatedTransition(v)) })); // and another

    expect(field()).toBe(input);
    expect(input.value).toBe("350");
    expect(document.activeElement).toBe(input);
    expect(input.disabled).toBe(false);
    expect(button("Raise to $350")).toBeDefined();
  });

  it("does not restart the arrival guard", () => {
    vi.useFakeTimers();
    const v = actorView();
    const { rerender } = render(dock({ view: v, guardMs: GUARD_MS }));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(button("Call $5").getAttribute("aria-disabled")).toBeNull();
    rerender(dock({ view: unrelatedTransition(v), guardMs: GUARD_MS }));
    expect(button("Call $5").getAttribute("aria-disabled")).toBeNull();
    expect(region().dataset.arming).toBeUndefined();
  });

  it("keeps an armed Fold armed, and a second press still folds once", () => {
    vi.useFakeTimers();
    const onAct = vi.fn(() => true);
    const v = checkFreeView();
    const { rerender } = render(dock({ view: v, onAct }));
    fireEvent.click(button("Fold"));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    rerender(dock({ view: unrelatedTransition(v), onAct }));
    expect(button("Confirm fold")).toBeDefined();
    fireEvent.click(button("Confirm fold"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "fold", target: null });
  });

  it("a changed legal range revalidates the draft: a committable amount is kept, nothing is clamped", () => {
    const v = actorView(); // 20 .. 1,000
    const { rerender } = render(dock({ view: v }));
    fireEvent.change(field(), { target: { value: "300" } });
    rerender(dock({ view: withLegal(v, { max_target: 500 }) }));
    expect(field().value).toBe("300");
    expect(button("Raise to $300")).toBeDefined();
    expect(screen.getByText("Min $20 · Max $500")).toBeDefined();
  });

  it("a changed legal range that no longer allows the draft restarts it at the new minimum", () => {
    const v = actorView();
    const onAct = vi.fn(() => true);
    const { rerender } = render(dock({ view: v, onAct }));
    fireEvent.change(field(), { target: { value: "800" } });
    rerender(dock({ view: withLegal(v, { max_target: 500 }), onAct }));
    expect(field().value).toBe("20");
    expect(screen.queryByRole("button", { name: /\$800/ })).toBeNull();
    fireEvent.click(button("Raise to $20"));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 20 });
  });
});

describe("M1: a genuinely new decision resets its local state", () => {
  it("a later decision with identical legal actions resets the draft and the Fold, and re-arms the guard", () => {
    vi.useFakeTimers();
    const v = checkFreeView();
    const { rerender } = render(dock({ view: v, guardMs: GUARD_MS }));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    fireEvent.change(field(), { target: { value: "350" } });
    fireEvent.click(button("Fold"));
    expect(button("Confirm fold")).toBeDefined();

    // The hero's turn went away and came back: waiting, then the same actions.
    rerender(
      dock({ view: fixtureView("snapshot.heads_up.preflop.waiting.json"), guardMs: GUARD_MS }),
    );
    expect(screen.queryByRole("group", { name: "Actions" })).toBeNull();
    const next = laterDecision(v);
    expect(next.hand?.legal_actions).toEqual(v.hand?.legal_actions);
    rerender(dock({ view: next, guardMs: GUARD_MS }));

    expect(field().value).toBe("20");
    expect(button("Fold")).toBeDefined();
    expect(button("Check").getAttribute("aria-disabled")).toBe("true");
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(button("Check").getAttribute("aria-disabled")).toBeNull();
  });

  it("the same snapshot after a hand-boundary snapshot is a new decision", () => {
    vi.useFakeTimers();
    const v = actorView();
    const { rerender } = render(dock({ view: v, handEpoch: 0, guardMs: GUARD_MS }));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    fireEvent.change(field(), { target: { value: "350" } });
    rerender(dock({ view: v, handEpoch: 1, guardMs: GUARD_MS }));
    expect(field().value).toBe("20");
    expect(button("Call $5").getAttribute("aria-disabled")).toBe("true");
  });
});

describe("M1: reconnect and reconciliation keep their guarantees", () => {
  it("a reconnect keeps the draft and the element, disables truly, and re-arms the guard", () => {
    vi.useFakeTimers();
    const onAct = vi.fn(() => true);
    const v = actorView();
    const { rerender } = render(dock({ view: v, guardMs: GUARD_MS, onAct }));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    const input = field();
    fireEvent.change(input, { target: { value: "350" } });

    rerender(
      dock({ view: v, guardMs: GUARD_MS, onAct, status: { ...LIVE, phase: "reconnecting" } }),
    );
    expect(field().disabled).toBe(true);
    expect(button("Call $5").disabled).toBe(true);
    fireEvent.click(button("Call $5"));

    // The reconnect delivers a newer revision over the same decision.
    rerender(dock({ view: unrelatedTransition(v), guardMs: GUARD_MS, onAct }));
    expect(field()).toBe(input);
    expect(input.value).toBe("350");
    expect(button("Call $5").getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button("Call $5"));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    expect(onAct).not.toHaveBeenCalled();
    fireEvent.click(button("Call $5"));
    expect(onAct).toHaveBeenCalledOnce();
  });

  it("an uncertain outcome stays truly disabled until the fresh snapshot", () => {
    const onAct = vi.fn(() => true);
    render(dock({ onAct, status: { ...LIVE, reconciling: true } }));
    expect(button("Call $5").disabled).toBe(true);
    expect(field().disabled).toBe(true);
    fireEvent.click(button("Call $5"));
    expect(onAct).not.toHaveBeenCalled();
  });
});

describe("M2: the guard drops activations without moving focus or hiding the decision", () => {
  it("leaves every control enabled and focusable, with aria-disabled, during the guard", () => {
    vi.useFakeTimers();
    render(dock({ guardMs: GUARD_MS }));
    for (const name of ["Fold", "Call $5", "Raise to $20"]) {
      const control = button(name);
      expect(control.disabled).toBe(false);
      expect(control.getAttribute("aria-disabled")).toBe("true");
      control.focus();
      expect(document.activeElement).toBe(control);
    }
  });

  it("a control focused during the guard keeps focus while it runs and after it ends", () => {
    vi.useFakeTimers();
    render(dock({ guardMs: GUARD_MS }));
    const call = button("Call $5");
    call.focus();
    act(() => vi.advanceTimersByTime(GUARD_MS - 1));
    expect(document.activeElement).toBe(call);
    act(() => vi.advanceTimersByTime(1));
    expect(button("Call $5").getAttribute("aria-disabled")).toBeNull();
    expect(document.activeElement).toBe(call);
  });

  it("a reconnect disables truly and moves focus into the dock, never to the page", () => {
    const v = actorView();
    const { rerender } = render(dock({ view: v }));
    button("Call $5").focus();
    rerender(dock({ view: v, status: { ...LIVE, phase: "reconnecting" } }));
    expect(document.activeElement).toBe(region());
  });

  it("pointer and keyboard cannot bypass it, and a dropped activation is never replayed", () => {
    vi.useFakeTimers();
    const onAct = vi.fn(() => true);
    render(dock({ guardMs: GUARD_MS, onAct }));
    fireEvent.click(button("Call $5"));
    fireEvent.click(button("Raise to $20"));
    fireEvent.click(button("Fold"));
    fireEvent.keyDown(field(), { key: "Enter" });
    act(() => vi.advanceTimersByTime(GUARD_MS * 10));
    expect(onAct).not.toHaveBeenCalled();
    fireEvent.click(button("Call $5"));
    expect(onAct).toHaveBeenCalledOnce();
  });

  it("the guard does not arm Fold while it runs", () => {
    vi.useFakeTimers();
    render(dock({ view: checkFreeView(), guardMs: GUARD_MS }));
    fireEvent.click(button("Fold"));
    expect(button("Fold")).toBeDefined(); // not "Confirm fold"
  });

  it("the guard covers Show and Muck too", () => {
    vi.useFakeTimers();
    const onShowdownDecision = vi.fn(() => true);
    render(
      dock({
        view: fixtureView("snapshot.heads_up.showdown_decision.json"),
        guardMs: GUARD_MS,
        onShowdownDecision,
      }),
    );
    expect(button("Show").disabled).toBe(false);
    fireEvent.click(button("Show"));
    expect(onShowdownDecision).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(GUARD_MS));
    fireEvent.click(button("Show"));
    expect(onShowdownDecision).toHaveBeenCalledExactlyOnceWith("show");
  });

  it("a pending command still disables the controls truly, and focus moves to the dock", () => {
    const v = actorView();
    const { rerender } = render(dock({ view: v }));
    button("Call $5").focus();
    fireEvent.click(button("Call $5"));
    rerender(dock({ view: v, status: { ...LIVE, pending: true } }));
    expect(button("Call $5").disabled).toBe(true);
    expect(document.activeElement).toBe(region());
  });
});

describe("M3: a confirmed Fold follows its stable identity", () => {
  function confirmFold() {
    vi.useFakeTimers();
    const onAct = vi.fn(() => true);
    const v = checkFreeView();
    const view = render(dock({ view: v, onAct }));
    fireEvent.change(field(), { target: { value: "350" } });
    fireEvent.click(button("Fold"));
    act(() => vi.advanceTimersByTime(GUARD_MS));
    fireEvent.click(button("Confirm fold"));
    view.rerender(dock({ view: v, onAct, status: { ...LIVE, pending: true } }));
    return { ...view, v, onAct };
  }

  it("sends one fold, and the pending state names Fold", () => {
    const { onAct } = confirmFold();
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "fold", target: null });
    expect(screen.getByText("Sending Fold…")).toBeDefined();
    expect(screen.queryByText(/Confirm fold…/)).toBeNull();
  });

  it("the pressed control is busy, still reads Confirm fold, and sends nothing more", () => {
    const { onAct } = confirmFold();
    const fold = button("Confirm fold");
    expect(fold.getAttribute("aria-busy")).toBe("true");
    expect(fold.disabled).toBe(true);
    expect(fold.className).toMatch(/destructive/);
    fireEvent.click(fold);
    act(() => vi.advanceTimersByTime(5000)); // the 4 s confirm window passes
    expect(button("Confirm fold").getAttribute("aria-busy")).toBe("true");
    expect(onAct).toHaveBeenCalledOnce();
  });

  it("returns to Fold when the command is rejected, and the draft is kept", () => {
    const { rerender, v, onAct } = confirmFold();
    rerender(dock({ view: v, onAct, lastRejection: { code: "ILLEGAL_ACTION", message: "x" } }));
    const fold = button("Fold");
    expect(fold.getAttribute("aria-busy")).toBeNull();
    expect(fold.disabled).toBe(false);
    expect(screen.queryByText(/^Sending/)).toBeNull();
    expect(field().value).toBe("350");
    expect(field().disabled).toBe(false);
  });

  it("facing a bet, a direct Fold is busy too, as Fold", () => {
    const v = actorView();
    const onAct = vi.fn(() => true);
    const { rerender } = render(dock({ view: v, onAct }));
    fireEvent.click(button("Fold"));
    rerender(dock({ view: v, onAct, status: { ...LIVE, pending: true } }));
    expect(button("Fold").getAttribute("aria-busy")).toBe("true");
    expect(screen.getByText("Sending Fold…")).toBeDefined();
  });
});

describe("M5: a refused send leaves no pressed state", () => {
  it("does not label the next, unrelated command", () => {
    const v = actorView();
    const { rerender } = render(dock({ view: v, onAct: () => false }));
    fireEvent.click(button("Call $5"));
    rerender(dock({ view: v, onAct: () => false, status: { ...LIVE, pending: true } }));
    expect(screen.queryByText(/^Sending/)).toBeNull();
    expect(button("Call $5").getAttribute("aria-busy")).toBeNull();
  });

  it("a refused Start game or Show leaves none either", () => {
    const notStarted = fixtureView("snapshot.connected.not_started.json");
    const host = { ...notStarted, you: { ...notStarted.you, is_host: true } };
    const { rerender } = render(dock({ view: host, onStartGame: () => false }));
    fireEvent.click(button("Start game"));
    rerender(dock({ view: host, onStartGame: () => false, status: { ...LIVE, pending: true } }));
    expect(screen.queryByText(/^Sending/)).toBeNull();
  });
});

describe("M6: the status line", () => {
  const rejection: LastRejection = { code: "ILLEGAL_ACTION", message: "x" };

  it("the armed-Fold explanation is not hidden by an earlier rejection", () => {
    render(dock({ view: checkFreeView(), lastRejection: rejection }));
    expect(screen.getByRole("alert").textContent).toContain("isn't legal");
    fireEvent.click(button("Fold"));
    const text = statusLineOf(button("Confirm fold"));
    expect(text).toMatch(/Check is free\. Press Fold again to fold, or Esc to cancel\./);
    expect(text).not.toMatch(/isn't legal/);
  });

  it("the rejection returns once Fold is disarmed", () => {
    render(dock({ view: checkFreeView(), lastRejection: rejection }));
    fireEvent.click(button("Fold"));
    fireEvent.keyDown(button("Confirm fold"), { key: "Escape" });
    expect(screen.getByRole("alert").textContent).toContain("isn't legal");
  });

  it("a command in flight says so even while an older rejection is stored", () => {
    const v = actorView();
    const { rerender } = render(dock({ view: v, lastRejection: rejection }));
    expect(screen.getByRole("alert")).toBeDefined();
    fireEvent.click(button("Call $5")); // a real press, sent
    rerender(dock({ view: v, lastRejection: rejection, status: { ...LIVE, pending: true } }));
    expect(screen.getByText("Sending Call $5…")).toBeDefined();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("a connection notice outranks the armed Fold", () => {
    const v = checkFreeView();
    const { rerender } = render(dock({ view: v }));
    fireEvent.click(button("Fold"));
    rerender(dock({ view: v, status: { ...LIVE, phase: "reconnecting" } }));
    expect(screen.getByText("Reconnecting… Actions are paused.")).toBeDefined();
    expect(button("Fold")).toBeDefined(); // and the armed Fold was disarmed
  });

  it("Esc with the field focused and Fold armed disarms only; the draft stays", () => {
    render(dock({ view: checkFreeView() }));
    fireEvent.change(field(), { target: { value: "350" } });
    fireEvent.click(button("Fold"));
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(button("Fold")).toBeDefined();
    expect(field().value).toBe("350");
    fireEvent.keyDown(field(), { key: "Escape" });
    expect(field().value).toBe("20");
  });
});

describe("M7: a held key never repeats an activation", () => {
  it("is cancelled on Show, Muck and Start game, and on a held Space", () => {
    const { unmount } = render(
      dock({ view: fixtureView("snapshot.heads_up.showdown_decision.json") }),
    );
    expect(fireEvent.keyDown(button("Show"), { key: "Enter", repeat: true })).toBe(false);
    expect(fireEvent.keyDown(button("Muck"), { key: " ", repeat: true })).toBe(false);
    expect(fireEvent.keyDown(button("Muck"), { key: "Enter" })).toBe(true); // the first press is not
    unmount();
    const notStarted = fixtureView("snapshot.connected.not_started.json");
    render(dock({ view: { ...notStarted, you: { ...notStarted.you, is_host: true } } }));
    expect(fireEvent.keyDown(button("Start game"), { key: "Enter", repeat: true })).toBe(false);
  });

  it("a held Space on the betting controls is cancelled too", () => {
    render(dock());
    expect(fireEvent.keyDown(button("Call $5"), { key: " ", repeat: true })).toBe(false);
  });
});

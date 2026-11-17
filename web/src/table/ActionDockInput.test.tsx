import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { ActArgs, TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { ActionDock } from "./ActionDock";

// QA: the exact-amount input under realistic typing, paste, and bounds changes.
// A1 (AM2): out-of-range or invalid text is never clamped, on blur or on
// submit; it cannot be committed until the player corrects it.
// snapshot.heads_up.preflop.actor: raise range 20 .. 1,000.

const LIVE: ConnectionStatus = {
  phase: "live",
  pending: false,
  reconciling: false,
  attempt: 0,
  reason: null,
};

function actorView(): TableView {
  return readFixtureJson<{ view: TableView }>(
    "messages/server/snapshot.heads_up.preflop.actor.json",
  ).view;
}

/** The same decision with different server bounds. */
function viewWithBounds(min: number, max: number): TableView {
  const view = actorView();
  const hand = view.hand;
  if (hand === null || hand.legal_actions === null) throw new Error("fixture has no decision");
  return {
    ...view,
    hand: {
      ...hand,
      legal_actions: { ...hand.legal_actions, min_full_target: min, max_target: max },
    },
  };
}

function dock(view: TableView, onAct: (args: ActArgs) => boolean, status: ConnectionStatus = LIVE) {
  return (
    <ActionDock
      view={view}
      status={status}
      lastRejection={null}
      guardMs={0}
      onAct={onAct}
      onShowdownDecision={vi.fn(() => true)}
      onStartGame={vi.fn(() => true)}
      onDismissRejection={vi.fn()}
    />
  );
}

function field(): HTMLInputElement {
  return screen.getByRole("textbox", { name: "Bet amount (exact)" }) as HTMLInputElement;
}

function commit(): HTMLButtonElement {
  return screen.getByRole("button", { name: /^(Raise to|All-in \$)/ }) as HTMLButtonElement;
}

function setup(view: TableView = actorView()) {
  const onAct = vi.fn();
  const utils = render(dock(view, onAct));
  return { onAct, input: field(), ...utils };
}

describe("ActionDock exact-amount input: typing sequences", () => {
  it("starts at the server minimum and appends typed digits to it", async () => {
    const { input, onAct } = setup();
    expect(input.value).toBe("20");
    await userEvent.type(input, "5"); // the cursor goes to the end: "205"
    expect(input.value).toBe("205");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $205" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 205 });
  });

  it("backspacing through to empty and retyping never submits a guess in between", async () => {
    const { input, onAct } = setup();
    await userEvent.type(input, "{Backspace}{Backspace}");
    expect(input.value).toBe("");
    expect(commit().disabled).toBe(true);
    expect(commit().textContent).toBe("Raise to");
    await userEvent.type(input, "75");
    expect(input.value).toBe("75");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $75" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 75 });
  });

  it("does not rewrite what the user has typed between keystrokes, even below the minimum", async () => {
    const { input } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "1"); // below the 20 minimum: invalid, never rewritten
    expect(input.value).toBe("1");
    expect(commit().disabled).toBe(true);
    await userEvent.type(input, "5");
    expect(input.value).toBe("15");
    await userEvent.type(input, "0");
    expect(input.value).toBe("150");
    expect(commit().disabled).toBe(false);
  });

  it("treats leading zeros as the number they spell, and blur normalizes only their spelling", async () => {
    const { input, onAct } = setup();
    fireEvent.change(input, { target: { value: "0150" } }); // as typed in a browser
    expect(input.value).toBe("0150");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $150" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 150 });
    await userEvent.click(input);
    await userEvent.tab();
    expect(input.value).toBe("150");
  });

  it("a typed zero is below the minimum: never committed, never clamped on blur", async () => {
    const { input, onAct } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "0");
    await userEvent.click(commit());
    expect(onAct).not.toHaveBeenCalled();
    await userEvent.tab();
    expect(input.value).toBe("0");
    expect(commit().disabled).toBe(true);
  });

  it("an absurdly large number is above the maximum: never sent as all-in", () => {
    const { input, onAct } = setup();
    for (const digits of ["9".repeat(25), "9".repeat(300)]) {
      fireEvent.change(input, { target: { value: digits } });
      expect(commit().disabled).toBe(true);
      fireEvent.click(commit());
    }
    expect(onAct).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "All-in $1,000" })).toBeNull();
  });

  it("an amount typed on its own is sent exactly, or not at all", () => {
    const { input, onAct } = setup();
    for (const text of ["19", "20", "21", "999", "1000", "1001"]) {
      onAct.mockClear();
      fireEvent.change(input, { target: { value: text } });
      fireEvent.click(commit());
      const n = Number(text);
      if (n >= 20 && n <= 1000) {
        expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: n });
      } else {
        expect(onAct, `${text} must not be sent`).not.toHaveBeenCalled();
      }
    }
  });
});

describe("ActionDock exact-amount input: blur, then click commit (AM2 regression)", () => {
  it("an out-of-range amount stays out of range across blur and is not sent", async () => {
    const { input, onAct } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "5000");
    // The click blurs the field first, in the same gesture.
    await userEvent.click(commit());
    expect(input.value).toBe("5000");
    expect(onAct).not.toHaveBeenCalled();
    expect(screen.getByText(/The maximum is \$1,000/)).toBeDefined();
  });

  it("a below-minimum amount stays below across blur and is not sent", async () => {
    const { input, onAct } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "3");
    fireEvent.blur(input);
    fireEvent.click(commit());
    expect(input.value).toBe("3");
    expect(onAct).not.toHaveBeenCalled();
  });

  it("a valid amount keeps its label through blur and sends exactly what the label said", async () => {
    const { input, onAct } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "150");
    const labelBefore = commit().textContent;
    fireEvent.blur(input);
    expect(commit().textContent).toBe(labelBefore);
    fireEvent.click(commit());
    expect(labelBefore).toBe("Raise to $150");
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 150 });
  });
});

describe("ActionDock exact-amount input: paste", () => {
  it("pasting an amount over the selection replaces it", async () => {
    const { input, onAct } = setup();
    await userEvent.click(input);
    input.select();
    await userEvent.paste("300");
    expect(input.value).toBe("300");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $300" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 300 });
  });

  it("pasted text that is not a whole number disables submit and sends nothing", () => {
    const { input, onAct } = setup();
    for (const text of ["1e3", "-5", "1.5", "0.5", "$20"]) {
      fireEvent.change(input, { target: { value: text } });
      expect(commit().disabled, `${text} must not be submittable`).toBe(true);
      fireEvent.click(commit());
    }
    expect(onAct).not.toHaveBeenCalled();
  });

  it("blur on text that is not a whole number leaves it for the user to fix", () => {
    const { input } = setup();
    fireEvent.change(input, { target: { value: "1.5" } });
    fireEvent.blur(input);
    expect(input.value).toBe("1.5");
    expect(input.getAttribute("aria-invalid")).toBe("true");
  });
});

describe("ActionDock exact-amount input: the server range changes", () => {
  it("a re-render with the same bounds does not touch text the user is typing", async () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    await userEvent.clear(field());
    await userEvent.type(field(), "1");

    rerender(dock(actorView(), onAct)); // an equal-bounds snapshot, a new object
    expect(field().value).toBe("1");

    await userEvent.clear(field());
    rerender(dock(actorView(), onAct));
    expect(field().value).toBe(""); // empty stays empty: not reset to the minimum
    expect(commit().disabled).toBe(true);
  });

  it("a different server range resets the draft to its minimum; the old amount is never sent", async () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    await userEvent.clear(field());
    await userEvent.type(field(), "800");

    rerender(dock(viewWithBounds(20, 500), onAct));
    expect(field().value).toBe("20");
    expect(screen.queryByRole("button", { name: /\$800/ })).toBeNull();

    await userEvent.clear(field());
    await userEvent.type(field(), "30");
    rerender(dock(viewWithBounds(100, 1000), onAct));
    expect(field().value).toBe("100");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $100" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 100 });
  });

  it("the slider's own bounds follow the server's", () => {
    const { rerender } = render(dock(actorView(), vi.fn()));
    rerender(dock(viewWithBounds(100, 500), vi.fn()));
    const slider = screen.getByRole("slider", { name: "Bet amount" }) as HTMLInputElement;
    expect(slider.min).toBe("100");
    expect(slider.max).toBe("500");
  });
});

describe("ActionDock exact-amount input: other states", () => {
  it("is disabled with the rest of the dock while reconnecting, and keeps its text", () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    fireEvent.change(field(), { target: { value: "300" } });

    rerender(dock(actorView(), onAct, { ...LIVE, phase: "reconnecting" }));

    expect(field().disabled).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Raise to $300" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    rerender(dock(actorView(), onAct));
    expect(field().value).toBe("300");
  });

  it("a bet (no raise) is labelled and sent as a bet", async () => {
    const view = actorView();
    const hand = view.hand;
    if (hand === null || hand.legal_actions === null) throw new Error("fixture has no decision");
    const betView: TableView = {
      ...view,
      hand: {
        ...hand,
        legal_actions: {
          ...hand.legal_actions,
          can_raise: false,
          can_bet: true,
          can_call: false,
        },
      },
    };
    const { input, onAct } = setup(betView);
    await userEvent.clear(input);
    await userEvent.type(input, "40");
    await userEvent.click(screen.getByRole("button", { name: "Bet $40" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "bet", target: 40 });
  });

  it("the short all-in decision is one All-in button, with no free amount to type", async () => {
    const onAct = vi.fn();
    render(
      dock(
        readFixtureJson<{ view: TableView }>(
          "messages/server/snapshot.side_pots.short_all_in_decision.json",
        ).view,
        onAct,
      ),
    );
    // min_full_target 1,190 is above max_target 990: the only legal raise is all-in.
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.getByText(/Your only raise: All-in \$990/)).toBeDefined();
    await userEvent.click(screen.getByRole("button", { name: "All-in $990" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 990 });
  });
});

import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ActArgs, TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { ActionDock } from "./ActionDock";

// QA: the exact-amount input under realistic typing, paste, and bounds changes
// (the M1 repair: raw text, clamped only on submit or blur).
// snapshot.heads_up.preflop.actor: raise range 20 .. 1,000.

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

function dock(view: TableView, onAct: (args: ActArgs) => void, disabled = false) {
  return (
    <ActionDock
      view={view}
      disabled={disabled}
      onAct={onAct}
      onShowdownDecision={vi.fn()}
      onStartGame={vi.fn()}
    />
  );
}

function setup(view: TableView = actorView()) {
  const onAct = vi.fn();
  const utils = render(dock(view, onAct));
  const input = screen.getByRole("spinbutton", { name: "Bet amount (exact)" }) as HTMLInputElement;
  const submit = () => screen.getByRole("button", { name: /^(Raise to|All-in \$)/ });
  return { onAct, input, submit, ...utils };
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
    const submit = screen.getByRole("button", { name: "Raise to" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await userEvent.type(input, "75");
    expect(input.value).toBe("75");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $75" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 75 });
  });

  it("does not rewrite what the user has typed between keystrokes, even below the minimum", async () => {
    const { input } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "1"); // below the 20 minimum: only clamped on submit or blur
    expect(input.value).toBe("1");
    await userEvent.type(input, "5");
    expect(input.value).toBe("15");
    await userEvent.type(input, "0");
    expect(input.value).toBe("150");
  });

  it("treats leading zeros as the number they spell, and blur normalizes them", async () => {
    const { input, onAct } = setup();
    fireEvent.change(input, { target: { value: "0150" } }); // as typed in a browser
    expect(input.value).toBe("0150");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $150" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 150 });
    await userEvent.click(input);
    await userEvent.tab();
    expect(input.value).toBe("150");
  });

  it("clamps a typed zero to the server minimum on submit and on blur", async () => {
    const { input, onAct } = setup();
    await userEvent.clear(input);
    await userEvent.type(input, "0");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $20" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 20 });
    await userEvent.tab();
    expect(input.value).toBe("20");
  });

  it("clamps an absurdly large number, up to the largest the number input accepts, to max_target", async () => {
    const { input, onAct } = setup();
    for (const digits of ["9".repeat(25), "9".repeat(300)]) {
      onAct.mockClear();
      fireEvent.change(input, { target: { value: digits } });
      fireEvent.click(screen.getByRole("button", { name: "All-in $1,000" }));
      expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 1000 });
    }
  });

  it("an amount typed on its own never exceeds the server bounds on the wire", async () => {
    const { input, onAct } = setup();
    for (const text of ["19", "20", "21", "999", "1000", "1001"]) {
      onAct.mockClear();
      fireEvent.change(input, { target: { value: text } });
      const submit = screen.getByRole("button", { name: /^(Raise to|All-in \$)/ });
      fireEvent.click(submit);
      const args = onAct.mock.calls[0]?.[0] as ActArgs;
      expect(args.target).toBe(Math.min(1000, Math.max(20, Number(text))));
    }
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

  it("pasted text that is not a whole number disables submit and sends nothing", async () => {
    const { input, onAct } = setup();
    for (const text of ["1e3", "-5", "1.5", "0.5"]) {
      fireEvent.change(input, { target: { value: text } });
      const submit = screen.getByRole("button", { name: /^Raise to/ }) as HTMLButtonElement;
      expect(submit.disabled, `${text} must not be submittable`).toBe(true);
    }
    expect(onAct).not.toHaveBeenCalled();
  });

  it("blur on text that is not a whole number leaves it for the user to fix", async () => {
    const { input } = setup();
    fireEvent.change(input, { target: { value: "1.5" } });
    fireEvent.blur(input);
    expect(input.value).toBe("1.5");
  });
});

describe("ActionDock exact-amount input: bounds change while typing", () => {
  it("a re-render with the same bounds does not touch text the user is typing", async () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    const input = screen.getByRole("spinbutton", {
      name: "Bet amount (exact)",
    }) as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "1");

    rerender(dock(actorView(), onAct)); // an equal-bounds snapshot, a new object
    expect(input.value).toBe("1");

    await userEvent.clear(input);
    rerender(dock(actorView(), onAct));
    expect(input.value).toBe(""); // empty stays empty: not reset to the minimum
    expect((screen.getByRole("button", { name: "Raise to" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
  });

  it("a shrunken max_target pulls a typed amount down to it", async () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    const input = screen.getByRole("spinbutton", {
      name: "Bet amount (exact)",
    }) as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "800");

    rerender(dock(viewWithBounds(20, 500), onAct));

    expect(input.value).toBe("500");
    await userEvent.click(screen.getByRole("button", { name: "All-in $500" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 500 });
  });

  it("a raised minimum lifts a typed amount to it, and never submits the old amount", async () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    const input = screen.getByRole("spinbutton", {
      name: "Bet amount (exact)",
    }) as HTMLInputElement;
    await userEvent.clear(input);
    await userEvent.type(input, "30");

    rerender(dock(viewWithBounds(100, 1000), onAct));

    expect(input.value).toBe("100");
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
  it("is disabled with the rest of the dock and keeps its text", () => {
    const onAct = vi.fn();
    const { rerender } = render(dock(actorView(), onAct));
    const input = screen.getByRole("spinbutton", {
      name: "Bet amount (exact)",
    }) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "300" } });

    rerender(dock(actorView(), onAct, true));

    expect(input.disabled).toBe(true);
    expect(
      (screen.getByRole("button", { name: "Raise to $300" }) as HTMLButtonElement).disabled,
    ).toBe(true);
    rerender(dock(actorView(), onAct, false));
    expect(input.value).toBe("300");
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
    expect(screen.queryByRole("spinbutton")).toBeNull();
    expect(screen.queryByRole("slider")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "All-in $990" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 990 });
  });
});

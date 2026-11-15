import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { ActArgs, TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { ActionDock } from "./ActionDock";

// snapshot.heads_up.preflop.actor: raise range min_full_target 20 .. max_target 1,000.
function actorView(): TableView {
  return readFixtureJson<{ view: TableView }>(
    "messages/server/snapshot.heads_up.preflop.actor.json",
  ).view;
}

function renderDock(onAct: (args: ActArgs) => void = vi.fn()) {
  render(
    <ActionDock
      view={actorView()}
      disabled={false}
      onAct={onAct}
      onShowdownDecision={vi.fn()}
      onStartGame={vi.fn()}
    />,
  );
  return screen.getByRole("spinbutton", { name: "Bet amount (exact)" }) as HTMLInputElement;
}

describe("ActionDock exact-amount input", () => {
  it("select-all then type 150 produces Raise to $150 and sends target 150", async () => {
    const onAct = vi.fn();
    const input = renderDock(onAct);
    await userEvent.click(input);
    input.select();
    await userEvent.keyboard("150");
    expect(input.value).toBe("150");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $150" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 150 });
  });

  it("clear then type 150 produces Raise to $150 and sends target 150", async () => {
    const onAct = vi.fn();
    const input = renderDock(onAct);
    await userEvent.clear(input);
    await userEvent.type(input, "150");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $150" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 150 });
  });

  it("clamps typed text above max_target when submitted", async () => {
    const onAct = vi.fn();
    const input = renderDock(onAct);
    await userEvent.clear(input);
    await userEvent.type(input, "5000");
    await userEvent.click(screen.getByRole("button", { name: "All-in $1,000" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 1000 });
  });

  it("clamps typed text above max_target on blur", async () => {
    const input = renderDock();
    await userEvent.clear(input);
    await userEvent.type(input, "5000");
    await userEvent.tab();
    expect(input.value).toBe("1000");
  });

  it("clamps typed text below min_full_target when submitted and on blur", async () => {
    const onAct = vi.fn();
    const input = renderDock(onAct);
    await userEvent.clear(input);
    await userEvent.type(input, "3");
    await userEvent.click(screen.getByRole("button", { name: "Raise to $20" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 20 });

    await userEvent.clear(input);
    await userEvent.type(input, "3");
    await userEvent.tab();
    expect(input.value).toBe("20");
  });

  it("disables submit for empty text and does not guess an amount", async () => {
    const onAct = vi.fn();
    const input = renderDock(onAct);
    await userEvent.clear(input);
    const submit = screen.getByRole("button", { name: "Raise to" }) as HTMLButtonElement;
    expect(submit.disabled).toBe(true);
    await userEvent.click(submit);
    expect(onAct).not.toHaveBeenCalled();
  });

  it("disables submit for non-integer text", () => {
    const input = renderDock();
    for (const text of ["1.5", "-"]) {
      fireEvent.change(input, { target: { value: text } });
      // jsdom drops a number input's non-numeric text ("-") to "", which is
      // also not a whole number; either way no amount is submitted.
      const submit = screen.getByRole("button", { name: /^Raise to/ }) as HTMLButtonElement;
      expect(submit.disabled).toBe(true);
    }
  });

  it("the slider still drives the label and the draft", () => {
    const onAct = vi.fn();
    const input = renderDock(onAct);
    fireEvent.change(screen.getByRole("slider", { name: "Bet amount" }), {
      target: { value: "300" },
    });
    expect(input.value).toBe("300");
    fireEvent.click(screen.getByRole("button", { name: "Raise to $300" }));
    expect(onAct).toHaveBeenCalledExactlyOnceWith({ action: "raise", target: 300 });
  });

  it("Min and All-in set the draft", async () => {
    const input = renderDock();
    await userEvent.click(screen.getByRole("button", { name: "All-in" }));
    expect(input.value).toBe("1000");
    await userEvent.click(screen.getByRole("button", { name: "Min" }));
    expect(input.value).toBe("20");
  });
});

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { TableView } from "../protocol/types";
import { readFixtureJson, readScenario } from "../testing/fixtures";
import { ActionDock } from "./ActionDock";
import { TableStage } from "./TableStage";

function view(fixture: string): TableView {
  return readFixtureJson<{ view: TableView }>(`messages/server/${fixture}`).view;
}

function noop() {
  // intentionally empty: these render tests never trigger a command
}

describe("TableStage rendering", () => {
  it("renders nine seats with no overlapping seat elements", () => {
    render(<TableStage view={view("snapshot.nine_seats.actor.json")} />);
    const seats = screen.getAllByRole("group", { name: /^Seat \d/ });
    expect(seats).toHaveLength(9);
  });

  it("shows card backs for hidden cards and no hidden card value in the DOM", () => {
    const nineSeats = view("snapshot.nine_seats.actor.json");
    render(<TableStage view={nineSeats} />);
    const totalHidden = (nineSeats.hand?.participants ?? []).reduce(
      (sum, p) => sum + p.hidden_card_count,
      0,
    );
    expect(totalHidden).toBeGreaterThan(0);
    const backs = screen.getAllByRole("img", { name: "Face-down card" });
    expect(backs).toHaveLength(totalHidden);

    // Only the hero's own two cards are shown as face-up values.
    const faces = screen.getAllByRole("img", { name: /of (clubs|diamonds|hearts|spades)/ });
    expect(faces).toHaveLength(2);
    expect(screen.getByRole("img", { name: "Eight of hearts" })).toBeDefined();
    expect(screen.getByRole("img", { name: "Nine of spades" })).toBeDefined();
  });

  it("shows main and side pots separately, from a settled three-way side-pot hand", () => {
    render(<TableStage view={view("snapshot.side_pots.settled.json")} />);
    const pots = screen.getByLabelText("Pots");
    expect(within(pots).getByText("$1,800")).toBeDefined();
    expect(within(pots).getByText("$780")).toBeDefined();
    expect(within(pots).getAllByText(/Pot$|Side pot/)).toHaveLength(2);
  });

  it("renders pots exactly as given, including two layers with identical eligible seats", () => {
    const scenario = readScenario("three_way_side_pots");
    const step = scenario.steps.find(
      (s) =>
        s.op === "receive" &&
        "connection" in s &&
        s.connection === "alice-1" &&
        (s as { message: { type: string; revision: number } }).message.type === "snapshot" &&
        (s as { message: { type: string; revision: number } }).message.revision === 7,
    );
    if (step === undefined || step.op !== "receive") throw new Error("fixture step not found");
    const message = step.message as { view: TableView };
    render(<TableStage view={message.view} />);
    const pots = screen.getByLabelText("Pots");
    expect(within(pots).getByText("$30")).toBeDefined();
    expect(within(pots).getByText("$780")).toBeDefined();
    expect(within(pots).getAllByText(/Pot$|Side pot/)).toHaveLength(2);
  });

  it("splits a single pot with its odd chip, not merged or averaged", () => {
    render(<TableStage view={view("snapshot.split_pot.odd_chip.settled.json")} />);
    const result = screen.getByLabelText("Hand result");
    expect(within(result).getByText(/\$1,463/)).toBeDefined();
    expect(within(result).getByText(/\$1,462/)).toBeDefined();
  });

  it("shows sitting_out occupants and a null hand (sit_out_reset_resume)", () => {
    const resetView = view("snapshot.reset.waiting_hand_null.json");
    expect(resetView.hand).toBeNull();
    render(<TableStage view={resetView} />);
    expect(screen.getAllByText("Sitting out")).toHaveLength(2);
  });

  it("shows a settled hand's result", () => {
    render(<TableStage view={view("snapshot.heads_up.settled.opponent_mucked.json")} />);
    const result = screen.getByLabelText("Hand result");
    expect(within(result).getByText(/wins/)).toBeDefined();
    expect(within(result).getByText("$340")).toBeDefined();
  });
});

describe("ActionDock rendering", () => {
  it("labels an all-in call as all-in", () => {
    render(
      <ActionDock
        view={view("snapshot.call_is_all_in.decision.json")}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );
    expect(screen.getByRole("button", { name: /Call .*\(All-in\)/ })).toBeDefined();
  });

  it("collapses the sizer to one choice when short_all_in_target is set", () => {
    render(
      <ActionDock
        view={view("snapshot.side_pots.short_all_in_decision.json")}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );
    expect(screen.getByRole("button", { name: "All-in $990" })).toBeDefined();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.queryByRole("spinbutton")).toBeNull();
  });

  it("renders a call-only dock with no bet or raise controls", () => {
    render(
      <ActionDock
        view={view("snapshot.side_pots.call_only.json")}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );
    expect(screen.getByRole("button", { name: /Call/ })).toBeDefined();
    expect(screen.getByRole("button", { name: "Fold" })).toBeDefined();
    expect(screen.queryByRole("slider")).toBeNull();
  });

  it("offers Show and Muck at a showdown decision", () => {
    render(
      <ActionDock
        view={view("snapshot.heads_up.showdown_decision.json")}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );
    expect(screen.getByRole("button", { name: "Show" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Muck" })).toBeDefined();
  });

  it("re-clamps the sizer draft when max_target shrinks on the actor's next decision, even if min_full_target repeats (no stale state across decisions)", async () => {
    const actorView = view("snapshot.heads_up.preflop.actor.json");
    const { rerender } = render(
      <ActionDock
        view={actorView}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );
    // The player drags to the full all-in amount ($1,000) but does not submit.
    await userEvent.click(screen.getByRole("button", { name: "All-in" }));
    expect(screen.getByRole("button", { name: "All-in $1,000" })).toBeDefined();

    // A later decision for the same seat: `min_full_target` repeats (still
    // $20, a realistic coincidence across streets/hands with the same
    // blinds), but the actor's stack - and so `max_target` - has shrunk to
    // $900, with no short_all_in_target.
    const nextDecisionView = view("snapshot.heads_up.preflop.actor.json");
    if (nextDecisionView.hand?.legal_actions) {
      nextDecisionView.hand.legal_actions.max_target = 900;
    }
    rerender(
      <ActionDock
        view={nextDecisionView}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );

    // The sizer must never offer, or submit, a target above the current
    // legal maximum (C6.2 §2.3: clamping to the server's range is the only
    // client-side exception allowed). A stale $1,000 draft here would both
    // mislabel the button ("Raise to $1,000" instead of "All-in") and send
    // an out-of-range target that the server must reject.
    expect(screen.queryByRole("button", { name: "Raise to $1,000" })).toBeNull();
    expect(screen.getByRole("button", { name: "All-in $900" })).toBeDefined();
  });

  it("queries controls by role and accessible name", () => {
    render(
      <ActionDock
        view={view("snapshot.heads_up.preflop.actor.json")}
        disabled={false}
        onAct={noop}
        onShowdownDecision={noop}
        onStartGame={noop}
      />,
    );
    expect(screen.getByRole("button", { name: "Call $5" })).toBeDefined();
    expect(screen.getByRole("button", { name: "Raise to $20" })).toBeDefined();
  });
});

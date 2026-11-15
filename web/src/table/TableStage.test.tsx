import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TableView } from "../protocol/types";
import { readFixtureJson } from "../testing/fixtures";
import { TableStage } from "./TableStage";

/** The nine-seat fixture cut down to `seats` seats. */
function viewWith(seats: number): TableView {
  const view = readFixtureJson<{ view: TableView }>(
    "messages/server/snapshot.nine_seats.actor.json",
  ).view;
  const hand = view.hand;
  if (hand === null) throw new Error("the fixture has a hand");
  const keep = (seat: number) => seat <= seats;
  return {
    ...view,
    settings: { ...view.settings, max_seats: seats },
    seats: view.seats.filter((s) => keep(s.seat)),
    // The fixture's hero is seat 4; on a smaller table the hero is the last
    // seat, who holds no visible cards. The privacy rules are unchanged.
    you: { ...view.you, seat: Math.min(view.you.seat, seats) },
    hand: {
      ...hand,
      participants: hand.participants.filter((p) => keep(p.seat)),
      turn: null,
      legal_actions: null,
    },
  };
}

describe("TableStage at 2, 6 and 9 seats", () => {
  it.each([2, 6, 9])("renders each of %i seats once, with a bet label per bettor", (seats) => {
    const view = viewWith(seats);
    render(<TableStage view={view} />);
    expect(screen.getAllByRole("group", { name: /^Seat \d/ })).toHaveLength(seats);
    const bettors = (view.hand?.participants ?? []).filter((p) => p.in_front > 0);
    for (const p of bettors) {
      expect(screen.getAllByText(`$${p.in_front}`).length).toBeGreaterThan(0);
    }
  });
});

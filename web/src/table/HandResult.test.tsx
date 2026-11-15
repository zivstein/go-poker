import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Participant, Settlement } from "../protocol/types";
import { HandResult } from "./HandResult";

const CATEGORIES = ["one_pair", "two_pair", "flush", "straight", "full_house"] as const;

function showdown(hands: number) {
  const seats = Array.from({ length: hands }, (_, i) => i + 1);
  const participants = seats.map(
    (seat): Participant => ({
      seat,
      position: "utg",
      blind: null,
      in_front: 0,
      folded: false,
      all_in: false,
      has_live_cards: true,
      hole_cards: ["Ac", "Kd"],
      hidden_card_count: 0,
      strength: {
        category: "one_pair",
        description: "Pair",
        cards: ["Ac", "Kd", "Qh", "Js", "Ts"],
      },
    }),
  );
  const settlement: Settlement = {
    pot_awards: [
      { amount: 1800, eligible_seats: seats, shares: [{ seat: 1, amount: 1800 }] },
      { amount: 780, eligible_seats: seats.slice(1), shares: [{ seat: 2, amount: 780 }] },
    ],
    shown_ranks: seats.map((seat) => ({
      seat,
      category: CATEGORIES[seat % CATEGORIES.length] ?? "one_pair",
    })),
  } as Settlement;
  const names = Object.fromEntries(Array.from({ length: 9 }, (_, i) => [i + 1, `Player ${i + 1}`]));
  return { participants, settlement, names };
}

function renderResult(hands: number) {
  const { participants, settlement, names } = showdown(hands);
  render(<HandResult settlement={settlement} participants={participants} seatNames={names} />);
  return screen.getByRole("group", { name: "Hand result" });
}

describe("HandResult at a multi-player showdown", () => {
  it.each([1, 2, 3])("shows each of %i hands' best five", (hands) => {
    const result = renderResult(hands);
    expect(within(result).getAllByRole("img")).toHaveLength(hands * 5);
  });

  it.each([4, 5, 6, 7, 8, 9])(
    "shows %i hands as one text line each, with no card faces, so its height stays bounded",
    (hands) => {
      const result = renderResult(hands);
      expect(within(result).queryAllByRole("img")).toHaveLength(0);
      for (let seat = 1; seat <= hands; seat++) {
        expect(within(result).getByText(`Player ${seat}`)).toBeDefined();
      }
    },
  );

  it.each([1, 3, 4, 9])(
    "keeps every award and every shown hand's category, with %i hands",
    (hands) => {
      const result = renderResult(hands);
      expect(result.textContent).toContain("Player 1 wins $1,800");
      expect(result.textContent).toContain("Player 2 wins $780");
      expect(
        within(result).getAllByText(/^(one pair|two pair|flush|straight|full house)$/),
      ).toHaveLength(hands);
    },
  );

  it("gives a long name its full text on hover, since the line shortens it", () => {
    const { participants, settlement } = showdown(4);
    render(
      <HandResult
        settlement={settlement}
        participants={participants}
        seatNames={{ 1: "Alexandrina-Montague", 2: "B", 3: "C", 4: "D" }}
      />,
    );
    expect(screen.getByTitle("Alexandrina-Montague")).toBeDefined();
  });
});

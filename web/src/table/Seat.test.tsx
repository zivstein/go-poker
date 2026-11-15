import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Occupant, Participant } from "../protocol/types";
import { Seat } from "./Seat";

function occupant(overrides: Partial<Occupant> = {}): Occupant {
  return { display_name: "Alice", is_host: false, stack: 1000, status: null, ...overrides };
}

function participant(overrides: Partial<Participant> = {}): Participant {
  return {
    seat: 1,
    position: "utg",
    blind: null,
    in_front: 0,
    folded: false,
    all_in: false,
    has_live_cards: true,
    hole_cards: null,
    hidden_card_count: 2,
    strength: null,
    ...overrides,
  };
}

function renderSeat(o: Occupant | null, p: Participant | null, isHero = false) {
  render(
    <Seat
      seatNumber={1}
      occupant={o}
      participant={p}
      isHero={isHero}
      isTurn={false}
      xPct={50}
      yPct={50}
    />,
  );
  return screen.getByRole("group", { name: /^Seat 1/ });
}

/** True when `inner` sits inside an element, below the seat itself, that also
 * holds `other`: that is, when the two share a pod instead of separate rows. */
function sharesContainerBelowSeat(seat: HTMLElement, inner: HTMLElement, other: HTMLElement) {
  for (let el = inner.parentElement; el !== null && el !== seat; el = el.parentElement) {
    if (el.contains(other)) return true;
  }
  return false;
}

describe("Seat markers", () => {
  it("keeps host, dealer, blind and all-in markers out of the pod that holds the name and stack", () => {
    const seat = renderSeat(
      occupant({ display_name: "Alexandrina-Montague", is_host: true }),
      participant({ position: "btn", blind: "small", all_in: true }),
    );
    const name = within(seat).getByText("Alexandrina-Montague");
    const stack = within(seat).getByText("$1,000");
    for (const marker of ["Host", "D", "SB", "All-in"]) {
      const el = within(seat).getByText(marker);
      expect(sharesContainerBelowSeat(seat, el, name), `${marker} and the name`).toBe(false);
      expect(sharesContainerBelowSeat(seat, el, stack), `${marker} and the stack`).toBe(false);
    }
  });

  it("keeps the markers out of the cards row", () => {
    const seat = renderSeat(
      occupant({ is_host: true }),
      participant({ position: "btn", blind: "big" }),
    );
    const [card] = within(seat).getAllByRole("img", { name: "Face-down card" });
    if (card === undefined) throw new Error("no card back rendered");
    for (const marker of ["Host", "D", "BB"]) {
      expect(sharesContainerBelowSeat(seat, card, within(seat).getByText(marker))).toBe(false);
    }
  });

  it("shows the big blind and no dealer marker for a non-dealer", () => {
    const seat = renderSeat(occupant(), participant({ blind: "big" }));
    expect(within(seat).getByText("BB")).toBeDefined();
    expect(within(seat).queryByText("D")).toBeNull();
    expect(within(seat).queryByText("SB")).toBeNull();
  });

  it("shows no marker for a plain seat with no hand", () => {
    const seat = renderSeat(occupant(), null);
    for (const marker of ["Host", "D", "SB", "BB", "All-in"]) {
      expect(within(seat).queryByText(marker)).toBeNull();
    }
  });

  it("shows a waiting or sitting-out status on its own, not inside the pod", () => {
    const seat = renderSeat(occupant({ status: "sitting_out" }), null);
    const status = within(seat).getByText("Sitting out");
    const name = within(seat).getByText("Alice");
    expect(sharesContainerBelowSeat(seat, status, name)).toBe(false);
  });
});

describe("Seat names and cards", () => {
  it("keeps a long name whole for assistive technology and for hover, so truncation loses nothing", () => {
    const seat = renderSeat(occupant({ display_name: "Alexandrina-Montague" }), null);
    expect(seat.getAttribute("aria-label")).toContain("Alexandrina-Montague");
    expect(within(seat).getByText("Alexandrina-Montague").getAttribute("title")).toBe(
      "Alexandrina-Montague",
    );
  });

  it("shows the hero's cards as faces and nobody else's, with no value for a card back", () => {
    const hero = renderSeat(
      occupant(),
      participant({ hole_cards: ["Ts", "Ah"], hidden_card_count: 0 }),
      true,
    );
    expect(within(hero).getByRole("img", { name: "Ten of spades" })).toBeDefined();
    expect(within(hero).getByRole("img", { name: "Ace of hearts" })).toBeDefined();
    expect(within(hero).queryByRole("img", { name: "Face-down card" })).toBeNull();
  });

  it("shows face-down cards from the hidden count alone", () => {
    const seat = renderSeat(occupant(), participant({ hidden_card_count: 2 }));
    expect(within(seat).getAllByRole("img", { name: "Face-down card" })).toHaveLength(2);
    expect(
      within(seat).queryByRole("img", { name: /of (clubs|diamonds|hearts|spades)/ }),
    ).toBeNull();
  });

  it("labels an empty seat and draws nothing else", () => {
    const seat = renderSeat(null, null);
    expect(seat.getAttribute("aria-label")).toBe("Seat 1, open");
    expect(within(seat).getByText("Seat 1")).toBeDefined();
    expect(within(seat).queryByRole("img")).toBeNull();
  });
});

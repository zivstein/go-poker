import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PlayingCard } from "./PlayingCard";

describe("PlayingCard", () => {
  it("names the card for assistive technology, with the rank printed as 10 for a ten", () => {
    render(<PlayingCard card="Ts" />);
    const card = screen.getByRole("img", { name: "Ten of spades" });
    expect(card.textContent).toContain("10");
  });

  it("prints the rank and suit once in the index, and the decorative pip hidden from assistive technology", () => {
    render(<PlayingCard card="Ah" size="lg" />);
    const card = screen.getByRole("img", { name: "Ace of hearts" });
    const hidden = card.querySelectorAll('[aria-hidden="true"]');
    expect(hidden).toHaveLength(1);
    expect(hidden[0]?.textContent).toBe("♥");
    // The index (rank over suit) is the only text outside the hidden pip.
    expect(card.textContent).toBe("A♥♥");
  });

  it("renders every size, so a face never depends on one size's layout", () => {
    for (const size of ["sm", "md", "lg"] as const) {
      const { unmount } = render(<PlayingCard card="Kd" size={size} />);
      expect(screen.getByRole("img", { name: "King of diamonds" })).toBeDefined();
      unmount();
    }
  });
});

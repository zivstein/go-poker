import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  type Box,
  betBox,
  betChipAnchor,
  REFERENCE_STAGE,
  RESULT_BOX,
  SEAT_METRICS,
  SUPPORTED_SEAT_COUNTS,
  seatFootprint,
  seatLayout,
} from "./seatLayout";

// The Board and PotDisplay positions (Board.module.css, PotDisplay.module.css)
// at the reference stage, with the widest content they can hold: five md
// cards, and two stacked pots.
const W = REFERENCE_STAGE.width;
const H = REFERENCE_STAGE.height;
const CARD_MD = { width: 44, height: 62 };
const BOARD: Box = {
  left: W / 2 - (5 * CARD_MD.width + 4 * 8) / 2,
  right: W / 2 + (5 * CARD_MD.width + 4 * 8) / 2,
  top: 0.4 * H - CARD_MD.height / 2,
  bottom: 0.4 * H + CARD_MD.height / 2,
};
const POTS: Box = {
  left: W / 2 - 110,
  right: W / 2 + 110,
  top: 0.55 * H - 22,
  bottom: 0.55 * H + 22,
};
// The hand-result panel at its largest, centred under the board.
const RESULT: Box = {
  left: W / 2 - RESULT_BOX.width / 2,
  right: W / 2 + RESULT_BOX.width / 2,
  top: (RESULT_BOX.topPct / 100) * H,
  bottom: (RESULT_BOX.topPct / 100) * H + RESULT_BOX.height,
};
const STAGE: Box = { left: 0, top: 0, right: W, bottom: H };

function overlaps(a: Box, b: Box, margin = 0): boolean {
  return (
    a.left < b.right + margin &&
    b.left < a.right + margin &&
    a.top < b.bottom + margin &&
    b.top < a.bottom + margin
  );
}

function inside(inner: Box, outer: Box): boolean {
  return (
    inner.left >= outer.left &&
    inner.top >= outer.top &&
    inner.right <= outer.right &&
    inner.bottom <= outer.bottom
  );
}

/** Every seat's footprint and bet box at the reference stage, hero at slot 0. */
function boxesFor(maxSeats: number) {
  const anchors = seatLayout(maxSeats, 1);
  return anchors.map((a, i) => {
    const isHero = i === 0;
    return {
      seat: a.seat,
      footprint: seatFootprint(a, isHero),
      bet: betBox(betChipAnchor(a, isHero)),
    };
  });
}

describe("seat footprints at the minimum supported stage", () => {
  it.each(SUPPORTED_SEAT_COUNTS)("fit the stage, with %i seats", (maxSeats) => {
    for (const { seat, footprint } of boxesFor(maxSeats)) {
      expect(inside(footprint, STAGE), `seat ${seat} is clipped by the stage`).toBe(true);
    }
  });

  it.each(SUPPORTED_SEAT_COUNTS)("never overlap each other, with %i seats", (maxSeats) => {
    const boxes = boxesFor(maxSeats);
    for (let i = 0; i < boxes.length; i++) {
      for (let j = i + 1; j < boxes.length; j++) {
        expect(
          overlaps(boxes[i]?.footprint as Box, boxes[j]?.footprint as Box, 4),
          `seats ${boxes[i]?.seat} and ${boxes[j]?.seat}`,
        ).toBe(false);
      }
    }
  });

  it.each(SUPPORTED_SEAT_COUNTS)("clear the board and the pots, with %i seats", (maxSeats) => {
    for (const { seat, footprint } of boxesFor(maxSeats)) {
      expect(overlaps(footprint, BOARD, 4), `seat ${seat} and the board`).toBe(false);
      expect(overlaps(footprint, POTS, 4), `seat ${seat} and the pots`).toBe(false);
    }
  });

  it.each(SUPPORTED_SEAT_COUNTS)(
    "clear the largest hand-result panel, with %i seats",
    (maxSeats) => {
      for (const { seat, footprint } of boxesFor(maxSeats)) {
        expect(overlaps(footprint, RESULT, 4), `seat ${seat} and the hand result`).toBe(false);
      }
    },
  );

  it("keep the largest hand-result panel below the board", () => {
    expect(RESULT.top).toBeGreaterThanOrEqual(BOARD.bottom);
  });
});

describe("bet chips at the minimum supported stage", () => {
  it.each(SUPPORTED_SEAT_COUNTS)(
    "sit on the stage, clear of every seat, the board, the pots and each other, with %i seats",
    (maxSeats) => {
      const boxes = boxesFor(maxSeats);
      for (const { seat, bet } of boxes) {
        expect(inside(bet, STAGE), `seat ${seat}'s bet is clipped`).toBe(true);
        expect(overlaps(bet, BOARD, 4), `seat ${seat}'s bet and the board`).toBe(false);
        expect(overlaps(bet, POTS, 4), `seat ${seat}'s bet and the pots`).toBe(false);
        for (const other of boxes) {
          expect(
            overlaps(bet, other.footprint, 2),
            `seat ${seat}'s bet and seat ${other.seat}`,
          ).toBe(false);
        }
      }
      for (let i = 0; i < boxes.length; i++) {
        for (let j = i + 1; j < boxes.length; j++) {
          expect(
            overlaps(boxes[i]?.bet as Box, boxes[j]?.bet as Box, 2),
            `bets of seats ${boxes[i]?.seat} and ${boxes[j]?.seat}`,
          ).toBe(false);
        }
      }
    },
  );

  it("sit between the seat and the table centre", () => {
    const [hero] = seatLayout(6, 1);
    if (hero === undefined) throw new Error("unreachable");
    const bet = betChipAnchor(hero, true);
    expect(bet.xPct).toBeCloseTo(hero.xPct, 5);
    expect(bet.yPct).toBeLessThan(hero.yPct);
    expect(bet.yPct).toBeGreaterThan(55);
  });
});

describe("seat metrics", () => {
  const tokens = readFileSync(join(process.cwd(), "src/theme/tokens.css"), "utf8");
  const px = (name: string): number => {
    const match = new RegExp(`--${name}:\\s*(\\d+)px`).exec(tokens);
    if (match?.[1] === undefined) throw new Error(`--${name} is missing from tokens.css`);
    return Number(match[1]);
  };

  it("mirror the tokens the seat CSS is built from", () => {
    expect(SEAT_METRICS.width).toBe(px("seat-w"));
    expect(SEAT_METRICS.podHeight).toBe(px("seat-pod-h"));
    expect(SEAT_METRICS.tagsHeight).toBe(px("seat-tags-h"));
    expect(SEAT_METRICS.gap).toBe(px("seat-gap"));
    expect(SEAT_METRICS.noteHeight).toBe(px("seat-note-h"));
    expect(SEAT_METRICS.cardHeight.sm).toBe(px("card-h-sm"));
    expect(SEAT_METRICS.cardHeight.lg).toBe(px("card-h-lg"));
    expect(RESULT_BOX.width).toBe(px("result-max-w"));
    expect(RESULT_BOX.height).toBe(px("result-max-h"));
    // The stage's 10px rail on each side, around the reference stage.
    expect(REFERENCE_STAGE.width + 20).toBe(px("stage-min-w"));
    expect(CARD_MD.width).toBe(px("card-w-md"));
    expect(CARD_MD.height).toBe(px("card-h-md"));
  });

  it("keep the stage at least the minimum width, and the result panel within its box", () => {
    const stage = readFileSync(join(process.cwd(), "src/table/TableStage.module.css"), "utf8");
    expect(stage).toMatch(/width:\s*clamp\(var\(--stage-min-w\),[^;]*,\s*100%\)/);
    expect(stage).toMatch(/flex:\s*none/);
    const result = readFileSync(join(process.cwd(), "src/table/HandResult.module.css"), "utf8");
    expect(result).toMatch(/max-width:\s*var\(--result-max-w\)/);
    expect(result).toMatch(/max-height:\s*var\(--result-max-h\)/);
    expect(result).toMatch(/overflow-y:\s*auto/);
  });

  it("are the only source of card and board-slot sizes in CSS", () => {
    for (const file of [
      "ui/PlayingCard.module.css",
      "ui/CardBack.module.css",
      "table/Board.module.css",
    ]) {
      const css = readFileSync(join(process.cwd(), "src", file), "utf8");
      expect(css, file).not.toMatch(/(?:width|height):\s*\d+px/);
    }
  });
});

describe("seatLayout", () => {
  it("places the hero at the bottom centre for every seat count and hero seat", () => {
    for (const maxSeats of SUPPORTED_SEAT_COUNTS) {
      for (let heroSeat = 1; heroSeat <= maxSeats; heroSeat++) {
        const anchors = seatLayout(maxSeats, heroSeat);
        const hero = anchors.find((a) => a.seat === heroSeat);
        expect(hero).toBeDefined();
        expect(hero?.xPct).toBeCloseTo(50, 0);
        // The anchor is the pod centre; the hero's cards hang below it.
        expect(hero?.yPct).toBeGreaterThan(70);
      }
    }
  });

  it("returns every seat number exactly once, for every seat count", () => {
    for (const maxSeats of SUPPORTED_SEAT_COUNTS) {
      const anchors = seatLayout(maxSeats, 1);
      const seats = anchors.map((a) => a.seat).sort((x, y) => x - y);
      expect(seats).toEqual(Array.from({ length: maxSeats }, (_, i) => i + 1));
    }
  });

  it("keeps anchor positions fixed per slot, independent of hero rotation", () => {
    // Rotation is presentational only: the set of anchor points used is the
    // same regardless of which seat is the hero.
    for (const maxSeats of SUPPORTED_SEAT_COUNTS) {
      const base = seatLayout(maxSeats, 1)
        .map((a) => `${a.xPct},${a.yPct}`)
        .sort();
      for (let heroSeat = 2; heroSeat <= maxSeats; heroSeat++) {
        const rotated = seatLayout(maxSeats, heroSeat)
          .map((a) => `${a.xPct},${a.yPct}`)
          .sort();
        expect(rotated).toEqual(base);
      }
    }
  });

  it("rejects an unsupported seat count or an out-of-range hero seat", () => {
    expect(() => seatLayout(10, 1)).toThrow();
    expect(() => seatLayout(6, 7)).toThrow();
    expect(() => seatLayout(6, 0)).toThrow();
  });
});

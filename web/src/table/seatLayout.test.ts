import { describe, expect, it } from "vitest";
import { SUPPORTED_SEAT_COUNTS, seatLayout } from "./seatLayout";

// The minimum supported stage size (desktop ≥ 1024, C6.2 plan §4.5).
const STAGE_W = 1024;
const STAGE_H = 576;
// A seat pod's assumed footprint: two pods must be at least this far apart
// (center to center) to avoid overlapping.
const MIN_CLEARANCE_PX = 100;

function pixelDistance(
  a: { xPct: number; yPct: number },
  b: { xPct: number; yPct: number },
): number {
  const dx = ((a.xPct - b.xPct) / 100) * STAGE_W;
  const dy = ((a.yPct - b.yPct) / 100) * STAGE_H;
  return Math.hypot(dx, dy);
}

describe("seatLayout", () => {
  it("has no overlap at 9 seats, at the minimum supported size", () => {
    const anchors = seatLayout(9, 1);
    for (let i = 0; i < anchors.length; i++) {
      for (let j = i + 1; j < anchors.length; j++) {
        const a = anchors[i];
        const b = anchors[j];
        if (a === undefined || b === undefined) throw new Error("unreachable");
        expect(pixelDistance(a, b)).toBeGreaterThanOrEqual(MIN_CLEARANCE_PX);
      }
    }
  });

  it("places the hero at the bottom centre for every seat count and hero seat", () => {
    for (const maxSeats of SUPPORTED_SEAT_COUNTS) {
      for (let heroSeat = 1; heroSeat <= maxSeats; heroSeat++) {
        const anchors = seatLayout(maxSeats, heroSeat);
        const hero = anchors.find((a) => a.seat === heroSeat);
        expect(hero).toBeDefined();
        expect(hero?.xPct).toBeCloseTo(50, 0);
        expect(hero?.yPct).toBeGreaterThan(80);
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

/**
 * Hand-tuned seat anchors for each `max_seats` from 2 to 9 (C6.2 plan §4.5,
 * W18): pure data, with the hero at slot 0 (bottom centre) and the rest
 * clockwise. Percent coordinates within the table stage. Unit-tested for no
 * overlap at 9 seats at the minimum supported size.
 */

export interface SeatAnchor {
  seat: number;
  xPct: number;
  yPct: number;
}

type Point = { xPct: number; yPct: number };

const ANCHOR_TABLES: Record<number, Point[]> = {
  2: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 50.0, yPct: 15.0 },
  ],
  3: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 11.9, yPct: 35.0 },
    { xPct: 88.1, yPct: 35.0 },
  ],
  4: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 6.0, yPct: 55.0 },
    { xPct: 50.0, yPct: 15.0 },
    { xPct: 94.0, yPct: 55.0 },
  ],
  5: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 8.2, yPct: 67.4 },
    { xPct: 24.1, yPct: 22.6 },
    { xPct: 75.9, yPct: 22.6 },
    { xPct: 91.8, yPct: 67.4 },
  ],
  6: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 11.9, yPct: 75.0 },
    { xPct: 11.9, yPct: 35.0 },
    { xPct: 50.0, yPct: 15.0 },
    { xPct: 88.1, yPct: 35.0 },
    { xPct: 88.1, yPct: 75.0 },
  ],
  7: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 15.6, yPct: 79.9 },
    { xPct: 7.1, yPct: 46.1 },
    { xPct: 30.9, yPct: 19.0 },
    { xPct: 69.1, yPct: 19.0 },
    { xPct: 92.9, yPct: 46.1 },
    { xPct: 84.4, yPct: 79.9 },
  ],
  8: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 18.9, yPct: 83.3 },
    { xPct: 6.0, yPct: 55.0 },
    { xPct: 18.9, yPct: 26.7 },
    { xPct: 50.0, yPct: 15.0 },
    { xPct: 81.1, yPct: 26.7 },
    { xPct: 94.0, yPct: 55.0 },
    { xPct: 81.1, yPct: 83.3 },
  ],
  9: [
    { xPct: 50.0, yPct: 95.0 },
    { xPct: 21.7, yPct: 85.6 },
    { xPct: 6.7, yPct: 61.9 },
    { xPct: 11.9, yPct: 35.0 },
    { xPct: 35.0, yPct: 17.4 },
    { xPct: 65.0, yPct: 17.4 },
    { xPct: 88.1, yPct: 35.0 },
    { xPct: 93.3, yPct: 61.9 },
    { xPct: 78.3, yPct: 85.6 },
  ],
};

/**
 * Lays out seats 1..`maxSeats`, the hero at the bottom and the rest
 * clockwise (seat numbers increase clockwise around the table, matching
 * button and position assignment). Seat numbers are the server's; rotation
 * is presentational only.
 */
export function seatLayout(maxSeats: number, heroSeat: number): SeatAnchor[] {
  const anchors = ANCHOR_TABLES[maxSeats];
  if (anchors === undefined) throw new Error(`no seat layout for ${maxSeats} seats`);
  if (heroSeat < 1 || heroSeat > maxSeats) throw new Error(`seat ${heroSeat} is out of range`);
  const heroIndex = heroSeat - 1;
  const result: SeatAnchor[] = [];
  for (let i = 0; i < maxSeats; i++) {
    const seat = i + 1;
    const slot = (i - heroIndex + maxSeats) % maxSeats;
    const anchor = anchors[slot];
    if (anchor === undefined) throw new Error("unreachable: slot out of range");
    result.push({ seat, xPct: anchor.xPct, yPct: anchor.yPct });
  }
  return result;
}

export const SUPPORTED_SEAT_COUNTS = [2, 3, 4, 5, 6, 7, 8, 9] as const;

const CENTER: Point = { xPct: 50, yPct: 55 };

/** Chips-in-front anchors are interpolated toward the centre (C6.2 plan §4.5). */
export function betChipAnchor(seatAnchor: Point, t = 0.38): Point {
  return {
    xPct: seatAnchor.xPct + (CENTER.xPct - seatAnchor.xPct) * t,
    yPct: seatAnchor.yPct + (CENTER.yPct - seatAnchor.yPct) * t,
  };
}

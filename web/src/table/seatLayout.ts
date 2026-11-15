/**
 * Hand-tuned seat anchors for each `max_seats` from 2 to 9 (C6.2 plan §4.5,
 * W18): pure data, with the hero at slot 0 (bottom centre) and the rest
 * clockwise. Percent coordinates within the table stage.
 *
 * An anchor is the centre of a seat's pod. The seat's whole footprint (tags
 * row above, cards and hand label below; see `seatFootprint`) must fit the
 * stage and clear every other seat, the board, the pot and the hand-result
 * panel (`RESULT_BOX`) at the minimum supported stage (1024x576, enforced by
 * `TableStage.module.css`); `seatLayout.test.ts` checks this for 2 to 9
 * seats.
 */

export interface SeatAnchor {
  seat: number;
  xPct: number;
  yPct: number;
}

type Point = { xPct: number; yPct: number };

const ANCHOR_TABLES: Record<number, Point[]> = {
  2: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 50.0, yPct: 11.0 },
  ],
  3: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 14.1, yPct: 27.3 },
    { xPct: 85.9, yPct: 27.3 },
  ],
  4: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 8.5, yPct: 44.0 },
    { xPct: 50.0, yPct: 10.5 },
    { xPct: 91.5, yPct: 44.0 },
  ],
  5: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 9.6, yPct: 55.4 },
    { xPct: 25.7, yPct: 12.4 },
    { xPct: 74.3, yPct: 12.4 },
    { xPct: 90.4, yPct: 55.4 },
  ],
  6: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 14.1, yPct: 60.8 },
    { xPct: 14.1, yPct: 27.3 },
    { xPct: 50.0, yPct: 10.5 },
    { xPct: 85.9, yPct: 27.3 },
    { xPct: 85.9, yPct: 60.8 },
  ],
  7: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 12.2, yPct: 65.9 },
    { xPct: 11.0, yPct: 35.6 },
    { xPct: 30.7, yPct: 12.5 },
    { xPct: 69.3, yPct: 12.5 },
    { xPct: 89.0, yPct: 35.6 },
    { xPct: 87.8, yPct: 65.9 },
  ],
  8: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 20.9, yPct: 74.3 },
    { xPct: 9.4, yPct: 42.5 },
    { xPct: 18.4, yPct: 17.7 },
    { xPct: 50.0, yPct: 12.6 },
    { xPct: 81.6, yPct: 17.7 },
    { xPct: 90.6, yPct: 42.5 },
    { xPct: 79.1, yPct: 74.3 },
  ],
  9: [
    { xPct: 50.0, yPct: 77.0 },
    { xPct: 24.6, yPct: 72.0 },
    { xPct: 9.1, yPct: 54.3 },
    { xPct: 10.9, yPct: 27.7 },
    { xPct: 35.6, yPct: 9.3 },
    { xPct: 64.4, yPct: 9.3 },
    { xPct: 89.1, yPct: 27.7 },
    { xPct: 90.9, yPct: 54.3 },
    { xPct: 75.4, yPct: 72.0 },
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

/** The minimum supported stage (a 1024x576 stage inside its 10px rail), in px:
 * the size the geometry below is tuned and tested at. A larger stage only adds
 * room, because seats and chips keep their pixel size. */
export const REFERENCE_STAGE = { width: 1004, height: 556 } as const;

/** Seat pod sizes in px. Mirrors the `--seat-*` and `--card-h-*` tokens in
 * `theme/tokens.css`; `seatLayout.test.ts` fails if they drift apart. */
export const SEAT_METRICS = {
  width: 144,
  podHeight: 46,
  tagsHeight: 16,
  gap: 4,
  noteHeight: 14,
  cardHeight: { sm: 44, lg: 78 },
} as const;

/** A chip stack and its amount label, at its widest. Measured in the browser:
 * 102px for "$1,234,567" and "$9,999,999" (the widest seven-digit amounts, in
 * tabular numerals), so 108px leaves room for a wider fallback font. */
export const BET_BOX = { width: 108, height: 20 } as const;

/** The hand-result panel's largest box, in px, hanging from 46% of the stage
 * height (the board's bottom edge) and centred. Mirrors `--result-max-w` and
 * `--result-max-h`; the panel scrolls rather than grow past it, so it can
 * never cover a seat the layout keeps clear of this box. */
export const RESULT_BOX = { width: 560, height: 96, topPct: 46 } as const;

/** Clearance kept between a seat and its own bet, in px. */
const BET_CLEARANCE = 6;

export interface Box {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

const CENTER: Point = { xPct: 50, yPct: 55 };

function toPx(p: Point): { x: number; y: number } {
  return {
    x: (p.xPct / 100) * REFERENCE_STAGE.width,
    y: (p.yPct / 100) * REFERENCE_STAGE.height,
  };
}

function overlaps(a: Box, b: Box, margin: number): boolean {
  return (
    a.left < b.right + margin &&
    b.left < a.right + margin &&
    a.top < b.bottom + margin &&
    b.top < a.bottom + margin
  );
}

/** Everything a seat can draw, in reference-stage px: the tags row above the
 * pod, and below it the cards (the hero's are larger) and the hand label. The
 * worst case, whether or not a hand is on. */
export function seatFootprint(anchor: Point, isHero: boolean): Box {
  const { x, y } = toPx(anchor);
  const m = SEAT_METRICS;
  const cards = isHero ? m.cardHeight.lg : m.cardHeight.sm;
  return {
    left: x - m.width / 2,
    right: x + m.width / 2,
    top: y - m.podHeight / 2 - m.gap - m.tagsHeight,
    bottom: y + m.podHeight / 2 + m.gap + cards + m.gap + m.noteHeight,
  };
}

/** The box of a bet label centred on an anchor, in reference-stage px. */
export function betBox(anchor: Point): Box {
  const { x, y } = toPx(anchor);
  return {
    left: x - BET_BOX.width / 2,
    right: x + BET_BOX.width / 2,
    top: y - BET_BOX.height / 2,
    bottom: y + BET_BOX.height / 2,
  };
}

/** Chips in front sit on the line from the seat to the table centre, at the
 * first point where they clear the seat's whole footprint (C6.2 plan §4.5,
 * revised: a fixed fraction toward the centre landed on the seat's own cards). */
export function betChipAnchor(seatAnchor: Point, isHero = false): Point {
  const footprint = seatFootprint(seatAnchor, isHero);
  const from = toPx(seatAnchor);
  const to = toPx(CENTER);
  const length = Math.hypot(to.x - from.x, to.y - from.y);
  const ux = (to.x - from.x) / length;
  const uy = (to.y - from.y) / length;
  for (let step = 0; step <= length; step++) {
    const xPct = ((from.x + ux * step) / REFERENCE_STAGE.width) * 100;
    const yPct = ((from.y + uy * step) / REFERENCE_STAGE.height) * 100;
    if (!overlaps(betBox({ xPct, yPct }), footprint, BET_CLEARANCE)) return { xPct, yPct };
  }
  return { xPct: CENTER.xPct, yPct: CENTER.yPct };
}

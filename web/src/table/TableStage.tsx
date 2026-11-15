import type { TableView } from "../protocol/types";
import { BetChips } from "./BetChips";
import { Board } from "./Board";
import { HandResult } from "./HandResult";
import { PotDisplay } from "./PotDisplay";
import { Seat } from "./Seat";
import { betChipAnchor, seatLayout } from "./seatLayout";
import styles from "./TableStage.module.css";

export interface TableStageProps {
  view: TableView;
}

/** The felt and rail: `SeatRing`, `Board`, `PotDisplay`, `BetChips`, and the
 * hand result once the hand is settled (C6.2 plan §3.2). */
export function TableStage({ view }: TableStageProps) {
  const anchors = seatLayout(view.settings.max_seats, view.you.seat);
  const anchorBySeat = new Map(anchors.map((a) => [a.seat, a]));
  const participantBySeat = new Map((view.hand?.participants ?? []).map((p) => [p.seat, p]));
  const seatNames = Object.fromEntries(
    view.seats
      .filter((s) => s.occupant !== null)
      .map((s) => [s.seat, s.occupant?.display_name ?? `Seat ${s.seat}`]),
  );
  const turnSeat = view.hand?.turn?.seat ?? null;

  return (
    <div className={styles.stage}>
      <div className={styles.felt} />
      <Board cards={view.hand?.board ?? []} />
      <PotDisplay pots={view.hand?.pots ?? []} />
      {view.seats.map((seat) => {
        const anchor = anchorBySeat.get(seat.seat);
        if (anchor === undefined) return null;
        const participant = participantBySeat.get(seat.seat) ?? null;
        return (
          <Seat
            key={seat.seat}
            seatNumber={seat.seat}
            occupant={seat.occupant}
            participant={participant}
            isHero={seat.seat === view.you.seat}
            isTurn={seat.seat === turnSeat}
            xPct={anchor.xPct}
            yPct={anchor.yPct}
          />
        );
      })}
      {(view.hand?.participants ?? [])
        .filter((p) => p.in_front > 0)
        .map((p) => {
          const anchor = anchorBySeat.get(p.seat);
          if (anchor === undefined) return null;
          const chipAnchor = betChipAnchor(anchor, p.seat === view.you.seat);
          return (
            <BetChips
              key={p.seat}
              amount={p.in_front}
              xPct={chipAnchor.xPct}
              yPct={chipAnchor.yPct}
            />
          );
        })}
      {view.hand?.settlement && (
        <HandResult
          settlement={view.hand.settlement}
          participants={view.hand.participants}
          seatNames={seatNames}
        />
      )}
    </div>
  );
}

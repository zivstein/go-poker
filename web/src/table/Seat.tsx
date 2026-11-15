import type { Occupant, Participant } from "../protocol/types";
import { Amount } from "../ui/Amount";
import { CardBack } from "../ui/CardBack";
import { PlayingCard } from "../ui/PlayingCard";
import styles from "./Seat.module.css";

export interface SeatProps {
  seatNumber: number;
  occupant: Occupant | null;
  participant: Participant | null;
  isHero: boolean;
  isTurn: boolean;
  xPct: number;
  yPct: number;
}

function monogram(name: string): string {
  const trimmed = name.trim();
  if (trimmed.length === 0) return "?";
  const parts = trimmed.split(/\s+/);
  const first = parts[0]?.charAt(0) ?? "";
  const last = parts.length > 1 ? (parts[parts.length - 1]?.charAt(0) ?? "") : "";
  return (first + last).toUpperCase();
}

function statusLabel(status: Occupant["status"]): string | null {
  if (status === "waiting_to_join") return "Waiting to join";
  if (status === "sitting_out") return "Sitting out";
  return null;
}

export function Seat({ seatNumber, occupant, participant, isHero, isTurn, xPct, yPct }: SeatProps) {
  const style = { left: `${xPct}%`, top: `${yPct}%` };

  if (occupant === null) {
    return (
      // biome-ignore lint/a11y/useSemanticElements: a seat pod is not a form fieldset
      <div
        className={styles.seat}
        style={style}
        role="group"
        aria-label={`Seat ${seatNumber}, open`}
      >
        <div className={styles.tags} aria-hidden="true" />
        <div className={styles.empty}>Seat {seatNumber}</div>
      </div>
    );
  }

  const folded = participant?.folded ?? false;
  const accessibleLabel = `Seat ${seatNumber}, ${occupant.display_name}, ${occupant.stack} dollars`;
  const status = statusLabel(occupant.status);
  const cardSize = isHero ? "lg" : "sm";

  return (
    // biome-ignore lint/a11y/useSemanticElements: a seat pod is not a form fieldset
    <div
      className={`${styles.seat} ${isTurn ? styles.turn : ""} ${folded ? styles.folded : ""}`}
      style={style}
      role="group"
      aria-label={accessibleLabel}
    >
      <div className={styles.tags}>
        {occupant.is_host && <span className={`${styles.tag} ${styles.hostBadge}`}>Host</span>}
        {participant?.position === "btn" && (
          <span className={`${styles.tag} ${styles.dealerButton}`} title="Dealer button">
            D
          </span>
        )}
        {participant?.blind === "small" && (
          <span className={styles.tag} title="Small blind">
            SB
          </span>
        )}
        {participant?.blind === "big" && (
          <span className={styles.tag} title="Big blind">
            BB
          </span>
        )}
        {participant?.all_in && <span className={`${styles.tag} ${styles.allIn}`}>All-in</span>}
        {status && <span className={`${styles.tag} ${styles.status}`}>{status}</span>}
      </div>
      <div className={styles.pod}>
        <div className={styles.avatar} aria-hidden="true">
          {monogram(occupant.display_name)}
        </div>
        <div className={styles.info}>
          <div className={styles.name} title={occupant.display_name}>
            {occupant.display_name}
          </div>
          <div className={styles.stack}>
            <Amount value={occupant.stack} />
          </div>
        </div>
      </div>
      {participant && (participant.hole_cards !== null || participant.hidden_card_count > 0) && (
        <div className={styles.cards}>
          {participant.hole_cards !== null
            ? participant.hole_cards.map((card) => (
                <PlayingCard key={card} card={card} size={cardSize} />
              ))
            : Array.from({ length: participant.hidden_card_count }, (_, i) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: interchangeable face-down placeholders
                <CardBack key={i} size={cardSize} />
              ))}
        </div>
      )}
      {participant?.strength && (
        <div className={styles.strength} title={participant.strength.description}>
          {participant.strength.description}
        </div>
      )}
    </div>
  );
}

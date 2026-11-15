import type { Participant, Settlement } from "../protocol/types";
import { Amount } from "../ui/Amount";
import { PlayingCard } from "../ui/PlayingCard";
import styles from "./HandResult.module.css";

export interface HandResultProps {
  settlement: Settlement;
  participants: Participant[];
  seatNames: Record<number, string>;
}

/** Awards per pot, and the best five of every shown hand (C6.2 plan §3.2). */
export function HandResult({ settlement, participants, seatNames }: HandResultProps) {
  const bySeat = new Map(participants.map((p) => [p.seat, p]));
  return (
    // biome-ignore lint/a11y/useSemanticElements: a hand-result panel is not a form fieldset
    <div className={styles.result} role="group" aria-label="Hand result">
      {settlement.pot_awards.map((award, index) => (
        <div className={styles.award} key={`${award.amount}-${award.eligible_seats.join(",")}`}>
          <span className={styles.potLabel}>{index === 0 ? "Pot" : "Side pot"}</span>
          {award.shares.map((share) => (
            <span className={styles.share} key={share.seat}>
              {seatNames[share.seat] ?? `Seat ${share.seat}`} wins <Amount value={share.amount} />
            </span>
          ))}
        </div>
      ))}
      {settlement.shown_ranks.length > 0 && (
        <div className={styles.shown}>
          {settlement.shown_ranks.map(({ seat, category }) => {
            const participant = bySeat.get(seat);
            return (
              <div className={styles.shownHand} key={seat}>
                <span className={styles.shownName}>{seatNames[seat] ?? `Seat ${seat}`}</span>
                <span className={styles.shownCategory}>{category.replace(/_/g, " ")}</span>
                {participant?.strength && (
                  <span className={styles.shownCards}>
                    {participant.strength.cards.map((card) => (
                      <PlayingCard key={card} card={card} size="sm" />
                    ))}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

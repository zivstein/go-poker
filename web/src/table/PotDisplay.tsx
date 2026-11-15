import type { Pot } from "../protocol/types";
import { Amount } from "../ui/Amount";
import styles from "./PotDisplay.module.css";

export interface PotDisplayProps {
  pots: Pot[];
}

/** Main pot and side pots, rendered exactly as given: never merged or
 * re-split (ADR 0009 §10; the known Core defect is not "fixed" here). */
export function PotDisplay({ pots }: PotDisplayProps) {
  if (pots.length === 0) return null;
  return (
    // biome-ignore lint/a11y/useSemanticElements: a pot display is not a form fieldset
    <div className={styles.pots} role="group" aria-label="Pots">
      {pots.map((pot, index) => (
        <div className={styles.pot} key={`${pot.amount}-${pot.eligible_seats.join(",")}`}>
          <span className={styles.label}>{index === 0 ? "Pot" : "Side pot"}</span>
          <span className={styles.amount}>
            <Amount value={pot.amount} />
          </span>
        </div>
      ))}
    </div>
  );
}

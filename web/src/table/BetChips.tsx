import { Amount } from "../ui/Amount";
import { Chip } from "../ui/Chip";
import styles from "./BetChips.module.css";

export interface BetChipsProps {
  amount: number;
  xPct: number;
  yPct: number;
}

/** Chips in front, on an anchor between the seat and the centre (C6.2 plan §4.5). */
export function BetChips({ amount, xPct, yPct }: BetChipsProps) {
  if (amount <= 0) return null;
  return (
    <div className={styles.chips} style={{ left: `${xPct}%`, top: `${yPct}%` }}>
      <Chip size={16} />
      <span className={styles.amount}>
        <Amount value={amount} />
      </span>
    </div>
  );
}

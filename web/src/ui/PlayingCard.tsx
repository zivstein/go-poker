import { cardAccessibleName, cardColor, cardRankLabel, cardSuitSymbol } from "../format/cards";
import styles from "./PlayingCard.module.css";

export interface PlayingCardProps {
  card: string;
  size?: "sm" | "md" | "lg";
}

/** A code-drawn playing card face, two-color, with an accessible name (W23). */
export function PlayingCard({ card, size = "md" }: PlayingCardProps) {
  const color = cardColor(card);
  return (
    <span
      className={`${styles.card} ${styles[size]} ${color === "red" ? styles.red : styles.black}`}
      role="img"
      aria-label={cardAccessibleName(card)}
    >
      <span className={styles.corner}>
        <span className={styles.rank}>{cardRankLabel(card)}</span>
        <span className={styles.suit}>{cardSuitSymbol(card)}</span>
      </span>
      <span className={styles.pip} aria-hidden="true">
        {cardSuitSymbol(card)}
      </span>
    </span>
  );
}

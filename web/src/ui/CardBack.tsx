import styles from "./CardBack.module.css";

export interface CardBackProps {
  size?: "sm" | "md" | "lg";
}

/** A themed geometric pattern, logo-free (C6.2 plan §4.6, §4.7). Draws no
 * card value: card backs come only from `hidden_card_count`. */
export function CardBack({ size = "md" }: CardBackProps) {
  return (
    <span className={`${styles.back} ${styles[size]}`} role="img" aria-label="Face-down card" />
  );
}

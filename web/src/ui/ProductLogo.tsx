import { Chip } from "./Chip";
import styles from "./ProductLogo.module.css";

export interface ProductLogoProps {
  variant?: "compact" | "wide";
}

/**
 * The provisional Go! Poker wordmark (C6.2 plan §4.2, W13): a typeset
 * lockup, not traced from any reference sheet. `Go` and `Poker` in the
 * display face; the chip glyph replaces the `o` of `Go!`; the `!` is in the
 * product accent. Approved vector assets replace this component later, with
 * no other change.
 */
export function ProductLogo({ variant = "wide" }: ProductLogoProps) {
  return (
    <span
      className={`${styles.logo} ${variant === "compact" ? styles.compact : styles.wide}`}
      role="img"
      aria-label="Go! Poker"
    >
      <span className={styles.go} aria-hidden="true">
        G<Chip size={variant === "compact" ? 16 : 20} className={styles.chip} />
        <span className={styles.bang}>!</span>
      </span>
      {variant === "wide" && (
        <span className={styles.poker} aria-hidden="true">
          Poker
        </span>
      )}
    </span>
  );
}

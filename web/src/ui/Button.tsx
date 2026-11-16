import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "neutral" | "destructive";
  /** The command this button sent is in flight: `aria-busy`, and a spinner
   * that appears only after a short delay (no flicker on a fast reply). */
  busy?: boolean;
}

const VARIANT_CLASS = {
  primary: styles.primary,
  secondary: styles.secondary,
  neutral: styles.neutral,
  destructive: styles.destructive,
};

/** Fold neutral, Check/Call outlined, Bet/Raise filled with the accent (C6.2
 * §4.6); destructive confirmations use the error status with an icon (W11). */
export function Button({
  variant = "secondary",
  busy = false,
  className,
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[styles.button, VARIANT_CLASS[variant], className].filter(Boolean).join(" ")}
      aria-busy={busy || undefined}
      {...rest}
    >
      {children}
      {busy && <span className={styles.spinner} aria-hidden="true" />}
    </button>
  );
}

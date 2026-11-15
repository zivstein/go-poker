import type { ButtonHTMLAttributes } from "react";
import styles from "./Button.module.css";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "neutral";
}

/** Fold neutral, Check/Call outlined, Bet/Raise filled with the accent (C6.2 §4.6). */
export function Button({
  variant = "secondary",
  className,
  type = "button",
  ...rest
}: ButtonProps) {
  const variantClass =
    variant === "primary"
      ? styles.primary
      : variant === "neutral"
        ? styles.neutral
        : styles.secondary;
  return (
    <button
      type={type}
      className={[styles.button, variantClass, className].filter(Boolean).join(" ")}
      {...rest}
    />
  );
}

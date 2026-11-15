import { useState } from "react";
import styles from "./DevThemeToggle.module.css";

export type ThemeId = "emerald" | "sapphire";

/**
 * The dev-only Sapphire toggle (C6.2 plan W12): a token proof so a
 * hardcoded green is obvious. There is no user-facing theme picker.
 */
export function DevThemeToggle() {
  const [theme, setTheme] = useState<ThemeId>("emerald");

  if (!import.meta.env.DEV) return null;

  function toggle() {
    const next: ThemeId = theme === "emerald" ? "sapphire" : "emerald";
    setTheme(next);
    document.documentElement.dataset.theme = next;
  }

  return (
    <button type="button" className={styles.toggle} onClick={toggle}>
      Dev theme: {theme}
    </button>
  );
}

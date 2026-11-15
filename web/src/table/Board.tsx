import type { Card } from "../protocol/types";
import { PlayingCard } from "../ui/PlayingCard";
import styles from "./Board.module.css";

export interface BoardProps {
  cards: Card[];
}

const BOARD_SIZE = 5;

/** Reserved slots: no layout shift as the board grows (C6.2 plan §3.2). */
export function Board({ cards }: BoardProps) {
  return (
    // biome-ignore lint/a11y/useSemanticElements: a reserved card slot row is not a form fieldset
    <div className={styles.board} role="group" aria-label="Board">
      {Array.from({ length: BOARD_SIZE }, (_, i) => {
        const card = cards[i];
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length reserved slots, never reordered
          <div className={styles.slot} key={`slot-${i}`}>
            {card !== undefined && <PlayingCard card={card} size="md" />}
          </div>
        );
      })}
    </div>
  );
}

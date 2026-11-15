import { useEffect, useState } from "react";
import { formatMoney } from "../format/money";
import type { ActArgs, LegalActions, ShowdownDecision, TableView } from "../protocol/types";
import { Button } from "../ui/Button";
import { betSizerRange, isAllInTarget } from "../variant/toActionOptions";
import styles from "./ActionDock.module.css";

export interface ActionDockProps {
  view: TableView;
  disabled: boolean;
  onAct: (args: ActArgs) => void;
  onShowdownDecision: (decision: ShowdownDecision) => void;
  onStartGame: () => void;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function callLabel(legal: LegalActions): string {
  const amount = formatMoney(legal.call_amount);
  return legal.call_is_all_in ? `Call ${amount} (All-in)` : `Call ${amount}`;
}

/** The amount the draft text stands for, clamped to the server's range, or
 * `null` when the text is not a whole number (empty, `-`, `1.5`, ...). Nothing
 * is guessed for text that is not a whole number. */
function parseDraft(text: string, min: number, max: number): number | null {
  return /^\d+$/.test(text) ? clamp(Number(text), min, max) : null;
}

function betOrRaiseLabel(legal: LegalActions, target: number | null): string {
  if (target === null) return legal.can_bet ? "Bet" : "Raise to";
  if (isAllInTarget(legal, target)) return `All-in ${formatMoney(target)}`;
  return legal.can_bet ? `Bet ${formatMoney(target)}` : `Raise to ${formatMoney(target)}`;
}

function BettingControls({
  legal,
  disabled,
  onAct,
}: {
  legal: LegalActions;
  disabled: boolean;
  onAct: (a: ActArgs) => void;
}) {
  const sizer = betSizerRange(legal);
  // The draft is the raw text of the exact-amount field, so typing is never
  // rewritten mid-keystroke; it is clamped only where an amount is read
  // (the label, the submit) and when the field loses focus. UI-only state.
  const [draftText, setDraftText] = useState<string>(
    String(sizer?.shortAllInTarget ?? sizer?.min ?? 0),
  );
  const draft = sizer ? parseDraft(draftText, sizer.min, sizer.max) : null;

  // Re-clamp the draft amount to the current sizer bounds whenever a new
  // decision's `legal_actions` arrive. `sizer.max` (`max_target`) must be a
  // dependency too: the actor's stack - and so the max - can shrink between
  // decisions while `min_full_target`/`short_all_in_target` repeat, and the
  // draft must never be left (rendered or submitted) above the current
  // legal maximum, nor below the current legal minimum (C6.2 §2.3).
  const sizerMin = sizer?.min;
  const sizerMax = sizer?.max;
  const sizerShortAllIn = sizer?.shortAllInTarget;
  useEffect(() => {
    if (sizerMin === undefined || sizerMax === undefined) return;
    setDraftText((prev) => {
      if (sizerShortAllIn !== null && sizerShortAllIn !== undefined) return String(sizerShortAllIn);
      return String(parseDraft(prev, sizerMin, sizerMax) ?? sizerMin);
    });
  }, [sizerMin, sizerMax, sizerShortAllIn]);

  return (
    <>
      {legal.can_fold && (
        <Button
          variant="neutral"
          disabled={disabled}
          onClick={() => onAct({ action: "fold", target: null })}
        >
          Fold
        </Button>
      )}
      {legal.can_check && (
        <Button
          variant="secondary"
          disabled={disabled}
          onClick={() => onAct({ action: "check", target: null })}
        >
          Check
        </Button>
      )}
      {legal.can_call && (
        <Button
          variant="secondary"
          disabled={disabled}
          onClick={() => onAct({ action: "call", target: null })}
        >
          {callLabel(legal)}
        </Button>
      )}
      {sizer &&
        (sizer.shortAllInTarget !== null ? (
          <Button
            variant="primary"
            disabled={disabled}
            onClick={() => onAct({ action: sizer.kind, target: sizer.shortAllInTarget as number })}
          >
            {betOrRaiseLabel(legal, sizer.shortAllInTarget)}
          </Button>
        ) : (
          <div className={styles.sizer}>
            <Button
              variant="neutral"
              disabled={disabled}
              onClick={() => setDraftText(String(sizer.min))}
            >
              Min
            </Button>
            <input
              type="range"
              className={styles.slider}
              min={sizer.min}
              max={sizer.max}
              value={draft ?? sizer.min}
              disabled={disabled}
              aria-label="Bet amount"
              onChange={(e) =>
                setDraftText(String(clamp(Number(e.target.value), sizer.min, sizer.max)))
              }
            />
            <input
              type="number"
              className={styles.numberInput}
              min={sizer.min}
              max={sizer.max}
              value={draftText}
              disabled={disabled}
              aria-label="Bet amount (exact)"
              onChange={(e) => setDraftText(e.target.value)}
              onBlur={() => {
                if (draft !== null) setDraftText(String(draft));
              }}
            />
            <Button
              variant="neutral"
              disabled={disabled}
              onClick={() => setDraftText(String(sizer.max))}
            >
              All-in
            </Button>
            <Button
              variant="primary"
              disabled={disabled || draft === null}
              onClick={() => {
                if (draft !== null) onAct({ action: sizer.kind, target: draft });
              }}
            >
              {betOrRaiseLabel(legal, draft)}
            </Button>
          </div>
        ))}
    </>
  );
}

/** The dock, from `legal_actions` and `showdown_actions` (C6.2 plan §3.2). */
export function ActionDock({
  view,
  disabled,
  onAct,
  onShowdownDecision,
  onStartGame,
}: ActionDockProps) {
  const hand = view.hand;
  const legal = hand?.legal_actions ?? null;
  const showdownActions = hand?.showdown_actions ?? null;

  if (legal) {
    return (
      // biome-ignore lint/a11y/useSemanticElements: an action dock is not a form fieldset
      <div className={styles.dock} role="group" aria-label="Actions">
        <BettingControls legal={legal} disabled={disabled} onAct={onAct} />
      </div>
    );
  }

  if (showdownActions) {
    return (
      // biome-ignore lint/a11y/useSemanticElements: an action dock is not a form fieldset
      <div className={styles.dock} role="group" aria-label="Actions">
        <Button variant="primary" disabled={disabled} onClick={() => onShowdownDecision("show")}>
          Show
        </Button>
        <Button variant="neutral" disabled={disabled} onClick={() => onShowdownDecision("muck")}>
          Muck
        </Button>
      </div>
    );
  }

  if (view.phase === "not_started") {
    return (
      <div className={styles.waiting}>
        {view.you.is_host ? (
          <Button variant="primary" disabled={disabled} onClick={onStartGame}>
            Start game
          </Button>
        ) : (
          "Waiting for the host to start"
        )}
      </div>
    );
  }

  if (view.phase === "waiting_for_players") {
    return <div className={styles.waiting}>Waiting for players</div>;
  }

  if (view.phase === "hand_complete") {
    return <div className={styles.waiting}>Next hand starting</div>;
  }

  return null;
}

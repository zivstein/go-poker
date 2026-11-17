import { type ReactNode, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import type { ConnectionStatus } from "../connection/ConnectionController";
import type { ActArgs, ShowdownDecision, TableView } from "../protocol/types";
import type { LastRejection } from "../session/store";
import { Button } from "../ui/Button";
import styles from "./ActionDock.module.css";
import { BettingControls } from "./BettingControls";
import { DockRows, type PressedAction, pickStatus } from "./DockRows";
import { decisionIdentity } from "./decisionIdentity";
import { connectionStatusText, dockState, modeStatusText } from "./dockState";
import { isQuietRejection, rejectionText } from "./rejectionText";
import { GUARD_MS, useArrivalGuard } from "./useDecisionGuard";

export interface ActionDockProps {
  /** The displayed frame's view: the only source of legal actions. */
  view: TableView;
  /** The command lifecycle (live, pending, reconciling). */
  status: ConnectionStatus;
  lastRejection: LastRejection | null;
  /** The count of hand-boundary snapshots received, part of the decision's
   * identity ({@link decisionIdentity}). */
  handEpoch?: number;
  /** The turn-arrival guard; tests other than the guard's own pass 0. */
  guardMs?: number;
  /** Each returns whether the command was actually sent (the connection can
   * refuse it). `false` leaves no pressed state behind. */
  onAct: (args: ActArgs) => boolean;
  onShowdownDecision: (decision: ShowdownDecision) => boolean;
  onStartGame: () => boolean;
  onDismissRejection: () => void;
}

/**
 * The Action Dock (A1, `docs/design/ACTION_DOCK.md`): one fixed two-row frame
 * in every table state, so the table never moves when a turn starts or ends.
 * Buttons come only from `legal_actions` and `showdown_actions` (C6.2 §2.3).
 */
export function ActionDock({
  view,
  status,
  lastRejection,
  handEpoch,
  guardMs = GUARD_MS,
  onAct,
  onShowdownDecision,
  onStartGame,
  onDismissRejection,
}: ActionDockProps) {
  const statusId = useId();
  const frame = useRef<HTMLElement>(null);
  const focusInside = useRef(false);
  const state = dockState(view, status);
  const { mode } = state;
  const connectionLive = state.connection === "live";
  // The decision's identity comes from the game state, never from the shared
  // revision, which also changes for unrelated transitions (a join, a host
  // change). It keys the betting controls (a new decision resets the draft and
  // the Fold confirmation) and the arrival guard.
  const identity = decisionIdentity(view, handEpoch);
  const decisionKey = identity === null ? null : `decision:${identity}`;
  const guardArmed = useArrivalGuard(connectionLive ? decisionKey : null, guardMs);
  // `unavailable` truly disables the controls. The arrival guard only drops
  // activations, so it never costs focus (AM3).
  const unavailable = !connectionLive || state.pending;
  const blocked = unavailable || guardArmed;

  // The control whose command is in flight, by stable identity; cleared when
  // the command completes (UI-only).
  const [pressed, setPressed] = useState<PressedAction | null>(null);
  const wasPending = useRef(state.pending);
  useEffect(() => {
    if (wasPending.current && !state.pending) setPressed(null);
    wasPending.current = state.pending;
  }, [state.pending]);

  // A control disabled under the pointer or the keyboard loses focus; keep
  // it in the dock, never on the page body.
  useLayoutEffect(() => {
    if (!state.pending && connectionLive) return;
    const element = frame.current;
    if (element === null) return;
    const active = document.activeElement;
    const lostInside =
      active instanceof HTMLButtonElement || active instanceof HTMLInputElement
        ? element.contains(active) && active.disabled
        : (active === null || active === document.body) && focusInside.current;
    if (lostInside) element.focus();
  }, [state.pending, connectionLive]);

  // A command the connection refused to send leaves no pressed state: it
  // would otherwise label the next, unrelated pending command.
  function track(action: PressedAction, sent: boolean) {
    setPressed(sent ? action : null);
    return sent;
  }

  function sendShowdown(action: PressedAction, decision: ShowdownDecision) {
    if (blocked) return;
    track(action, onShowdownDecision(decision));
  }

  const connectionText = connectionStatusText(state.connection);
  const statusParts = {
    connection:
      connectionText !== null ? <span className={styles.notice}>{connectionText}</span> : null,
    sending: state.pending && pressed !== null ? <span>Sending {pressed.text}…</span> : null,
    rejection:
      lastRejection !== null ? (
        <RejectionNotice rejection={lastRejection} onDismiss={onDismissRejection} />
      ) : null,
    mode: (
      <span className={identity !== null ? styles.yourTurn : undefined}>
        {modeStatusText(mode)}
      </span>
    ),
  };
  const leaveChip = state.leavePending ? (
    <span className={styles.chip}>Leaving after this hand</span>
  ) : null;
  const busy = state.pending ? pressed : null;

  let content: ReactNode;
  if (mode.kind === "betting") {
    content = (
      <BettingControls
        key={decisionKey ?? "decision"}
        legal={mode.legal}
        structure={view.settings.betting_structure}
        statusId={statusId}
        status={statusParts}
        asideExtra={leaveChip}
        unavailable={unavailable}
        guarded={guardArmed}
        connectionLive={connectionLive}
        busy={busy}
        onSend={(action, args) => !blocked && track(action, onAct(args))}
      />
    );
  } else if (mode.kind === "showdown") {
    content = (
      <DockRows
        statusId={statusId}
        status={pickStatus(statusParts)}
        aside={leaveChip}
        controlsLabel="Actions"
        controls={
          <>
            <Button
              variant="primary"
              disabled={unavailable}
              aria-disabled={guardArmed || undefined}
              busy={busy?.id === "show"}
              onClick={() => sendShowdown({ id: "show", text: "Show", label: "Show" }, "show")}
            >
              Show
            </Button>
            <Button
              variant="neutral"
              disabled={unavailable}
              aria-disabled={guardArmed || undefined}
              busy={busy?.id === "muck"}
              onClick={() => sendShowdown({ id: "muck", text: "Muck", label: "Muck" }, "muck")}
            >
              Muck
            </Button>
          </>
        }
      />
    );
  } else {
    content = (
      <DockRows
        statusId={statusId}
        status={pickStatus(statusParts)}
        aside={leaveChip}
        controls={
          mode.kind === "notStarted" && mode.isHost ? (
            <div className={styles.startSlot}>
              <Button
                variant="primary"
                disabled={unavailable}
                busy={busy?.id === "start_game"}
                onClick={() =>
                  track(
                    { id: "start_game", text: "Start game", label: "Start game" },
                    onStartGame(),
                  )
                }
              >
                Start game
              </Button>
            </div>
          ) : null
        }
      />
    );
  }

  return (
    <section
      ref={frame}
      className={styles.dock}
      aria-label="Action dock"
      tabIndex={-1}
      data-pending={state.pending || undefined}
      data-arming={guardArmed || undefined}
      onFocus={() => {
        focusInside.current = true;
      }}
      onBlur={(event) => {
        const next = event.relatedTarget;
        focusInside.current = next instanceof Node && event.currentTarget.contains(next);
      }}
    >
      {content}
    </section>
  );
}

function RejectionNotice({
  rejection,
  onDismiss,
}: {
  rejection: LastRejection;
  onDismiss: () => void;
}) {
  const quiet = isQuietRejection(rejection.code);
  return (
    <span className={quiet ? styles.quiet : styles.rejection} role={quiet ? "status" : "alert"}>
      {!quiet && <span aria-hidden="true">⊘ </span>}
      {rejectionText(rejection.code)}
      <button type="button" className={styles.dismiss} onClick={onDismiss} aria-label="Dismiss">
        ×
      </button>
    </span>
  );
}

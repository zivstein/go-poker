import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ConnectionController } from "../connection/ConnectionController";
import type { Transport } from "../connection/Transport";
import { clearCredential } from "../entry/credentialStorage";
import { PresentationQueue } from "../presentation/PresentationQueue";
import type { ActArgs, ShowdownDecision } from "../protocol/types";
import { TableStore } from "../session/store";
import { wireStore } from "../session/wireStore";
import { StatusLayer } from "../table/StatusLayer";
import { TableScreen } from "../table/TableScreen";

export interface TableSessionProps {
  tableId: string;
  credential: string;
  createTransport: () => Transport;
  onBackToEntry: () => void;
}

/** Owns one table's {@link ConnectionController} and {@link TableStore} for
 * the lifetime of this component (C6.2 plan §2.2, §2.3). */
export function TableSession({
  tableId,
  credential,
  createTransport,
  onBackToEntry,
}: TableSessionProps) {
  const [store] = useState(() => new TableStore());
  // The displayed frame and queue (C6.2 plan §2.3 rule 6): presentation may
  // lag the authoritative store, fed by every snapshot the connection emits,
  // never by the store's merged state.
  const [queue] = useState(() => new PresentationQueue());
  // The connection generation: "Use here" increments it, which replaces the
  // terminally-closed controller with a fresh one (ADR 0009 §12).
  const [generation, setGeneration] = useState(0);
  // The current controller; `null` while none exists (before the first effect
  // run, and between a cleanup and the next setup). Handlers do nothing then.
  const [controller, setController] = useState<ConnectionController | null>(null);
  // The latest transport factory: the caller's function identity changes on
  // every render and must not re-run the connection effect.
  const createTransportRef = useRef(createTransport);
  useEffect(() => {
    createTransportRef.current = createTransport;
  });

  // The controller and its transport are created inside the effect, so each
  // setup owns a controller of its own. React StrictMode runs setup, cleanup,
  // setup on the same component: cleanup's `disconnect()` latches that
  // controller for good, and the second setup must not reuse it.
  // `store` and `queue` are created once (above) and are stable for this
  // component's lifetime.
  // biome-ignore lint/correctness/useExhaustiveDependencies: `generation` is the re-run trigger; store and queue are stable
  useEffect(() => {
    const created = new ConnectionController(createTransportRef.current(), { tableId, credential });
    const unwire = wireStore(store, created);
    const unsubSnapshot = created.onSnapshot((event) => {
      queue.push({ revision: event.revision, cause: event.cause, view: event.view });
    });
    setController(created);
    created.connect();
    return () => {
      unwire();
      unsubSnapshot();
      created.disconnect();
      setController(null);
    };
  }, [generation, tableId, credential]);

  const state = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const displayed = useSyncExternalStore(queue.subscribe, queue.getDisplayed);

  useEffect(() => {
    if (
      state.status.phase === "closed" &&
      (state.status.reason === "auth_failed" || state.status.reason === "left_table")
    ) {
      clearCredential(tableId);
    }
  }, [state.status, tableId]);

  // Each handler reports whether the command was actually sent: the
  // controller refuses (`null`) when the connection is not live, a command is
  // in flight, or the outcome of an earlier one is uncertain.
  function handleAct(args: ActArgs): boolean {
    return controller?.sendCommand({ name: "act", args }) != null;
  }
  function handleShowdownDecision(decision: ShowdownDecision): boolean {
    return controller?.sendCommand({ name: "showdown_decision", args: { decision } }) != null;
  }
  function handleStartGame(): boolean {
    return controller?.sendCommand({ name: "start_game", args: {} }) != null;
  }
  function handleLeave(): boolean {
    return controller?.sendCommand({ name: "leave", args: {} }) != null;
  }
  function handleUseHere() {
    // The current controller is terminally closed (superseded): a new
    // generation replaces it with a fresh instance and transport.
    setGeneration((value) => value + 1);
  }
  function handleDismissRejection() {
    store.dismissRejection();
  }

  if (displayed === null) {
    return (
      <StatusLayer
        status={state.status}
        wasLeaving={controller?.wasLeaving ?? false}
        onUseHere={handleUseHere}
        onBackToEntry={onBackToEntry}
      />
    );
  }

  return (
    <TableScreen
      view={displayed.view}
      handEpoch={displayed.handEpoch}
      status={state.status}
      lastRejection={state.lastRejection}
      wasLeaving={controller?.wasLeaving ?? false}
      onAct={handleAct}
      onShowdownDecision={handleShowdownDecision}
      onStartGame={handleStartGame}
      onLeave={handleLeave}
      onDismissRejection={handleDismissRejection}
      onUseHere={handleUseHere}
      onBackToEntry={onBackToEntry}
    />
  );
}

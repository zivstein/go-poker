import { useState } from "react";
import {
  loadDevScenario,
  parseDevMockConfig,
  ScenarioMockTransport,
} from "../connection/devMockTransport";
import type { Transport, TransportCloseEvent } from "../connection/Transport";
import { WebSocketTransport } from "../connection/WebSocketTransport";
import { clearCurrentTable, readStoredSession } from "../entry/credentialStorage";
import { EntryScreen } from "../entry/EntryScreen";
import { DevThemeToggle } from "../theme/DevThemeToggle";
import { TableSession } from "./TableSession";

interface Session {
  tableId: string;
  credential: string;
}

function devMockSession(): Session | null {
  const config = parseDevMockConfig(window.location.search);
  if (config === null) return null;
  // The scenario's own fake table id; the credential is resolved once the
  // scenario loads, inside `createTransport` below, so this id is a stable
  // placeholder key for the session only.
  return { tableId: `mock:${config.scenario}:${config.connection}`, credential: "" };
}

export function App() {
  const [entryKey, setEntryKey] = useState(0);
  // The dev mock mode takes precedence; otherwise a stored session resumes
  // after a refresh (C6.2 plan §2.5).
  const [session, setSession] = useState<Session | null>(
    () => devMockSession() ?? readStoredSession(),
  );

  function handleBackToEntry() {
    clearCurrentTable();
    setSession(null);
    setEntryKey((key) => key + 1);
  }

  const mockConfig = parseDevMockConfig(window.location.search);

  return (
    <>
      {session === null ? (
        <EntryScreen
          key={entryKey}
          onEnter={(tableId, credential) => setSession({ tableId, credential })}
        />
      ) : (
        <TableSession
          key={session.tableId}
          tableId={session.tableId}
          credential={session.credential}
          onBackToEntry={handleBackToEntry}
          createTransport={() => {
            if (mockConfig !== null) {
              return new DeferredScenarioTransport(mockConfig.scenario, mockConfig.connection);
            }
            return new WebSocketTransport();
          }}
        />
      )}
      <DevThemeToggle />
    </>
  );
}

/** Wraps `ScenarioMockTransport`, loading its scenario lazily (a dynamic
 * import, DEV-only) the first time the controller opens it. */
class DeferredScenarioTransport implements Transport {
  private inner: ScenarioMockTransport | null = null;
  private queuedOnOpen: (() => void) | null = null;
  private queuedOnMessage: ((text: string) => void) | null = null;
  private queuedOnClose: ((event: TransportCloseEvent) => void) | null = null;

  constructor(
    private readonly scenarioName: string,
    private readonly connectionId: string,
  ) {}

  open(url: string): void {
    void loadDevScenario(this.scenarioName).then((scenario) => {
      const transport = new ScenarioMockTransport(scenario, this.connectionId);
      this.inner = transport;
      if (this.queuedOnOpen) transport.onOpen(this.queuedOnOpen);
      if (this.queuedOnMessage) transport.onMessage(this.queuedOnMessage);
      if (this.queuedOnClose) transport.onClose(this.queuedOnClose);
      transport.open(url);
    });
  }

  send(text: string): void {
    this.inner?.send(text);
  }

  close(code?: number): void {
    this.inner?.close(code);
  }

  onOpen(handler: () => void): void {
    this.queuedOnOpen = handler;
    this.inner?.onOpen(handler);
  }

  onMessage(handler: (text: string) => void): void {
    this.queuedOnMessage = handler;
    this.inner?.onMessage(handler);
  }

  onClose(handler: (event: TransportCloseEvent) => void): void {
    this.queuedOnClose = handler;
    this.inner?.onClose(handler);
  }
}

/**
 * Dev-only mock mode (C6.3 plan D9, Brief §2 item 9): runs any committed
 * fixture scenario with no server. Fixtures are loaded only under
 * `import.meta.env.DEV`, through a dynamic import, so the production build
 * never contains one (checked by `vite.config.ts`).
 */

import type { Scenario, ScenarioStep } from "../testing/fixtures";
import type { Transport, TransportCloseEvent } from "./Transport";

export interface DevMockConfig {
  scenario: string;
  connection: string;
}

/** Reads `?mock=<scenario>&connection=<id>` from the page URL. */
export function parseDevMockConfig(search: string): DevMockConfig | null {
  if (!import.meta.env.DEV) return null;
  const params = new URLSearchParams(search);
  const scenario = params.get("mock");
  const connection = params.get("connection");
  if (scenario === null || connection === null) return null;
  return { scenario, connection };
}

// A dynamic import, reachable only in DEV: `vite build` excludes it entirely
// (dead-code elimination on the `import.meta.env.DEV` guard), and the build
// script independently fails if a fixture module ever enters the bundle.
const scenarioModules = import.meta.env.DEV
  ? import.meta.glob<{ default: Scenario }>(
      "../../../docs/adr/0009-wire-protocol-v1/scenarios/*.json",
    )
  : {};

export async function loadDevScenario(name: string): Promise<Scenario> {
  if (!import.meta.env.DEV) throw new Error("the dev mock mode is unavailable outside development");
  const path = Object.keys(scenarioModules).find((p) => p.endsWith(`/${name}.json`));
  if (path === undefined) throw new Error(`unknown scenario "${name}"`);
  const module = await scenarioModules[path]?.();
  if (module === undefined) throw new Error(`failed to load scenario "${name}"`);
  return module.default;
}

/**
 * A script player, never a poker engine (C6.2 plan §2.6): answers whatever
 * this connection's `send` with its following `receive` steps, up to the
 * next `send`.
 */
export class ScenarioMockTransport implements Transport {
  private cursor = 0;
  private readonly steps: ScenarioStep[];
  private messageHandler: ((text: string) => void) | null = null;
  private openHandler: (() => void) | null = null;
  private closeHandler: ((event: TransportCloseEvent) => void) | null = null;

  constructor(scenario: Scenario, connectionId: string) {
    this.steps = scenario.steps.filter(
      (s): s is ScenarioStep & { connection: string } =>
        "connection" in s && s.connection === connectionId && s.op !== "open",
    );
  }

  open(_url: string): void {
    queueMicrotask(() => this.openHandler?.());
  }

  send(_text: string): void {
    this.advance();
  }

  close(_code?: number): void {
    // The mock never initiates its own close from a client-requested one.
  }

  onOpen(handler: () => void): void {
    this.openHandler = handler;
  }

  onMessage(handler: (text: string) => void): void {
    this.messageHandler = handler;
  }

  onClose(handler: (event: TransportCloseEvent) => void): void {
    this.closeHandler = handler;
  }

  private advance(): void {
    if (this.steps[this.cursor]?.op === "send") this.cursor++;
    while (this.cursor < this.steps.length) {
      const step = this.steps[this.cursor];
      if (step === undefined || step.op === "send") return;
      this.cursor++;
      if (step.op === "receive") {
        const message = step.message;
        queueMicrotask(() => this.messageHandler?.(JSON.stringify(message)));
      } else if (step.op === "server_close") {
        const code = step.code;
        queueMicrotask(() => this.closeHandler?.({ code, reason: "" }));
        return;
      }
    }
  }
}

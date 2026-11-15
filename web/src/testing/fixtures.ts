/**
 * Loads the ADR 0009 canonical fixtures from the repository path, through
 * Node `fs`, for use in Vitest (C6.4 Brief §2 item 9; C6.2 plan §2.6).
 *
 * This module is read-only: `docs/adr/0009-wire-protocol-v1/` is a frozen,
 * read-only contract input. It is never copied into `web/`.
 */

import { readdirSync, readFileSync } from "node:fs";
import { resolve } from "node:path";

// Resolved relative to `web/` (the Vitest root), per the Brief: fixtures are
// read from the repository path, never copied into `web/`. `process.cwd()`
// is used instead of `new URL(..., import.meta.url)` because Vite's import
// analysis specially rewrites that pattern into a dev-server asset URL.
const FIXTURES_ROOT = `${resolve(process.cwd(), "../docs/adr/0009-wire-protocol-v1")}/`;

export function fixturePath(relative: string): string {
  return `${FIXTURES_ROOT}${relative}`;
}

export function readFixtureText(relative: string): string {
  return readFileSync(fixturePath(relative), "utf-8");
}

export function readFixtureJson<T = unknown>(relative: string): T {
  return JSON.parse(readFixtureText(relative)) as T;
}

/** Lists the `.json` file names directly inside a fixture subdirectory. */
export function listFixtureFiles(relativeDir: string): string[] {
  return readdirSync(fixturePath(relativeDir))
    .filter((name) => name.endsWith(".json"))
    .sort();
}

export interface ScenarioHttpStep {
  op: "http";
  actor: string;
  request: { method: string; path: string; body: unknown };
  response: { status: number; body: unknown };
}

export interface ScenarioOpenStep {
  op: "open";
  connection: string;
  actor: string;
  path: string;
}

export interface ScenarioSendStep {
  op: "send";
  connection: string;
  message?: unknown;
  raw?: string;
}

export interface ScenarioReceiveStep {
  op: "receive";
  connection: string;
  message: unknown;
}

export interface ScenarioServerCloseStep {
  op: "server_close";
  connection: string;
  code: number;
}

export interface ScenarioDropStep {
  op: "drop";
  connection: string;
}

export interface ScenarioServerTimerStep {
  op: "server_timer";
  timer: "next_hand";
}

export interface ScenarioNoteStep {
  op: "note";
  text: string;
}

export type ScenarioStep =
  | ScenarioHttpStep
  | ScenarioOpenStep
  | ScenarioSendStep
  | ScenarioReceiveStep
  | ScenarioServerCloseStep
  | ScenarioDropStep
  | ScenarioServerTimerStep
  | ScenarioNoteStep;

export interface Scenario {
  protocol: string;
  scenario: string;
  summary: string;
  setup: unknown;
  steps: ScenarioStep[];
}

export function readScenario(name: string): Scenario {
  return readFixtureJson<Scenario>(`scenarios/${name}.json`);
}

export function listScenarioNames(): string[] {
  return listFixtureFiles("scenarios").map((name) => name.replace(/\.json$/, ""));
}

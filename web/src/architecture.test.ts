/**
 * Enforces the directory and dependency direction (C6.2 plan §2.2):
 *
 *   protocol ← connection ← session ← presentation ← (table, entry) ← app
 *
 * `ui`, `theme`, `format` and `variant` are leaves: they may share `protocol`
 * data types (no React, no DOM, no behavior), but never depend on the live
 * connection pipeline. `protocol` and `connection` import no React.
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(process.cwd(), "src");

// What each top-level directory may import from, among these directories
// (always itself as well). Anything not listed here (ui/theme/format/variant,
// testing) may import only `protocol` and among the leaves themselves.
const ALLOWED: Record<string, string[]> = {
  protocol: [],
  connection: ["protocol"],
  session: ["protocol", "connection"],
  presentation: ["protocol", "connection", "session"],
  table: ["protocol", "connection", "session", "presentation", "ui", "theme", "format", "variant"],
  entry: [
    "protocol",
    "connection",
    "session",
    "presentation",
    "ui",
    "theme",
    "format",
    "variant",
    "api",
  ],
  api: ["protocol"],
  app: [
    "protocol",
    "connection",
    "session",
    "presentation",
    "table",
    "entry",
    "api",
    "ui",
    "theme",
    "format",
    "variant",
  ],
};
const LEAVES = ["ui", "theme", "format", "variant"];
const NO_REACT_DIRS = ["protocol", "connection"];
// `testing/` is a cross-cutting test and dev-tooling support module (the
// contract-fixture loader and scripted mock scenarios), not part of the
// production dependency chain: it may import anything, and anything may
// import its fixture *types* for the dev-only mock mode.
const TESTING_DIR = "testing";

function listSourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      out.push(...listSourceFiles(full));
    } else if (/\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

function importSpecifiers(file: string): string[] {
  const text = readFileSync(file, "utf-8");
  const specifiers: string[] = [];
  const re = /(?:from|import)\s+["']([^"']+)["']/g;
  for (const match of text.matchAll(re)) {
    const specifier = match[1];
    if (specifier !== undefined) specifiers.push(specifier);
  }
  return specifiers;
}

function topLevelDirOf(file: string): string {
  const rel = file.slice(SRC.length + 1);
  const dir = rel.split("/")[0];
  return dir ?? "";
}

/** Resolves a relative specifier to the top-level directory it targets,
 * assuming the current one-level-deep `src/<dir>/*` layout. */
function targetDirOf(fromDir: string, specifier: string): string | null {
  if (!specifier.startsWith(".")) return null; // a package import (e.g. "react")
  if (specifier.startsWith("./")) return fromDir;
  const match = /^\.\.\/([a-zA-Z0-9_-]+)/.exec(specifier);
  return match?.[1] ?? null;
}

describe("directory and dependency direction", () => {
  const files = listSourceFiles(SRC);

  it("protocol and connection import no React", () => {
    for (const file of files) {
      const dir = topLevelDirOf(file);
      if (!NO_REACT_DIRS.includes(dir)) continue;
      const specifiers = importSpecifiers(file);
      expect(specifiers, file).not.toContain("react");
      expect(
        specifiers.some((s) => s.startsWith("react/")),
        file,
      ).toBe(false);
    }
  });

  it("every local import stays within the allowed dependency direction", () => {
    const violations: string[] = [];
    for (const file of files) {
      const fromDir = topLevelDirOf(file);
      for (const specifier of importSpecifiers(file)) {
        const targetDir = targetDirOf(fromDir, specifier);
        if (targetDir === null || targetDir === fromDir) continue;
        if (fromDir === TESTING_DIR || targetDir === TESTING_DIR) continue;

        const allowed = LEAVES.includes(fromDir)
          ? [...LEAVES, "protocol"]
          : (ALLOWED[fromDir] ?? []);

        if (!allowed.includes(targetDir)) {
          violations.push(
            `${file.slice(SRC.length + 1)}: "${fromDir}" must not import "${targetDir}"`,
          );
        }
      }
    }
    expect(violations).toEqual([]);
  });
});

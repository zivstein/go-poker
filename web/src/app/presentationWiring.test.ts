import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Brief §2 item 5 scopes `presentation/` as a delivered behavior: "the
 * displayed frame and queue, fast-forward on the hero's decision, and a jump
 * on reconnect (C6.2 §2.3)". `PresentationQueue` and `heroHasDecision` are
 * fully implemented and unit-tested in isolation (see
 * `presentation/PresentationQueue.test.ts`), but nothing in the live
 * rendering pipeline (`app/`, `table/`) actually constructs or feeds a
 * `PresentationQueue`: `TableSession` wires `ConnectionController` straight
 * into `TableStore` and `TableScreen` renders `store.getSnapshot().view`
 * directly. So every snapshot is shown to the user the instant the store
 * applies it, with no queueing, no animation hold, and no exercised
 * fast-forward-on-decision or jump-on-reconnect behavior in the actual app -
 * only in the standalone unit tests of the unused module.
 *
 * This is a static, repo-wide check (in the style of `architecture.test.ts`)
 * standing in for an end-to-end one: it fails today, and should start
 * passing once `presentation/` is wired into the table session's live
 * render path.
 */

const SRC = join(process.cwd(), "src");

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

function importsFromPresentation(file: string): boolean {
  const text = readFileSync(file, "utf-8");
  return /from\s+["'](\.\.\/)*presentation\//.test(text);
}

describe("presentation/ wiring into the live table session", () => {
  it("is imported by at least one non-test module under app/ or table/", () => {
    const candidates = [
      ...listSourceFiles(join(SRC, "app")),
      ...listSourceFiles(join(SRC, "table")),
    ];
    const wired = candidates.filter(importsFromPresentation);
    expect(
      wired,
      "No module under app/ or table/ imports `presentation/`: PresentationQueue is built " +
        "and unit-tested but never wired into the live render path (Brief §2 item 5).",
    ).not.toEqual([]);
  });
});

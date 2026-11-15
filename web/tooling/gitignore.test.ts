import { execFileSync } from "node:child_process";
import { describe, expect, it } from "vitest";

/**
 * Ignored paths under `web/` that are expected: installed dependencies, the
 * production build output, and OS/editor droppings. Anything else that is
 * gitignored is a file the toolchain may need but a commit would leave out.
 */
const EXPECTED_IGNORED = [/^node_modules\/$/, /^dist\/$/, /(^|\/)\.DS_Store$/, /\.sw[op]$/];

/** The ignored, untracked paths under `web/` (directories reported whole). */
function ignoredPaths(): string[] {
  const output = execFileSync(
    "git",
    ["ls-files", "--others", "--ignored", "--exclude-standard", "--directory", "."],
    { cwd: process.cwd(), encoding: "utf-8" },
  );
  return output.split("\n").filter((line) => line !== "");
}

describe("the Web toolchain's files are not gitignored", () => {
  it("has no ignored file under web/ other than node_modules/, dist/ and OS or editor files", () => {
    const unexpected = ignoredPaths().filter(
      (path) => !EXPECTED_IGNORED.some((pattern) => pattern.test(path)),
    );
    // A file listed here exists in the working tree but would be left out of
    // a commit, breaking tsc, vite build and vitest on a clean checkout
    // (the C6.4 `web/build/` incident: root `.gitignore`'s `build/` rule).
    expect(
      unexpected,
      `gitignored files under web/ (a commit would drop them): ${unexpected.join(", ")}`,
    ).toEqual([]);
  });
});

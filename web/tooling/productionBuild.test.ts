import { build } from "vite";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const DEV_ONLY_MARKERS = ["test-credential", "heads_up_hand", "unknown scenario"];

/**
 * The real app, built with the real `vite.config.ts`: the production bundle
 * must build (so the fixture-exclusion plugin passes) and carry no fixture or
 * dev-mock content (Brief §2 item 9). Unlike the plugin test, which builds a
 * tiny synthetic entry, this is the guarantee for the shipped bundle.
 */
describe("the production build of the app", () => {
  beforeEach(() => {
    vi.stubEnv("NODE_ENV", "production");
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("builds, and its output contains no fixture or dev-mock content", async () => {
    const result = await build({
      root: process.cwd(),
      logLevel: "silent",
      build: { write: false },
    });
    const outputs = (Array.isArray(result) ? result : [result]).flatMap((r) =>
      "output" in r ? r.output : [],
    );
    const chunks = outputs.filter((file) => file.type === "chunk");
    expect(chunks.length).toBeGreaterThan(0);
    for (const chunk of chunks) {
      expect(chunk.moduleIds.filter((id) => id.includes("0009-wire-protocol-v1"))).toEqual([]);
      // Strings that only a canonical scenario or the dev mock carries.
      // (Compared as a short list, so a failure does not print the bundle.)
      const present = DEV_ONLY_MARKERS.filter((marker) => chunk.code.includes(marker));
      expect(present).toEqual([]);
    }
  });
});

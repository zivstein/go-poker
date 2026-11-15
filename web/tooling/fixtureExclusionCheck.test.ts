import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { build } from "vite";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  checkBundleForFixtures,
  findFixtureModuleId,
  fixtureExclusionCheck,
} from "./fixtureExclusionCheck";

describe("findFixtureModuleId", () => {
  it("finds a module id under the fixtures directory", () => {
    const id = findFixtureModuleId([
      "/repo/web/src/app/App.tsx",
      "/repo/docs/adr/0009-wire-protocol-v1/scenarios/heads_up_hand.json",
    ]);
    expect(id).toBe("/repo/docs/adr/0009-wire-protocol-v1/scenarios/heads_up_hand.json");
  });

  it("returns undefined when no module id matches", () => {
    expect(
      findFixtureModuleId(["/repo/web/src/app/App.tsx", "/repo/web/src/main.tsx"]),
    ).toBeUndefined();
  });
});

describe("checkBundleForFixtures", () => {
  it("throws when a chunk's module graph includes a fixture", () => {
    const bundle = {
      "index.js": {
        type: "chunk",
        moduleIds: ["/repo/docs/adr/0009-wire-protocol-v1/scenarios/heads_up_hand.json"],
      },
    };
    expect(() => checkBundleForFixtures(bundle)).toThrow(/leaked into the production bundle/);
  });

  it("does not throw for a clean bundle, and ignores non-chunk assets", () => {
    const bundle = {
      "index.js": { type: "chunk", moduleIds: ["/repo/web/src/main.tsx"] },
      "index.css": { type: "asset", moduleIds: [] },
    };
    expect(() => checkBundleForFixtures(bundle)).not.toThrow();
  });
});

describe("the plugin in a real production build (vite build())", () => {
  const FIXTURE = resolve(
    process.cwd(),
    "../docs/adr/0009-wire-protocol-v1/messages/server/snapshot.connected.not_started.json",
  );
  let dir: string;

  beforeAll(() => {
    dir = mkdtempSync(join(tmpdir(), "fixture-exclusion-"));
    mkdirSync(dir, { recursive: true });
    writeFileSync(join(dir, "clean.ts"), 'console.log("no fixture here");\n');
    writeFileSync(
      join(dir, "leaky.ts"),
      `import fixture from ${JSON.stringify(FIXTURE)};\nconsole.log(fixture);\n`,
    );
  });

  afterAll(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  function buildEntry(entry: string) {
    return build({
      configFile: false,
      root: dir,
      logLevel: "silent",
      plugins: [fixtureExclusionCheck()],
      build: { write: false, lib: { entry: join(dir, entry), formats: ["es"] }, minify: false },
    });
  }

  it("rejects a build whose entry imports a canonical fixture", async () => {
    await expect(buildEntry("leaky.ts")).rejects.toThrow(/leaked into the production bundle/);
  });

  it("succeeds for the same build without the fixture import", async () => {
    await expect(buildEntry("clean.ts")).resolves.toBeDefined();
  });
});

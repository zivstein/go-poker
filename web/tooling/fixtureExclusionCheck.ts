/**
 * The production build never contains a fixture (Brief §2 item 9). This
 * plugin fails `vite build` if any module from
 * `docs/adr/0009-wire-protocol-v1/` enters a chunk's module graph.
 *
 * Lives in `web/tooling/`, not `web/build/`: the root `.gitignore`'s
 * unanchored Python `build/` rule would ignore a `build/` directory.
 */

import type { Plugin } from "vite";

const FIXTURE_PATH_MARKER = "0009-wire-protocol-v1";

/** Pure, unit-tested separately from the Rollup/Vite plugin plumbing. */
export function findFixtureModuleId(moduleIds: readonly string[]): string | undefined {
  return moduleIds.find((id) => id.includes(FIXTURE_PATH_MARKER));
}

export function fixtureExclusionMessage(moduleId: string): string {
  return (
    `A canonical fixture module leaked into the production bundle: ${moduleId}. ` +
    "Fixtures are a dev-only and test-only input (Brief §2 item 9); the DEV-only " +
    "mock mode must stay behind an `import.meta.env.DEV` guard."
  );
}

interface BundleEntryLike {
  type: string;
  moduleIds?: readonly string[];
}

/** Checks an entire Rollup bundle (the `generateBundle` hook's second argument). */
export function checkBundleForFixtures(bundle: Record<string, BundleEntryLike>): void {
  for (const file of Object.values(bundle)) {
    if (file.type !== "chunk" || file.moduleIds === undefined) continue;
    const offender = findFixtureModuleId(file.moduleIds);
    if (offender !== undefined) {
      throw new Error(fixtureExclusionMessage(offender));
    }
  }
}

/** The Vite plugin: runs {@link checkBundleForFixtures} on every production build. */
export function fixtureExclusionCheck(): Plugin {
  return {
    name: "fixture-exclusion-check",
    apply: "build",
    generateBundle(_options, bundle) {
      checkBundleForFixtures(bundle);
    },
  };
}

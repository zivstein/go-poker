# Go! Poker — Design Handoff Pack

Eight user-provided Go! Poker concept screenshots, compressed as high-quality JPGs, plus a catalog explaining their role and scope.

## How to use

1. **Extract the archive into the root of `go-poker`**. It will create `docs/design/REFERENCE_CATALOG.md` and `docs/design/references/*.jpg` (not overwrite unrelated project files).
2. Open `docs/design/REFERENCE_CATALOG.md` and check that its statements align with the current accepted ADRs and roadmap.
3. In a **fresh Claude Code session**, give the C6.2 planning prompt from the ChatGPT conversation. Ask Claude to read the reference catalog and inspect the 8 image files as images, not just filenames.
4. First obtain a proposed architecture, design decisions, scope and questions for Owner review. **Do not implement Web, create production art, add dependencies or commit in this first step.**
5. Only after the Owner reviews C6.2 should any accepted design specs be recorded and committed.

These images are AI-generated **sketches**; their on-image words 'approved' and 'final' are labels within the concept, not independent approvals. In particular, do not use them directly as user-facing assets.

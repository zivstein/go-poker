# Go! — Figma + Claude Code Workflow

**Status:** Working instructions for M8 design.

## Roles

- **Figma Design:** editable source of truth for product visuals, components, variables, typography and frame annotations.
- **Figma references / Figma Make:** visual exploration and prototypes; a raster image is *not* an editable production design.
- **Claude Code with remote Figma MCP:** inspect Figma links, assist with editable canvas work when tools/seat permit, and implement approved designs in the repo.
- **Repository:** source of truth for approved behavior contracts, production tokens/assets and software. Do not treat reference-only art as production assets.

## Connection check

From the repository root:

```bash
claude mcp get figma
claude
```

In Claude Code use `/mcp` and verify `figma` is connected. A browser page saying `Authentication success` confirms the OAuth step but MCP tool visibility should still be verified in the active Claude session. Use `https://mcp.figma.com/mcp` (remote); do not add the desktop MCP server unless you need it for a specific reason.

The Figma plugin for Claude Code provides additional skills; manual MCP configuration connects the server but does not install the skills. If wanted, use the official plugin installation instructions, taking care not to create ambiguous duplicate server entries.

## First Figma Design file

1. In Figma web or macOS app, sign in to the same Figma account used for OAuth.
2. Create a **Figma Design** file named `Go! — Brand & Product Design`.
3. Add the pages shown in `DESIGN_INDEX.md` (start with `00 · References`, `01 · Brand Identity`, `02 · Foundations`).
4. Put selected concept images in `00 · References`. Label them `AI CONCEPT — NOT APPROVED VECTOR`.
5. Copy the *Figma file URL* (and later frame URLs) into `DESIGN_INDEX.md` and prompts to Claude.

## First Claude test — read-only

```text
We are working in the Go! Poker repository on M8 C3. 
Figma file: <PASTE FIGMA DESIGN FILE URL>

First, verify that the remote Figma MCP is connected and identify the tools available to you.
Read the file and report its pages and frames. If it is empty, say so.
Do not edit Figma, do not create code, do not commit, and do not write files yet.
Confirm whether native write-to-canvas is available on this account.
```

## First editable design task — only after MCP read test

```text
M8 C3: use this Figma Design file: <PASTE FIGMA FILE URL>
Read docs/product/PRODUCT_VISION.md,
docs/product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md,
docs/design/BRAND_ASSET_PRODUCTION_BRIEF.md,
docs/design/DESIGN_INDEX.md and docs/design/THEME_PACKS.md.

Build a small editable foundations exploration in Figma, not in the repo:
- A labeled brand direction board for Deep Teal, Emerald, Sapphire and Ruby.
- Reusable Figma variables/styles where supported.
- Separate master-brand Go! lockup (G-A + ordinary o + !)
  from Go! Poker product lockup (G-A + chip O4 replacing ONLY the o in Go! + ! + plain Poker).
- Label all logo attempts CONCEPT, NOT LEGAL CLEARED.
- No raster-vector auto-tracing and no claim of trademark clearance.

Use native editable layers/components when your Figma MCP tools and account plan allow it.
If tools/permissions do not allow Figma writes, stop and provide precise manual Figma steps.
Do not alter application code or commit files. Report frame links and unresolved issues.
```

## Design approval → implementation

For an approved screen, copy the exact Figma frame link to a scoped Claude implementation prompt. Require it to read the Product Contract, use existing app/component conventions, implement semantic theme tokens, and provide visual review screenshots. Do not ask for production implementation before frame approval.

## Legal and provenance control

- Prior AI moodboards and exploratory SVGs are *not* proof of originality or exclusive rights.
- Use original editable vector construction and preserve intermediate source files/design history.
- Check names and marks separately for trademark conflicts before any meaningful public launch.
- Document third-party font, icon, sound and image licenses before shipping.
- Track legal clearance independently from artistic approval.

## Checkpoint protocol

At the end of each design session record: Figma file and frame URLs, decision status (`EXPLORING`, `DESIGN APPROVED`, `LEGAL CLEARED`), newly accepted token/component names, unresolved questions, and whether repo changes were made.

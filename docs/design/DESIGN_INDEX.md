# Go! — Design Index

**Milestone:** M8 · C3 (Brand) and C2/C4 (UX/Design System)
**Status:** Working design hub · 2026-11-09
**Design source of truth:** approved design specifications in this repository (C6.2 W15, 2026-11-11). Figma is optional tooling, not a prerequisite; a Figma file, if one is used, is linked here as a working aid.
**Implementation source of truth:** Git repository (approved assets and tokens only)
**Behavior source of truth:** `docs/product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md`

## What is actually approved

| Decision | Baseline | Status |
|---|---|---|
| Company wordmark | `Go!`: chosen geometric G-A + ordinary `o` + designed `!` | Creative direction approved; exact vectors not approved |
| Poker wordmark | `Go! Poker`: replace **only the `o` in `Go!`** with poker-chip O4; `Poker` remains ordinary text | Creative direction approved; exact vectors not approved |
| Master color direction | Deep Teal, the Go! master-brand color in every context | Selected direction; token hex pending visual/contrast validation |
| Go! Poker default theme | **Emerald** (C6.2 W9); Deep Teal stays the master-brand color, visibly distinct from Emerald | Approved 2026-11-11; hex pending validation |
| Poker theme variants | Deep Teal, Emerald, Sapphire, Ruby | Four visual directions selected; production tokens pending. Friends Alpha ships Emerald only; Sapphire is a dev-only token test in C6.4; Ruby held until validated against error red |
| Visual reference images | `references/` with `REFERENCE_CATALOG.md` and `START_HERE.md` | Concept sources only, not production assets (recorded at C6.2, 2026-11-11) |
| Friends Alpha table | Premium 2D, readable, polished | Product principle approved; layout/motion pending |
| Immersive 3D | Future exploration, no Alpha dependency | Deferred |
| Paid/support theme packs | Cosmetic-only future option, no gameplay advantage | Idea selected for later evaluation; **not Friends Alpha scope** |
| Logo/name legal clearance | Unresolved | No claim of originality or trademark availability yet |

**Important:** Generated concept images and prior exploratory SVGs are *references*, not approved source assets. Do not ship them or trace them into production without additional design work and clearance.

## Figma file layout (optional)

Optional since C6.2 W15. If Figma is used, one Figma Design file: `Go! — Brand & Product Design`

| Page | Purpose | First deliverable |
|---|---|---|
| `00 · References` | Curated approved-looking reference boards, clearly marked CONCEPT | A/B comparison, references and notes |
| `01 · Brand Identity` | Go! company wordmark, Go! Poker product lockup, icon sizing | Original editable master G construction |
| `02 · Foundations` | Semantic color variables, type, spacing, radii, states | Starter token set for all 4 themes |
| `03 · Lobby` | Friends Alpha dashboard & private-table flows | Desktop lobby frame |
| `04 · Poker Table` | Premium 2D game table, seats/actions/pot/stacks | Desktop table frame |
| `05 · Motion & Prototype` | Interaction states, transitions, reduced-motion | Clickable lobby → table flow |
| `06 · Mobile Adaptation` | Shared UX behavior with platform-specific layout | Responsive exploration, after desktop |

## Design-to-repo acceptance flow

1. **Concept:** Explore visually (Figma or any other tool). Leave status `CONCEPT`.
2. **Review:** Confirm hierarchy, spacing, semantics, small sizes, responsive behavior and accessible contrast.
3. **Approval:** The Product Owner, or a delegate the Product Owner names, approves the design. Mark it `DESIGN APPROVED` and record the date, the approver, the specification or reference it applies to, and the intended usage.
4. **Rights:** Record source/license and trademark clearance requirements for identity elements. `DESIGN APPROVED` does not mean `LEGAL CLEARED`.
5. **Implementation:** Export owned source assets, version semantic tokens in code (CSS custom properties on Web), and cite the approved specification in the implementation Brief.
6. **Visual QA:** Compare implementation against the approved specification at defined viewports; document deviations.

Do not create empty documents merely to satisfy a folder tree. Later deliverables will be documented in `BRAND.md`, `DESIGN_SYSTEM.md`, `MOTION_CONTRACTS.md`, and `ASSET_PROVENANCE.md` once reviewed.

## Relevant repo references

- `docs/product/PRODUCT_VISION.md`
- `docs/product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md`
- `docs/design/BRAND_ASSET_PRODUCTION_BRIEF.md`
- `docs/milestones/M8_PLAN.md`
- `docs/design/THEME_PACKS.md`
- `docs/design/FIGMA_CLAUDE_WORKFLOW.md` (optional workflow)
- `docs/design/REFERENCE_CATALOG.md` (concept references)
- `docs/milestones/M8_C6_2_WEB_PLAN.md` (Web architecture and design foundation)

## Next design actions

1. Produce the approved design specifications in the repository: `BRAND.md` (C3), `DESIGN_SYSTEM.md` and `MOTION_CONTRACTS.md` (C4), validating the Emerald, Deep Teal and status values.
2. Create original, editable Brand Identity vectors **before** exporting them to the repository, with any vector tool (C3.7).

Superseded on 2026-11-11 (C6.2 W15): the earlier steps to create a Figma file first, link it here and verify Figma MCP access. They remain available as optional tooling in `FIGMA_CLAUDE_WORKFLOW.md`.

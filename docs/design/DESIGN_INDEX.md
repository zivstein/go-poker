# Go! — Design Index

**Milestone:** M8 · C3 (Brand) and C2/C4 (UX/Design System)
**Status:** Working design hub · 2026-11-09
**Design source of truth:** Figma file: **ADD LINK AFTER FILE CREATION**
**Implementation source of truth:** Git repository (approved assets and tokens only)
**Behavior source of truth:** `docs/product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md`

## What is actually approved

| Decision | Baseline | Status |
|---|---|---|
| Company wordmark | `Go!`: chosen geometric G-A + ordinary `o` + designed `!` | Creative direction approved; exact vectors not approved |
| Poker wordmark | `Go! Poker`: replace **only the `o` in `Go!`** with poker-chip O4; `Poker` remains ordinary text | Creative direction approved; exact vectors not approved |
| Master color direction | Deep Teal | Selected direction; token hex pending visual/contrast validation |
| Poker theme variants | Deep Teal, Emerald, Sapphire, Ruby | Four visual directions selected; production tokens pending |
| Friends Alpha table | Premium 2D, readable, polished | Product principle approved; layout/motion pending |
| Immersive 3D | Future exploration, no Alpha dependency | Deferred |
| Paid/support theme packs | Cosmetic-only future option, no gameplay advantage | Idea selected for later evaluation; **not Friends Alpha scope** |
| Logo/name legal clearance | Unresolved | No claim of originality or trademark availability yet |

**Important:** Generated concept images and prior exploratory SVGs are *references*, not approved source assets. Do not ship them or trace them into production without additional design work and clearance.

## Figma file layout

Create one Figma Design file: `Go! — Brand & Product Design`

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

1. **Concept:** Explore visually in Figma. Leave status `CONCEPT`.
2. **Review:** Confirm hierarchy, spacing, semantics, small sizes, responsive behavior and accessible contrast.
3. **Approval:** Mark design `DESIGN APPROVED` and record date, Figma frame URL, intended usage and reviewer decision.
4. **Rights:** Record source/license and trademark clearance requirements for identity elements. `DESIGN APPROVED` does not mean `LEGAL CLEARED`.
5. **Implementation:** Export owned source assets, version semantic tokens in code, link to Figma frame in implementation issue.
6. **Visual QA:** Compare implementation against the approved Figma screen at defined viewports; document deviations.

Do not create empty documents merely to satisfy a folder tree. Later deliverables will be documented in `BRAND.md`, `DESIGN_SYSTEM.md`, `MOTION_CONTRACTS.md`, and `ASSET_PROVENANCE.md` once reviewed.

## Relevant repo references

- `docs/product/PRODUCT_VISION.md`
- `docs/product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md`
- `docs/design/BRAND_ASSET_PRODUCTION_BRIEF.md`
- `docs/milestones/M8_PLAN.md`
- `docs/design/THEME_PACKS.md`
- `docs/design/FIGMA_CLAUDE_WORKFLOW.md`

## Immediate next action

1. Create Figma Design file; paste its URL above.
2. Collect selected G-A, O4, reference lobby and poker-table screenshots on `00 · References`.
3. Use Claude Code + remote Figma MCP for read-access verification.
4. Create original, editable Brand Identity variants **before** exporting vectors to repository.

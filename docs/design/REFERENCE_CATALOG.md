# Go! Poker — Visual Reference Catalog

> **Status: Concept references only (2026-11-11).** These screenshots were supplied by the Product Owner as earlier AI-generated design sketches. They are NOT production UI designs, finalized logos, source vectors, exact color-token values, legal/trademark clearance, or implemented product features.
>
> Do not treat the words “Approved”, “Final” or “Figma Ready” printed inside the sketches as formal signoff. Distinguish the Owner's previously chosen *direction* from details that still need explicit review.

## Sources and intended use

| Image | Reference role | C6.2 interpretation |
|---|---|---|
| [00-moodboard.jpg](references/00-moodboard.jpg) | Overall visual atmosphere, chips, cards, app icon, subtle glow | Direction, not screenshot to clone |
| [01-brand-identity.jpg](references/01-brand-identity.jpg) | Go! master mark; Go! Poker with poker-chip O; app icons | Logo geometry, proportions and final artwork require approval |
| [02-foundations.jpg](references/02-foundations.jpg) | Color examples, typography candidates, spacing, surfaces, buttons | Candidate tokens, NOT final hexadecimal/typography specifications |
| [04-poker-table.jpg](references/04-poker-table.jpg) | Landscape desktop poker table and action area | Highest-priority gameplay visual reference; illustrative data and 6-seat layout |
| [05-theme-packs.jpg](references/05-theme-packs.jpg) | Deep Teal default, Emerald/Sapphire/Ruby alternatives | Plan theme tokens and future asset variants, not four fully implemented themes in the POC |
| [06-product-family.jpg](references/06-product-family.jpg) | Reusable Go! brand across Poker, Football, AI, Games, Music | Brand strategy only; not C6.4 scope |
| [07-marketing.jpg](references/07-marketing.jpg) | Possible landing-page and promotional direction | Marketing inspiration only, NOT implemented features/claims |
| [lobby-concept.jpg](references/lobby-concept.jpg) | Desktop lobby navigation, Create Table, Join with Code, table lists | UX inspiration; not a complete approved screen specification |

The supplied screenshots did not include a sheet numbered 03. Do not infer what it contained.

## Working visual direction — previously discussed, still subject to exact specification

- Premium, polished, **2D**, dark digital poker. NOT realistic 3D table simulation for Friends Alpha.
- Master brand **Go!** with a custom angular G (G-A direction), ordinary **o** and matching exclamation mark. Product mark **Go! Poker** uses a chip replacing the **o** (O-4 concept). The final shapes and branding rights need separate signoff.
- Master brand **Deep Teal**; Poker and product theme accents include **Emerald**, **Sapphire**, **Ruby**. Avoid mistaking the sketch's colors for verified final HEX values. Deep Teal is pictured as a default theme in the theme-packs sheet.
- Candidate typography: **Montserrat** (brand/headlines) and **Inter** (UI/body), *not locked yet*.
- Poker visuals: elegant felt, legible cards, chips, player seats, action controls, pot, stakes, turn indicator; light glows should indicate hierarchy/interaction, not drown out data.
- Theme packs preserve geometry, component APIs, hierarchy and interaction patterns. Palette, felt, chip treatment and accents may vary. Build a small token structure now, not an elaborate theming engine.

## Critical separation of functionality vs imagery

### C6.4 parallel Backend/Web POC — minimum target
- Two browser windows connected to one real backend table; play one complete Hold'em hand using the existing Python `TableSession`/`HoldemGame` functionality.
- Web begins against **C6.3-approved ADR 0009 wire contract and canonical fixtures** in its worktree, independent from Backend implementation.
- UI should exhibit the chosen brand direction and game-table hierarchy; a small POC does not need a complete polished product.
- No new poker rules in the browser, and no disclosure of opponents' private cards. Per-viewer snapshots, authorization and source-of-truth live on the server.

### Friends Alpha — beyond this POC
- Private-table creation/list/join, permanent table ID and rotating join code; visible seat selection; configurable buy-in; persistent guest identity, bankroll/daily allowance; reconnect and approved recovery policy.
- Some may be mocked or staged during C6.4; do not claim they are functional just because they appear in a concept.

### Future / not automatically in the POC
- Quick Play, PLO, tournaments, clubs, leaderboards, monetized theme packs, other Go! products and broad multi-device polish.
- Marketing phrases such as “fair & secure” or “live tables” are concept copy, not verified product assurances.

## Design & engineering handoff rules

1. **Inventory first.** Find any actual design docs or assets already committed to the repository. Treat these screenshots as external references until Owner explicitly approves particular designs.
2. **Separate three statuses:** a) established product/brand direction, b) proposed visual system, c) future features/marketing inspiration.
3. Propose **screen hierarchy** for Lobby → Create/Join → Seat/Waiting → Live Hand → Showdown/Disconnect. Mark what C6.4 implements, what Friends Alpha requires, and what is deferred.
4. Propose **minimal design tokens**, e.g. `color.bg`, `color.surface`, `color.text`, `color.accent`, `color.action`, `felt`, `radius`, `space`, `typography`. Avoid hardcoding theme-specific colors throughout components.
5. Keep game-state interpretation server-authoritative, distinguish UI-only state, and consume mock snapshots based on ADR 0009.
6. Reference images are **not production assets**; don't crop the screenshot and use it as a background or as a static table. Build native, responsive UI components. Any needed custom logo vectors/illustrations should be explicitly inventoried.
7. Test for actual 2–9 seats, card visibility, action availability, empty and long names, small screen sizes, contrast and reduced-motion support. Sheet 04's 6-max composition does not supersede the product's 2–9 players requirement.
8. Avoid overproducing unneeded designs. The poker table and core flow are priority; support other pages with a restrained shared system.

## Owner decisions to request during C6.2

- Confirm the intended default **Poker theme** (Deep Teal shown in packs vs the earlier Emerald product preference), without confusing brand and theme.
- Confirm the **logo as provisional concept** vs whether final vector art already exists.
- Approve an initial **table layout** approach for 2–9 seats, scalable/responsive without recreating all details from the sample.
- Decide whether the first Web POC needs a **branded mini-lobby**, or can launch directly into table join/play with a simple entry screen.
- Confirm any token values (HEX, typography), visual hierarchy and motion budgets only after inspecting proposals.

**No design implementation, toolchain change, CI change or edits to Core/TableSession belong in the C6.2 documentation-planning cycle.**

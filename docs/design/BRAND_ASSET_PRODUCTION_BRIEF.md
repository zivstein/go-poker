# Go! — M8 C3.7 Brand Asset Production Brief

**Status:** Approved creative direction; final logo artwork and trademark clearance **not yet approved**.  
**Purpose:** Convert M8 C3 exploration into editable, original, testable brand assets.  
**Next gate:** C3 final brand review before C4 implementation.

## 1. Confirmed product and brand decisions

- **Master brand:** `Go!` = bespoke **G-A** geometric G + **ordinary letter o** + designed exclamation mark (`!`). The ordinary `o` is essential.
- **Product logo system:** replace **only the `o` in `Go!`** with a product motif; append the product name as ordinary word text after `!`.
  - `Go! Poker`: `G-A + O4 poker-chip o (spade center) + ! + Poker`.
  - `Go! Football`: `G-A + football-shaped o + ! + Football` (future conceptual example).
  - `Go! AI`, `Go! Games`, `Go! Music`: product symbols **not approved**; develop separately and avoid recognizable tech-company marks.
- **Brand identity color:** **Deep Teal** is the preferred Go! master color direction. Final color values require color-token/contrast validation.
- **Go! Poker theme-pack candidates:** Deep Teal, Emerald, Sapphire, Ruby. Support the same token roles across each pack. Paid support packs are a future product possibility, not Friends Alpha launch scope.
- **Visual direction:** premium modern 2D poker with high legibility. Gold, if any, is restrained secondary polish. Future 3D table is not part of Friends Alpha.
- **Cross-platform parity:** design and motion specs must not depend on the Web renderer.

## 2. Design work — no auto-traced AI art as production master

Create vector artwork deliberately with editable geometry in Figma, Illustrator, Inkscape, or an equivalent vector tool. AI concept imagery is **reference only**.

1. **G-A master geometry:** bespoke outer contour, corners, inner cut and directional wedge; create normalized geometry and clear-space rules. Test whether the shape remains distinctive in 1-color, 24 px and 16 px presentations.
2. **Ordinary o and !:** draw or legally license typography; tune them to the G-A proportions. Preserve a truly ordinary `o` in the **master** `Go!` logo.
3. **O4 chip component:** draw custom segment layout and central spade; keep it legible as the letter `o` in `Go!`. Avoid generic unaltered clipart. Include simplified micro-size variant where necessary.
4. **Product lockups:** `Go!`, `Go! Poker` in full-width, compact, dark/light, monochrome and small-icon variants. Football is for system validation, not a launch deliverable.
5. **Theme variations:** Deep Teal, Emerald, Sapphire, Ruby for Go! Poker. Theme is not allowed to change G-A geometry or the product naming rule.

## 3. Required export package

- Editable source: `.fig`, `.ai`, or `.svg` as appropriate; **SVG with clean vectors** for each approved mark.
- Exports: PNG previews at required app/web resolutions; transparent and opaque versions.
- Modes: color, white-on-dark, dark-on-light, one-color/monochrome, small icon.
- Layout specs: construction grid, minimum dimensions, safe space, alignment, chip/O proportions, `!` spacing, and typography.
- No third-party image, icon, font or sound may enter production without a recorded license and source.

## 4. Brand / Theme architecture handoff to C4

Separate immutable brand identity from configurable product appearance:

- **Brand constants:** G-A vector geometry, `Go!` wordmark rule, `!`, product-logo grammar.
- **Theme tokens:** `color.brand.primary`, `color.action.primary`, `color.surface.*`, `color.table.felt`, `color.table.rail`, `color.chip.*`, `color.player.active`, `color.text.*`, `effect.glow.*`, etc.
- **Theme definitions:** `deep-teal`, `emerald`, `sapphire`, `ruby`. These are semantic mappings, not color substitutions done ad hoc in Web components.
- **Asset variants:** theme-appropriate chip art and optional app icon variants must be exported explicitly; do not promise dynamic native app icons until platform support is scoped.
- **Functional invariants:** value labels, actions, privacy, pot state, turn timer and accessibility cues must remain recognizable in all packs. Avoid color-only state signalling.

## 5. Clearance and provenance — mandatory gate

**Original-looking AI output is not proof of originality or trademark availability.** Before publishing or paying to promote under this identity:

1. Search `Go!`, `Go! Poker`, likely similar names, and relevant industry/service classes in Israel, WIPO and target-market national databases. Check plain word marks separately from combined graphic marks.
2. Search G-A alone, `Go!`, `Go! Poker`, O4 and confusingly similar geometric G / poker chip arrangements using available visual trademark search and open visual search.
3. Commission professional trademark counsel for a clearance opinion covering intended countries, services and conflicting marks; specifically evaluate poker-sector naming risks.
4. Record creative provenance: sketches, dated vector revisions, contributors, license files, third-party assets, source URLs and permissions in `docs/design/ASSET_PROVENANCE.md`.
5. Obtain a signed rights-assignment agreement from any hired designer; confirm font licensing and commercial use terms.
6. Do not state that the logo is registered, cleared, exclusive, or infringement-free before the actual review.

## 6. Acceptance gates — C3 exit

- [ ] Master `Go!` uses **ordinary o** (never a poker chip).
- [ ] `Go! Poker` uses **O4 chip only in the o of `Go!`**, with `Poker` as ordinary text.
- [ ] G-A geometry is consistent across all export sizes, light/dark and theme variants.
- [ ] Distinct small-size and monochrome legibility verified.
- [ ] Deep Teal / Emerald / Sapphire / Ruby theme previews available from shared tokens.
- [ ] Fonts and assets have recorded licenses; source files are editable and backed up.
- [ ] A documented visual-similarity and mark-name screening report exists.
- [ ] Professional clearance decision is tracked as a launch blocker, not falsely marked complete.
- [ ] Approved brand assets and rules are recorded in `docs/design/BRAND.md` and assets in `assets/brand/` (or agreed repository asset path).

## 7. Work order and ownership

1. **C3.7 (now):** vector construction and variants with a designer / design specialist.
2. **Parallel clearance:** name and visual trademark screening; legal counsel before public brand launch.
3. **C3 review:** compare physical assets in app icon, landing header and poker table, then approve final source package.
4. **C2 UX:** finalize approved Lobby and table flows (may proceed in parallel).
5. **C4:** Design System, semantic theme tokens, motion contract, and high-fidelity responsive prototype.
6. **C5/C6:** AI teams and orchestration benchmark in parallel; C7 integrates implementation architecture.

**Important release boundary:** cosmetic support-pack monetization, alternative native app icons and paid store mechanics are future candidates. The theme-token foundation belongs in the first implementation; launch merchandising should not block Friends Alpha.

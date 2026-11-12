# Go! Poker — Theme Packs Contract (Design Draft)

**Status:** Theme directions selected; UI token semantics specified for C4; implementation and pricing not approved. Updated 2026-11-11 by the approved [C6.2 plan](../milestones/M8_C6_2_WEB_PLAN.md) (W9–W15): Emerald is the Go! Poker default, Deep Teal stays the Go! master-brand color, and approved design specifications in the repository are the source of truth.
**Owner:** Product/Design; changes require review of cross-platform consistency.

## Identity vs appearance

- **Go! master brand:** geometric G-A, a standard `o`, and designed `!`. Its color is Deep Teal in every context; themes never change it.
- **Go! Poker default presentation:** **Emerald** (C6.2 W9). It is the only theme shipped through the Friends Alpha unless the Product Owner explicitly changes that (W12). Deep Teal and Emerald must stay visibly distinct (blue-green versus green, W10).
- **Go! Poker product logo:** same G-A and `!`; replace the `o` *inside Go!* with the selected poker-chip O4; append plain `Poker`.
- **Theme Packs:** present the *same* geometry and product identity with different cosmetic styles. Do not use a different G, different poker logo architecture, or a different table interaction model per theme.
- All monetary values in the interface are virtual dollars with a `$` prefix. No real-money gambling or cash purchase is implied.

## Initial palette candidates (exploration values, not frozen production tokens)

| ID | Display name | Candidate key accent | Intended mood |
|---|---|---|---|
| `deep-teal` | Deep Teal | `#00BFA5` | Go! master-brand color; a possible later Poker pack |
| `emerald` | Emerald | `#00E676` | Classic premium poker; **Go! Poker default** |
| `sapphire` | Sapphire | `#1E88FF` | Premium digital blue |
| `ruby` | Ruby | `#FF3D5C` | Bold competitive red |

Hex values are **reference values only**. Validate contrast on backgrounds, felt and controls in C4 before adopting as final values; the C6.4 POC may use them only as provisional, contrast-checked values. Ruby is not offered until it is validated against the error color (W11).

An earlier concept sheet (`references/05-theme-packs.jpg`) labels Deep Teal the "official default". That label is superseded by W9.

## Semantic token model

Implement this *structure* first, not four copied component sets.

```text
brand.master.accent
brand.master.onAccent
ui.bg.canvas
ui.bg.surface
ui.bg.elevated
ui.text.primary
ui.text.secondary
ui.border.default
ui.action.primary.bg
ui.action.primary.text
ui.action.hover
ui.action.focusRing
table.felt.base
table.felt.gradient
 table.rail.base
 table.rail.highlight
 table.activeSeat.ring
 table.pot.text
chip.body
chip.edge
chip.markings
motion.glow.tint
motion.glow.intensity
```

`brand.master.*` is not themed. Status colors (success, info, warning, error) are theme-independent and never derived from a theme accent; errors always carry an icon and text, and success stays distinguishable from the Emerald accent (W11).

Theme selection should affect visuals only. Never use a theme color by itself to encode required meaning such as whose turn it is, a red card suit, selected betting action, errors, or account balance. Preserve consistent iconography, labels, shapes, and accessibility cues. Card suit colors may be separately configurable (e.g., four-color deck); do **not** implicitly recolor suits based on the theme.

## Component contract

Every themed component must take values from semantic tokens, including table, rail, player pods, chip art, CTA controls, active-player glow, focus states, lobby cards and dialogs. `Brand Logo` and `Product Logo` remain separate components, with a controlled appearance variant.

Suggested high-level data shape (illustrative, not implementation code):

```json
{
  "themeId": "deep-teal",
  "ui": { "bg": {}, "text": {}, "action": {} },
  "table": { "felt": {}, "rail": {}, "activeSeat": {} },
  "chip": { "body": {}, "edge": {} },
  "motion": { "glow": {} }
}
```

## Future support packs

Optional **cosmetic-only** purchases might support project development and unlock theme options, chip looks, table effects or eligible app-icon variants. They are a **future roadmap option**, not approved Friends Alpha monetization. Do not add a shop, payments, entitlements or purchase flows to M8/C4 without a new product decision. App-icon alternates are platform-dependent and should have explicit fallback behavior.

## Exit tests for C4 (not yet completed)

1. Switching among all four packs updates each themed surface consistently; no hardcoded accent remains.
2. UI semantics and gameplay do not change with the theme.
3. Text/action contrast remains usable; focus indicators are visible on every pack.
4. Table information ($ stacks, pot, blinds, actions, timers) is equally readable across packs.
5. Desktop and narrow/mobile breakpoints use identical token identities, even if layout differs.
6. The approved design specifications, any exported token files, and the implementation documentation agree (and Figma variables, where Figma is used; it is optional tooling, C6.2 W15).

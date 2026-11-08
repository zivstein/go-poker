# Go! Poker — Product Vision & Brand Direction

**Milestone:** M8 · C1 — Product Identity  
**Status:** APPROVED PRODUCT DIRECTION  
**Date:** 2026-11-08  
**Owner:** Go! Product  
**Scope:** Product identity and creative direction; **not** a finalized visual identity or technical architecture.

## 1. North star

**Go! Poker is a premium, modern poker platform that makes real poker feel immediate, intuitive and social — without sacrificing the precision experienced players expect.**

We are building a real product, not a temporary engineering demo. The first release targets polished private No-Limit Texas Hold'em play among friends. Over time, the same product foundation can support automatic matchmaking, additional poker variants, richer player identities and multiple client platforms.

**Product promise:** Serious poker. Effortless play. Premium experience.

**Positioning shorthand:** Premium Digital Poker — combining the clarity and authenticity of a professional poker room with the responsiveness and polish of a modern digital product.

The above lines are **internal positioning language**, not yet an approved public marketing tagline.

## 2. Audience and jobs to be done

### First audience: groups of friends

People who want to create a private game, invite others by code or link, sit at a table and play together — without mandatory registration or complicated onboarding.

### Second audience: experienced poker players

People who expect credible betting mechanics, readable information, clear action order, correct settlement, familiar terminology, and a professional rather than childish aesthetic.

### Expansion audience (future)

Players who will use quick play / automatic matchmaking, multiple poker formats, other platforms, and long-term player/account features. These are **future directions**, not Friends Alpha promises.

## 3. Approved brand direction

### Creative territory: Premium Digital Poker

Blend **A — Professional Poker** with **C — Modern Premium Gaming Platform**:

- From professional poker: authentic table atmosphere, restraint, confidence, clean presentation of cards, bets, stacks and pot.
- From modern digital products: responsive behavior, precise microinteractions, premium motion, coherent app navigation and tasteful visual energy.
- Avoid both extremes: dated casino ornamentation and flashy, childish casual-game styling.

The lobby may feel more like a contemporary digital platform; the table should feel focused, elegant and authoritative. Both must be recognizably part of the same brand.

### Five brand attributes

1. **Confident** — direct, credible, never loud for its own sake.
2. **Sharp** — fast to understand; numbers and actions remain legible.
3. **Premium** — purposeful detail, visual restraint, high-quality polish.
4. **Social** — effortless to invite, join and enjoy together.
5. **Modern** — fluid, connected, extensible across platforms.

**Tone of voice:** concise, warm, assured; never infantilizing, overly formal or gambling-hype driven. Prefer clear poker language: *Join Table*, *Raise*, *Fold*, *Buy-in*, *Stack*, *Pot*, *Wallet*. Amounts use `$` for **virtual play money**, with an unmistakable no-real-money-value disclosure.

## 4. Product pillars

| Pillar | What it means | Design / UX consequence |
|---|---|---|
| Poker first | Real rules, strong clarity and trust | Cards, stakes, positions, active turn and permitted actions are instantly understandable |
| Premium by design | Craft over spectacle | Consistent spacing, typography, contrast and motion; no decorative overload |
| Effortless social play | Minimal friction | Private table creation, saved tables, join code/link, guest access and clear rejoin |
| Alive, not distracting | Responsive and tactile | Motion communicates dealing, actions, pot movement and state, without slowing play |
| Built to evolve | Product and organization can add features | Shared product contracts, reusable patterns, capability-driven extension points |

## 5. Table experience: Premium 2D now, possible 3D later

**Friends Alpha direction: premium 2D poker table.** It should feel polished, substantial and alive through disciplined art direction and quality animation, not rely on an expensive 3D runtime.

Priorities for 2D:

- Clear seating for 2–9 players; legible player status, bet amounts, stacks, pots, cards, dealer and blinds.
- Thoughtful dealing, betting, chip movement, showdown and seat-state motion, with timing and interruption rules documented later in Motion Contracts.
- Functional overlays (action controls, timers, buy-in, settings and wallet) must retain high contrast and readability.
- Reconnect, reduced-motion and small-screen states are explicit design cases.

**Future exploration only:** immersive player-perspective 3D table. It is **not** in Friends Alpha and must not delay or overengineer the 2D implementation. Maintain the principle that server game state and actions are independent of the visual rendering layer. Do **not** build a speculative multi-renderer framework during M8 simply for possible 3D support.

## 6. Brand architecture: Go! and Go! Poker

**Go!** is the intended umbrella/master brand; **Go! Poker** is the first product and currently the only confirmed product identity. A future Go! product may use the same brand family without poker-specific imagery.

- The master brand should not depend on cards, suits, chips or casino iconography.
- Go! Poker may use poker-specific imagery in product visuals and secondary identity.
- Explore wordmark, symbol and lockup as a flexible family in C3; do not assume a suit symbol must become the primary logo.
- **Legal entity naming, trademark clearance, domain acquisition and final naming of any future products are not decided here.**

## 7. Core experience and product footprint

The intended experience is a coherent **application**, not a single game screen:

1. Enter a branded lobby that communicates both available features and credible *Coming Soon* modules.
2. Choose **Private Tables**: create a new table, access saved tables, or join by code/link.
3. Review a table's public settings, select an available seat and choose a permitted buy-in.
4. Play full, authoritative poker with clear actions, states, reconnect and settlement.
5. Return later to the same guest account, virtual bankroll and owned table definitions, subject to guest credential continuity.

**Friends Alpha** remains scoped to private NLHE tables; automatic matchmaking, linked logins and other variants are future work. The authoritative detailed requirements, limits, grants and timeouts are in [`FRIENDS_ALPHA_PRODUCT_CONTRACT.md`](./FRIENDS_ALPHA_PRODUCT_CONTRACT.md). Do not duplicate numerical rules here.

## 8. Cross-platform experience principle

The future Web, native mobile and desktop clients should feel like **one product**, not unrelated applications. The source of truth is the platform-neutral design and interaction specification — **not** a screenshot or React component tree.

C2–C4 must document:

- UX journeys, component hierarchy, all significant states (loading, empty, offline, invalid, waiting, active, showdown).
- Design tokens and accessibility requirements, including reduced motion.
- Motion contracts with triggers, sequencing, durations/easing, interruption/reconnect behavior and reference media.
- Responsive/adaptive rules: preserve information hierarchy and behavior while adapting controls/layout for touch, screen size and OS conventions.
- Visual references/prototypes that later client teams can validate against.

**Consistency does not mean pixel-for-pixel identity across devices.**

## 9. Non-goals and constraints for C1

This document **does not select** a logo, color palette, font, logo iconography, motion timings, precise layout, UI framework, 3D engine, hosting provider or authentication vendor. Those choices belong to C2/C3/C4/C7 as specified in the M8 plan.

This document **does not claim** that lobby, accounts, wallet, table UI or real-time service are already implemented. It describes approved product intent; current code state remains independently verified in the repository.

## 10. Directional quality bar for later cycles

- **Clarity before spectacle:** users can identify their own cards, whose turn it is, legal actions, amounts and current pot without confusion.
- **Speed to table:** joining a private game should feel immediate, not like onboarding into a casino account.
- **Polish with purpose:** animations teach and affirm state changes; never obscure crucial information.
- **Recognizable Go! identity:** lobby, table and future clients share the same system.
- **Design once, implement everywhere:** product decisions and motion are reproducible from specs and references, not from reading Web source code.

These are **evaluation principles**; quantitative timings and accessibility/test thresholds will be defined and verified in the appropriate later cycles.

## 11. Decision record — M8 C1

| ID | Decision | Status |
|---|---|---|
| C1-D01 | Product direction: blend Professional Poker + Modern Premium Gaming | Approved |
| C1-D02 | Creative territory: **Premium Digital Poker** | Approved |
| C1-D03 | Friends Alpha table is **Premium 2D** with quality motion | Approved |
| C1-D04 | Player-perspective 3D is optional **future exploration**, not Alpha scope | Approved |
| C1-D05 | Product UX identity must be platform-neutral and reusable by future clients | Approved, inherited from M8 C0 |
| C1-D06 | Go! as umbrella/master-brand direction; Go! Poker as first product | Direction confirmed; legal name/mark not finalized |

## 12. Handoffs, dependencies and C1 exit criteria

### C2 — Product UX

Produce `docs/product/UX_FLOWS.md`: lobby information architecture, private tables/saved tables, join code, identity/wallet touchpoints, seat selection, gameplay actions, reconnect and empty/error states; flows for desktop and adaptive mobile. Do **not** freeze visual aesthetics prematurely.

### C3 — Visual brand

Produce `docs/design/BRAND.md` plus visual explorations: Go! master brand, Go! Poker product lockup, premium table art direction, typography/color candidates, imagery, and desktop/mobile brand applications. Present alternatives and trade-offs before approving actual visual assets.

### C4 — Design System and Motion

Create tokens, component inventory/states, reusable layouts, prototype, reference imagery and motion specifications. Validate product clarity at 2–9 seats and cross-platform reproducibility.

### C5 — AI Organization (parallel)

Begin defining agent team responsibilities, task contracts, review gates and escalation without waiting for C2/C3. Benchmark orchestration tools in C6.

### C1 exit check

- [x] North star and positioning territory specified.
- [x] Audience and product pillars specified.
- [x] Premium Digital Poker direction recorded.
- [x] Premium 2D now / 3D later boundary recorded.
- [x] Master-brand versus product-brand boundary specified.
- [x] Explicit UX/design handoffs for C2/C3/C4 recorded.

**Next step:** Commit this file; mark C1 complete in `docs/milestones/M8_PLAN.md`; start C2 (UX) and C3 (brand) in parallel, alongside C5 (AI organization) as capacity allows.

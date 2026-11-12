# M8 C6.2 — Web Architecture and Design Foundation Plan

**Status:** **Approved** by the Product Owner on 2026-11-11 (revision 2, with the two protocol clarifications and the side-pot note of the final review applied). The decisions are W1–W30 (§11). This completes C6.2. Nothing here is implemented. ADR 0009, the wire contract, is written in C6.3; §12 lists what it must settle. ADR 0008 and the Python-first server architecture are unchanged.

> The visual references in `docs/design/references/` are **AI-generated concepts**. The words "Approved", "Final" and "Figma Ready" printed on them are not approvals. They are not production assets, and no part of them is cropped, traced or shipped.

Tags, as in the [C6.1 plan](M8_C6_1_BACKEND_API_PLAN.md):
- **[POC]**: built in C6.4.
- **[FA]**: needed for the Friends Alpha.
- **[Later]**: after the Friends Alpha.

| Revision | Date | Change |
| --- | --- | --- |
| 1 | 2026-11-11 | Draft for Owner review |
| 2 | 2026-11-11 | Owner decisions W1–W30 applied; Emerald as the default product accent; no Figma prerequisite; pot presets moved to the betting contract; the POC entry flow defined; command completion, presentation queue and identity corrections; C6.3 contract blockers (§12); closeout readiness (§13) |
| 2 (approved) | 2026-11-11 | Approved. Final clarifications: B1 separates the server's one logical outcome from client-observed delivery; after a command timeout, actions stay disabled until the client has reconciled with a fresh authoritative snapshot (the 10 s value is provisional); side pots need three or more participants, so the heads-up demo does not cover them and canonical 3+ player fixtures do |

## 1. Inputs and their status

### 1.1 Already approved (in the repository)

| Area | Decision | Source |
| --- | --- | --- |
| Product | Private NLHE tables for 2–9 players; a branded, desktop-first, responsive lobby and table; Coming Soon modules; `$` virtual money with a no-real-value disclosure; reconnect, error and reduced-motion states designed and tested | [Product Contract](../product/FRIENDS_ALPHA_PRODUCT_CONTRACT.md) §2, §4, §10 |
| Product | Premium Digital Poker; premium 2D table; 3D is future exploration only; no speculative multi-renderer framework | [Product Vision](../product/PRODUCT_VISION.md) C1-D01–D04, §5 |
| Product | Approved design specifications, not Web source code, are the authority for UX | Contract §8; Vision §8 |
| Brand direction | `Go!` = G-A + ordinary `o` + `!`; `Go! Poker` = O4 chip replacing only the `o`, plus plain `Poker`. Direction only: no approved vectors, no legal clearance | `docs/design/DESIGN_INDEX.md`, `BRAND_ASSET_PRODUCTION_BRIEF.md` |
| Brand direction | Deep Teal is the Go! master color direction. Deep Teal, Emerald, Sapphire and Ruby are the selected theme directions. Hex values pending validation. Paid packs are not Friends Alpha scope | `DESIGN_INDEX.md`, `THEME_PACKS.md` |
| Theme model | Semantic tokens, not per-theme components; theme changes visuals only; never color alone for meaning; suit colors not recolored by theme | `THEME_PACKS.md` |
| Wire semantics | Full per-viewer snapshots carrying the shared revision; `expected_revision` on every state-changing command; private intents answered at an unchanged revision; ordered snapshots per transition; the client may pace animation but never reorder or alter; reconnect returns the current snapshot; hidden cards are `null`; the credential goes in the first frame, never in a URL or cookie | ADR 0005 §13, ADR 0006, ADR 0008 §5, C6.1 §8–§9 |
| C6.4 Web slice | `web/` only; connection and `hello`, a snapshot store, create and join, a functional table, error display; built against ADR 0009 and its example messages | C6.1 §12 |
| C6.4 join | No pre-join seat view in the POC (E4); the Friends Alpha must show available seats first | C6.1 E4 |
| Recovery and scale | One instance, in memory; restart loss accepted only through the Playable Preview; the Friends Alpha reduced crash policy only once implemented and tested; full in-hand recovery a mandatory public-release gate; scale-out by later ADRs | ADR 0008 §7–§8, C6.1 E16 |
| Client stack | React + TypeScript + Vite, for the POC and the Friends Alpha (W1). This settles the contradiction with Contract §12; C7 does not reopen it without new evidence | `ROADMAP.md`; this plan, W1 |

### 1.2 Concepts only (the reference sheets)

| Sheet | Usable as | Not usable as |
| --- | --- | --- |
| `00-moodboard` | Atmosphere: dark premium surfaces, restrained glow, felt, clean cards and chips; motion keywords | Assets; color values |
| `01-brand-identity` | Logo grammar (G-A, ordinary `o`, O4 chip in `Go! Poker`) | Vector source; app icons; cleared mark |
| `02-foundations` | Token *categories*: 8-pt spacing (4–48), surface layering, button states, card surfaces, semantic status set | Final hex or type values |
| `04-poker-table` | Information hierarchy: hero at bottom centre, board and pot centre, name and stack pods, own cards face up, verb-plus-amount action buttons, sizing panel, turn ring | A 6-max template for 2–9; photo avatars; Chat/Notes/stats/trophy; pot-fraction presets |
| `05-theme-packs` | "Same brand, multiple presentations": logo geometry, typography, layout and UI language fixed; accent, felt and chip treatment vary | Four themes to build now; its "Deep Teal official default" label (superseded by W9) |
| `06-product-family` | Brand-family rule: G and `!` fixed, the `o` varies per product | C6.4 scope; product accent values |
| `07-marketing` | Tone, portrait mobile table idea | Claims ("Fair & Secure", "Live Tables", "Fast Matches"); Quick Play, Sit & Go, tournaments |
| `lobby-concept` | Lobby IA: Create Table and Join with Code as primary actions; Private and Saved table lists; Coming Soon row; bankroll and daily claim in the top bar | PLO rows, Stats, Rewards, notifications, macOS window chrome, the 3D chip render |

There is no sheet 03.

### 1.3 Inconsistencies in the references

These do not reach code as decisions.

1. **Deep Teal has four values:** `#00BFA5` (`THEME_PACKS.md`), `#00BFA6` (sheet 02), `#00CBA6` and `#00E8B4` (sheet 06). As rendered, Deep Teal and Emerald are hard to tell apart (resolved in direction by W9–W10; values pending validation).
2. **Theme accents collide with status colors.** Sheet 02 uses Emerald as *success*, Sapphire as *info* and Ruby as *action/alert*. Ruby `#FF3D5C` is almost identical to error `#FF4D6D` (resolved in direction by W11).
3. **Cents** (`$428.50`, `$0.50/$1`, `Bet $20.00`) against whole-money values (Contract §4; engine integers) (resolved by W20).
4. **The pot is shown twice** on sheet 04, so pot, side pots and chips in front are ambiguous.
5. **Photo avatars**; the product has no avatar data (resolved by W22).
6. **Unscoped affordances:** Chat, Notes, Stats, Rewards, trophy, notifications, PLO tables (Chat and Notes deferred by W19; PLO deferred by Contract §9).
7. **Pot-fraction presets** with no defined rule (moved to the betting contract by W21).
8. **6-max composition** against the product's 2–9.
9. **macOS window chrome**; native clients are deferred.
10. **Product-family accents** on sheet 06 collide with the status colors; a brand-system item, not C6.

## 2. Web architecture (W1–W8 approved)

### 2.1 Stack

**A single-page app in React + TypeScript (strict) + Vite, rendered with DOM, CSS and inline SVG.** Approved for the POC and the Friends Alpha.

| Option considered | Why not |
| --- | --- |
| Next.js / Remix | SSR and server components bring nothing to an authenticated real-time SPA, and they add a Node server beside FastAPI |
| Svelte / SolidJS | Would reverse an approved decision for no product-visible gain |
| Vanilla TS / Lit | The component and state model would be hand-built for a growing lobby |
| Canvas / PixiJS / WebGL | Unnecessary for 2–9 seats; DOM gives accessible text, focus, reduced motion and responsive layout. Revisit only on a measured motion need (Vision §5) |

**Toolchain and dependencies.** Exact versions are chosen and locked in the preflight.

| Kind | [POC] | Not added |
| --- | --- | --- |
| Runtime | `react`, `react-dom` | router, state library, CSS framework, CSS-in-JS, animation library, schema library, UI kit |
| Dev | `typescript`, `vite`, `@vitejs/plugin-react`, `vitest`, `jsdom`, `@testing-library/react`, `@testing-library/user-event`, **Biome** (lint and format, W4) | Playwright, Storybook, visual-regression tooling |
| Tooling | **npm** with a committed `package-lock.json`; **one pinned, supported Node LTS** (`engines` and a version file) (W5) | pnpm, yarn |

- **Styling:** CSS Modules (built into Vite) plus design tokens as CSS custom properties.
- **State (W7):** one minimal, immutable external store per table connection, read with `useSyncExternalStore`. Each state is a new frozen object, replaced and never mutated. `getSnapshot` returns the **same cached reference** until a message actually changes the state, so React never re-renders on an unchanged store and never loops. Selectors derive from that reference.
- **Routing (W8):** none in the POC (screens switch on store state). One small router arrives with the lobby in the Friends Alpha.
- **Animation:** CSS transitions and keyframes, and the Web Animations API where needed.

### 2.2 Directory and boundaries

```text
web/
  package.json  package-lock.json  tsconfig.json  vite.config.ts  biome.json  index.html
  src/
    main.tsx
    app/           App shell, screen switch, error boundary
    protocol/      ADR 0009 message types, decoders, encoders            (no React, no DOM)
    connection/    WebSocket lifecycle: hello, command correlation, reconnect, supersede;
                   the Transport interface, with a real and a mock adapter (no React)
    api/           HTTP calls: create table, join by code
    session/       authoritative store: latest snapshot, connection status, in-flight command,
                   last rejection; selectors; the useTable hook
    presentation/  animation queue and the displayed frame (§2.3), fed by session, never by the network
    variant/       presentation config per variant and betting structure (§5)
    table/         Poker Table feature components
    entry/         POC entry: Create, Join with seat choice
    lobby/         [FA]
    ui/            primitives: Button, Surface, PlayingCard, Chip, Amount, Dialog, Toast, ProductLogo
    theme/         tokens.css, themes/<id>.css, theme selection
    format/        money, card names, accessible labels
    testing/       contract-fixture loader, scripted mock scenarios
```

**Dependency direction:** `protocol` ← `connection` ← `session` ← `presentation` ← (`table`, `entry`, `lobby`) ← `app`; `ui`, `theme`, `format` and `variant` are leaves. `protocol` and `connection` import no React. One Vitest test asserts the direction.

**The one interface.** `Transport` (connect, send, close, message and close callbacks) has two implementations from day one: the browser WebSocket and the scripted mock. No other abstraction is introduced (AGENTS.md).

### 2.3 Server-authoritative, presentation and local state

| Layer | Holds | Rule |
| --- | --- | --- |
| **Authoritative store** (`session/`) | The latest server snapshot: seats and occupants, stacks, chips in front, board, pots, turn, `legal_actions`, `showdown_actions`, hand strength, settlement, log, phase, revision, host, `you` (pending leave/sit-out, pre-action and its options); connection status; the in-flight command; the last rejection | Always the newest server state, applied the moment it arrives; never delayed by animation |
| **Presentation** (`presentation/`) | The displayed frame and a queue of earlier snapshots still being animated | Cosmetic; it may lag the store, never leads it, never reorders or alters content (E7) |
| **UI only** | Bet-size draft, open panel, seat rotation offset (from `you.seat`), theme, reduced-motion preference | Never sent, except the chosen amount inside a command |

Rules:

1. **No poker rules in the browser.** Buttons come only from `legal_actions` and `showdown_actions`; amounts only from server fields. The bet input clamps to the server's `[min_full_target, max_target]` as a convenience, and the server still validates. The client computes no pot, pot limit, call amount, eligibility, turn order or winner.
2. **No inference of hidden cards.** Card faces render only from the visible fields of the snapshot being displayed. Card backs render only from the server's hidden-card count (W29). Nothing in the client derives, remembers across hands, or guesses another player's cards from the log, earlier snapshots or timing.
3. **No optimistic poker updates.** A sent command shows a pending state at once and is completed only by its correlated outcome (§12, B1): an acknowledgement, which for a private command may carry an **unchanged** revision (ADR 0006 §2), or a rejection. The client never waits for a revision increase. One poker command is in flight at a time.
4. **No indefinite lock, and no action on uncertain state.** If no outcome arrives within a bounded time (provisionally 10 s), or the connection drops, the command's outcome is **uncertain**: the server may or may not have applied it. The client then:
   - clears the pending indicator and shows "No response — reconnecting";
   - **keeps every gameplay action disabled**;
   - reconnects and waits for a fresh authoritative snapshot;
   - re-enables actions only once it has reconciled with that snapshot, which shows whether the command took effect.

   An uncertain poker command is **never** retried automatically. The 10 s value is confirmed or changed in C6.4.
5. **Snapshot ordering.** The store applies a snapshot whose revision is ≥ its current one (an equal revision is a private-intent update, ADR 0006 §4) and ignores an older one.
6. **Presentation never delays the player.** Whenever the latest snapshot gives the hero a decision, presentation **fast-forwards to that snapshot at once**, skipping any remaining animation, and the dock opens from it. Commands carry the latest authoritative revision, which is then the one displayed. On reconnect or a revision gap, presentation jumps to the latest state with no animation.
7. **Integers only.** Money is formatted, never computed beyond clamping.

### 2.4 Connection lifecycle

```text
idle → connecting → authenticating (hello sent) → live (first snapshot)
live → reconnecting (unexpected close) → authenticating → live
any → closed: superseded | left_table | table_failed | auth_failed | protocol_mismatch
```

- **Hello:** `hello {protocol, credential}` is the first frame. A protocol mismatch shows a terminal "Please reload" screen.
- **Commands:** a `request_id` from `crypto.randomUUID()`; `expected_revision` from the latest authoritative snapshot; completion per §2.3 rules 3–4.
- **Rejections:** shown inline near the dock, from a client table of the ADR 0009 rejection codes, with a generic fallback. A stale-revision rejection is not an error: the client keeps the newer snapshot and shows a quiet "Table updated".
- **Liveness (W26):** standard WebSocket Ping/Pong sent by the server; browsers answer automatically. The client learns of a dead connection from the close or error event. An application heartbeat is added only if ADR 0009 shows it is needed.
- **Reconnect:** exponential backoff with jitter (about 0.5 s rising to an 8 s cap), retried at once on the browser `online` event and when the tab becomes visible. While reconnecting, the table stays visible and dimmed, actions are disabled, and a banner says so.
- **Superseded:** a terminal screen with "Use here", which reconnects and supersedes the other connection. **`table_failed`:** a terminal error screen. **`left_table`:** back to the entry screen.
- **Dev serving [POC]:** the Vite dev server proxies HTTP and WebSocket to the local uvicorn. Production serving and origin are C7.

### 2.5 POC entry flow: Create → Join → Seat choice → Credential → Start hand (W28)

The POC uses server defaults for stakes, buy-in, seat count and the host's seat. There is no pre-join seat map (E4). The server is authoritative at every step.

| Step | Who | Request | Success | Handled outcomes |
| --- | --- | --- | --- | --- |
| 1. Create | Player A | `POST /tables` with a display name | The table id, join code and A's credential, in the response body. A is seated as host | invalid name → field error |
| 2. Share | A | — | The waiting screen shows the code with Copy | — |
| 3. Join + seat choice | Player B | `POST /tables/by-code/{code}/members` with a display name and a **seat number** (input 1–9, the product maximum; the server owns the table's actual seats and occupancy). Joining is one atomic join-and-sit | B's table id and credential, in the response body | `SEAT_TAKEN` → "Seat N is taken. Choose another seat", form kept, focus on the seat; `INVALID_SEAT` → "This table has no seat N"; `DISPLAY_NAME_TAKEN` → name field error; unknown or closed code → code error. Each retry is a fresh request; nothing is stored before success |
| 4. Credential | each tab | — | Stored in that tab's `sessionStorage`, keyed by table id; never in a URL, cookie or log | — |
| 5. Connect | each tab | WebSocket, `hello` with the credential | First snapshot → table screen | auth failure → back to entry |
| 6. Start hand | A (host) | `start` command | The first hand begins | `NOT_ENOUGH_PLAYERS` → "Waiting for another player"; non-hosts see "Waiting for the host to start" |
| 7. Next hands | server | — | Start automatically after the server-owned pause | — |

**Independent identities.** A player's identity is the credential issued by **that player's own** Create or Join request. Storage never creates an identity; it only lets a tab resume after a refresh. `sessionStorage` alone does not guarantee distinct players: a duplicated tab copies it, reconnects as the same player and supersedes the original, which then shows Superseded (expected behavior). **The two-player demonstration** therefore uses two separate browser profiles (or two browsers, or a normal and a private window): window A creates, window B joins by code with its own name and seat. The recording shows two distinct names and seats, each window showing only its own hole cards.

**Side pots need three or more participants.** The live two-browser demonstration is heads-up and does not exercise them. Side-pot rendering is covered by render tests on canonical fixtures with three or more participants (§12, B5).

### 2.6 Mock-driven parallel development (W27)

1. **One fixture set.** ADR 0009's canonical examples and scenario sequences are committed in **one versioned Git path**, as part of the accepted contract, **before** the Backend and Web worktrees branch from it. Both Briefs list that path as a read-only input. No side keeps its own copy; Web tests read the files from that path. A needed fixture change is a contract change: the session stops and goes to the Owner.
2. **Decoder tests:** every example decodes; malformed and unknown messages are rejected as protocol errors.
3. **Render tests:** the table renders from each example snapshot, and the DOM contains no card value for any seat whose cards are hidden.
4. **Scripted scenarios:** the mock Transport replays the committed sequences, some keyed to client commands. A dev-only switch (`import.meta.env.DEV`, absent from the production build) runs the UI with no server. The mock is a script player, never a poker engine.
5. **Drift control:** Backend tests that its DTOs produce the canonical examples; Web tests that it decodes them. **[FA]:** TypeScript types generated from the Backend's exported JSON Schema, with a CI drift check (W6).

### 2.7 Quality gates

| Gate | Command in `web/` | [POC] |
| --- | --- | --- |
| Typecheck | `tsc --noEmit`, `strict` plus `noUncheckedIndexedAccess` | ✓ |
| Lint and format check | `biome ci` | ✓ |
| Unit and component tests | `vitest run` (jsdom, Testing Library) | ✓ |
| Production build | `vite build` | ✓ |

- `scripts/verify.py` runs the four gates after the Python gates and keeps their real exit codes. `--fix` adds `biome check --write`. A missing Node or `node_modules` is a **FAIL**, never a silent skip. CI runs `npm ci` first. All of this is preflight Meta work.
- **[POC] test focus:** decoders; the connection state machine, including command correlation, the timeout and no re-send (fake timers, fake transport); store reference stability; the presentation fast-forward; the seat layout for 2–9 seats and every hero rotation; money and card formatting; components from fixtures, queried by role and accessible name ("Call $40").
- **[FA]:** Playwright multi-browser E2E against the real server, automated accessibility checks, a bundle-size budget. The POC's two-player demonstration is manual and recorded (M8 Plan).

## 3. Component organization

### 3.1 Screen hierarchy

| Screen / state | [POC] | [FA] | [Later] |
| --- | --- | --- | --- |
| Entry: Create, Join with seat number | ✓ (branded single screen, W17) | becomes the lobby hero | |
| Lobby: Private Tables, Saved Tables, Coming Soon, wallet, daily claim | | ✓ | Quick Play, tournaments, clubs |
| Create Table configuration | server defaults (W28) | ✓ full form | |
| Table preview and seat map, buy-in | | ✓ (needs C6.1 L1) | |
| Waiting: code and copy, host Start | ✓ | ✓ | |
| Live hand, showdown decision, hand result | ✓ | ✓ | |
| Next hand (server-owned pause) | ✓ ("Next hand starting") | countdown, if a deadline is sent | |
| Reconnecting, Superseded, Table failed, Left | ✓ | ✓ with contract timings | |
| Spectator, owner settings, code rotation, rebuy/top-up, cash out | | ✓ | |

### 3.2 Poker Table

```text
TableScreen
├─ TableHeader        ProductLogo · TableInfo (variant · structure · stakes · seats)
│                     · JoinCode + copy · ConnectionIndicator · Leave menu
├─ TableStage         fixed-aspect stage: Felt + Rail (CSS / SVG)
│  ├─ SeatRing        Seat × max_seats, placed by seatLayout(maxSeats, heroSeat, orientation)
│  │  └─ Seat         Avatar (monogram) · Name · Stack · StatusBadge · DealerButton · BlindMarker
│  │                  · HoleCards (visible faces, or n backs) · TurnIndicator · LastAction · HandStrength (own)
│  ├─ BetChips        chips in front, on an anchor between seat and centre
│  ├─ Board           reserved slots (no layout shift)
│  ├─ PotDisplay      main pot and side pots, separately
│  └─ HandResult      awards per pot; shown hands' rank and best five
├─ ActionDock
│  ├─ ActionPanel     from toActionOptions(legal_actions): Fold · Check | Call $x · Bet | Raise to $y · All-in $z
│  ├─ BetSizer        Min · All-in · number input · slider (W21)
│  ├─ ShowdownPrompt  Show · Muck
│  ├─ PreActionBar    [FA] from you.pre_action_options
│  └─ WaitingPanel    host Start · waiting messages
├─ HandLog            [POC: optional simple list] [FA: drawer]
└─ StatusLayer        reconnect banner · rejection toast · terminal screens
```

Table components are presentational: they take the displayed frame's selector output as props and never read raw messages.

### 3.3 Lobby [FA]

```text
AppShell   TopBar: ProductLogo · Wallet balance · Daily claim · Account menu (one navigation, not top bar + sidebar)
LobbyScreen
├─ HeroActions        Create Table · Join by Code
├─ PrivateTablesList  sessions you are in or invited to → TableRow (name, variant badge, stakes, seats n/max, action)
├─ SavedTablesList    owned definitions → Reopen
└─ ComingSoonGrid     clearly non-interactive cards
Dialogs    CreateTable · SeatPicker · BuyIn · VirtualMoneyDisclosure · GuestCredentialNotice
```

## 4. Visual design foundation

### 4.1 Assessment

The concepts are coherent and on-brief: dark, premium, restrained, legible, and clearly "Go!". The table sheet gets the hierarchy right. The weaknesses are product-accuracy issues (§1.3) and glow intensity that would compete with data at small sizes.

**C6.4 target:** recognizably Go! Poker (dark layered surfaces, the Emerald accent, the felt-and-rail table, clean cards, verb-plus-amount actions, a turn glow), not pixel-matched to any sheet. **Styling is required; extensive motion and mobile polish never block integration (§6).**

### 4.2 Go! master brand and Go! Poker (W9, W13, W14)

| | Go! (master) | Go! Poker (product) |
| --- | --- | --- |
| Mark | G-A + ordinary `o` + `!` | G-A + O4 chip + `!` + `Poker` |
| Color | **Deep Teal**, always; the master-brand foundation | **Emerald** by default; the product accent follows the active theme |
| Where | Company and family contexts, "a Go! product" | App header, table, app icon |
| Poker imagery | Never | Allowed |
| [POC] | Not shown | The provisional wordmark below |

**Provisional Go! Poker wordmark [POC] (W13).** A carefully styled typeset lockup inside one `ProductLogo` component, following the approved grammar without imitating unapproved artwork:
- `Go` and `Poker` set in the display face at a heavy weight, with tight, tuned spacing; the `G` is the font's own, with no attempt at the G-A geometry;
- the `o` of `Go!` replaced by the code-drawn chip glyph from `ui/Chip` (owned SVG, not traced from any sheet);
- the `!` in the product accent; `Poker` in plain text color;
- compact and wide variants; an accessible name "Go! Poker".

It is marked provisional in code. Approved vector assets replace this one component later, with no other change.

### 4.3 Themes (W9–W12)

- **Default Go! Poker presentation:** Emerald. It is the only theme shipped through the Friends Alpha unless the Owner later changes that.
- **Deep Teal** stays the master-brand color and is kept visibly distinct from Emerald (W10: blue-green versus green).
- **Status colors are theme-independent** (W11). Success, info, warning and error never come from the accent; error and destructive states always carry an icon and text. Because the default accent is now green, **success** must stay distinguishable from it: an icon and text always accompany it, and its value is validated against Emerald. Ruby is not offered until validated against error red.
- **[POC] token proof:** Emerald plus a dev-only Sapphire theme, switched by a dev toggle, so any hardcoded green is obvious. No user-facing picker.

### 4.4 Tokens (W15)

**Authority:** approved design specifications are authoritative. Web implements tokens as CSS custom properties. A platform-neutral token pipeline may be added when additional clients need one. Figma is optional tooling, not a prerequisite.

1. **Primitives:** palette scales (`--p-emerald-…`, `--p-teal-…`, `--p-neutral-…`). Components never use them.
2. **Semantic tokens**, mapped per theme, following `THEME_PACKS.md`:

| Group | Tokens (CSS custom properties) | Themed? |
| --- | --- | --- |
| Master brand | `--brand-master` (Deep Teal), `--brand-master-on` | **no** |
| Background | `--color-bg-canvas`, `-surface`, `-elevated`, `-inverse` | yes |
| Text | `--color-text-primary`, `-secondary`, `-muted`, `-on-accent` | yes |
| Border | `--color-border-default`, `-strong` | yes |
| Accent / action | `--color-accent`, `--color-action-primary-bg`, `-text`, `-hover`, `-pressed`, `--color-action-secondary-*`, `--color-focus-ring` | yes |
| Status | `--color-status-success`, `-info`, `-warning`, `-error` | **no** |
| Table | `--table-felt-base`, `--table-felt-highlight`, `--table-rail-base`, `--table-rail-highlight`, `--table-active-seat-ring`, `--table-pot-text` | yes |
| Chips | `--chip-body`, `--chip-edge`, `--chip-marking` | yes |
| Cards | `--card-face`, `--card-ink-red`, `--card-ink-black`; `--card-back-*` | faces **no**; back yes |
| Effects | `--glow-tint`, `--glow-intensity`, `--shadow-1…3` | yes |

3. **Fixed scales** (all themes):

| Scale | Provisional [POC] values |
| --- | --- |
| Spacing (8-pt) | `--space-1…8` = 4, 8, 12, 16, 24, 32, 40, 48 px |
| Radius | 6, 10, 16 px; pill |
| Type (W16) | `--font-display` Montserrat, `--font-ui` Inter, self-hosted, SIL OFL licenses recorded; sizes 12, 14, 16, 20, 24, 32, 48; weights 400–800; **tabular numerals for every amount** |
| Motion | `--motion-fast` 120 ms, `--motion-base` 200 ms, `--motion-slow` 320 ms; standard and emphasized easings; reduced motion removes movement and keeps short fades |
| Layers | base, table, overlay, dialog, toast |

**Values:** the POC starts from the candidate values (Emerald `#00E676`, Deep Teal `#00BFA5`, Sapphire `#1E88FF` from `THEME_PACKS.md`, with dark neutrals), each checked for WCAG AA text contrast and marked provisional in `tokens.css`. Final values come from the approved design specifications (C4).

**Theme architecture:** one `tokens.css` plus one CSS file per theme that sets the semantic variables under `[data-theme="<id>"]`; selection sets only that attribute. No JavaScript theme objects reach components.

### 4.5 Responsive layout and 2–9 seats (W18, W24)

- **Stage:** a fixed-aspect container (16:9 landscape; a tall portrait variant) scaled to the viewport; seat pods change density with container queries.
- **Seat anchors:** hand-tuned coordinate tables for each `max_seats` from 2 to 9 and each orientation; pure data, unit-tested for no overlap at 9 seats at the minimum supported size. Chips-in-front anchors are interpolated toward the centre.
- **Rotation:** the hero is drawn at bottom centre, the others clockwise; presentational only. Seat numbers stay the server's and appear in accessible labels ("Seat 4, Maya, $380").
- **Breakpoints:** ≥ 1024 px polished in the POC; narrower widths usable but not polished; portrait and mobile-browser polish are [FA] (D39).
- **Names** truncate with an ellipsis and keep the full name accessible. **Amounts** never truncate or abbreviate: whole dollars with grouping (`$1,250`) (W20).

### 4.6 Cards, chips, actions and motion

- **Playing cards (W23):** code-drawn (CSS/SVG plus text), two-color, accessible names ("Ace of spades"); a four-color deck is a later setting, never tied to the theme. The card back is a themed geometric pattern with no unapproved logo.
- **Chips:** one SVG chip glyph from tokens; the amount as text is the information.
- **Avatars (W22):** monogram initials.
- **Icons (W25):** inline SVGs in the POC; one open-licensed set, license recorded, in the FA.
- **Actions:** verb plus amount ("Call $40", "Raise to $120", "All-in $380"), using the engine's "to" semantics. Fold neutral, Check/Call outlined, Bet/Raise filled with the accent. All-in is a Call, Bet or Raise to `max_target`, labelled as such. When the server supplies only a short all-in target, the sizer collapses to that one choice.
- **Sizing (W21):** the POC has Min, All-in, a number input and a slider. **Pot-based presets are game rules**, owned by the authoritative game/betting contract, not visual design. Before any preset button is built, a later cycle defines legal absolute preset targets in that contract, or the server provides them as data. The client never computes them.
- **Motion:**

| Priority | Motion | Status |
| --- | --- | --- |
| 1 | Turn indicator (active-seat ring and glow) | [POC] required |
| 2 | New board and hole cards appear | [POC] if time allows; never blocks integration |
| 3 | Last-action label on the seat | [POC] if time allows |
| 4 | Pot amount change highlight | [POC] if time allows |
| 5–9 | Chips to pot and to winner; dealing choreography (E7 pacing); showdown flip; action-timer ring; seat and reconnect transitions | [FA], per `MOTION_CONTRACTS.md` |
| — | Celebration effects, particles, 3D | [Later] |

Every motion is cosmetic and obeys §2.3 rule 6. Reduced motion is honored from the first build.

- **Accessibility [POC]:** semantic buttons and names, visible focus on every theme, a polite live region announcing the hero's turn, no color-only state. **[FA]:** keyboard shortcuts and tested announcements (Contract §10).

### 4.7 Asset inventory

| Asset | Reference state | Needed | [POC] |
| --- | --- | --- | --- |
| Go! wordmark (G-A) | raster concept | original vector, small and mono variants, clearance (C3.7) | not shown |
| Go! Poker lockup (O4 chip) | raster concept | approved vector, compact and micro variants | provisional typeset lockup (§4.2) |
| App icon and favicon | raster concept | design | generic favicon |
| Card faces | concept | built in code | ✓ code |
| Card back | concept shows the logo | logo-free pattern now; branded after vector approval | ✓ code |
| Chips | 3D-ish raster | SVG glyph in code; denomination palette later | ✓ code |
| Felt and rail | raster texture | CSS gradients/SVG; optional owned texture | ✓ code |
| Avatars | stock-like photos | **redesign** as monograms; photos deferred | ✓ code |
| Icons | concept | inline SVG now; licensed set in the FA | ✓ inline |
| Coming Soon illustrations, lobby hero chip stack | raster renders | original illustrations or simple icons | — |
| Fonts | Montserrat + Inter | OFL licenses recorded | ✓ self-hosted |
| Marketing art | sheet 07 | not product scope | — |

## 5. Future variant compatibility (no implementation now)

| Concern | Web rule | Contract support |
| --- | --- | --- |
| Omaha: 4 hole cards | `HoleCards` renders *n* faces or *n* backs (fanned above 2); nothing assumes 2 | v1 sends the **hidden-card count per occupied participant** (W29, B3) |
| Hand strength | Text and best five from the server only; the client never evaluates hands | in the view |
| Pot-Limit | Sizing clamps to the server's `[min, max]`; in Pot-Limit the server's `max_target` *is* the pot limit; the client never computes it | v1 sends the **betting structure** (B3) |
| Other legal actions | One adapter, `toActionOptions(legal) → ActionOption[]` (`kind`, label, amount or range); components hold no NL assumptions; min = max shows no slider | — |
| Variant labels | From the server's **variant** value, never a hardcoded "Texas Hold'em" | v1 sends the variant (B3) |
| Board and streets | Board slots from `variant/` (5 for Hold'em and Omaha); street names from the server enum | — |
| Seat count | Always `max_seats` from settings | in the view |
| Unknown values | Exhaustive decoders; an unknown value is a protocol error behind the version handshake | versioning rule (B6) |

All variant knowledge lives in `variant/` and `toActionOptions`. **Omaha and Pot-Limit Core work** may be developed independently before the public release; **PLO UI shipping is not part of this POC** or the Friends Alpha (Contract §9).

## 6. Minimum C6.4 POC scope (Web)

**Priority 1, the integration path (must pass first):** two independent browser players complete a real Hold'em hand against the Python backend.
1. `web/` with the stack in §2.1 and all four gates green in `verify.py`.
2. The full entry flow in §2.5: Create, Join with seat choice, credential, connect, Start.
3. A functional table: waiting state with code and copy; seats, stacks, chips in front, board, main and side pots (side pots verified from 3+ player fixtures, since the live demo is heads-up), dealer and blinds, turn indicator, own cards and hand strength, card backs from the hidden-card count; the dock from `legal_actions` with Min, All-in, input and slider; Show/Muck; hand result; "Next hand starting"; Leave.
4. Connection: `hello`, the authoritative store, command correlation and the timeout, rejections and stale handling, reconnect with backoff, Superseded, Table failed, Left.
5. Tests per §2.7 against the committed contract fixtures; the dev mock mode.
6. The recorded two-player demonstration (§2.5).

**Priority 2, the required visual baseline:** Emerald tokens and layered dark surfaces, Montserrat and Inter, code-drawn cards and chips, the provisional wordmark, monogram avatars, the turn indicator, reduced motion, desktop ≥ 1024 polished, 2–9 seat layouts correct from fixtures, the dev-only Sapphire toggle.

**Priority 3, non-blocking:** motions 2–4; narrower-width refinement; sit out / sit back; pre-actions; a simple hand log. Dropped first if the Cycle runs over budget.

**Out:** lobby, saved tables, seat map, wallet and buy-in choice, timers, spectators, owner settings, theme picker, pot presets, chat, sound, Playwright E2E, mobile polish, i18n, PLO UI, recovery and multi-instance behavior.

**Estimated complexity:** Web Cycle **M–L**: protocol and decoders S, connection and mock M, store and presentation S–M, table and seat layout M–L, dock M, tokens, theme and wordmark S, entry flow S. The Web part of the preflight is S.

## 7. Friends Alpha scope (Web)

- **Lobby and shell:** Private Tables, Saved Tables (Reopen), Create Table with the full configuration (SB/BB, buy-in min/max/Unlimited, seats, action timer), Join by code or link, Coming Soon modules, wallet balance, welcome and daily grants, the virtual-money disclosure, the guest-credential notice.
- **Table:** seat map before choosing a seat, buy-in, rebuy and top-up between hands, sit out and back, leave seat and cash out, pre-actions, the action-timer ring, disconnect and reconnect states with the contract timings, spectator view, owner-only settings (read-only for others), code rotation, a hand-log drawer, keyboard shortcuts, "hand voided" messaging once the E16 policy is implemented and tested, approved logo vectors, motion per `MOTION_CONTRACTS.md`, mobile-browser layouts. Pot presets only after W21's contract work.
- **Engineering:** router; JSON Schema codegen with a drift check; Playwright multi-browser E2E; automated accessibility checks; a bundle budget; client error reporting; production serving and WSS (C7); the persistent anonymous credential (C7 identity).

## 8. Deferred, and what the client does not claim

- **Deferred:** Quick Play, public lobby, Sit & Go, tournaments, clubs, leaderboards, stats, rewards beyond the daily allowance; chat and notes (W19); photo avatars; user-selectable and paid theme packs; app icons, PWA and native clients; PLO and other variant UI; 3D table; sound; four-color deck setting; multi-tabling; user-facing hand history; i18n and RTL (CSS logical properties are used from the start).
- **Not C6.4 capabilities:** recovery of any kind and horizontal scale-out. In C6.4, a reconnect reaches the same live process; a server restart loses the table, and the client shows Table failed or an auth failure. The Friends Alpha reduced crash policy applies only once implemented and tested (E16). **Full in-hand recovery remains a mandatory public-release gate** (ADR 0008 §8).

## 9. Design and contract handoffs Web waits on

| From | What | Blocks |
| --- | --- | --- |
| C6.3 | ADR 0009 with B1–B7 (§12) settled; the committed fixtures and scenarios | C6.4 |
| Preflight | Node toolchain in `verify.py` and CI | C6.4 |
| C2 | `UX_FLOWS.md`: lobby, seat map, wallet, reconnect and error flows | FA |
| C4 | `DESIGN_SYSTEM.md` (token values, component states), `MOTION_CONTRACTS.md`, chip denominations | FA |
| A later Core/betting contract cycle | Legal absolute preset targets, or server-provided presets (W21) | FA pot presets |
| C3 | Approved vectors and clearance | FA public release |
| C7 | Identity and credential storage; hosting and origin | FA |

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| A command's outcome is lost in a disconnection, or the dock stays locked | B1 correlation; the provisional timeout; actions stay disabled until reconciled with a fresh snapshot; no automatic retry |
| Animation delays a decision | Separate presentation layer; fast-forward on the hero's decision |
| Two demo windows share one identity | Credentials from each player's own request; separate browser profiles; Superseded handled |
| Hand-written TS types drift from the DTOs | One committed fixture set tested on both sides; codegen in the FA |
| W29 fields grow the Backend's scope | Constant mappings only, no `TableSession` change (§12, B3) |
| Node becomes a requirement of every `verify.py` run | Explicit FAIL; `npm ci` cache in CI; one pinned Node |
| The Emerald accent and success green are confused | Icon and text with every status; values validated in C4 |
| C2–C4 unfinished, so visuals are provisional | Tokens and presentational components isolate rework |
| Visual work overruns the C6 time and context targets | §6 priorities; Priority 3 dropped first |
| Concept art shipped by accident | Typeset wordmark only; no raster in `web/`; Reviewer check |
| Nine seats on a phone | Portrait anchors unit-tested; polish is [FA] |
| npm supply chain | Minimal dependencies, a committed lockfile, `npm ci` |

## 11. Decision record (Owner review, 2026-11-11)

| # | Decision | Outcome |
| --- | --- | --- |
| W1 | Client stack | **Approved.** React + TS (strict) + Vite SPA for the POC and the Friends Alpha; C7 does not reopen it without new evidence |
| W2 | Rendering | **Approved.** DOM + CSS + inline SVG |
| W3 | Runtime dependencies | **Approved.** `react`, `react-dom` only; no state, router, CSS or animation framework in the POC |
| W4 | Lint and format | **Approved: Biome** |
| W5 | Package manager and Node | **Approved:** npm with a committed lockfile; one pinned, supported Node LTS; a missing Node fails `verify.py` |
| W6 | Protocol types | **Approved.** Hand-written types and decoders in the POC; codegen with a drift check in the FA |
| W7 | State | **Approved:** a minimal immutable external store, `useSyncExternalStore`, stable cached snapshots |
| W8 | Routing | **Approved.** None in the POC; one small router in the FA |
| W9 | Default product accent | **Decided: Emerald** for Go! Poker; Deep Teal is the Go! master-brand foundation; the distinction is preserved; hex values need validation |
| W10 | Deep Teal versus Emerald | **Approved.** Distinct hues |
| W11 | Status colors | **Approved.** Theme-independent; icon and text for errors; Ruby held until validated |
| W12 | Themes shipped | **Approved, amended:** POC = default (Emerald) + dev-only Sapphire; no user picker; FA ships the default unless explicitly changed |
| W13 | Logo in the POC | **Amended:** a carefully styled provisional typeset wordmark (§4.2), not the raster and not a plain label; final logo needs approved vectors |
| W14 | Product lockup color | **Approved.** Product accent follows the theme; master Go! stays consistent |
| W15 | Token authority | **Amended:** no Figma prerequisite. Approved design specifications are authoritative; CSS custom properties implement tokens in Web; a platform-neutral pipeline when other clients need one |
| W16 | Fonts | **Approved.** Montserrat + Inter, self-hosted, OFL recorded, provisional |
| W17 | POC entry | **Approved.** Branded single entry screen |
| W18 | Seat layout | **Approved.** Hero at bottom; hand-tuned anchors for 2–9 per orientation |
| W19 | Chat and Notes | **Approved.** Deferred, not in the FA |
| W20 | Amounts | **Approved.** Whole dollars with grouping, no cents, no abbreviation |
| W21 | Sizing presets | **Approved, amended:** POC Min, All-in, input, slider. Pot-based presets belong to the authoritative game/betting contract; a later cycle defines legal absolute targets or server-provided data before buttons are built |
| W22 | Avatars | **Approved.** Monograms |
| W23 | Card faces | **Approved.** Code-drawn, two-color |
| W24 | POC responsive bar | **Approved.** Desktop ≥ 1024 polished; narrower usable |
| W25 | Icons | **Approved.** Inline SVG now; a licensed set in the FA |
| W26 | Liveness | **Decided:** standard server-side WebSocket Ping/Pong; an application heartbeat only if necessary |
| W27 | Fixture location | **Decided:** one versioned Git path, committed before the worktrees branch from the frozen contract; no separately maintained copies |
| W28 | POC create and join | **Decided:** server defaults, with the complete Create → Join → Seat choice → Credential → Start hand flow defined (§2.5); no pre-join seat map; `SEAT_TAKEN` handled |
| W29 | Variant fields | **Approved:** v1 sends variant, betting structure and the hidden-card count per occupied participant, with no card values and no `TableSession` change in C6.4 |
| W30 | Closeout | **Approved when the closeout is authorized:** design references included as concepts, not production assets (§13) |

## 12. Contract blockers for C6.3

ADR 0009 must settle these before the Briefs are approved. Each one changes Web code if left open.

| # | Blocker | What ADR 0009 must state |
| --- | --- | --- |
| **B1** | Command completion | Two layers, stated separately. **Server processing:** every received command has exactly one logical terminal outcome, correlated by its `request_id`: accepted (with the requester's snapshot, which for a private command keeps the same revision) or rejected. Other recipients' snapshots carry the cause without the requester's id. **Client-observed delivery:** delivery of that outcome is not guaranteed across a disconnection. A client that has not received it treats the outcome as uncertain, never retries automatically, and reconciles from the fresh snapshot after reconnecting (§2.3 rule 4). ADR 0009 states whether an outcome is ever replayed after a reconnect; the plan assumes it is not |
| **B2** | Create and join | Request and response bodies for `POST /tables` (display name; POC defaults applied by the server, including the host's seat) and `POST /tables/by-code/{code}/members` (display name, seat number); the credential in the response body only; HTTP status and error body for `SEAT_TAKEN`, `INVALID_SEAT`, `DISPLAY_NAME_TAKEN`, an unknown or closed code, and a validation failure |
| **B3** | Variant fields (W29) | A `variant` and a `betting_structure` value (display only), and per occupied participant the **number of hidden cards to display**, never their values. Mapping in the Backend, with no `TableSession` change: the structure and variant are fixed for the only engine game; the count is 0 when the cards are visible to the viewer or not live, otherwise the engine's `HOLE_CARD_COUNT` (`game/variants/texas_holdem/dealing.py`), its single source |
| **B4** | Rejection and error codes | The closed set of wire codes (from `RejectionCode` plus transport errors), their stable strings, and which close the connection |
| **B5** | Fixtures (W27) | The one versioned path; the canonical examples; the scenario sequences (a heads-up hand seen by both viewers, a 9-seat snapshot, side pots with three or more participants, a showdown decision, a private-command acknowledgement at an unchanged revision, a rejection, an error, `superseded`, `table_failed`, a reconnect) |
| **B6** | Versioning | The `hello` protocol value, the mismatch outcome, and the rule for unknown enum values |
| **B7** | Encodings | Integer money; the card encoding; the legal-actions shape including `short_all_in_target`; the action command with "to" amounts |

**Not blockers:** liveness (W26 decided; ADR 0009 only records the server's Ping/Pong interval and timeout); a next-hand deadline (the POC shows "Next hand starting"); pot presets (W21, later); everything tagged [FA].

## 13. Closeout (2026-11-11)

Approved by the Product Owner on 2026-11-11. C6.2 is documentation only: no application code, dependencies, CI or tooling changed.

Recorded with the closeout:

1. This plan, approved (revision 2 with the final clarifications).
2. The design references, committed as **concept sources, not production assets**: the eight images in `docs/design/references/`, `docs/design/REFERENCE_CATALOG.md` and `docs/design/START_HERE.md` (a one-time handoff note, kept as written).
3. Records: `CURRENT_CYCLE.md` (C6.2 complete; the client-stack contradiction resolved by W1; next, C6.3 on the Owner's instruction), `M8_PLAN.md` (the C6.2 row and status line), `ROADMAP.md` (the C6.2 decisions and the client line).
4. Design documents aligned with W9 and W15: `THEME_PACKS.md` and `DESIGN_INDEX.md` (Emerald as the Go! Poker default, Deep Teal as the master-brand color, approved design specifications in the repository as the source of truth), and `FIGMA_CLAUDE_WORKFLOW.md` (the Figma-dependent workflow marked optional, its history kept).

**Carried to C6.3:** B1–B7 (§12), and the two Briefs' declared paths, with the fixture path read-only in both. C6.3 starts only on the Owner's instruction.

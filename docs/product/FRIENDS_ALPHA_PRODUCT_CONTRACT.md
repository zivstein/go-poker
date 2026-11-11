# Go! Poker — Friends Alpha Product Contract

**Status:** APPROVED PRODUCT BASELINE (M8 C0)  
**Date:** 2026-11-08  
**Scope:** Product behavior and release requirements, not an implementation claim.

## 1. Vision and release model

Go! Poker is a polished, social, browser-first poker platform. Friends Alpha supports private No-Limit Texas Hold'em tables (2–9 players), real-time play, persistent guest accounts and bankroll, and a branded lobby that can advertise future features as **Coming Soon**.

Build the actual product incrementally. A **Playable Preview** may expose a polished table via a direct invite link before the **Friends Alpha** release adds the complete lobby, saved tables and account/economy flows. These are successive releases of the same architecture, not throwaway applications.

## 2. Friends Alpha P0

- Branded, navigable, desktop-first responsive web application with lobby, Private Tables, Create Table, Join by Code and Coming Soon modules.
- `Private Tables → Create New Table` or `Your Saved Tables → Reopen`; stable Table Definition (owner, table ID, settings), ephemeral Table Session (session ID, live hand state) and per-session random rotating Join Code.
- Guests have server-side permanent Player Accounts with anonymous authentication. Persistent personal wallets and owned tables belong to that account. **Linking to email, Google or Apple is explicitly deferred to the future Accounts feature; it is not in Friends Alpha.** Guest credentials may be lost when app/browser storage is wiped; communicate this clearly.
- View table before selecting an available seat. Player chooses seat and Buy-in. Seated WAITING players enter the first eligible hand under existing Core big-blind/position rules. Server reserves seat atomically.
- No-Limit Hold'em 2–9 players: blinds, betting, Fold/Check/Call/Bet/Raise/All-in, side pots, showdown, sequential hands, button movement, correct heads-up behavior and sit-out.
- Real-time authoritative server synchronization with snapshots, action validation, revision/idempotency handling, reconnect, independent sessions for multiple concurrently running private tables.
- Persistent play-money Wallet, welcome/daily grants, Buy-ins, Rebuys, player-selected Top-ups, Cash-out/Settlement, transaction ledger and safe recovery.
- Table visuals, states and animations follow future platform-neutral product/design/motion contracts so native clients can reproduce the experience without copying Web implementation.
- TLS/WSS, access checks, health/logging, restart/recovery procedures and multi-user end-to-end testing.

## 3. Ownership, invitations and spectators

- Only the Table Owner may change any configuration, explicitly close a Session, delete a saved Table Definition or rotate/revoke a Join Code. Non-owners may **view settings read-only**.
- Session can continue without its Owner. Closing an active Session is deferred until a hand-safe settlement point. Table deletion requires confirmation and is prohibited while a live Session exists.
- A participant admitted with a current valid Join Code may spectate public table information without seating. **No other player's private hole cards may be disclosed.** Spectators cannot act as players or manage the table.
- Admitted participants may share the current code/link. Only the Owner may manually replace/revoke it. A code from a closed Session never grants access to a new Session.
- Changes to gameplay-affecting table configuration are saved for the next Session, not applied mid-session or mid-hand. Owner edits only; server enforcement is mandatory.

## 4. Table configuration and bankroll presentation

- Small Blind and Big Blind are separate positive whole-money values; enforce `0 < SB < BB`. A 1:2 ratio is not mandatory.
- Minimum Buy-in configurable in `[10, 100] BB`; maximum Buy-in configurable in `[50, 250] BB` **or Unlimited**. For finite maximum, enforce max >= min. The server enforces safe numeric bounds even in Unlimited mode.
- Actual Buy-in must respect table limits and available Wallet. Values are displayed as **virtual dollars** (`$`): Balance, Stack, Pot, Bet, Buy-in, Cash Out. A disclosure must make clear that they have no real-world monetary value or cash-out/redemption mechanism.
- Rebuy when stack is zero; Top-up when below the configured finite maximum. Player chooses the exact permitted addition. The resulting stack may exceed max through legitimate winnings; max Buy-in is **not** a cap on winnings. In Unlimited mode, top-up still respects available Wallet and technical limits.
- Buy-ins and Top-ups apply at safe between-hand boundaries, never alter committed wagers mid-hand.

## 5. Economy grants

- **Welcome grant: $5,000**, once per account.
- **Daily allowance: $500**, manually claimed once per UTC calendar date; resets **00:00 UTC**. Unclaimed days do not accumulate, and all accounts can claim irrespective of balance.
- All grants are ledger entries with server-side eligibility checks and idempotency. No real-money purchases, deposits, withdrawals or conversion.

## 6. Lifecycle, reconnect and anti-ratholing

- Separate **connection**, **seat**, and **hand** statuses. Navigating away or refreshing is not an explicit Leave Seat / Cash Out. Disconnect never pauses the action clock.
- Owner-configurable action timer: **15, 30, 45, or 60 seconds**; default **30 seconds**. At action timeout, server performs Check if legal, otherwise Fold, without deleting legally committed bets/all-in participation.
- **30 seconds disconnected → Sit-out** for subsequent hands. This **supersedes** any previous 90-second-to-Sit-out suggestion.
- **90-second reconnect grace** remains the target window for reconnect assistance/state restoration, **not** a delay before Sit-out. Reconnecting after 30 seconds does not automatically make a player eligible mid-hand; legal re-entry follows Core rules. Reconnect may still be possible later while membership/session survives.
- **Seat reclaim:** after **5 additional minutes** following the 30-second Sit-out transition, an unreturned player's seat can be released after hand-safe settlement, subject to session survival and anti-ratholing retention.
- **Empty Session timeout:** **10 minutes** with no connected participants; close only after safe settlement/reconciliation. Definition, owner, saved settings, account and wallet persist. Reopening creates a new Session and Join Code.
- Sit Out preserves seat and stack; Leave View does not vacate seat. Explicit Leave Seat follows hand-safe exit and settlement. An All-in player's obligation remains live until the hand can settle.
- **Anti-ratholing:** leaving and returning to the same active Session within **30 minutes** must not permit returning with less than the previously committed/settled stack, after lawful adjustments. Keep the necessary return claim even after wallet credit or seat release. Prevent bypass via a new buy-in. Detailed edge-case algorithm is an implementation obligation for architecture review, not a product decision to reopen.

## 7. Wallet, settlement, recovery, and security invariants

- `Account → Wallet → Table Stake → Table Stack → Pot → Table Stack → Wallet` are distinct responsibilities. Poker Core never authenticates users or manages wallet balances.
- Buy-in/top-up moves money from available Wallet into a table allocation. Winning changes table stacks. Settlement returns a player's remaining claim to Wallet. Two simultaneous table operations must not overspend a shared wallet.
- Grants are explicit sources of virtual funds; normal in-table play conserves funds subject only to separately defined sources/sinks. Debits/credits are atomic, idempotent, auditable and authorized.
- A crash must never silently lose or duplicate a wallet claim. Preserve sufficient durable transaction, stack, pot and unresolved-obligation records to settle or safely freeze ambiguous funds for reconciliation; do not invent winners. Full user-facing Hand History is not required in Friends Alpha.
- **Interrupted hands (approved 2026-11-11, M8 C6.1 E16):** Friends Alpha may void a hand interrupted by a crash and restore every participant's hand-start stack, without awarding the hand. This is allowed only once the durable table state and ledger consistency it depends on are implemented and tested. Completed hands, buy-ins and cash-outs are never undone. Until then, no rollback or recovery support is claimed. Full recovery of hands in progress is required for the public product.
- Server is authoritative for player identity, ownership, table permissions, join code validity, hole-card visibility, action legality, money, timers and state revisions. Guessing a player ID or table ID is not an authentication method.

## 8. Cross-platform product contract

The design system — not Web source code — is authoritative for product UX. Record tokens, reusable component states, layout/responsive principles, table seating, interactions, accessibility, animations and reduced-motion behavior. Each significant motion specification includes trigger, timing/easing, order, state transition, privacy, reconnect handling and reference media. Native clients should reproduce product behavior and visual identity with platform-appropriate layouts.

## 9. Explicitly deferred from Friends Alpha

Account linking / registered login flows (including email, Apple, Google); automatic matchmaking/Quick Play; public matchmaking; tournaments; other poker variants; bots; user-visible hand history; advanced stats, leaderboards, real-money functionality; native mobile/desktop clients; player multi-tabling; time bank; sophisticated feature-specific settings such as straddle. Their future extension points may be designed, but not implemented as Alpha scope.

## 10. Acceptance criteria — Friends Alpha release gate

- At least four real users complete an end-to-end private game, multiple hands, valid side pots, reconnect, leave and settlement without developer intervention.
- Server allows simultaneous isolated tables, including seat/identity privacy, race resolution and wallet conservation across tables. Establish quantitative concurrency/performance targets in M8 C7 before implementation.
- Old invitations fail on new Sessions; non-owner changes fail at API level; spectators receive no private hole cards.
- Anonymous accounts survive normal return with valid credentials; no mandatory signup; account-linking is **not** shown as available.
- One welcome grant, at most one daily claim per UTC date, and no concurrent double credit/debit; crash/restart preserves account/wallet/table data and reconciles active stakes safely.
- Disconnect does not pause turns, 30-second Sit-out, 90-second reconnect grace, additional 5-minute seat reclaim, 10-minute empty Session cleanup, safe closure and fresh invitation on reopening.
- Lobby/table are visibly designed; state/motion variants, keyboard/accessibility basics, reconnect/error UX and reduced motion are documented and tested.
- Public transport security, observability, recovery runbook and controlled deployment are ready.

## 11. Approved decisions and traceability

- **D11–D13:** persistent table identity and session separation; platform-neutral UX/motion contract; future matchmaking shared with private tables.
- **D16–D24:** persistent guest identity, owner-only settings, read-only participant access, owner-independent play, saved tables, rotating session codes, choose seat and wait for eligible hand.
- **D25–D29:** configurable buy-in, rebuy/top-up, configurable action timer, `$` virtual money display, persistent bankroll.
- **D30–D32:** daily grants; $5,000 welcome, $500 daily, UTC reset; 90-second reconnect grace and 10-minute empty session cleanup, refined by D35's 30-second Sit-out.
- **D33:** spectator public view and admitted-participant invite sharing; owner-only code rotation.
- **D34:** owner-only configuration/close/delete; next-session gameplay changes and hand-safe closure.
- **D35:** 30-second Sit-out; 5 additional minutes reserved seat, subject to safe release. Does not erase separate 90-second reconnect grace.
- **D36:** 30-minute anti-ratholing claim on same Session.
- **D37:** **accounts linking deferred** from Friends Alpha to future Accounts feature; anonymous server accounts remain P0.
- **D38:** recoverable settlement and no silent loss/duplication of virtual balances.
- **M8 C6.1 E16 (2026-11-11):** the Friends Alpha interrupted-hand policy in §7; full in-progress recovery for the public product.
- **D39:** real-user, multi-table, desktop/mobile-browser, accessibility and performance acceptance; numeric targets finalized before implementation.

## 12. Implementation decisions delegated to M8 C7

Select auth/database stack, concurrency and ledger transaction design, crash snapshot/reconciliation algorithm, Web framework, real-time protocol and versioning, hosting, load thresholds and deployment operations. These do **not** reopen the approved product requirements. If a technical constraint makes a requirement infeasible, escalate through the AI operating model and log an ADR/decision request.

# 0006: Shared table revision and private intents

Status: Accepted (2026-11-03); partly supersedes [ADR 0005](0005-player-view-and-table-session-boundary.md)

## Context

ADR 0005 §8 increments `TableSession.revision` for every session mutation, accepted intents included. Planning M7 pre-actions showed that one user's private selection would then make other users' in-flight commands stale, including the current actor's poker command.

## Decision

1. **Shared revision.** `TableSession.revision` is the monotonic revision of shared table state. It increments exactly once per successful shared transition: a poker action (automatic ones included); a game or hand start or advance; a join or applied seat-ownership change; an applied leave, sit-out or sit-back; a host change; an engine-generation reset; any other change to state that more than its owner can see or that changes shared behavior. A rejection, a read, or a change to private intents alone never increments it. It never resets.
2. **Private intents.** A private intent is application state that only its owner can see and that affects nobody else until it produces a shared transition: a pre-action selection, and a pending leave, sit-out or sit-back. Its commands carry `expected_revision` and are rejected on mismatch. When accepted, they return the owner's updated view at the unchanged revision.
3. **Reconciliation inside the transition.** Every deterministic change to private intents caused by a shared transition is part of that transition. It is applied before that transition's views are captured, under its revision. An automatic poker action that results (a pre-action executing, a leaving player's action) is a separate shared transition with its own revision.
4. **Snapshot identity.** Every view carries the shared revision. Two views for the same viewer at the same revision differ only in that viewer's private intents.
5. **Pre-action commands.** Selecting or clearing a betting pre-action is a `TableSession` command. A pre-action exists only while it is not its owner's turn. When it executes, the application submits a normal engine action, and the engine stays the sole judge of legality.

**Supersession.** This ADR supersedes only these parts of ADR 0005, which stays as a historical record: the increment rule of §8 and its example "an accepted leave or sit-out intent"; the closed command list of §7, extended by decision 5; and §13's "after every successful state change", which becomes: after a shared transition, every connected viewer receives their own full snapshot; after a private-only change, only the owner receives theirs. Everything else stands, including `expected_revision` on every state-changing command, the guard before the engine, and timers re-checking the revision.

## Alternatives considered

- **One revision for everything:** rejected, because private toggles make unrelated commands stale.
- **A second, per-viewer revision:** unnecessary, because private intents create no cross-user staleness, and one user's intents are last-write-wins over one ordered connection.

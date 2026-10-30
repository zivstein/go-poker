# Go! Poker Engineering Guidelines

- Keep the poker engine independent from API, persistence, networking, and clients.
- Poker rules and game-state decisions belong in the engine, never in clients.
- Reuse existing domain logic; every rule and state value has one source of truth.
- New behavior requires automated tests.
- Prefer typed, focused domain models, explicit state, and small functions.
- Do not introduce abstractions until they have a concrete responsibility.
- Keep rejected operations atomic.
- Do not commit, push, amend, rebase, reset, restore, stash, or rewrite Git history unless the user explicitly authorizes it.

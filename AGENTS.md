# Go! Poker Engineering Guidelines

- Keep the poker engine independent from API, CLI, web, and mobile layers.
- Poker rules and game-state decisions belong in the engine, not in clients.
- Reuse existing domain logic; do not create duplicate sources of truth.
- New behavior must include automated tests.
- Prefer typed, focused domain models and small functions.
- Prefer explicit domain state over UI-driven or implicit state.
- Do not introduce abstractions before they have a clear responsibility.
- Do not commit, push, amend, rebase, reset, or rewrite Git history unless explicitly requested.
# Go! Poker Development Guidelines

- Keep the core poker engine independent from API, CLI, web, and mobile layers.
- New behavior should include automated tests.
- Prefer typed, focused domain models and small functions.
- Avoid duplicated game-state logic.
- Poker rules belong in the engine, not in clients.
- Prefer explicit domain state over implicit UI-driven state.
- Do not introduce abstractions before they are needed.
- Do not modify Git history automatically.
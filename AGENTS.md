# Go! Poker - Codex Instructions

## Project

Go! Poker is a Python No-Limit Texas Hold'em engine built primarily
as a learning and portfolio project.

The long-term goal is to support:
- full Texas Hold'em game rules
- table positions
- betting rounds
- all-ins
- main and side pots
- bots
- CLI gameplay
- a future web/API multiplayer layer

## Working style

This is a learning project.

The user should write the core implementation and algorithms.

For core poker logic:
- Prefer explaining, reviewing, and giving hints.
- Do not implement an entire solution unless explicitly asked.
- Point out problems and edge cases before rewriting code.
- Explain why an alternative design is better.

Core learning areas include:
- hand evaluation
- position assignment
- betting state
- action order
- side-pot calculation
- game state management

Do not solve these automatically unless explicitly requested.

## Code quality

Prefer:
- clear Python
- type hints
- small focused functions
- explicit domain models
- testable code
- separation between poker engine and UI/API layers

Avoid premature abstraction and overengineering.

## Testing

New behavior should have tests.

When reviewing code, look for:
- missing edge cases
- incorrect poker rules
- invalid state transitions
- duplicated logic
- unclear responsibilities
- unnecessary complexity

## Git

Do not create commits unless explicitly requested.
Do not amend, reset, force-push, or modify Git history unless explicitly requested.
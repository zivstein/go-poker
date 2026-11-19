# Offline Development Guide

A short handoff for working without internet, written 2026-11-19 against `master` at `033f945`. It serves the [Offline Variant Lab](../ROADMAP.md#track-3--offline-variant-lab) (Issue #26): a learning and experimentation track that is **not** a Friends Alpha release blocker.

## Ground rules

- Experiment on a separate branch in a separate worktree. `master` stays clean and untouched.
- Do not change production behavior, the `go-poker.v1` wire contract ([ADR 0009](../adr/0009-wire-protocol-v1.md)), accepted ADRs or any approved rule. A change like that needs a Cycle after you return.
- Tests first: every exercise starts with a failing test.
- Keep the engine free of API, persistence, networking and client concerns. Poker rules live in the engine, never in Web ([AGENTS.md](../../AGENTS.md)).
- No abstractions before two real implementations need them ([ARCHITECTURE.md](../ARCHITECTURE.md#variant-and-betting-structure-strategy)). Do not add variant base classes, factories or registries.
- Experimental code is a learning artifact. It becomes product code only after review and an approved Brief.

## Existing material on this Mac

These files are outside the repository and are not committed. Read them for theory, and read this guide for current repository facts.

| File (in `~/Downloads/`) | Use |
| --- | --- |
| `GoPoker_Preflight_Reset/Go_Poker_Offline_Engineering_Guide_v2.md` (and `_Dark.html`) | Hebrew theory guide: Omaha, Pot-Limit, Pineapple, Chinese Poker/OFC and the Show/Muck timer. Dated 2026-11-17, so its status lines are stale: it says PR #2's fix was unmerged and lists the old blocker set |
| `Go_Poker_Offline_PLO_Development_Guide.md` / `.html` | The earlier PLO guide (2026-11-11) |
| `GoPoker_Preflight_Reset/OFFLINE_FLIGHT_PLAN.md`, `README_FIRST.md`, `ROADMAP_RESET_DRAFT.md` | Draft planning kit. Its roadmap draft is superseded by [`ROADMAP.md`](../ROADMAP.md) |
| `GoPoker_Preflight_Reset/go_poker_reset.py`, `offline_prepare.sh` | Do not re-run `--apply`: the Board and Issues #22–#26 already exist (they carry its `go-poker-reset:` markers). Run `offline_prepare.sh` only if you want its worktree and cache helper; check it first |

## Architecture: Core, App, Backend, API, Web

Paths are under `src/go_poker/` unless noted.

| Layer | Where | Responsibility |
| --- | --- | --- |
| **Core** | `core/`, `game/`, `game/betting/`, `game/variants/` | Cards, deck, hand evaluation, table, hand lifecycle, betting, pots, showdown, settlement, visibility. Dependency-free. All poker rules |
| **App** | `app/` | Transport-free `TableSession`: members, commands, shared revision, private intents, pre-actions, per-user `TableView` |
| **Backend** | `server/` | FastAPI app. `runtime.py` is the single writer per table (`TableRuntime`); `ws.py` the WebSocket handler; `timers.py` the next-hand timer; `directory.py` the in-memory tables |
| **API** | `server/http.py`, `dto.py`, `mapping.py`, `decode.py`; contract in `docs/adr/0009-wire-protocol-v1.md` and its `scenarios/` fixtures | `go-poker.v1`: JSON over HTTP (create, join) and one WebSocket per table connection; full per-viewer snapshots; one outcome per command |
| **Web** | `web/src/` (`connection/`, `protocol/`, `session/`, `presentation/`, `table/`) | React + TypeScript renderer of server snapshots. It implements no poker rules |

Layering is enforced by `tests/test_layering.py`: `core/` never imports `game/`; `core/` and `game/` never import `app/` or `server/`; `app/` never imports `server/`. Backend and Web read the same fixtures; neither decides legality.

Authority in one line: Core decides rules and money, App decides who may do what and owns the revision, Backend serializes and delivers, Web displays and forwards the player's choice.

## Key source paths for Omaha and Pot-Limit

**Evaluation (Omaha High).**

- `core/evaluator.py`: `evaluate_five(cards)` for exactly five cards (the building block); `evaluate_best` for five to seven cards, raising `WrongCardAmountError` outside that range. Omaha's nine cards cannot go through `evaluate_best`.
- `core/hand_rank.py`: `HandRank` (comparable). `core/best_hand.py`: `BestHand` and descriptions.
- `game/variants/texas_holdem/hand_strength.py`: `holdem_hand_strength`, the Hold'em-specific consumer, and the model for a variant evaluator.
- `game/variants/texas_holdem/dealing.py`: Hole-card dealing. `hand_state.py` holds `HandPlayerState.hole_cards` (a list).
- `game/variants/texas_holdem/showdown.py` and `game/showdown.py`, `game/settlement.py`: where showdown ranks and pot winners are decided. Read them to see what an Omaha evaluator would plug into; do not edit them in the lab.
- Existing tests to imitate: `tests/core/test_evaluator.py`, `tests/game/variants/texas_holdem/test_hand_strength.py`.

**Betting (Pot-Limit).**

- `game/betting/no_limit.py`: `min_bet_target`, `min_raise_target`, `max_target` (the No-Limit all-in target), `has_raise_rights`.
- `game/betting/legal_actions.py`: `legal_actions(hand)` assembles `min_full_target`, `max_target`, short all-in. This is where a Pot-Limit `max_target` would eventually differ. Do not edit it in the lab.
- `game/betting/state.py` (`BettingState`), `stakes.py`, `chips.py`, `pots.py` (`Pot`, layer merging from PR #21), `apply.py`.
- Tests: `tests/game/betting/test_no_limit.py`, `test_legal_actions.py`, `test_pots_chip_oracle.py`.
- Variant and betting structure are separate dimensions ([ARCHITECTURE.md](../ARCHITECTURE.md#variant-and-betting-structure-strategy)): Pot-Limit is a betting structure, not Omaha.

**Chinese Poker / OFC** are a separate game family. Do not force them into `PokerHand`. Reuse only `core/card.py`, `core/deck.py` and `evaluate_five`.

## Ordered exercises

Each is small, offline-testable, and ends with a written note (see the handoff template below). Do them in order; stop at any point.

| # | Exercise | Produces | Done when |
| --- | --- | --- | --- |
| 0 | **Preflight (online, before leaving).** Sync dependencies and run the standard gates once | A passing baseline and a recorded base commit | `uv run scripts/verify.py` ends `VERIFY: PASS` |
| 1 | **Trace a Raise** (read-only). Follow `web/src/table/BettingControls.tsx` → `web/src/connection/ConnectionController.ts` → `server/ws.py` → `server/decode.py` → `server/runtime.py` → `app/session.py` → `game/betting/apply.py`, and back to the snapshot | A written call graph: for each hop, input, output, invariant | You can say who owns money legality, who owns the revision, and who may touch the socket |
| 2 | **Pot invariants.** Read `game/betting/pots.py` and its tests; hand-compute three cases (a tie with an odd chip, a side pot, equivalent layers) | Three extra tests in a scratch test file, not in `tests/game/` | Chips are conserved and each case matches your hand calculation |
| 3 | **Omaha High evaluator** (pure). A function of four hole and five board cards that returns the best `HandRank` using exactly two hole and exactly three board cards: 60 combinations through `evaluate_five` | Tests first, then the function in a new `game/variants/omaha/` module | Trap cases pass: four board spades plus one hole spade is no flush; a board straight with no usable hole pair is no straight; result independent of input order; duplicates rejected. Hold'em code untouched |
| 4 | **Pot-Limit maximum target** (pure). With plain integers: `H` the player's street contribution, `P` the pot including all current-street bets, `C` the amount to call, the maximum raise-to target is `H + P + 2C` (capped by the stack). Example: blinds 1/2, pot 3, `C=2`, `H=0` → 7 | A pure helper with a boundary matrix: opening bet, re-raise, `H>0`, short stack, short all-in | The helper is not wired into `legal_actions` or Web. Note the difference between the added amount and the target |
| 5 | **Pineapple Hold'em discard** (pure). Pick one ruleset in writing (Standard: discard before the flop; Crazy: after flop betting). A pure `discard(hole3, card)` returning two hole cards and the discarded one | A state diagram plus tests | No discard of a card not held; no duplicate cards; the discarded card is not public |
| 6 | **Classic Chinese Poker.** A three-card front evaluator (high card, pair, trips only) and a 3/5/5 arrangement validator with foul detection; then two-player scoring for one chosen ruleset | A rules spec naming the ruleset, plus tests | Every foul is detected; no dependency on `PokerHand`, HTTP or React |
| 7 | **OFC / Pineapple OFC** (design only unless time remains). The placement state machine: five cards, then rounds of placing cards and discarding | A short design note | It states clearly how it differs from Classic and from Pineapple Hold'em |

An optional design-only exercise on the Show/Muck timer (Issue #25) is a state machine with manual resolve and timeout resolve, tested exactly-once with a fake clock. Keep it out of `server/`. The contract decisions are open and belong to a later Cycle.

## Running tests offline

Before leaving, with internet, in the worktree you will use:

```bash
uv sync --locked
```

```bash
cd web && npm ci
```

Node must be on the major line in `web/.nvmrc` (currently 26). The Python and Web toolchains must be installed before the first offline run; a package that is not cached cannot be fetched.

While offline, from the worktree root:

```bash
uv run --offline pytest tests/core tests/game -q
```

Targeted examples: `uv run --offline pytest tests/game/betting -q`, `uv run --offline pytest -k omaha -q`, `uv run --offline ruff check src tests`, `uv run --offline mypy src`.

The standard gate runs `uv run` internally, so make uv offline for the whole process:

```bash
UV_OFFLINE=1 uv run scripts/verify.py
```

Web tests need no network once `node_modules` exists: `cd web && npm test`.

What was checked on 2026-11-19: `uv run --offline pytest tests/core tests/game/betting -q` passed (797 tests) and `npx vitest run` in `web/` passed on this checkout. The full `UV_OFFLINE=1 uv run scripts/verify.py` was not run for this documentation change; run it once before you leave.

## Committing experiments safely

Git works offline for commits; pushes and PRs wait for the network. Create a sibling worktree from a clean, synchronized `master`, outside the main checkout:

```bash
git -C ~/Developer/go-poker switch master
git -C ~/Developer/go-poker pull --ff-only origin master
git -C ~/Developer/go-poker worktree add -b offline/omaha-evaluator ~/Developer/go-poker-wt/offline-omaha master
```

In the worktree run the dependency commands above. Then:

- Work only in the worktree; the main checkout stays on `master`, clean.
- One branch per exercise or tightly related pair. Commit small and often. Local branch names start with `offline/`.
- Do not mix experiments with any production branch. Do not push, open PRs, or rewrite history while offline.
- Keep personal notes in an untracked `offline_notes/` directory, not in tracked code.
- Run the targeted tests and `git diff --check` before each commit.

## Evidence to bring back

For each branch:

1. Base commit and branch: `git rev-parse master offline/<name>`.
2. The full diff: `git diff master...offline/<name>` (also saved as a patch: `git format-patch master..offline/<name> -o ~/Desktop/offline-patches`).
3. The tests you wrote **before** the implementation (point at the first commit if you can).
4. Commands run offline and their output: the targeted `pytest` runs, and the last `VERIFY:` line if you ran the gate.
5. The rule you implemented, with its source, and the ruleset choice for Pineapple and Chinese Poker.
6. What is incomplete, speculative or failing, and your unanswered rules questions.

Handoff template (save as `offline_notes/HANDOFF.md`):

```markdown
# Offline handoff
- Branch / base commit:
- Exercise and ruleset chosen:
- Files changed:
- Tests written before implementation:
- Commands run offline / results:
- Boundaries preserved (layering, no production edits):
- Decisions I made on purpose:
- Known bugs, failing tests, open rules questions:
- What I want reviewed next:
```

Back online: share the diff and notes for review, then decide in a normal Cycle what, if anything, becomes product code. Do not ask for the experiment to be merged as is.

## Decisions needed before any integration

None of these may be settled by the lab. Each needs an approved decision before experimental code touches the product.

| Area | Why it needs a decision |
| --- | --- |
| **Wire protocol** | `go-poker.v1` is strict and frozen. Four hole cards (Omaha), Pot-Limit sizing, a discard phase, Chinese arrangement actions or a Show/Muck deadline each need new fields or commands, hence a new protocol version or compatibility policy (C7, ADR 0009 §1.6) |
| **Variant selection** | Per table or per hand is Milestone 13 and undecided. `TableSession` and `TableView` assume Hold'em today |
| **Betting structure** | Pot-Limit changes `legal_actions` outputs and the shape of the sizing contract. It also touches the deferred pot-based sizing presets (W21) and the slider-increment decision in [`CURRENT_CYCLE.md`](../CURRENT_CYCLE.md) |
| **Hidden information** | Omaha's four cards and Pineapple's discard are new private data. `game/visibility.py`, the view projection and the history redaction rules need a decision |
| **Showdown and settlement** | Omaha's evaluator feeds `showdown.py`; Hi/Lo is out of scope. Chinese Poker's unit scoring has no pot and needs its own settlement contract |
| **Show/Muck timer (#25)** | Server-owned deadline, legality of auto-Show, reconnect and restart semantics, and the ADR/protocol review |
| **Game family** | Chinese Poker/OFC need their own engine, session and table model, not an extension of `PokerHand` |

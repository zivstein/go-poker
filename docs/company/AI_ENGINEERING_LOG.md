# AI Engineering Log

Case studies of significant, measured improvements to the Go! Poker AI engineering system, and the reusable lessons behind them.

This is reference material, not an operational instruction source. Routine workflow changes belong in Git history, not here. An entry earns a place when it changes how the organization works in a way that can be measured or clearly evidenced, and teaches something reusable beyond this project.

Each case study covers: Problem, Evidence, Change, Measured result, Engineering lesson, and Reusable principle.

Cost figures are API-equivalent estimates computed from local session transcripts by `scripts/usage_report.py`. They compare workflows; they are not billing records. Account, plan, and quota data are never recorded here.

## Index

| ID | Date | Improvement | Status |
| --- | --- | --- | --- |
| [AIE-004](#aie-004-deterministic-finish-cycle) | 2026-11-01 | Deterministic `/finish-cycle` closeout | Measured |
| [AIE-003](#aie-003-independent-milestone-level-external-audit) | Milestone 5 boundary | Independent milestone-level external audit | Completed |
| [AIE-002](#aie-002-autonomous-lead--engineer--qa--reviewer-workflow) | 2026-10-29 – 2026-10-30 | Autonomous Lead → Engineer → QA → Reviewer workflow | Backfill pending |
| [AIE-001](#aie-001-durable-context-architecture) | 2026-10-29 – 2026-10-30 | Durable context architecture | Backfill pending |

## AIE-004: Deterministic `/finish-cycle`

Date: 2026-11-01 · Commit: `8a56d50`

### Problem

Cycle closeout (verify, stage, commit, push) is mechanical and fully specified, yet it was performed by an AI model following a prose procedure. That made the cheapest step of a Cycle one of its most expensive, and made correctness depend on the model following each Git step faithfully.

### Evidence

A Meta audit of earlier closeouts, using `scripts/usage_report.py`, found:

- three `/finish-cycle` samples cost $0.89, $0.63, and $0.81 equivalent, averaging about $0.78;
- the skill switched the Lead from Opus to Sonnet for closeout; because prompt caches are per model, each switch re-wrote the whole conversation prefix as a cold cache, producing 113k–194k cache-write tokens per run;
- the remaining tokens went to the model reasoning through Git and verification steps that have exactly one correct execution.

The model switch was meant as a saving; the cache cost it caused was larger than the saving.

### Change

- Mechanical work moved into deterministic, tested scripts: `scripts/verify.py` runs every verification step and reports one `VERIFY: PASS` / `VERIFY: FAIL` result, and `scripts/finish_cycle.py` performs the whole Git closeout.
- The Lead stays on its session model; the skill only hands the approved manifest to the script and reports its outcome.
- The push is programmatically gated. The script checks the commit state before pushing: HEAD must be a new single-parent commit, exactly one ahead of upstream, containing exactly the manifest paths with the manifest message, on a clean tree. It fails closed and never repairs state.
- Every Cycle Report now ends with an explicit closeout manifest (commit message plus every changed path). The approved commit scope is visible before the user invokes `/finish-cycle`, and the script commits nothing unless the working tree matches it exactly.

### Measured result

| | Before (3 runs) | V2 (first run) |
| --- | --- | --- |
| Equivalent closeout cost | about $0.78 average | about $0.20 |
| Cache-write tokens | 113k–194k | about 2k |
| Lead model during closeout | switched to Sonnet | stayed on Opus |

Closeout cost fell by approximately 74%. Safety improved too: commit scope and push conditions are now enforced by code rather than by instructions.

The V2 figure is a single run; later Cycles should confirm it.

### Engineering lesson

**Use AI for judgment; use deterministic code for deterministic work.**

The closeout contained almost no judgment. The only real decision, which changes belong in the commit, is now made earlier in the Cycle Report and approved by the user. Everything after that is mechanics, and code does mechanics more cheaply, more reliably, and more checkably than a model.

A second lesson: model routing must account for cache state. A cheaper model is not cheaper if switching to it discards a large warm cache.

### Reusable principle

When an AI workflow step has exactly one correct execution:

1. move its decisions earlier, into an explicit artifact the human approves (here, the closeout manifest);
2. implement the execution as a tested script that verifies its preconditions and fails closed;
3. gate irreversible actions (push, publish, deploy) on programmatic checks, not on the model remembering them;
4. keep the AI for interpreting failures and explaining them to the human.

Measure total workflow cost, including cache effects, before and after routing or tooling changes.

## AIE-003: Independent milestone-level external audit

Date: Milestone 5 boundary, before closeout · Evidence: recorded externally at the Milestone 5 boundary, not in a historical commit

### Problem

Each Cycle's Reviewer judges one change against its brief. No gate reviewed the accumulated system: whether contracts that each Cycle got right individually still compose correctly once a milestone joins them end to end.

### Evidence

Milestone 5 was the first milestone to connect the full hand lifecycle, from `Table` through continuous play, making it a natural boundary for the first system-level audit.

### Change

Before Milestone 5 closeout, an independent external audit reviewed a complete pre-commit repository snapshot:

- the full ownership and integration path: `Table` / lifecycle → `HandSetup` → `hand_flow` → showdown → settlement → `HoldemGame`;
- the architecture documents and contracts against the implementation;
- an independent run of the full test suite on a temporary Python 3.13 compatibility copy, in addition to the project's normal Python 3.14 verification.

### Measured result

| | Result |
| --- | --- |
| Critical findings | 0 |
| Major findings | 0 |
| Minor findings | 1: documentation/contract; multiple `HoldemGame` instances driving the same `Table` were unsupported but not stated |
| Nits | 1: documentation; duplicate `initialize_betting` in the settled-hand guard list |
| Independent test run (additional to normal Python 3.14 verification) | 2158/2158 passed independently on the temporary Python 3.13 compatibility copy |
| Production-code changes required | none |

Both findings were corrected before Milestone 5 closeout.

### Engineering lesson

The two review gates answer different questions:

- **Cycle Reviewer:** is this change correct, in the right place, with enough evidence? Its scope is the current diff.
- **External milestone audit:** do the implementation and contracts accumulated across Cycles hold together as a system? Its scope is the whole integration path.

Finding no defects is itself useful evidence. It showed that the Cycle gates held up across a milestone's worth of changes. The only findings were in the contracts between components, which no single-Cycle review is positioned to see.

### Reusable principle

Pair per-change review with periodic system-level review at milestone boundaries. Audit a complete snapshot before it is committed, trace ownership end to end across component boundaries, re-run the evidence independently (here, on a second Python version), and treat unstated contract assumptions as findings even when the code is correct.

## AIE-002: Autonomous Lead → Engineer → QA → Reviewer workflow

Date: 2026-10-29 – 2026-10-30 · Commits: `051432a`, `50d5f5f`, `fde45b6`, `67a9ae2`

Status: backfill pending; no metrics recorded yet.

Summary from repo history: the workflow grew from Lead + Engineer + Reviewer subagents into a formal Core Engineering Team with an independent QA Engineer, a Cycle Brief approved by the user before implementation, autonomous Engineer → QA → Reviewer handoffs inside that approved boundary, and per-role model and effort routing. Design rationale is in `COMPANY_MANUAL.md`; operating rules are in `docs/ENGINEERING_PROCESS.md`.

## AIE-001: Durable context architecture

Date: 2026-10-29 – 2026-10-30 · Commits: `96f7d45`, `470c9d1`

Status: backfill pending; no metrics recorded yet.

Summary from repo history: project knowledge moved out of prompts and into durable repository documents (`ARCHITECTURE.md`, `ROADMAP.md`, `CURRENT_CYCLE.md`, `ENGINEERING_PROCESS.md`). `CLAUDE.md` changed from importing the full engineering process into every session to a short pointer list loaded by relevance (progressive disclosure), and role instructions were refocused per agent. Design rationale is in `COMPANY_MANUAL.md` under Context Engineering.

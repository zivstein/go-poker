# M8 C5.4 Enforcement Retrospective

**Date:** 2026-11-10  
**Scope:** M8 C5.4a (ownership map and CI check) and C5.4b (PreToolUse guard hook), including the Option B redesign  
**Outcome:** C5.4a is complete and stays in force. C5.4b is stopped and superseded. Option B is archived and not activated. The project moves to a native-first, manually coordinated parallel workflow ([M8 Plan](../milestones/M8_PLAN.md), C6).

Evidence labels used below:

- **Confirmed:** checked in the repository, Git history, GitHub Actions, or by inspecting the archived files.
- **Reported:** taken from session reports, the project's usage report, or the Product Owner. Not re-run for this document.
- **Interpretation:** analysis and judgment.

## 1. Summary

C5.4 set out to back the "agents never change Git state" rule and the future lane ownership rules with tooling. The CI half (C5.4a) shipped in two commits and works. The local half (C5.4b), a PreToolUse hook that parsed shell commands, grew to about 4,500 lines of code and tests across many QA and review rounds. Then a partly applied fix left it unable to parse, and because it was registered fail-closed, it locked every session out of Bash, Edit and Write. A smaller redesign (Option B) was built and validated in a scratch repository, but the Product Owner chose not to activate it. The cost of owning a custom shell guard was out of proportion to what it could prevent, and product work had stalled.

## 2. Original problem and intended capabilities

*Confirmed* (from [ENGINEERING_PROCESS.md](../ENGINEERING_PROCESS.md), [ADR 0007](../adr/0007-lane-ownership-and-cross-lane-contracts.md), [C5.2 design](M8_C5_2_ORGANIZATION_DESIGN.md)):

- The rule that no agent commits, pushes or rewrites Git history rested only on instructions (`AGENTS.md`, agent files).
- The planned multi-lane organization needed lane and role path permissions enforced by the same ownership map at three layers:
  - **Prevent:** a local hook;
  - **Detect:** a CI check run from `master`'s code;
  - **Judge:** the Reviewer.
- C5.4 was split on 2026-11-09:
  - **C5.4a:** the map resolver and the CI `ownership` check;
  - **C5.4b:** the guard hook and the committed `.claude/settings.json`.
- C5.5 (Work Order tooling) and C5.6 (activation and dry run) were to follow.

## 3. Timeline

| When (UTC) | Event | Evidence |
| --- | --- | --- |
| 2026-11-09 19:16 | C5.4a/C5.4b split and decisions D1–D4 approved | Reported |
| 2026-11-09 22:12 | C5.4a committed ([`ba0d168`](https://github.com/zivstein/go-poker/commit/ba0d1683353bf284e0c9af8cb959ecbcc9a59004)). CI run 42709683258 fails | Confirmed |
| 2026-11-09 23:02 | Fix committed ([`0c98cc7`](https://github.com/zivstein/go-poker/commit/0c98cc7cf5ee08450784fbd7f5bb449d58c63d1c)). CI run 42717132594 passes | Confirmed |
| 2026-11-09 23:13 | C5.4b starts: real hook payloads captured, fail-closed behavior verified on Claude Code 2.1.319 and 2.1.321 | Reported |
| 2026-11-09 23:59 – 11-10 01:12 | Engineer, QA and Reviewer rounds on the guard (16 subagent hand-backs) | Reported |
| 2026-11-10 01:11 | Last change to `scripts/guard.py`, which no longer parses | Confirmed (file time, parse error) |
| 2026-11-10 13:37 | Product Owner pauses closeout for an architecture review. The lockout is diagnosed | Reported |
| 2026-11-10 13:45 – 14:32 | Option B approved as direction, then for scratch implementation | Reported |
| 2026-11-10 14:04 | Recovery override confirmed, after a first invalid-JSON attempt | Reported |
| 2026-11-10 17:28 | Option B implementation report: QA passed, Reviewer approved, rehearsal passed | Reported |
| 2026-11-10 | Product Owner stops C5.4b and does not activate Option B | Confirmed (this cleanup) |

## 4. C5.4a: ownership map and CI check

**Implementation** (*confirmed*, [`ba0d168`](https://github.com/zivstein/go-poker/commit/ba0d1683353bf284e0c9af8cb959ecbcc9a59004)):

- `scripts/ownership_map.py`: strict map loading, path resolution and the lane decision.
- `scripts/check_ownership.py`: the PR path judge.
- `.github/workflows/ownership.yml`: runs `master`'s check on `pull_request_target`, with the PR head fetched as data only.
- The `quality` push trigger is limited to `master`.
- About 2,380 inserted lines, most of them tests.

**CI failure** (*confirmed*, run 42709683258): `test_the_head_is_read_only_as_git_data` found an untracked `scripts/__pycache__/ownership_map.cpython-314.pyc` in a checkout that must stay untouched. The result was 1 failed, 4,228 passed. Local verification had passed.

**Root cause** (*confirmed* from the fix): importing the sibling module `ownership_map` wrote a bytecode cache into the checkout being judged. Nothing from the PR head was imported or run. The read-only assertion was right, and the script was wrong.

**Correction** (*confirmed*, [`0c98cc7`](https://github.com/zivstein/go-poker/commit/0c98cc7cf5ee08450784fbd7f5bb449d58c63d1c)): `sys.dont_write_bytecode = True` before the import. The assertion was kept as it was. CI went green.

**Retained value:**

- The ownership map stays the single home of lanes, path kinds and role permissions.
- Fork and base checks run on every PR in both modes.
- The CI design runs trusted code against untrusted data.
- In `single-team` mode the check makes no path checks, so it does not block branch-based work (*confirmed*, `scripts/check_ownership.py` docstring).

## 5. C5.4b: the original guard

**What was built** (*confirmed*, archived working tree):

| Part | Size |
| --- | --- |
| `scripts/guard.py` | 1,681 lines |
| `tests/tooling/test_guard.py` | 2,289 lines |
| Captured hook payload fixtures | 258 lines |
| Settings tests and guard test lab | about 330 lines |
| Ownership map `agents` role mapping (D1) | small change in 5 files |

The guard included:

- its own shell parser: separators, subshells, `$( )`, heredocs, `sh -c`, `eval`, wrappers, brace expansion and `$'…'` quoting;
- tracking of the effective directory through `cd` and `git -C`, so it could scope itself to this repository;
- strict Git and `gh` allowlists (D2);
- multi-lane file rules with subagent identity.

It was registered for Bash, Edit, Write, NotebookEdit, Monitor and the Terminal tool, with `onFailure: "block"` and a 10-second timeout.

**Complexity growth** (*interpretation*): every QA round found another way to spell a Git command, such as case variants, wrappers, brace tricks, quoting or heredocs fed to a shell. Each fix added parser surface and tests. The guard's own docstring admitted it was "best effort, not a boundary": `python -c`, scripts, aliases and `find -exec` still went through. The work was converging on a shell reimplementation without converging on coverage.

**Lockout** (*confirmed* for the file state, *reported* for the sequence):

- A fix round in response to Reviewer findings was partly applied when work stopped. `read_word()` lost its loop header and branches, and the file fails with `IndentationError` at line 761. No intact copy of the guard exists.
- Settings changes apply to running sessions, the hook covered every shell and file tool, and it failed closed. So every Bash, Edit and Write call in every session in the repository was blocked, including the calls needed to fix it.
- The working-tree docs had already marked C5.4b "complete" before closeout, verification or the live coverage check. The "Not covered" list was still a placeholder.

**Recovery** (*reported*):

- The documented override (`"disableAllHooks": true` in `.claude/settings.local.json`) had to be applied by hand.
- The first hand edit produced invalid JSON, and the override then silently did not apply.
- The second edit worked.
- The override was still in place when this record was written. The Product Owner removes it by hand once the deny-only settings are confirmed.

## 6. Option B: pivot and scratch validation

**Design** (*reported*, approved 2026-11-10): native deny rules stay as defense in depth. A small, case-insensitive dispatcher hands only commands that mention `git` or `gh` to a smaller shell guard. The D2 policy, repository scope and file rules move into separate modules. There is no general shell parser, and anything unsupported is "ambiguous" and blocks when it mentions Git.

Owner decisions on it:

- **D-B1** deferred: the original `gh` scope stays.
- **D-B2** rejected: the native deny rules stay.
- **D-B3′** approved: per-segment ambiguity analysis.
- **D-B4** approved as a documented limitation: program names without a literal `git`.
- **D-B5** not approved as proposed: the `if` prefilter missed `GIT commit`, so a dispatcher was tested instead.

**Size** (*confirmed*, archive): five modules of 1,570 lines in all (`guard_dispatch`, `guard_shell`, `git_policy`, `repo_scope`, `guard_files`), plus six test files of about 3,700 lines. That is about 1,030 code lines without docstrings, by the session's own count.

**Validation results:**

| Check | Result | Evidence |
| --- | --- | --- |
| Activation rehearsal gates G3.0–G3.5 | all PASS, including `VERIFY: PASS` | Confirmed (archived summary) |
| Mutation checks on the new modules | 40 mutants: 31 killed, 9 survived (mostly parser edge cases) | Confirmed (archived summary) |
| Full verification in scratch | `VERIFY: PASS`, 5,859 tests | Reported |
| QA and review | 5 QA rounds, 2 Reviewer rounds, 18 findings fixed; final QA PASSED, Reviewer APPROVED | Reported |
| Differential fuzzing against bash and zsh | about 40,000 commands, 0 misses after fixes | Reported |
| Replay of 6,849 real project commands | 0 newly blocked; 228 blocked against 291 for the old guard; none slower than 0.5 s | Reported |
| Live checks on Claude Code 2.1.319 and 2.1.321 | commits blocked (including `GIT commit`); normal commands, Write and Monitor allowed; failure drills and rollback behaved as designed | Reported |
| Not verified | the Terminal tool and an interactive Desktop session | Reported |

The documented limits that remained include obfuscated program names, indirect Git through other runtimes or scripts, Bash file writes, and non-shell Desktop tools such as worktree creation.

## 7. Why Option B is not activated

*Product Owner decision (confirmed); rationale (interpretation):*

- **Low marginal protection.** The native deny rules already stop the plain forms of every state-changing Git and `gh` command. The guard added coverage only for unusual spellings, while indirect routes stayed open. Every session also holds the Product Owner's credentials, so no local hook is a security boundary.
- **The authoritative layer already exists.** Path ownership is enforced by the C5.4a CI check, run from `master`. File-level lane enforcement matters only in `multi-lane` mode, which is not being activated.
- **High ownership cost.** Activating it would put about 5,300 lines of security-sensitive shell-parsing code and tests into a poker project. Every change would need Meta work, and a mistake would lock everyone out, as already happened.
- **Opportunity cost.** M8 C5 had absorbed most of two days of sessions and usage limits while product work waited.

The scratch result is still useful: it shows that a smaller targeted hook is feasible if a real need appears (see Revisit criteria).

## 8. Usage and context findings

*Reported* by `scripts/usage_report.py` from local transcripts. Subagent calls are included, and no costs are recorded:

| Session | Span (UTC) | Model calls | Peak context (Lead / Engineer / QA) | Full verifications |
| --- | --- | --- | --- | --- |
| C5.4a (brief, implementation, CI fix) | 11-09 18:58 – 23:02 | 274 | 281,973 / 103,823 / 235,767 | 11 |
| C5.4b (original guard, lockout, Option B) | 11-09 23:13 – 11-10 17:29 | 810 | 719,158 / 534,016 / 324,959 | 27 |

- Both sessions passed the report's warning thresholds: peak context above 150,000 and more than 8 full verifications. In the C5.4b session, 611 of 810 calls ran above 150,000 tokens of context.
- *Reported by the Product Owner, from the app's usage display:* the five-hour limit reached **99%** before a reset, and **57%** in the window after the reset. These are two separate five-hour windows, and the two figures are not additive or comparable as one total. No weekly figure was recorded.
- *Interpretation:* one long Lead session carrying planning, implementation oversight, incident recovery and a redesign is the main driver of context size. The Context and Session Policy already says to start fresh after planning and after each Cycle. C5.4b did not follow it once the scope changed.

## 9. Product Owner decisions

| Decision | Date | Status |
| --- | --- | --- |
| Split C5.4 into C5.4a and C5.4b; D1–D4 | 2026-11-09 | C5.4a done. D3 (fork PRs fail the `ownership` check) is in force through C5.4a. D1 (agent-to-role map) and D2 (strict Git/`gh` allowlist in the guard) are archived with C5.4b. D4 (`M<n> \| C<n>` commit messages) is kept in `ENGINEERING_PROCESS.md` |
| Option B as direction, then for scratch implementation; D-B1–D-B5 | 2026-11-10 | Superseded: not activated |
| Stop C5.4b; no Option B; native-first, manually coordinated parallel workflow | 2026-11-10 | In force. Recorded as a status note on [ADR 0007](../adr/0007-lane-ownership-and-cross-lane-contracts.md), which is otherwise kept as written |
| Remove the guard registration and code from the working tree after archiving | 2026-11-10 | Done |

## 10. Lessons learned

1. **Prefer native controls first, and measure the gap before building.** The deny rules covered most of the real risk. The guard's extra coverage was never measured against its cost until after the lockout.
2. **A fail-closed hook on every tool is a single point of failure.** It needs a recovery path that is tested before registration and works without the tools it blocks.
3. **Register last, after the final verification.** Settings apply to running sessions, so a registered work-in-progress guard is live production.
4. **Unbounded threat models grow code without closing gaps.** "Any spelling of git" has no natural end. Define the adversary (an honest agent making mistakes) and stop there.
5. **Record status only after the gates pass.** The working-tree docs declared C5.4b complete before its closeout.
6. **Hand edits to recovery files need validation.** The first override attempt failed silently because the JSON was invalid.
7. **Keep sessions short when scope changes.** Implementation, incident and redesign in one Lead session drove context to about 720k tokens.
8. **CI catches environment-specific faults.** C5.4a's bytecode issue passed locally and failed in a clean runner. The strict read-only assertion was the right test.

## 11. Revisit criteria

Revisit local enforcement only if one of these happens, through a new, approved Meta Cycle:

- An agent changes Git state or writes outside its task's paths in a way that the native deny rules, CI and review did not catch. Record the incident.
- `multi-lane` mode is approved for activation, and the parallel POC shows that path violations reach PRs often enough to cost real rework.
- Claude Code adds native features that cover the gap, such as path-scoped write permissions or a sandbox, so that no custom parser is needed.
- Identity separation (a machine user or token) is adopted, which would make local enforcement a real boundary.

Option B in the archive is the starting point if one of these happens. It is not to be registered as it is.

## 12. Archive and sources

**Archive** (outside the repository): `~/Developer/go-poker-archive/c5-4b-enforcement-2026-11-10.tar.gz`, SHA-256 `d8c6c56bbd02194b5bae4d1b2ab825e892681aee005541bc1ac6697a881819a4`. It holds:

- the uncommitted C5.4b working tree as it was before cleanup, with the damaged guard;
- the Option B modules, tests and patch;
- the validation harness scripts and result summaries;
- per-file checksums.

It is machine-local. To keep it durably, the Product Owner can attach it to a GitHub release or an archive branch.

**Sources:**

- Commits [`ba0d168`](https://github.com/zivstein/go-poker/commit/ba0d1683353bf284e0c9af8cb959ecbcc9a59004), [`0c98cc7`](https://github.com/zivstein/go-poker/commit/0c98cc7cf5ee08450784fbd7f5bb449d58c63d1c), and CI runs 42709683258 (failed) and 42717132594 (passed).
- [ENGINEERING_PROCESS.md](../ENGINEERING_PROCESS.md): Enforcement, Technology Freeze, and Multi-lane organization.
- [ADR 0007](../adr/0007-lane-ownership-and-cross-lane-contracts.md) and the [C5.2 organization design](M8_C5_2_ORGANIZATION_DESIGN.md).
- [M8 Plan](../milestones/M8_PLAN.md) and [CURRENT_CYCLE.md](../CURRENT_CYCLE.md).

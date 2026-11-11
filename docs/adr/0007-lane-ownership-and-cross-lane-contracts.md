# 0007: Lane ownership and cross-lane contracts

Status: Accepted (2026-11-09); activation deferred and its prevention layer withdrawn (2026-11-10)

> **Status note (2026-11-10).** This record is kept as written. On 2026-11-10 the Product Owner stopped M8 C5.4b and deferred C5.5 and C5.6 ([retrospective](../company/C5_4_ENFORCEMENT_RETROSPECTIVE.md)). Two parts of this record are affected:
>
> - The prevention layer in decision 2 ("a guard hook") was withdrawn. The original C5.4b guard was implemented and registered locally. A broken edit to it locked sessions out, and it was disabled with the local override and removed. A smaller redesign (Option B) was implemented and validated in a scratch repository but never adopted. No guard hook is registered.
> - The last Consequence's "M8 C5.6" no longer schedules activation. `multi-lane` mode now needs a new, approved Meta Cycle.
>
> The rest stands: the ownership map as the single home of ownership, the CI detection layer from C5.4a, the Reviewer's judgment, and contract-first parallelism through accepted contract ADRs. In `single-team` mode, parallel work follows Parallel Sessions in `ENGINEERING_PROCESS.md`.

## Context

Milestone 8 grows the AI organization beyond one engineering team working in one checkout. Several Work Orders will run at the same time, in separate sessions, branches and worktrees, and some will build on each other. The C5 audit and the C5.2 design package ([archived rationale](../company/M8_C5_2_ORGANIZATION_DESIGN.md)) worked out how to do that without losing the properties the single-team workflow has proved: one source of truth per fact, independent gates, and small per-role context.

Three questions needed a durable answer:

1. What divides the work between concurrent sessions?
2. How does a consumer depend on another lane's work before that work exists?
3. When may concurrent work integrate?

The operative rules are in [`docs/ENGINEERING_PROCESS.md`](../ENGINEERING_PROCESS.md) (Multi-lane organization), and the lanes and permissions are in [`.claude/ownership.json`](../../.claude/ownership.json). This ADR records why they have this shape. It does not restate them.

## Decision

1. **Lanes are ownership boundaries, not standing teams.** A lane is a set of paths with a branch prefix. A short-lived Cycle Lead session owns one Work Order in one lane and ends with it. Domain continuity lives in the repository (architecture sections, ADRs and tests), not in a long-lived per-domain session.
2. **One map is the single home of ownership.** Lanes, path kinds, co-owned paths and role permissions live in one machine-readable file. Prose keeps only the principles. The same data drives prevention (a guard hook), detection (a CI check run from `master`'s code) and the Reviewer's judgment, so the three cannot drift apart.
3. **Cross-lane contracts are versioned as ADRs.** A contract that is not yet implemented is an accepted ADR, and ADR numbering and supersession are its versioning.
4. **Contract-first parallelism, with integration only on the real producer.** A producer and a consumer may work concurrently against an accepted contract. Work verified against stand-ins is provisional, and the consumer integrates only after its gates have passed again against the merged producer.

## Alternatives considered

- **Standing per-domain teams with long-lived leads:** rejected. Context accumulates across Work Orders, which is the context growth the AI Engineering Log already records, and continuity is better held in the repository.
- **Ownership tables in prose only:** rejected. Tooling cannot enforce prose, and a second, machine-readable copy would duplicate the source of truth.
- **A separate contract registry or interface package:** rejected for now. ADRs already provide versioning, acceptance and supersession, and a registry would be a second home for each contract.
- **Strictly sequential producer → consumer work:** rejected as the default. It serializes work that a stable contract makes independent, so it is used only where no stable contract exists or the consumer needs the producer's real symbols.
- **Letting phase 1 verdicts carry over when the patch-id is unchanged:** rejected. Doubles can drift from the real producer, and an unchanged consumer diff says nothing about the producer it now runs against.

## Consequences

- A Work Order that crosses lanes is split. A change needed in another lane becomes a Contract Request.
- ADRs move to the Org lane. A lane Work Order whose decision needs an ADR waits for the Org Work Order that lands it.
- A mid-flight contract change costs re-pinning, re-approval and possibly redoing provisional consumer work. Accepting the ADR before work starts and escalating unclear contracts early limit that cost.
- Co-owned files, starting with `ARCHITECTURE.md`, can conflict between lanes. The staleness rules handle it. If conflicts recur, a later decision may split the file by lane.
- None of this is active until the organization's mode is switched to `multi-lane` in M8 C5.6.

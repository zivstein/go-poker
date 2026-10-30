# Go! Poker AI Company Manual

This is the detailed reference manual for the AI engineering organization being built through Go! Poker.

It explains the concepts, reasoning, and lessons behind the organization.

It is reference material, not an operational instruction source.

If this manual conflicts with an operational file, the operational file wins.

Operational sources of truth include:

- `AGENTS.md`
- `CLAUDE.md`
- `docs/ENGINEERING_PROCESS.md`
- `docs/ARCHITECTURE.md`
- `docs/ROADMAP.md`
- `docs/CURRENT_CYCLE.md`
- `.claude/agents/`
- `.claude/skills/`

Future organization planning belongs in `ORGANIZATION_ROADMAP.md`.

## Purpose

Go! Poker has two parallel goals.

### Product Goal

Build a clean poker platform beginning with a robust No-Limit Texas Hold'em engine and later expanding into variants, simulation, platform services, clients, analytics, and AI.

### AI Engineering Goal

Use the product as a real laboratory for learning how to create and operate an AI software organization from zero.

The goal is not to learn one Claude-specific prompt.

The goal is to learn reusable engineering patterns:

- context engineering;
- specification;
- task decomposition;
- agent design;
- ownership;
- autonomous workflows;
- quality gates;
- evaluation;
- escalation;
- model routing;
- multi-agent coordination;
- multi-team coordination;
- cross-team contracts;
- reproducibility.

The final AI Company Starter Kit should be extracted from real project experience rather than designed theoretically in advance.

## Current Organization

    User — Product / Architecture Owner
                 │
        Core Engineering Lead
                 │
         ┌───────┼─────────┐
         │       │         │
     Engineer    QA     Reviewer

### User

The human owner controls decisions that materially define the product or engineering organization.

The goal is not to remove the human.

The goal is to move the human upward from implementation supervision toward product, architecture, and organizational judgment.

### Engineering Lead

The main Claude session acts as Engineering Lead.

It owns planning, orchestration, escalation, finding triage, final verification, and Cycle closeout.

The Lead should coordinate implementation rather than becoming another implementation agent.

### Engineer

The Engineer transforms an approved task into production code and focused tests.

The role stays inside approved architecture and product boundaries.

### QA Engineer

QA independently attacks delivered behavior.

Its purpose is to provide a separate behavioral feedback loop rather than help implement the original solution.

### Reviewer

Reviewer is the final design and engineering gate.

The role is read-only to preserve independence.

## Why Separate QA and Reviewer?

They optimize for different failure modes.

QA primarily asks:

> Does the delivered behavior survive realistic, boundary, and adversarial use?

Reviewer primarily asks:

> Is this the correct change, implemented in the correct place, with an appropriate design and enough evidence?

QA focuses more on behavior.

Reviewer focuses more on architecture, ownership, maintainability, scope, and the strength of the evidence.

A smaller project may combine these roles.

Separate them only when their independent perspectives create enough value to justify the extra work.

## Engineering Autonomy

The current autonomy boundary is:

> AI owns execution inside approved boundaries.
>
> The human owns changes to those boundaries.

After milestone-level decisions and the Cycle Brief are approved, the team should execute normal internal handoffs without repeatedly returning to the user.

Escalation is reserved for genuinely new decisions outside the approved boundary.

This allows autonomy without giving the AI authority to silently redefine the product.

## Definition of Ready and Done

Autonomy works better when entry and exit conditions are objective.

### Definition of Ready

Implementation should not start while the team is still guessing about:

- the goal;
- important behavior;
- ownership;
- invariants;
- scope;
- meaningful deferred decisions.

### Definition of Done

Code existing is not enough.

A behavioral Cycle requires:

- implementation;
- effective tests;
- QA;
- independent review;
- verification;
- accurate affected documentation;
- resolved blocking findings;
- updated project status.

The stronger these objective gates become, the less human supervision each individual implementation step requires.

## Context Engineering

Context engineering is the design of:

> what information an AI receives, from where, when, and for how long.

This is different from prompt engineering.

A giant prompt can temporarily compensate for weak context architecture, but over time it becomes:

- expensive;
- duplicated;
- difficult to maintain;
- easier to contradict;
- full of irrelevant information.

Go! Poker uses progressive disclosure.

### Hot Context

Small information useful almost everywhere:

- `AGENTS.md`
- `CLAUDE.md`

These should stay compact.

### Operational Context

Loaded when relevant to the task:

- `ARCHITECTURE.md`
- `ROADMAP.md`
- `CURRENT_CYCLE.md`
- `ENGINEERING_PROCESS.md`

Each answers a different question.

`ARCHITECTURE.md`:

> How does the system work now?

`ROADMAP.md`:

> Where is the product going?

`CURRENT_CYCLE.md`:

> What are we doing now?

`ENGINEERING_PROCESS.md`:

> How does the current engineering team operate?

### Role Context

Loaded when a specialized role runs:

- `.claude/agents/*`

Each role receives only the instructions specific to its responsibility.

### Workflow Context

Loaded when a reusable procedure is invoked:

- `.claude/skills/*`

This prevents recurring procedures from occupying permanent context.

### Reference Context

Loaded only when deeper understanding is useful:

- `docs/company/*`
- future ADRs;
- future historical/reference documentation.

The goal is not minimum context.

The goal is minimum necessary context with deeper information available on demand.

## Repository as Durable Memory

The repository is long-term organizational memory.

Conversation history is temporary working memory.

Different artifacts store different kinds of knowledge:

- architecture docs → current technical truth;
- tests → executable behavioral examples;
- Git → implementation history;
- roadmap → product direction;
- organization roadmap → company direction;
- company manual → AI-engineering reasoning and learning;
- current cycle → active work.

This means a completed conversation does not need to remain alive for the project to remember what matters.

## Prompt Design

Once durable context is strong, prompts should become small.

A normal task prompt should usually contain only:

- goal;
- task-specific scope;
- unusual constraints;
- success criteria.

A useful editing question is:

> Can the agent already obtain this reliably from the repository?

If yes, the information usually should not be repeated in the prompt.

## Agents

An Agent is a bounded AI role.

A useful Agent definition answers:

- what does this role own?
- what may it modify?
- what decisions may it make?
- what must it escalate?
- what evidence must it return?

An Agent is not merely a personality.

Do not create an Agent just to simulate a company organization chart.

Create one when a distinct responsibility, context, permission boundary, or independent perspective creates real value.

## Skills

A Skill is a reusable procedure.

Use a Skill when a workflow:

- repeats;
- benefits from a stable procedure;
- may still require some AI judgment.

The first Go! Poker Skill is `/finish-cycle`.

It exists because Cycle closeout is a recurring operation with a stable contract.

## Hooks

A Hook is automatic event-driven behavior.

Mental model:

    event happens
    → automatic behavior runs

Hooks are useful when:

- the trigger is clear;
- the behavior should reliably happen every time;
- the work requires little or no judgment;
- automation is better than expecting an Agent to remember the action.

Go! Poker currently uses no Hooks.

That is intentional.

A capability should be added because it solves a real problem, not because the platform supports it.

## Scripts

Scripts perform deterministic work.

They are useful when an AI should not spend reasoning or context on a repeatable mechanical operation.

A useful pattern may eventually become:

    Skill
    → AI makes judgment calls
    → deterministic script performs mechanics
    → AI evaluates the result

Do not create scripts until repetition or reliability justifies them.

## Architecture Decision Records

`ARCHITECTURE.md` answers:

> What is true now?

An ADR answers:

> Why was an important durable decision made this way?

ADRs are useful when future engineers are likely to need the reasoning behind a consequential decision.

Examples may include:

- public contracts;
- persistent data models;
- cross-team interfaces;
- important external dependencies;
- subsystem ownership boundaries.

Do not create ADRs for ordinary implementation choices.

The operational ADR rules live in `ENGINEERING_PROCESS.md`. A useful template:

    # NNNN: Title

    Status: Accepted (YYYY-MM-DD) | Superseded by NNNN

    ## Context

    ## Decision

    ## Alternatives considered

    ## Consequences

Accepted ADRs are historical records. A changed decision gets a new ADR that supersedes the old one, and both say so.

## Model Routing

Models are compute resources, not employee identities.

Use stronger reasoning where judgment creates leverage and cheaper execution where the task has already been constrained.

Current strategy:

    architecture / difficult planning
    → Opus xhigh

    normal Cycle Lead
    → opusplan high

    Engineer
    → Sonnet high

    QA
    → Sonnet high

    Reviewer
    → Opus high

    mechanical work
    → Sonnet or Haiku medium

### The Trade-Off

Using Sonnet instead of Opus for execution is a real local capability trade-off.

The goal is not to pretend all models are equally capable.

The organization protects final quality through:

- clear specifications;
- strong tests;
- independent QA;
- independent review;
- escalation.

Routing defaults are therefore not ceilings.

If a cheaper model creates repeated misunderstanding or repair loops, escalation may be both better and cheaper overall.

Measure total completion cost rather than token count alone.

### Routing Depends on Configuration

Per-agent `model` frontmatter only works if nothing overrides it. `CLAUDE_CODE_SUBAGENT_MODEL_FORCE` makes subagents ignore their per-agent `model` setting, which silently defeats per-role routing. When routing matters, check the models agents actually run with `/tasks` rather than assuming the configuration took effect.

## Evaluation Engineering

Evaluation engineering is the design of objective mechanisms that show whether AI-produced work is correct.

Current Go! Poker examples include:

- unit tests;
- integration tests;
- invariants;
- deterministic randomized stress tests;
- isolated mutation experiments;
- Ruff;
- mypy;
- CI.

Possible future mechanisms include:

- property-based testing;
- contract testing;
- end-to-end testing;
- golden datasets;
- benchmarks;
- performance regression testing;
- security validation.

Principle:

> Better objective feedback enables safer autonomy.

## Why Tests Matter to AI Autonomy

Tests are not only product protection.

They are feedback channels for AI agents.

A constrained implementation model becomes much safer when:

    specification is clear
    + tests are strong
    + QA is independent
    + review is independent

Weak evaluation increases the capability required from every individual agent and increases human inspection.

## Development QA vs Product Automation

These are different responsibilities.

### Development QA

Works inside a development Cycle.

It validates the specific feature or change being delivered.

### Product Automation

Validates the assembled product across real product-facing interfaces and subsystem boundaries.

A dedicated Automation Engineering Team is planned only after a usable client surface exists.

Its future design belongs in `ORGANIZATION_ROADMAP.md`.

## Session Lifecycle

A session is temporary compute context.

A normal lifecycle is:

    fresh session
    → recover durable state from repository
    → complete one coherent unit of work
    → user approves commit
    → /finish-cycle
    → SESSION COMPLETE
    → close session

Use `/compact` when continuing the same unfinished task.

Start fresh when moving to a new coherent unit of work.

The project should not rely on long-lived conversations as permanent memory.

## Control Plane vs Product Plane

Feature work changes the product.

Meta work changes the AI engineering system itself.

Control-plane files include:

- `CLAUDE.md`;
- `AGENTS.md`;
- `ENGINEERING_PROCESS.md`;
- `.claude/agents/`;
- `.claude/skills/`;
- future Hooks/config.

Separating Meta work from feature work prevents an implementation agent from casually rewriting the rules that govern its own behavior.

## Organization Growth

Future organization design is documented separately in `ORGANIZATION_ROADMAP.md`.

This separation is deliberate.

Product work should not automatically load speculative information about future teams.

The company grows only when the product creates real ownership boundaries.

## AI Company Starter Kit

The final Starter Kit should not simply copy the Go! Poker repository.

It should extract reusable patterns and decision frameworks from actual project experience.

Likely runtime components include:

- entry-context templates;
- architecture/context templates;
- Agent templates;
- Skill patterns;
- Hook/script patterns when proven useful.

Likely learning material includes:

- context engineering;
- Agent design;
- Skill design;
- Hooks;
- model routing;
- evaluation engineering;
- team design;
- multi-team contracts;
- real examples from Go! Poker.

The value of the Kit is not the files themselves.

The value is understanding when to use each pattern and when not to.

## Learning Progression

### Level 1 — AI Pair Programmer

Human decides, AI writes, human inspects.

Completed.

### Level 2 — Autonomous Engineering Cycle

Human approves important boundaries.

The AI team implements, tests, reviews, and verifies inside those boundaries.

Current capability.

### Level 3 — Bootstrap a Project From Zero

Learn to create requirements, architecture, repository context, Agents, evaluation, and milestones from an empty repository.

### Level 4 — Team Design

Learn when separate roles create meaningful separation of responsibility.

### Level 5 — Context Engineering

Design durable memory and progressive disclosure.

An established practice in this project that continues to evolve as the product and organization grow.

### Level 6 — Evaluation Engineering

Increase objective feedback and safe autonomy.

Already partially practiced through tests, invariants, stress testing, and mutation experiments.

### Level 7 — Multi-Team Organization

Introduce independently owned teams and explicit cross-team contracts.

### Level 8 — Cross-Team Features

Coordinate work spanning multiple teams.

### Level 9 — Extract the Starter Kit

Extract reusable patterns only after enough real experience exists.

### Final Exercise

Bootstrap a new unrelated software project from zero.

The user should design:

- requirements;
- architecture;
- repository context;
- organization;
- Agents;
- workflows;
- evaluation;
- milestones.

The AI should audit and challenge that design rather than generating the whole organization automatically.

## Current Lessons Learned

### Giant Prompts Do Not Scale

Long prompts were useful while important knowledge was still implicit.

Once that knowledge became durable repository context, repeating it became unnecessary overhead.

The solution is not merely shorter prompts.

The solution is:

    good durable context
    + progressive disclosure
    + short task-specific prompts

### More Context Is Not Always Better

Irrelevant context consumes tokens and attention and can introduce conflicts.

Useful information should remain available without always being loaded.

### Strong Models Should Be Used Where They Create Leverage

Using Opus everywhere is expensive.

Using cheaper models everywhere can create hidden rework.

Routing is an optimization problem, not a fixed ideology.

### Independent Feedback Creates Information

Engineer, QA, and Reviewer remain separate because they attack different failure modes.

Independence matters only while it produces meaningful additional evidence.

### Git and Tests Are Organizational Memory

Git preserves what changed.

Tests preserve executable examples of what must remain true.

Markdown should not duplicate either without a durable reason.

## Glossary

### Agent

A bounded AI role with responsibility, permissions, authority, context, and an output contract.

### Skill

A reusable AI-driven procedure.

### Hook

Automatic behavior triggered by a defined event.

### Script

Deterministic executable automation.

### ADR

Architecture Decision Record: a durable explanation of why an important architecture decision was made.

### Context Engineering

Designing what information an AI receives, when, from where, and for how long.

### Evaluation Engineering

Designing objective mechanisms that determine whether AI-produced work is correct.

### Cycle

One independently completable implementation unit inside an approved milestone.

### Milestone

A meaningful product capability generally delivered through multiple Cycles.

### Gate

An independent validation or review stage required before work progresses.

### Escalation

Returning a decision to a higher-authority role because it exceeds the current role's approved boundary.

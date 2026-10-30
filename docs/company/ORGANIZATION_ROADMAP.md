# AI Organization Roadmap

This document tracks possible future growth of the AI engineering organization around Go! Poker.

It is planning/reference context, not part of normal feature execution.

Teams and roles are created only when the product creates a real independently ownable responsibility.

## Current Organization

    Product / Architecture Owner
                │
       Core Engineering Lead
                │
       ┌────────┼────────┐
       │        │        │
    Engineer   QA    Reviewer

One Core Engineering Team currently owns the poker engine.

## Growth Principle

Do not create organizational complexity in advance.

A new team should exist when:

- it owns a meaningful subsystem or cross-product responsibility;
- that responsibility can evolve independently;
- separate context, skills, or tooling improve execution;
- coordination through an explicit contract becomes better than one team owning everything.

A new role should exist only when it adds a distinct responsibility or independent perspective.

## Core Maturity Checkpoint

After the complete Texas Hold'em hand engine exists, review whether Core responsibilities and interfaces are stable enough for downstream teams to depend on them.

This is an organization-design checkpoint, not an automatic team split.

## Platform / Backend Team

Create a dedicated Platform / Backend team when persistence, accounts, APIs, or realtime services become substantial product work.

Possible ownership includes:

- persistence;
- accounts and authentication;
- backend APIs;
- realtime sessions;
- multiplayer transport;
- reconnect behavior;
- service-level state;
- integration with the Core engine.

Core remains the owner of poker-domain rules.

This stage introduces an important AI-engineering problem:

**cross-team contracts.**

## Web/Desktop Team

Create a Web/Desktop team when a real browser client becomes active product work.

The Web/Desktop team owns browser and desktop presentation and client behavior.

It consumes platform and engine contracts rather than recreating poker rules.

## Mobile Team

Create a dedicated Mobile team when mobile development becomes substantial enough to justify independent ownership.

Its architecture and tooling should be chosen from the product requirements that exist at that time rather than assumed in advance.

## Automation Engineering Team

Create a dedicated Automation Engineering Team once at least one usable client surface exists — Web or Mobile — and meaningful integrated product flows can be exercised.

This team is different from development QA inside individual engineering teams.

### Development QA

Development QA validates work inside a development Cycle.

Typical question:

> Does this implementation satisfy its approved behavior, boundaries, and invariants?

### Automation Engineering

Automation Engineering validates the assembled product through real product-facing interfaces and subsystem boundaries.

Typical question:

> Does the integrated product work correctly from the outside?

Possible ownership includes:

- API automation;
- backend integration;
- contract testing;
- realtime/multiplayer flows;
- browser automation;
- mobile automation;
- end-to-end user journeys;
- cross-client scenarios;
- reconnect/recovery scenarios;
- regression suites;
- test environments;
- test data;
- automation infrastructure;
- CI execution and reporting;
- automation reliability.

Automation should use public and product-facing interfaces whenever practical rather than reaching into internal implementation details merely to make testing easier.

### Why This Team Matters

It provides an independent cross-product quality function.

Conceptually:

    Core ───────┐
    Platform ───┤
    Web ────────┼──→ Automation Engineering
    Mobile ─────┘       validates the integrated product

It also creates a practical environment for learning and reusing AI-assisted Automation/SDET workflows.

Possible future roles may include:

- Automation Engineering Lead;
- Automation Engineer;
- API/Integration specialist;
- Web E2E specialist;
- Mobile Automation specialist;
- Test Infrastructure specialist;
- Performance/Load specialist.

These are possibilities, not planned positions.

Create them only when real workload creates distinct ownership.

## Simulation / Bots

Bots and simulation may eventually justify independent ownership if they become a substantial evolving subsystem.

Do not create a Simulation team merely because simulation exists.

## Data / Analytics

A Data/Analytics team may become useful once structured history, statistics, and analytical pipelines become substantial product capabilities.

## AI / Coaching

An AI-focused team may become useful once reliable history, simulation, and analytics provide a stable data foundation.

## Infrastructure / Release / Observability

Dedicated ownership may become useful when deployments, environments, production reliability, release management, or observability become substantial work.

## Multi-Team Learning Goals

As the organization grows, the project should deliberately learn:

- ownership boundaries;
- team-specific context;
- cross-team contracts;
- dependency management;
- parallel execution;
- integration validation;
- handoffs between teams;
- release coordination;
- when organizational complexity is not worth its cost.

The final AI Company Starter Kit should extract these as reusable decision patterns rather than reproducing the Go! Poker organization blindly.

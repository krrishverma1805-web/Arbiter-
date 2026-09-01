# Arbiter — Documentation

This folder is the product's thinking, written down. It is part of the deliverable.

| # | Doc | What it answers |
|---|---|---|
| 01 | [Market & Thesis](01-market-and-thesis.md) | Why build this, why now, which finance-ops loop, backed by sources |
| 02 | [Product Specification](02-product-spec.md) | What Arbiter is, what's in the box and why each thing, how it works end to end, who it's for, what it deliberately doesn't do |
| 03 | [Competitive Landscape](03-competitive-landscape.md) | Every serious competitor, their strengths/weaknesses, the feature matrix, and Arbiter's defensible wedge |
| 04 | [Technical Architecture](04-technical-architecture.md) | Principles, system diagram, the deterministic/AI boundary, data model, recon spec, matching algorithm, agent implementation, tech choices with rationale, known gaps |
| 05 | [Design Doctrine](05-design-doctrine.md) | The cockpit: design thesis, the three surfaces, the visual system, interaction rules, accessibility, what "next-gen" actually means here |
| 06 | [Feature Inventory](06-feature-inventory.md) | Every feature (A–M), its job, why it exists, its priority (P0/P1/P2) |
| 07 | [Evaluation & Benchmark](07-evaluation-and-benchmark.md) | The ground-truth dataset, the anomaly catalog, exact metric definitions, the scorecard artifact, the anti-cherry-pick guarantees, and this methodology's own limitations |
| 08 | [Why It Might Not Sell](08-why-it-might-not-sell.md) | The internal red-team — 12 rated risks, honest mitigations, and the repositioning that makes it sellable |
| 09 | [Open Strategic Questions](09-open-strategic-questions.md) | The 10 decisions that are yours, each with a recommendation and reasoning |
| 10 | [Implementation Plan](10-implementation-plan.md) | Build philosophy, the judging-criteria map, milestones M0–M5, priority bands, plan risks, the submission checklist |

### Architecture Decision Records — [`adr/`](adr/)

| ADR | Decision |
|---|---|
| [0001](adr/0001-deterministic-core-ai-at-the-boundary.md) | Deterministic core, AI only at the ambiguity boundary |
| [0002](adr/0002-event-sourced-store.md) | Event-sourced, append-only store with hash chaining |
| [0003](adr/0003-recon-spec-as-data.md) | Reconciliation logic is a declarative spec, not code |

### Also

- [`BUILD-LOG.md`](BUILD-LOG.md) — running, honest account of what broke during the build and how it was fixed (the "Failure Recovery" criterion)

### Reading paths

- **Judge / reviewer, 10 minutes:** README → 02 → 07 → 04 §1–3
- **"Is this a real business?":** 01 → 03 → 08 → 09
- **"Can this person engineer?":** 04 → 07 → 10 → `adr/`
- **Building it:** 10 → 06 → 04 → 05 → the spec files in [`../specs/`](../specs/)

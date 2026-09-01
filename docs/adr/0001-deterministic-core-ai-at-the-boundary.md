# ADR-0001 — Deterministic core, AI only at the ambiguity boundary

- **Status:** Accepted
- **Date:** 2026-09-02
- **Deciders:** Arbiter build

## Context

Arbiter reconciles money. Its output influences (indirectly) financial statements that get signed and audited. The Buildathon's "AI Judgment" criterion explicitly rewards choosing deterministic solutions where AI is unnecessary. The 2026 market context ([docs/01](../01-market-and-thesis.md)) is that verification/trust — not generation — is the bottleneck, and incumbents are framing their entire AI story around a "trust and governance gap."

We must decide where, if anywhere, an LLM sits in the reconciliation pipeline.

## Decision

The pipeline is **deterministic by default**. An LLM is invoked at **exactly one step**: adjudicating exceptions that the deterministic classifier has already tagged `AMBIGUOUS` or `UNEXPLAINED`.

Deterministic (no LLM, ever): ingestion/normalization, deduplication, all matching passes, settlement decomposition arithmetic, confidence scoring, rule-based exception classification, scorecard computation, event replay.

LLM (bounded, proposal-only): for an ambiguous/unexplained exception, produce a `Proposal` — `{category (enum from spec taxonomy), confidence, explanation, evidence_refs[], suggested_action, draft_rule?}`.

Guarantees:
1. No agent tool mutates a match, a record, a ledger entry, or moves money. Tools are read-only or proposal-only.
2. Every proposal is an immutable event, badged in the UI, and requires a human accept/edit/reject before it affects anything.
3. `arbiter run --no-ai` runs the entire pipeline with zero LLM calls and still produces a full scorecard.
4. Model id + prompt hash + evidence bundle hash are recorded on every proposal event.
5. Per-exception token/time budget; on exhaustion the exception is marked `budget-exceeded` and reported on the scorecard.
6. The scorecard **measures AI lift** — category accuracy and resolution usefulness with the LLM vs. `--no-ai` — so the LLM's value is a reported number, not an assumption.

## Consequences

**Positive:**
- Reproducibility and auditability: same inputs + spec + seed → identical events, regardless of model behavior.
- Cost is bounded and reported.
- Directly satisfies the "AI Judgment" criterion and the skeptical-finance-buyer objection ([docs/08](../08-why-it-might-not-sell.md) R5).
- The deterministic core is independently valuable and shippable even if the LLM step is cut.
- Testability: the hard-to-test non-deterministic surface is one small, well-isolated module.

**Negative:**
- Less "wow, the AI does everything" surface area for a demo. Mitigated by measuring and showing real lift.
- The deterministic core must be genuinely excellent — there is no LLM to paper over weak matching logic. (This is arguably also positive.)
- Some valuable AI use cases (autonomous spec evolution, strategy selection) are deferred. Noted as future work.

## Alternatives considered

- **LLM-first matching** (let the model propose matches): rejected — non-deterministic money math, unauditable, expensive, and exactly what the "AI Judgment" criterion warns against.
- **LLM in classification for all exceptions** (not just ambiguous ones): rejected — if a spec rule can classify it deterministically, using the LLM adds cost, latency, and non-determinism for no benefit.
- **No LLM at all:** viable, and it's the `--no-ai` mode. Rejected as the default because variance _explanation_ in natural language genuinely compresses human verification time, which is the core product thesis — but only where a human would otherwise have to investigate manually.

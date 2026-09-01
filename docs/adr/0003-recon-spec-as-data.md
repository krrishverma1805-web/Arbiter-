# ADR-0003 — Reconciliation logic is a declarative spec, not code

- **Status:** Accepted
- **Date:** 2026-09-02

## Context

Arbiter needs to close the settlement-reconciliation loop for the Buildathon, but the same engine should credibly handle bank-to-book and GST-2B matching to show it isn't a one-off. Reconciliation logic also needs to be auditable and, eventually, customer-editable — a controller should be able to see and change "what counts as a match" without a code deploy.

## Decision

A reconciliation is fully described by a **YAML recon spec**: sources + column maps, join keys per pass, tolerance bands, the decomposition identity, confidence weights, thresholds, the exception taxonomy, and deterministic classification/resolution rules. The engine is generic over the spec.

Rule `when` expressions are parsed into a **small safe AST** with a whitelisted operator set (comparisons, `abs`, `exists`, `unmatched`, field access) — never `eval`. This makes customer- and AI-authored rules safe to execute and statically analyzable.

Rules learned from human resolutions ([docs/02](../02-product-spec.md) §5.3) are appended to the spec's `rules:` list with a provenance comment and reviewed as a git-style diff before taking effect.

## Consequences

**Positive:** loop-agnostic engine; logic is diffable and reviewable in version control; the learning loop is just "append a validated rule"; customers can own their rules; two shipped specs (`razorpay-settlement`, `gst-2b`) prove generality cheaply.

**Negative:** a spec DSL is a surface to design and document; a malformed spec can corrupt results (mitigated: strict validation with helpful errors, ADR-required); very unusual reconciliations may not be expressible and need engine changes (acceptable — the common cases drive the design).

## Alternatives considered

- **Hard-coded settlement logic:** fastest to a demo, but no generality story and no path to customer-editable rules.
- **Full scripting (embed Lua/Starlark):** more powerful, but a much larger security and documentation surface than the whitelisted AST, and unnecessary for the rule shapes reconciliation actually needs.

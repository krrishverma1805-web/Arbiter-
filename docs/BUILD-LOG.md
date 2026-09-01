# Build Log

An honest, running account of what broke during development and how it was resolved.
This directly serves the Buildathon's **Failure Recovery** criterion — kept from day one,
not reconstructed at the end.

Format: newest first. Each entry: what broke · how it showed up · root cause · fix · what changed to prevent recurrence.

---

## 2026-09-02 — Repository & research phase

- **Set up:** monorepo plan, full `docs/` research and specification set, three ADRs, reference recon specs.
- **Nothing broken yet** — code begins at milestone M0.
- **Decision captured:** confined the LLM to a single bounded step ([ADR-0001](adr/0001-deterministic-core-ai-at-the-boundary.md)) after weighing an LLM-first matching approach and rejecting it on reproducibility/auditability grounds.

---

<!--
Template for future entries:

## YYYY-MM-DD — <short title>

**Symptom:** what was observed (test failure, wrong number, crash, judge feedback)
**Root cause:** the actual reason
**Fix:** what was changed
**Prevention:** the test / gate / doc added so it can't silently recur
-->

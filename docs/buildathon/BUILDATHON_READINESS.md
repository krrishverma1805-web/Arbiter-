# BUILDATHON READINESS

**Verdict: READY WITH KNOWN LIMITATIONS.**

Arbiter passes every P0 gate in `ARBITER_FINAL_BUILDATHON_SHIP_SPEC.md`. The
limitations that remain are disclosed everywhere and are the *right* limitations
for a pre-customer submission — they are not fixable before the Buildathon
without a customer or a CI secret.

_Assessed 2026-09-04, HEAD after the final ship pass. Full validation:
[`FINAL_VALIDATION.md`](FINAL_VALIDATION.md)._

---

## P0 gate (spec §8, §31) — all pass

### Product
- [x] five-second product comprehension — the hosted-demo overview leads with `93.8% verified · ₹1.73L held · 9 exceptions · 0 unsafe`
- [x] three-minute demo works ([`DEMO.md`](DEMO.md)), deterministic (frozen replay), live gpt-4o trace as the bonus
- [x] exception queue clean · evidence drawer is the "wow" · AI is not the visual hero · keyboard workflow works

### AI
- [x] real investigation trace works · `get_record` works · grounding works · verifier works
- [x] unsupported proposals escalate (demonstrated live)
- [x] cost is honest (never `$0.000`) · model identity correct · calibration model-specific or hidden

### Safety
- [x] Safety Kernel gates every proposal · R5 / money-movement categories cannot return SAFE
- [x] counterfactual check works (positive confirmation, not "no red flag")
- [x] provider failure escalates · prompt injection contained · ghost/unseen citations fail
- [x] Attack Arbiter passes (12 contained · 0 unsafe) · 14 control invariants pass

### Benchmark
- [x] deterministic benchmark passes + regression gate
- [x] agent benchmark passes (99 cases, usefulness/safety scored apart, CI-gated)
- [x] synthetic/live labels explicit everywhere ([`CLAIMS_AUDIT.md`](CLAIMS_AUDIT.md))
- [x] no metric inflated · seed/version recorded · reproduction commands work

### Documentation
- [x] one authoritative status ([`docs/STATUS.md`](../STATUS.md)) · README matches UI matches code
- [x] limitations explicit · claims map to proofs

### Security
- [x] no secrets · no private data · dependency audit passes · injection tests pass

### Demo
- [x] frozen replay works · live trace works when available · fallback works · no core-demo network dependency
- [x] numbers verified · attack demonstration works

---

## Known limitations (spec §25) — disclosed, not hidden

| # | Limitation | Fixable before submission? |
|---|---|---|
| 1 | **No real customer data.** Every accuracy number is synthetic. | No — needs a design partner. |
| 2 | **No full live-model agent benchmark.** Scripted clients bound the harness; one live gpt-4o investigation is captured. The nightly CI step is wired. | Only if the `ANTHROPIC_API_KEY` secret is set. |
| 3 | **Production-scale not load-tested** (500 orgs, 10k runs/day). | No — needs a load-test rig. |
| 4 | A confidently-wrong agent whose wrong category is residual-compatible reaches a green `PROPOSE` ~46% of the time (a human rejects it; nothing auto-applies). | Partially — the live verifier catches more; the number is honest. |
| 5 | OCR for scanned PDFs, live connectors, ERP posting, SOC 2 | No — stated v1 non-goals. |

---

## Why "READY WITH KNOWN LIMITATIONS" and not "READY"

The only thing standing between this and unqualified "READY" is limitation #2 —
a live-model agent benchmark. That is a CI-secret away, not a code task, and the
submission is honest about it. Every other axis (correctness, safety, evidence,
reproducibility, UX, documentation) is green.

## Not ready would mean

A red validation stage, an undisclosed limitation, a claim without a proof, an
unsafe resolution in the red-team, or a demo that needs the network. **None of
those is true.**

## If the API-key secret is added

Set `ANTHROPIC_API_KEY` in the repo secrets → the nightly CI job runs
`arbiter agent-bench --client anthropic --seeds 4`, uploads the result, and
limitation #2 downgrades to "measured, small sample". At that point the verdict
is **READY**.

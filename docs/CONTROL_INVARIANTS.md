# Control Invariants

The 13 properties Arbiter must never violate, each with the executable test that
proves it. Run them all: `pytest packages/engine/tests/test_control_invariants.py`.

| # | Invariant | Test | Where it lives |
|---|-----------|------|----------------|
| 1 | No LLM call can mutate money, a match, a record, or the ledger | `test_agent_tools_are_all_read_only` | `agent/tools.py` — the tool surface holds only read methods; the test runs every one and asserts the snapshot is byte-identical |
| 2 | No proposal can bypass the Safety Kernel | `test_every_proposal_passes_through_the_kernel` | `agent/investigator._finalize_proposal` always calls `kernel.evaluate`; the `Decision` is on every `AGENT_PROPOSAL_CREATED` event |
| 3 | Every proposal carries at least one evidence reference | `test_a_proposal_without_evidence_is_invalid` | `agent/schemas.Proposal.evidence_refs` has `min_length=1` |
| 4 | Every evidence reference must resolve to a real record/decomp/match | `test_a_fabricated_citation_escalates` | `agent/grounding.check_grounding` → `fabricated` → kernel escalates `contradictory` |
| 5 | Financial arithmetic uses exact integer minor units, never float | `test_money_math_is_integer_only` | `money.py` — `to_minor` / `format_minor`; `Decimal` in, `int` out |
| 6 | Risk tier R5 (control breach) never returns SAFE | `test_r5_control_category_never_returns_safe` | `kernel.evaluate` step 6 |
| 7 | A money-movement / dispute category never returns SAFE | `test_never_safe_categories_never_return_safe` | `kernel.evaluate` step 6b + `policy.never_safe_categories` |
| 8 | An unparseable / verdict-less verifier response escalates (fail-closed) | `test_a_broken_verifier_response_escalates` | `agent/investigator._verify` returns `(False, …)` on a parse failure |
| 9 | A provider outage escalates the affected exception, it does not sink the run | `test_provider_failure_escalates_not_crashes` | `agent/orchestrate` wraps the call; escalation reason `provider_unavailable` |
| 10 | Prompt-injected record content cannot control the agent | `test_injection_content_is_quarantined_and_fenced` | `exceptions/injection.py` routes to SECURITY_REVIEW (bypasses the agent); `agent/fencing` wraps anything that does reach it |
| 11 | A closed exception (`resolved` / `wont_fix`) is terminal | `test_a_closed_exception_cannot_transition` | `exceptions/state.py` — `TERMINAL`; API returns 409 |
| 12 | Replay reproduces the terminal hash byte-for-byte | `test_replay_reproduces_the_terminal_hash` | `replay.py` + `events/store.verify` |
| 13 | AI can be disabled without disabling reconciliation; a human confirms every proposal | `test_no_ai_preserves_a_complete_reconciliation` | `run.py` — `--no-ai` skips INVESTIGATING; the scorecard still computes. Nothing in the engine or API auto-applies a `SAFE` decision — `grep -rn '"SAFE"' packages/` shows the only reader is the scorecard metric |

## The one that matters most

**Invariant 13, second half — Arbiter never auto-resolves.** A `Decision.action`
of `SAFE` is advisory: it tells the cockpit "the checks all passed, this is
likely fine to accept," but a human still clicks. There is no code path,
anywhere in the engine or the API, that applies a proposal without a
`RESOLUTION_APPLIED` event whose `actor` is a human. `unsafe_resolution_rate` in
the benchmark measures *how often the SAFE gate would have been wrong* — a
trust check on the gate itself, not a description of an auto-apply that doesn't
exist.

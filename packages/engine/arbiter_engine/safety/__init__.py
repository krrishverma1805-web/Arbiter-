"""The Safety Kernel — the single deterministic gate every agent proposal passes.

`ENGINEERING_AUDIT.md` G1/G2/G3: the checks that decide whether an AI proposal is
safe to present, needs a caveat, or must be escalated used to be scattered across
`grounding.py`, `investigator._finalize_proposal` and `orchestrate`. They now live
here, behind one call:

    kernel.evaluate(proposal, tools, grounding, policy, verifier_result) -> Decision

The kernel is pure (no LLM, no DB, no clock). It runs, in order:

    schema (already enforced) -> grounding -> counterfactual arithmetic ->
    risk tier (R0..R5) -> policy thresholds -> Decision

`Decision.action` is one of SAFE / PROPOSE / ESCALATE / QUARANTINE, with the risk
tier (R0–R5) and machine-readable reason codes. It is persisted in the `decision`
field of the AGENT_PROPOSAL_CREATED / AGENT_ESCALATED event, so a run's gating is
auditable and replayable.
"""

from arbiter_engine.safety.kernel import Decision, evaluate
from arbiter_engine.safety.policy import POLICY_VERSION, Policy
from arbiter_engine.safety.risk import RiskTier, assess_risk

__all__ = [
    "Decision",
    "Policy",
    "POLICY_VERSION",
    "RiskTier",
    "assess_risk",
    "evaluate",
]

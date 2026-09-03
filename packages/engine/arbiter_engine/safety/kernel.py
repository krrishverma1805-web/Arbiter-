"""The Safety Kernel gate (ENGINEERING_AUDIT.md G1, spec §8).

`evaluate()` is the single deterministic decision point for every agent proposal.
It preserves the behaviour the scattered checks had before — a fabricated
citation or a below-floor grounded confidence still escalates — and adds two
fail-closed checks the spec asks for (§13, §92): a deterministic counterfactual
arithmetic check, and a rule that material money (risk R4+) needs a *confident*
conclusion, not merely a plausible one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from arbiter_engine.safety import counterfactual
from arbiter_engine.safety.policy import Policy
from arbiter_engine.safety.risk import RiskTier, assess_risk

if TYPE_CHECKING:
    from arbiter_engine.agent.grounding import GroundingReport
    from arbiter_engine.agent.schemas import Proposal

Action = Literal["SAFE", "PROPOSE", "ESCALATE", "QUARANTINE"]


@dataclass
class Decision:
    action: Action
    risk: RiskTier
    reasons: list[str] = field(default_factory=list)
    # set when action == ESCALATE — maps to Escalate.reason
    escalation_reason: str | None = None
    detail: str = ""
    grounded_confidence: float = 0.0
    policy_version: str = ""

    @property
    def escalated(self) -> bool:
        return self.action in ("ESCALATE", "QUARANTINE")

    def as_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "risk": self.risk.code,
            "risk_label": self.risk.label,
            "reasons": list(self.reasons),
            "escalation_reason": self.escalation_reason,
            "detail": self.detail,
            "grounded_confidence": round(self.grounded_confidence, 4),
            "policy_version": self.policy_version,
        }


def evaluate(
    proposal: Proposal,
    exc: Any,
    snap: Any,
    grounding: GroundingReport,
    policy: Policy,
    *,
    verifier_result: tuple[bool, str] | None = None,
) -> Decision:
    gc = grounding.grounded_confidence
    tier, risk_reasons = assess_risk(exc, proposal, grounding, policy)
    d = Decision(
        action="PROPOSE",
        risk=tier,
        reasons=list(risk_reasons),
        grounded_confidence=gc,
        policy_version=policy.version,
    )

    def esc(reason: str, detail: str) -> Decision:
        d.action = "ESCALATE"
        d.escalation_reason = reason
        d.detail = detail
        d.reasons.append(reason)
        return d

    # 1. grounding — a fabricated citation is a control breach, not a soft fail
    if grounding.fabricated:
        return esc(
            "contradictory",
            "the proposal cited record(s) that do not exist in this run: "
            + ", ".join(grounding.fabricated[:3]),
        )

    # 2. the grounded confidence is below the escalation floor
    if gc < policy.theta_escalate:
        return esc(
            "evidence_exhausted",
            grounding.category_note
            or "the cited evidence does not support the conclusion strongly enough",
        )

    # 3. deterministic counterfactual — does the arithmetic actually fit the hypothesis?
    cf_ok, cf_note = counterfactual.check(proposal, exc, snap)
    if not cf_ok:
        return esc("counterfactual_contradicted", cf_note)
    if cf_note:
        d.reasons.append("counterfactual_ok")

    # 4. the 2nd-model verifier (when it ran)
    if verifier_result is not None and not verifier_result[0]:
        return esc("verifier_rejected", verifier_result[1])

    # 5. material money needs a confident conclusion, not just a plausible one
    if (
        policy.escalate_material_below_conclude
        and tier >= RiskTier.R4_MATERIAL
        and gc < policy.theta_conclude
    ):
        return esc(
            "material_risk",
            f"{tier.code} ({tier.label}) exception at grounded confidence "
            f"{gc:.2f} < {policy.theta_conclude:.2f} — a human should confirm this",
        )

    # 6. a control category never auto-presents as SAFE
    if tier >= RiskTier.R5_CONTROL_BREACH:
        d.action = "PROPOSE"
        d.detail = "control-sensitive — presented with a caveat, human confirmation required"
        return d

    # 7. safe iff low risk, high confidence, category matches the evidence
    if (
        tier <= RiskTier.R2_LOW_RISK_PROPOSAL
        and gc >= policy.theta_conclude
        and grounding.category_consistent
    ):
        d.action = "SAFE"
        d.detail = "grounded, low-risk, category consistent"
    else:
        d.action = "PROPOSE"
        d.detail = d.detail or "presented for review"
    return d

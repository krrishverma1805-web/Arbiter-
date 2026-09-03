"""Deterministic financial risk tiers R0–R5 (ENGINEERING_AUDIT.md G2, spec §7).

Risk is NOT the model's confidence. It is computed from observable financial
signals: category, ₹ impact, evidence coverage, candidate uniqueness, and whether
the proposed category is consistent with the evidence shape. `assess_risk`
returns the single highest tier that applies.
"""

from __future__ import annotations

from enum import IntEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from arbiter_engine.agent.grounding import GroundingReport
    from arbiter_engine.agent.schemas import Proposal
    from arbiter_engine.safety.policy import Policy


class RiskTier(IntEnum):
    R0_INFORMATIONAL = 0
    R1_SAFE_CLASSIFICATION = 1
    R2_LOW_RISK_PROPOSAL = 2
    R3_AMBIGUOUS = 3
    R4_MATERIAL = 4
    R5_CONTROL_BREACH = 5

    @property
    def code(self) -> str:
        return self.name.split("_", 1)[0]  # "R4"

    @property
    def label(self) -> str:
        return self.name.split("_", 1)[1].replace("_", " ").lower()


def assess_risk(
    exc: Any,
    proposal: Proposal,
    grounding: GroundingReport,
    policy: Policy,
) -> tuple[RiskTier, list[str]]:
    """Return (tier, reason_codes). The tier is the max of every rule that fires."""
    impact = abs(int(getattr(exc, "amount_impact_minor", 0) or 0))
    category = str(proposal.category)
    candidates = list(getattr(exc, "candidates", []) or [])
    reasons: list[str] = []
    tier = RiskTier.R2_LOW_RISK_PROPOSAL  # a grounded agent proposal starts here

    # R0 — a trivial, self-evidently-safe residual
    if category == "ROUNDING" and impact <= int(policy.tolerances.get("rounding", 100)):
        return RiskTier.R0_INFORMATIONAL, ["within_rounding_tolerance"]

    # R1 — small, cleanly-shaped classification
    if impact < policy.verify_above_minor and grounding.category_consistent:
        tier = RiskTier.R1_SAFE_CLASSIFICATION

    # R3 — genuine ambiguity
    if len(candidates) >= 2:
        tier = max(tier, RiskTier.R3_AMBIGUOUS)
        reasons.append("multiple_candidates")
    if not grounding.category_consistent:
        tier = max(tier, RiskTier.R3_AMBIGUOUS)
        reasons.append("category_evidence_mismatch")
    if policy.theta_escalate <= grounding.grounded_confidence < policy.theta_conclude:
        tier = max(tier, RiskTier.R3_AMBIGUOUS)
        reasons.append("confidence_in_uncertain_band")

    # R4 — material financial impact
    if impact >= policy.material_minor:
        tier = max(tier, RiskTier.R4_MATERIAL)
        reasons.append("material_impact")
    if category == "UNEXPLAINED" and impact >= policy.verify_above_minor:
        tier = max(tier, RiskTier.R4_MATERIAL)
        reasons.append("unexplained_with_material_money")

    # R5 — control / security concern
    if category in policy.control_categories:
        tier = max(tier, RiskTier.R5_CONTROL_BREACH)
        reasons.append(f"control_category:{category}")
    if grounding.fabricated:
        tier = max(tier, RiskTier.R5_CONTROL_BREACH)
        reasons.append("fabricated_citation")

    return tier, reasons

"""Versioned, deterministic gating policy (ENGINEERING_AUDIT.md G2, spec §7/§8).

Everything the Safety Kernel needs to make a decision, loaded from the recon
spec's `adjudication:` block so it is git-diffable and per-tenant tunable. The
version string is recorded on every gated decision so a financial decision is
auditable against the exact policy that produced it (spec §56).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

POLICY_VERSION = "safety-policy-v1"

# ₹ impact at or above which an exception is "material" (risk tier R4) — a
# material proposal needs a confident, verified conclusion or it is escalated.
_DEFAULT_MATERIAL_MINOR = 5_000_00  # ₹5,000

# categories that are inherently a control/security concern (risk tier R5) —
# a proposal touching one of these is never presented without a human.
_DEFAULT_CONTROL_CATEGORIES = ("SECURITY_REVIEW", "WRONG_ACCOUNT")

# categories that always need a human sign-off even with a confident, grounded,
# arithmetic-confirmed proposal — they are money-movement or dispute decisions,
# not classifications. The kernel will PROPOSE them but never mark them SAFE.
_DEFAULT_NEVER_SAFE_CATEGORIES = (
    "DUPLICATE",
    "CHARGEBACK",
    "PARTIAL_PAYMENT",
    "WRONG_ACCOUNT",
    "MISSING_UTR",
    "UNEXPLAINED",
    "SECURITY_REVIEW",
)


@dataclass(frozen=True)
class Policy:
    version: str = POLICY_VERSION
    # from adjudication.stopping
    theta_conclude: float = 0.80  # grounded confidence at/above which a proposal can be "SAFE"
    theta_escalate: float = 0.55  # grounded confidence below which a proposal is escalated
    # from adjudication
    verify_above_minor: int = 100_00  # ≥ this ₹ impact → the 2nd-model verifier runs
    # from adjudication.risk (new)
    material_minor: int = _DEFAULT_MATERIAL_MINOR
    control_categories: tuple[str, ...] = _DEFAULT_CONTROL_CATEGORIES
    never_safe_categories: tuple[str, ...] = _DEFAULT_NEVER_SAFE_CATEGORIES
    # a proposal at risk R4+ must clear theta_conclude, not just theta_escalate
    escalate_material_below_conclude: bool = True
    tolerances: dict[str, int] = field(default_factory=dict)  # e.g. {"rounding": 100}

    @classmethod
    def from_spec(cls, spec: Any) -> Policy:
        adj = dict(getattr(spec, "adjudication", {}) or {})
        stopping = dict(adj.get("stopping", {}) or {})
        risk = dict(adj.get("risk", {}) or {})
        ident = dict(getattr(spec, "identity", {}) or {})
        tol = dict(risk.get("tolerances", {}) or {})
        tol.setdefault("rounding", int(ident.get("rounding_tolerance_minor", 100)))
        return cls(
            version=str(risk.get("version", POLICY_VERSION)),
            theta_conclude=float(stopping.get("theta_conclude", 0.80)),
            theta_escalate=float(stopping.get("theta_escalate", 0.55)),
            verify_above_minor=int(adj.get("verify_above_minor", 100_00)),
            material_minor=int(risk.get("material_minor", _DEFAULT_MATERIAL_MINOR)),
            control_categories=tuple(risk.get("control_categories", _DEFAULT_CONTROL_CATEGORIES)),
            never_safe_categories=tuple(
                risk.get("never_safe_categories", _DEFAULT_NEVER_SAFE_CATEGORIES)
            ),
            escalate_material_below_conclude=bool(
                risk.get("escalate_material_below_conclude", True)
            ),
            tolerances=tol,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "theta_conclude": self.theta_conclude,
            "theta_escalate": self.theta_escalate,
            "verify_above_minor": self.verify_above_minor,
            "material_minor": self.material_minor,
            "control_categories": list(self.control_categories),
            "never_safe_categories": list(self.never_safe_categories),
            "escalate_material_below_conclude": self.escalate_material_below_conclude,
        }

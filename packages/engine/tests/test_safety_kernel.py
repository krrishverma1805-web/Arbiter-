"""The Safety Kernel — the deterministic gate every agent proposal passes.

Covers policy loading, the R0–R5 risk tiers, the counterfactual arithmetic
checks, and the kernel's decision paths (ENGINEERING_AUDIT.md G1–G3, spec §8).
Pure — no LLM, no DB.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from arbiter_engine.agent.grounding import GroundingReport
from arbiter_engine.agent.schemas import EvidenceRef, Proposal, SuggestedAction
from arbiter_engine.safety import counterfactual, kernel
from arbiter_engine.safety.policy import Policy
from arbiter_engine.safety.risk import RiskTier, assess_risk


# ---- lightweight fakes -----------------------------------------------------
@dataclass
class _Rec:
    id: str
    amount_minor: int = 0
    settled_at: str = ""
    value_date: str = ""
    source: str = "razorpay_recon"
    external_ids: dict[str, str] = field(default_factory=dict)


@dataclass
class _Decomp:
    group_id: str
    residual_minor: int
    components: dict[str, int] = field(default_factory=dict)
    settlement_utr: str = ""
    expected_minor: int = 0


@dataclass
class _Snap:
    records: dict[str, Any] = field(default_factory=dict)
    decompositions: list[Any] = field(default_factory=list)


@dataclass
class _Exc:
    id: str = "exc_1"
    amount_impact_minor: int = 0
    category: str | None = None
    record_ids: list[str] = field(default_factory=list)
    candidates: list[Any] = field(default_factory=list)


def _proposal(category: str, *, conf: float = 0.9, action: str = "accept_variance") -> Proposal:
    return Proposal(
        exception_id="exc_1",
        category=category,  # type: ignore[arg-type]
        confidence=conf,
        explanation="test",
        evidence_refs=[EvidenceRef(claim="c", record_id="r1", field="amount")],
        suggested_action=SuggestedAction(action=action, detail="d"),  # type: ignore[arg-type]
    )


def _grounding(
    *, gc: float = 0.9, fabricated: list[str] | None = None, cat_ok: bool = True
) -> GroundingReport:
    return GroundingReport(
        refs_total=1,
        refs_resolved=1,
        refs_field_ok=1,
        fabricated=fabricated or [],
        category_consistent=cat_ok,
        grounded_confidence=gc,
    )


# ---- policy --------------------------------------------------------------
def test_policy_defaults_and_from_spec_override() -> None:
    p = Policy()
    assert p.theta_conclude == 0.80 and p.theta_escalate == 0.55
    assert p.version == "safety-policy-v1"

    class _Spec:
        adjudication = {
            "verify_above_minor": 25000,
            "stopping": {"theta_conclude": 0.9, "theta_escalate": 0.6},
            "risk": {"material_minor": 200000, "version": "razorpay-risk-v1"},
        }
        identity = {"rounding_tolerance_minor": 100}

    q = Policy.from_spec(_Spec())
    assert q.verify_above_minor == 25000
    assert q.theta_conclude == 0.9
    assert q.material_minor == 200000
    assert q.version == "razorpay-risk-v1"
    assert q.tolerances["rounding"] == 100


# ---- risk tiers --------------------------------------------------------
def test_risk_r0_rounding_within_tolerance() -> None:
    tier, _ = assess_risk(
        _Exc(amount_impact_minor=40), _proposal("ROUNDING"), _grounding(), Policy()
    )
    assert tier is RiskTier.R0_INFORMATIONAL


def test_risk_r4_material_impact() -> None:
    tier, reasons = assess_risk(
        _Exc(amount_impact_minor=800000), _proposal("TIMING"), _grounding(), Policy()
    )
    assert tier >= RiskTier.R4_MATERIAL
    assert "material_impact" in reasons


def test_risk_r5_control_category_and_fabrication() -> None:
    tier, _ = assess_risk(
        _Exc(amount_impact_minor=1000), _proposal("WRONG_ACCOUNT"), _grounding(), Policy()
    )
    assert tier is RiskTier.R5_CONTROL_BREACH
    tier2, _ = assess_risk(
        _Exc(amount_impact_minor=1000),
        _proposal("DUPLICATE"),
        _grounding(fabricated=["ghost"]),
        Policy(),
    )
    assert tier2 is RiskTier.R5_CONTROL_BREACH


def test_risk_r3_multiple_candidates() -> None:
    tier, reasons = assess_risk(
        _Exc(amount_impact_minor=1000, candidates=[1, 2]),
        _proposal("TIMING"),
        _grounding(),
        Policy(),
    )
    assert tier >= RiskTier.R3_AMBIGUOUS
    assert "multiple_candidates" in reasons


# ---- counterfactual ---------------------------------------------------
def test_counterfactual_refund_direction_contradiction() -> None:
    # a chargeback/partial payment withholds money — an OVER settlement contradicts it
    exc = _Exc(amount_impact_minor=5000, record_ids=["r1"])
    snap = _Snap(records={"r1": _Rec("r1")}, decompositions=[_Decomp("r1", residual_minor=5000)])
    ok, note = counterfactual.check(_proposal("CHARGEBACK"), exc, snap)
    assert ok is False and "OVER expected" in note


def test_counterfactual_timing_semantics() -> None:
    # a bank credit and its settlement on different dates, and the money DID land
    # (residual ≈ 0) → a clean timing difference, positively confirmed
    exc = _Exc(amount_impact_minor=0, record_ids=["s1", "b1"])
    snap = _Snap(
        records={
            "s1": _Rec("s1", settled_at="2026-08-06"),
            "b1": _Rec("b1", value_date="2026-09-01", source="bank"),
        }
    )
    ok, note = counterfactual.check(_proposal("TIMING"), exc, snap)
    assert ok is True and note.startswith("confirmed:")

    # different dates but money still outstanding → NOT a clean timing diff
    exc_short = _Exc(amount_impact_minor=-9000, record_ids=["s1", "b1"])
    ok_s, note_s = counterfactual.check(_proposal("TIMING"), exc_short, snap)
    assert ok_s is False and "outstanding" in note_s

    # bank credit and settlement on the SAME date → no spread → contradiction
    snap.records["b1"] = _Rec("b1", value_date="2026-08-06", source="bank")
    ok2, note2 = counterfactual.check(_proposal("TIMING"), exc, snap)
    assert ok2 is False and "same" in note2

    # nothing outstanding, no cross-source gap → contradiction
    exc0 = _Exc(amount_impact_minor=0, record_ids=["s1"])
    snap0 = _Snap(records={"s1": _Rec("s1", settled_at="2026-08-06")})
    ok3, note3 = counterfactual.check(_proposal("TIMING"), exc0, snap0)
    assert ok3 is False and "nothing is outstanding" in note3

    # the FULL expected credit outstanding, same-date settlement lines → a period
    # straddle: confirmed
    exc4 = _Exc(amount_impact_minor=-50_000, record_ids=["r1", "r2"])
    snap4 = _Snap(
        records={
            "r1": _Rec("r1", settled_at="2026-09-01"),
            "r2": _Rec("r2", settled_at="2026-09-01"),
        },
        decompositions=[_Decomp("g", residual_minor=-50_000, expected_minor=50_000)],
    )
    ok4, note4 = counterfactual.check(_proposal("TIMING"), exc4, snap4)
    assert ok4 is True and note4.startswith("confirmed:")

    # only PART of the credit outstanding, no cross-source gap → silent (not SAFE)
    snap4.decompositions = [_Decomp("g", residual_minor=-8_000, expected_minor=50_000)]
    exc4.amount_impact_minor = -8_000
    ok5, note5 = counterfactual.check(_proposal("TIMING"), exc4, snap4)
    assert ok5 is True and note5 == ""


def test_counterfactual_duplicate_needs_repeated_id() -> None:
    exc = _Exc(record_ids=["r1", "r2"])
    snap = _Snap(
        records={
            "r1": _Rec("r1", amount_minor=1000, external_ids={"payment_id": "pay_A"}),
            "r2": _Rec("r2", amount_minor=1000, external_ids={"payment_id": "pay_B"}),
        }
    )
    ok, note = counterfactual.check(_proposal("DUPLICATE"), exc, snap)
    assert ok is False and "no payment_id" in note


def test_counterfactual_silent_for_unmodelled_category() -> None:
    ok, note = counterfactual.check(_proposal("FX_DIFFERENCE"), _Exc(), _Snap())
    assert ok is True and note == ""


# ---- the kernel ------------------------------------------------------
def _snap_for(exc: _Exc, residual: int = 0, gross: int = 0) -> _Snap:
    return _Snap(
        records={i: _Rec(i, settled_at="2026-08-06") for i in exc.record_ids},
        decompositions=[_Decomp(exc.record_ids[0], residual, {"gross": gross})]
        if exc.record_ids
        else [],
    )


def test_kernel_safe_path() -> None:
    exc = _Exc(amount_impact_minor=1000, category="FEE_DEDUCTION", record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("FEE_DEDUCTION"), exc, _snap_for(exc, 300, 100000), _grounding(gc=0.92), Policy()
    )
    assert d.action == "SAFE"
    assert d.risk <= RiskTier.R2_LOW_RISK_PROPOSAL
    assert d.escalated is False


def test_kernel_fabricated_citation_escalates() -> None:
    exc = _Exc(amount_impact_minor=1000, record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("TIMING"), exc, _snap_for(exc), _grounding(fabricated=["ghost"]), Policy()
    )
    assert d.action == "ESCALATE" and d.escalation_reason == "contradictory"


def test_kernel_below_theta_escalate() -> None:
    exc = _Exc(amount_impact_minor=1000, record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("TIMING", conf=0.4), exc, _snap_for(exc), _grounding(gc=0.4), Policy()
    )
    assert d.action == "ESCALATE" and d.escalation_reason == "evidence_exhausted"


def test_kernel_counterfactual_contradiction_escalates() -> None:
    exc = _Exc(amount_impact_minor=5000, category="CHARGEBACK", record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("CHARGEBACK"), exc, _snap_for(exc, residual=5000), _grounding(gc=0.9), Policy()
    )
    assert d.action == "ESCALATE" and d.escalation_reason == "counterfactual_contradicted"


def test_kernel_material_needs_confidence() -> None:
    # a material TIMING straddle (full credit outstanding, CF confirms) but the
    # grounded confidence is only 0.7 → material money needs a confident, not
    # merely plausible, conclusion → escalate
    exc = _Exc(amount_impact_minor=-900000, category="TIMING", record_ids=["r1", "r2"])
    snap = _Snap(
        records={
            "r1": _Rec("r1", settled_at="2026-09-01"),
            "r2": _Rec("r2", settled_at="2026-09-01"),
        },
        decompositions=[_Decomp("g", residual_minor=-900000, expected_minor=900000)],
    )
    d = kernel.evaluate(_proposal("TIMING", conf=0.7), exc, snap, _grounding(gc=0.7), Policy())
    assert d.action == "ESCALATE" and d.escalation_reason == "material_risk"
    assert d.risk >= RiskTier.R4_MATERIAL


def test_kernel_verifier_rejection_escalates() -> None:
    # MISSING_UTR has no counterfactual check, so the verifier verdict is the gate
    exc = _Exc(amount_impact_minor=1000, record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("MISSING_UTR"),
        exc,
        _snap_for(exc),
        _grounding(gc=0.9),
        Policy(),
        verifier_result=(False, "the citation does not support the claim"),
    )
    assert d.action == "ESCALATE" and d.escalation_reason == "verifier_rejected"


def test_kernel_control_category_never_safe() -> None:
    exc = _Exc(amount_impact_minor=1000, category="WRONG_ACCOUNT", record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("WRONG_ACCOUNT"), exc, _snap_for(exc), _grounding(gc=0.95), Policy()
    )
    assert d.action == "PROPOSE"  # presented with a caveat, not SAFE
    assert d.risk is RiskTier.R5_CONTROL_BREACH


def test_kernel_decision_serialises() -> None:
    exc = _Exc(amount_impact_minor=1000, category="FEE_DEDUCTION", record_ids=["r1"])
    d = kernel.evaluate(
        _proposal("FEE_DEDUCTION"), exc, _snap_for(exc, 200, 100000), _grounding(gc=0.92), Policy()
    )
    js = d.as_dict()
    assert (
        js["action"] == "SAFE" and js["risk"] == "R1" and js["policy_version"] == "safety-policy-v1"
    )

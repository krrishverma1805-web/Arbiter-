"""Grounding + category verification for agent proposals (docs/12 §4, docs/28 §1.3).

The agent's `evidence_refs` are self-reported — the model *says* record X's field
Y supports its claim. Before a proposal is trusted:

  1. **Grounding** — every `record_id` in `evidence_refs` must resolve to a real
     record / decomposition / match in this run. A ref that points at nothing is
     a fabrication: the proposal is rejected and the exception escalates.
  2. **Category check** — a deterministic sanity test that the proposed category
     is consistent with the shape of the evidence (a `DUPLICATE` needs a repeated
     payment_id; a `ROUNDING` needs a small residual; …). Zero LLM cost. A
     mismatch downgrades confidence and is surfaced to the human.

`grounded_confidence` is what the cockpit shows and what the escalation threshold
is compared against — never the model's raw self-assessment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arbiter_engine.agent.schemas import Proposal
    from arbiter_engine.agent.tools import RunSnapshot

_RECORD_FIELDS = {
    "amount",
    "amount_minor",
    "fee_minor",
    "tax_minor",
    "value_date",
    "settled_at",
    "posted_date",
    "counterparty",
    "reference",
    "kind",
    "source",
    "currency",
    "external_ids",
    "untrusted",
}
_DERIVED_FIELDS = {
    "residual",
    "residual_minor",
    "components",
    "expected",
    "actual",
    "decomposition",
}


@dataclass
class GroundingReport:
    refs_total: int = 0
    refs_resolved: int = 0
    refs_field_ok: int = 0
    fabricated: list[str] = field(default_factory=list)
    category_consistent: bool = True
    category_note: str = ""
    grounded_confidence: float = 0.0

    @property
    def grounded(self) -> bool:
        return not self.fabricated

    def as_dict(self) -> dict[str, object]:
        return {
            "refs_total": self.refs_total,
            "refs_resolved": self.refs_resolved,
            "refs_field_ok": self.refs_field_ok,
            "fabricated": list(self.fabricated),
            "grounded": self.grounded,
            "category_consistent": self.category_consistent,
            "category_note": self.category_note,
            "grounded_confidence": round(self.grounded_confidence, 4),
        }


def _resolves(record_id: str, snap: RunSnapshot) -> tuple[bool, bool]:
    """(record_id points at something real, the field name is plausible-ready).

    Returns (resolved, is_record). `resolved` covers records, decomposition keys
    (settlement_utr / group_id) and match ids; `is_record` is True only for an
    actual Record (so the field check knows which vocabulary to use).
    """
    if record_id in snap.records:
        return True, True
    for d in snap.decompositions:
        if record_id in (d.settlement_utr, d.group_id):
            return True, False
    for m in snap.matches:
        if record_id == m.id:
            return True, False
    # bare settlement_utr carried on a record's external_ids
    for r in snap.records.values():
        if record_id in r.external_ids.values():
            return True, False
    return False, False


def _field_ok(field_name: str, is_record: bool) -> bool:
    f = (field_name or "").split(".")[0].strip().lower()
    if not f:
        return False
    if is_record:
        return f in _RECORD_FIELDS or f in _DERIVED_FIELDS
    return f in _DERIVED_FIELDS or f in _RECORD_FIELDS


def _category_check(proposal: Proposal, snap: RunSnapshot) -> tuple[bool, str]:
    """Deterministic: is the proposed category consistent with the evidence shape?"""
    cat = proposal.category
    ref_recs = [
        snap.records[r.record_id] for r in proposal.evidence_refs if r.record_id in snap.records
    ]
    exc = next((e for e in snap.exceptions if e.id == proposal.exception_id), None)
    residual = abs(exc.amount_impact_minor) if exc is not None else None

    pay_ids = [
        r.external_ids.get("payment_id") for r in ref_recs if r.external_ids.get("payment_id")
    ]
    has_dispute = any(r.external_ids.get("dispute_id") or r.kind == "chargeback" for r in ref_recs)
    has_utr_gap = any(
        not r.external_ids.get("settlement_utr") and not r.external_ids.get("utr") for r in ref_recs
    )

    if cat == "DUPLICATE" and len(pay_ids) == len(set(pay_ids)):
        return False, "DUPLICATE proposed but no repeated payment_id in the cited records"
    if cat == "ROUNDING" and residual is not None and residual > 500:
        return False, f"ROUNDING proposed but the residual is {residual} minor (> ₹5.00)"
    if cat == "CHARGEBACK" and not has_dispute:
        return False, "CHARGEBACK proposed but no dispute_id / chargeback record cited"
    if cat == "MISSING_UTR" and ref_recs and not has_utr_gap:
        return False, "MISSING_UTR proposed but every cited record has a UTR"
    if cat == "WRONG_ACCOUNT" and not ref_recs:
        return False, "WRONG_ACCOUNT proposed with no records cited"

    # the suggested action must fit the category — an internally inconsistent
    # proposal (right category, wrong fix) is not trustworthy
    action = proposal.suggested_action.action
    allowed = _ACTIONS_FOR.get(cat)
    if allowed is not None and action not in allowed:
        return False, f"{cat} proposed with action '{action}', expected one of {sorted(allowed)}"
    return True, ""


# category -> the resolution actions that are coherent with it
_ACTIONS_FOR: dict[str, set[str]] = {
    "ROUNDING": {"accept_variance", "wont_fix"},
    "SPLIT_SETTLEMENT": {"accept_variance", "carry_forward"},
    "FEE_DEDUCTION": {"flag_overcharge", "raise_dispute", "accept_variance"},
    "TAX_DEDUCTION": {"flag_overcharge", "raise_dispute", "accept_variance"},
    "TIMING": {"carry_forward", "accept_variance"},
    "DUPLICATE": {"void_duplicate_of", "route_to_human"},
    "CHARGEBACK": {"raise_dispute", "route_to_human"},
    "MISSING_UTR": {"request_data", "route_to_human", "attribute_to"},
    "WRONG_ACCOUNT": {"route_to_human", "attribute_to", "request_data"},
    "PARTIAL_PAYMENT": {"route_to_human", "carry_forward", "request_data"},
}


def check_grounding(proposal: Proposal, snap: RunSnapshot) -> GroundingReport:
    rep = GroundingReport(refs_total=len(proposal.evidence_refs))
    for ref in proposal.evidence_refs:
        resolved, is_record = _resolves(ref.record_id, snap)
        if not resolved:
            rep.fabricated.append(ref.record_id)
            continue
        rep.refs_resolved += 1
        if _field_ok(ref.field, is_record):
            rep.refs_field_ok += 1

    rep.category_consistent, rep.category_note = _category_check(proposal, snap)

    total = max(rep.refs_total, 1)
    if rep.fabricated:
        # a fabricated citation caps confidence hard — this is a hallucination
        rep.grounded_confidence = min(proposal.confidence, 0.25) * (rep.refs_resolved / total)
    else:
        field_factor = 0.6 + 0.4 * (rep.refs_field_ok / total)
        rep.grounded_confidence = proposal.confidence * field_factor
    if not rep.category_consistent:
        rep.grounded_confidence = min(rep.grounded_confidence, 0.4)
    rep.grounded_confidence = max(0.0, min(1.0, rep.grounded_confidence))
    return rep

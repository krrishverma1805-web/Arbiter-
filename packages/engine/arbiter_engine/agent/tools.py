"""Read-only / proposal-only tools for the investigation agent (docs/19 §3).

Every tool operates on an immutable snapshot of the run. None of them mutates a
match, a record, a ledger entry, or money — this is the backstop that makes
money-safety independent of model-safety (docs/14 C3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from arbiter_engine.agent.fencing import fence
from arbiter_engine.decompose.identity import decompose_group
from arbiter_engine.models import Decomposition, Match, MatchCandidate, ReconException, Record
from arbiter_engine.money import format_minor


@dataclass
class RunSnapshot:
    records: dict[str, Record]
    matches: list[Match]
    decompositions: list[Decomposition]
    exceptions: list[ReconException]
    candidates: dict[str, list[MatchCandidate]] = field(default_factory=dict)
    prior_counterparties: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    prior_resolutions: list[dict[str, Any]] = field(default_factory=list)
    resolution_memory: Any = None  # ResolutionMemory | None (avoid an import cycle)

    @classmethod
    def from_projection(cls, proj: Any) -> RunSnapshot:
        return cls(
            records={r.id: r for r in proj.records},
            matches=list(proj.matches),
            decompositions=list(proj.decompositions),
            exceptions=list(proj.exceptions),
        )


def _record_view(r: Record, *, redact_account: bool = True) -> dict[str, Any]:
    ext = dict(r.external_ids)
    if redact_account and "account" in ext:
        ext["account"] = "****"
    return {
        "id": r.id,
        "source": r.source,
        "kind": r.kind,
        "amount": format_minor(r.amount_minor),
        "amount_minor": r.amount_minor,
        "fee_minor": r.fee_minor,
        "tax_minor": r.tax_minor,
        "value_date": r.value_date.isoformat() if r.value_date else None,
        "settled_at": r.settled_at.isoformat() if r.settled_at else None,
        "counterparty": r.counterparty,
        "reference": r.reference,
        "external_ids": ext,
        "untrusted": {k: fence(k, r.id, v) for k, v in r.untrusted.items() if v},
    }


class Tools:
    """Bound to one RunSnapshot; the investigator exposes these to the model."""

    def __init__(self, snap: RunSnapshot, exc: ReconException | None = None) -> None:
        self.snap = snap
        self.exc = exc

    # -- read-only ----------------------------------------------------------
    def query_evidence(
        self,
        source: str = "any",
        external_id: str | None = None,
        amount_minor_low: int | None = None,
        amount_minor_high: int | None = None,
        kind: str | None = None,
    ) -> dict[str, Any]:
        out: list[dict[str, Any]] = []
        for r in sorted(self.snap.records.values(), key=lambda x: x.id):
            if source != "any" and r.source != source:
                continue
            if kind and r.kind != kind:
                continue
            if external_id and external_id not in r.external_ids.values():
                continue
            if amount_minor_low is not None and r.amount_minor < amount_minor_low:
                continue
            if amount_minor_high is not None and r.amount_minor > amount_minor_high:
                continue
            out.append(_record_view(r))
            if len(out) >= 40:
                break
        return {"records": out, "count": len(out)}

    def counterparty_history(
        self, counterparty: str | None = None, settlement_account: str | None = None
    ) -> dict[str, Any]:
        from arbiter_engine.match.entity import canonical_entity

        raw = counterparty or settlement_account or ""
        # the map is keyed on the canonical entity, so "ACME PVT LTD" and
        # "Acme Private Limited" resolve to the same prior activity (docs/28 §1.2)
        key = canonical_entity(raw) or raw
        hits = self.snap.prior_counterparties.get(key) or self.snap.prior_counterparties.get(
            raw, []
        )
        return {"resolved_entity": key, "prior_activity": hits}

    def similar_exceptions(
        self, category_hint: str | None = None, pattern: str | None = None
    ) -> dict[str, Any]:
        mem = self.snap.resolution_memory
        network = self._network_resolutions()
        if mem is not None and self.exc is not None:
            recs = [self.snap.records[i] for i in self.exc.record_ids if i in self.snap.records]
            hits = mem.recall(self.exc, recs, k=6)
            if category_hint:
                hits = [h for h in hits if h.category == category_hint] or hits
            out: dict[str, Any] = {
                "resolved_before": [
                    {
                        "category": h.category,
                        "resolution": h.resolution,
                        "similarity": h.similarity,
                        "from_run": h.run_id,
                    }
                    for h in hits
                ],
                "method": "semantic",
            }
            if network:
                out["from_the_network"] = network
            return out
        hits2 = [
            r
            for r in self.snap.prior_resolutions
            if (not category_hint or r.get("category") == category_hint)
        ]
        res: dict[str, Any] = {"resolved_before": hits2[:10], "method": "category_filter"}
        if network:
            res["from_the_network"] = network
        return res

    def _network_resolutions(self) -> list[dict[str, Any]]:
        """Opt-in global pattern library (docs/28 §3 item 15). Empty unless the
        tenant set `ARBITER_GLOBAL_PATTERNS`."""
        if self.exc is None:
            return []
        try:
            from arbiter_engine.learn.global_patterns import recall_global
        except Exception:  # pragma: no cover
            return []
        recs = [self.snap.records[i] for i in self.exc.record_ids if i in self.snap.records]
        return [
            {"resolution": h.action, "other_teams": h.distinct_tenants, "times_seen": h.occurrences}
            for h in recall_global(self.exc, recs)
        ]

    def candidate_matches(self, record_id: str) -> dict[str, Any]:
        cands = self.snap.candidates.get(record_id, [])
        return {
            "candidates": [
                {
                    "hypothesis": c.hypothesis,
                    "record_ids": c.record_ids,
                    "score_bits": c.score_bits,
                    "per_field_weights": c.per_field_weights,
                }
                for c in cands
            ]
        }

    def decomposition_detail(
        self, settlement_utr: str | None = None, group_id: str | None = None
    ) -> dict[str, Any]:
        for d in self.snap.decompositions:
            if (settlement_utr and d.settlement_utr == settlement_utr) or (
                group_id and d.group_id == group_id
            ):
                return {
                    "settlement_utr": d.settlement_utr,
                    "expected": format_minor(d.expected_minor),
                    "actual": format_minor(d.actual_minor),
                    "residual": format_minor(d.residual_minor),
                    "residual_minor": d.residual_minor,
                    "ledger_crosscheck_ok": d.ledger_crosscheck_ok,
                    "components": {k: format_minor(v) for k, v in d.components.items()},
                }
        # not pre-computed — compute on the fly for the utr's records
        if settlement_utr:
            items = [
                r
                for r in self.snap.records.values()
                if r.external_ids.get("settlement_utr") == settlement_utr
            ]
            if items:
                d = decompose_group(
                    "adhoc",
                    settlement_utr,
                    sorted(items, key=lambda r: r.id),
                    bank_amount_minor=None,
                )
                return {
                    "settlement_utr": settlement_utr,
                    "expected": format_minor(d.expected_minor),
                    "components": {k: format_minor(v) for k, v in d.components.items()},
                }
        return {"error": "no decomposition for that key"}


def build_task_message(
    exc: ReconException, snap: RunSnapshot, spec: Any, thresholds: dict[str, float]
) -> str:
    recs = [snap.records[rid] for rid in exc.record_ids if rid in snap.records]
    lines: list[str] = []
    lines.append(f'<exception id="{exc.id}">')
    lines.append(
        f"  <summary>{exc.category or 'UNEXPLAINED'} — impact "
        f"{format_minor(exc.amount_impact_minor)}. The deterministic classifier "
        f"could not resolve this.</summary>"
    )
    lines.append("  <records>")
    for r in recs:
        v = _record_view(r)
        lines.append(f'    <record id="{r.id}" source="{r.source}" kind="{r.kind}">')
        lines.append(
            f"      amount={v['amount']} value_date={v['value_date']} settled_at={v['settled_at']} "
            f"reference={r.reference!r} external_ids={v['external_ids']}"
        )
        for fenced in v["untrusted"].values():
            lines.append(f"      {fenced}")
        lines.append("    </record>")
    lines.append("  </records>")

    utr = next(
        (
            r.external_ids.get("settlement_utr")
            for r in recs
            if r.external_ids.get("settlement_utr")
        ),
        None,
    )
    if utr:
        d = next((d for d in snap.decompositions if d.settlement_utr == utr), None)
        if d:
            lines.append(
                f'  <decomposition settlement_utr="{utr}" '
                f"expected={format_minor(d.expected_minor)} "
                f"actual={format_minor(d.actual_minor)} "
                f"residual={format_minor(d.residual_minor)} "
                f"ledger_crosscheck_ok={d.ledger_crosscheck_ok}/>"
            )
    if exc.candidates:
        lines.append("  <candidates>")
        for c in exc.candidates[:3]:
            lines.append(f'    <candidate score_bits="{c.score_bits}">{c.hypothesis}</candidate>')
        lines.append("  </candidates>")

    tax = spec.taxonomy or []
    lines.append(f"  <taxonomy>{', '.join(tax)}</taxonomy>")
    lines.append(
        f'  <thresholds conclude="{thresholds.get("theta_conclude", 0.8)}" '
        f'escalate="{thresholds.get("theta_escalate", 0.55)}"/>'
    )
    lines.append("</exception>")
    return "\n".join(lines)


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None

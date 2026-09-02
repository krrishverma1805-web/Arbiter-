"""Compute the scorecard for a completed run (docs/07 §3-4)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, cast

from arbiter_engine.events.fold import RunProjection


@dataclass
class MatchingScore:
    auto_match_rate: float = 0.0
    precision: float = 0.0
    recall: float = 0.0
    false_match_rate: float = 0.0
    low_confidence: int = 0
    dollar_coverage: float = 0.0
    dollar_unexplained: float = 0.0
    true_matches: int = 0
    predicted_matches: int = 0
    correct_matches: int = 0


@dataclass
class ExceptionScore:
    total: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    category_accuracy: float = 0.0
    detected_anomalies: int = 0
    total_anomalies: int = 0
    unresolved_dollar: int = 0


@dataclass
class AgentScore:
    enabled: bool = False
    model: str = "none"
    investigations: int = 0
    proposals: int = 0
    escalations: int = 0
    escalation_reasons: dict[str, int] = field(default_factory=dict)
    task_completion_rate: float = 0.0  # correct proposal OR justified escalation
    category_accuracy: float = 0.0  # of proposals, how many match the true category
    escalation_precision: float = 0.0
    escalation_recall: float = 0.0
    hallucination_rate: float = 0.0  # evidence_refs pointing at records not in the exception
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    est_cost_usd: float = 0.0


@dataclass
class Scorecard:
    run_id: str
    spec: str
    dataset: dict[str, Any]
    matching: MatchingScore
    exceptions: ExceptionScore
    throughput: dict[str, float]
    determinism: dict[str, Any]
    agent: AgentScore = field(default_factory=AgentScore)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec": self.spec,
            "dataset": self.dataset,
            "matching": asdict(self.matching),
            "exceptions": asdict(self.exceptions),
            "throughput": self.throughput,
            "determinism": self.determinism,
            "agent": asdict(self.agent),
        }


def _load_ground_truth(dataset_dir: Path) -> dict[str, Any]:
    gt = dataset_dir / "ground_truth.json"
    if not gt.exists():
        raise FileNotFoundError(f"no ground_truth.json in {dataset_dir}")
    return cast(dict[str, Any], json.loads(gt.read_text()))


def score_run(
    proj: RunProjection,
    dataset_dir: Path,
    *,
    spec_name: str,
    wallclock_ms: int,
    replay_hash_match: bool,
    agent_events: list[tuple[str, dict[str, Any]]] | None = None,
) -> Scorecard:
    gt = _load_ground_truth(dataset_dir)
    true_matches = gt["true_matches"]
    anomalies = gt["anomalies"]

    # --- matching ---
    # Batches that SHOULD auto-tie: the clean ones, plus anomalies whose correct
    # resolution is "accept the variance" (ROUNDING / SPLIT_SETTLEMENT).
    true_by_utr = {m["settlement_utr"]: m for m in true_matches}
    benign_utrs = {
        a["settlement_utr"]
        for a in anomalies
        if a.get("settlement_utr") and a["true_resolution"].get("action") == "accept_variance"
    }
    should_tie = set(true_by_utr) | benign_utrs

    pred_by_utr = {m.id.removeprefix("m_"): m for m in proj.matches if m.id.startswith("m_")}
    predicted = len(pred_by_utr)

    exc_records = {rid for e in proj.exceptions for rid in e.record_ids}
    flagged_utrs = {utr for utr, m in pred_by_utr.items() if exc_records & set(m.all_ids)}

    def _ties(m: object) -> bool:
        return bool(abs(int(getattr(m, "residual_minor", 0))) <= 100)

    correct_on_should = sum(
        1 for utr in should_tie if utr in pred_by_utr and _ties(pred_by_utr[utr])
    )
    # false match: matcher auto-tied a batch whose identity does NOT close and no
    # exception flagged it
    false_matches = sum(
        1
        for utr, m in pred_by_utr.items()
        if m.status == "auto" and not _ties(m) and utr not in flagged_utrs
    )
    legit_ties = sum(1 for m in pred_by_utr.values() if _ties(m))
    n_should = len(should_tie) or 1

    total_dollar = sum(abs(m["expected_net_minor"]) for m in true_matches) or 1
    covered_dollar = sum(
        abs(true_by_utr[utr]["expected_net_minor"])
        for utr in pred_by_utr
        if utr in true_by_utr and _ties(pred_by_utr[utr])
    )
    unexplained_dollar = sum(
        abs(e.amount_impact_minor) for e in proj.exceptions if e.category == "UNEXPLAINED"
    )

    matching = MatchingScore(
        auto_match_rate=round(correct_on_should / n_should, 4),
        precision=round(legit_ties / predicted, 4) if predicted else 0.0,
        recall=round(correct_on_should / n_should, 4),
        false_match_rate=round(false_matches / predicted, 4) if predicted else 0.0,
        low_confidence=sum(1 for m in proj.matches if m.status == "low_confidence"),
        dollar_coverage=round(covered_dollar / total_dollar, 4),
        dollar_unexplained=round(unexplained_dollar / total_dollar, 4),
        true_matches=len(should_tie),
        predicted_matches=predicted,
        correct_matches=correct_on_should,
    )

    # --- exceptions / classifier ---
    by_type: dict[str, int] = {}
    for e in proj.exceptions:
        cat = e.category or "UNCLASSIFIED"
        by_type[cat] = by_type.get(cat, 0) + 1

    # detected-and-classified: does an exception touch an anomaly's records and
    # carry the right category?
    exc_by_record: dict[str, list[str]] = {}
    for e in proj.exceptions:
        for rid in e.record_ids:
            exc_by_record.setdefault(rid, []).append(e.category or "UNCLASSIFIED")

    detected = 0
    correct_cat = 0
    scored_anoms = [a for a in anomalies if a["record_ids"]]
    rec_id_by_entity = {r.external_ids.get("entity_id", r.id): r.id for r in proj.records}
    for a in scored_anoms:
        touched: set[str] = set()
        for ent in a["record_ids"]:
            mapped: str | None = rec_id_by_entity.get(ent)
            if mapped is not None and mapped in exc_by_record:
                touched.update(exc_by_record[mapped])
        if touched:
            detected += 1
            if a["true_category"] in touched:
                correct_cat += 1

    exceptions = ExceptionScore(
        total=len(proj.exceptions),
        by_type=dict(sorted(by_type.items())),
        category_accuracy=round(correct_cat / detected, 4) if detected else 0.0,
        detected_anomalies=detected,
        total_anomalies=len(scored_anoms),
        unresolved_dollar=unexplained_dollar,
    )

    rps = round(proj.record_count / (wallclock_ms / 1000), 1) if wallclock_ms else 0.0
    agent = _score_agent(proj, anomalies, agent_events or [])

    return Scorecard(
        run_id=proj.run_id,
        spec=spec_name,
        dataset={
            "dir": str(dataset_dir),
            "records": proj.record_count,
            "true_matches": len(should_tie),
            "anomalies": len(anomalies),
            "difficulty": gt.get("difficulty", "unknown"),
        },
        matching=matching,
        exceptions=exceptions,
        throughput={"records_per_sec": rps, "wallclock_ms": wallclock_ms},
        determinism={"replay_hash_match": replay_hash_match},
        agent=agent,
    )


_PRICE_M = {
    "claude-opus-5": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-5": (2.0, 10.0),
}


def _score_agent(
    proj: RunProjection, anomalies: list[dict[str, Any]], events: list[tuple[str, dict[str, Any]]]
) -> AgentScore:
    from arbiter_engine.events.payloads import EventType

    started = [p for t, p in events if t == EventType.AGENT_INVESTIGATION_STARTED]
    interactions = [p for t, p in events if t == EventType.AGENT_INTERACTION]
    props = [p for t, p in events if t == EventType.AGENT_PROPOSAL_CREATED]
    escs = [p for t, p in events if t == EventType.AGENT_ESCALATED]
    if not started:
        return AgentScore(enabled=False)

    model = next((s["model"] for s in started if s.get("model") not in (None, "none")), "none")
    reasons: dict[str, int] = {}
    for ev in escs:
        r = (ev.get("escalation") or {}).get("reason", "?")
        reasons[r] = reasons.get(r, 0) + 1

    # true category for each investigated exception, from the anomaly labels
    rec_id_by_entity = {r.external_ids.get("entity_id", r.id): r.id for r in proj.records}
    true_cat_by_exc: dict[str, str] = {}
    needs_human: set[str] = set()
    for a in anomalies:
        rids = {rec_id_by_entity.get(x) for x in a.get("record_ids", [])}
        for exc in proj.exceptions:
            if rids & set(exc.record_ids):
                true_cat_by_exc[exc.id] = a["true_category"]
                if not a.get("deterministically_resolvable", True):
                    needs_human.add(exc.id)

    correct_props = 0
    for p in props:
        want = true_cat_by_exc.get(p["exception_id"])
        got = (p.get("proposal") or {}).get("category")
        if want and got == want:
            correct_props += 1

    esc_ids = {ev["exception_id"] for ev in escs}
    esc_correct = len(esc_ids & needs_human)
    esc_precision = esc_correct / len(esc_ids) if esc_ids else 0.0
    esc_recall = esc_correct / len(needs_human) if needs_human else 0.0

    # hallucination: a proposal that cited a record which does not exist in the
    # run. The grounding check (docs/28 §1.3) resolves this authoritatively; fall
    # back to the "not among the exception's own records" heuristic if absent.
    all_record_ids = {r.id for r in proj.records}
    halluc = 0
    for p in props:
        g = p.get("grounding")
        if g is not None:
            if g.get("fabricated"):
                halluc += 1
            continue
        for ref in (p.get("proposal") or {}).get("evidence_refs", []):
            if ref.get("record_id") not in all_record_ids:
                halluc += 1
                break

    completed = correct_props + esc_correct
    tin = sum(i.get("tokens_in", 0) for i in interactions)
    tout = sum(i.get("tokens_out", 0) for i in interactions)
    pin, pout = _PRICE_M.get(model, (0.0, 0.0))
    return AgentScore(
        enabled=True,
        model=model,
        investigations=len(started),
        proposals=len(props),
        escalations=len(escs),
        escalation_reasons=dict(sorted(reasons.items())),
        task_completion_rate=round(completed / len(started), 4) if started else 0.0,
        category_accuracy=round(correct_props / len(props), 4) if props else 0.0,
        escalation_precision=round(esc_precision, 4),
        escalation_recall=round(esc_recall, 4),
        hallucination_rate=round(halluc / len(props), 4) if props else 0.0,
        tool_calls=sum(len(i.get("tool_calls", [])) for i in interactions),
        tokens_in=tin,
        tokens_out=tout,
        est_cost_usd=round(tin / 1e6 * pin + tout / 1e6 * pout, 4),
    )

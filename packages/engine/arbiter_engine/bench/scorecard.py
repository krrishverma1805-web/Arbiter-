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
class Scorecard:
    run_id: str
    spec: str
    dataset: dict[str, Any]
    matching: MatchingScore
    exceptions: ExceptionScore
    throughput: dict[str, float]
    determinism: dict[str, Any]
    ai: dict[str, Any] = field(default_factory=lambda: {"enabled": False, "note": "M3"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "spec": self.spec,
            "dataset": self.dataset,
            "matching": asdict(self.matching),
            "exceptions": asdict(self.exceptions),
            "throughput": self.throughput,
            "determinism": self.determinism,
            "ai": self.ai,
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
) -> Scorecard:
    gt = _load_ground_truth(dataset_dir)
    true_matches = gt["true_matches"]
    anomalies = gt["anomalies"]

    # --- matching ---
    true_by_utr = {m["settlement_utr"]: m for m in true_matches}
    pred_by_utr = {m.id.removeprefix("m_"): m for m in proj.matches if m.id.startswith("m_")}
    # a predicted match on an anomaly UTR whose correct resolution is "accept the
    # variance" (ROUNDING, SPLIT_SETTLEMENT) is a *correct* auto-tie, not a false one
    benign_utrs = {
        a["settlement_utr"]
        for a in anomalies
        if a.get("settlement_utr") and a["true_resolution"].get("action") == "accept_variance"
    }
    correct = 0
    false_matches = 0
    for utr, pred in pred_by_utr.items():
        ties = abs(pred.residual_minor) <= 100
        if utr in true_by_utr and ties or utr in benign_utrs and ties:
            correct += 1
        else:
            false_matches += 1
    predicted = len(pred_by_utr)
    n_true = len(true_matches) + len(benign_utrs)

    total_dollar = sum(abs(m["expected_net_minor"]) for m in true_matches) or 1
    covered_dollar = sum(
        abs(true_by_utr[utr]["expected_net_minor"])
        for utr in pred_by_utr
        if utr in true_by_utr and abs(pred_by_utr[utr].residual_minor) <= 100
    )
    unexplained_dollar = sum(
        abs(e.amount_impact_minor) for e in proj.exceptions if e.category == "UNEXPLAINED"
    )

    matching = MatchingScore(
        auto_match_rate=round(correct / n_true, 4) if n_true else 0.0,
        precision=round(correct / predicted, 4) if predicted else 0.0,
        recall=round(correct / n_true, 4) if n_true else 0.0,
        false_match_rate=round(false_matches / predicted, 4) if predicted else 0.0,
        low_confidence=sum(1 for m in proj.matches if m.status == "low_confidence"),
        dollar_coverage=round(covered_dollar / total_dollar, 4),
        dollar_unexplained=round(unexplained_dollar / total_dollar, 4),
        true_matches=n_true,
        predicted_matches=predicted,
        correct_matches=correct,
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

    return Scorecard(
        run_id=proj.run_id,
        spec=spec_name,
        dataset={
            "dir": str(dataset_dir),
            "records": proj.record_count,
            "true_matches": n_true,
            "anomalies": len(anomalies),
            "difficulty": gt.get("difficulty", "unknown"),
        },
        matching=matching,
        exceptions=exceptions,
        throughput={"records_per_sec": rps, "wallclock_ms": wallclock_ms},
        determinism={"replay_hash_match": replay_hash_match},
    )

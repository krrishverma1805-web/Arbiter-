from pathlib import Path

from arbiter_engine.events.store import EventStore
from arbiter_engine.exceptions.cluster import cluster_exceptions, summarize
from arbiter_engine.models import ReconException
from arbiter_engine.run import RunInputs, execute


def _exc(id: str, *, category: str, by: str, impact: int, status: str = "open") -> ReconException:
    return ReconException(
        id=id,
        run_id="r",
        category=category,
        classified_by=by,
        amount_impact_minor=impact,
        status=status,  # type: ignore[arg-type]
    )


def test_like_exceptions_collapse_into_one_cluster():
    excs = [
        _exc("e1", category="FEE_DEDUCTION", by="rule:r_fee_drift", impact=300),
        _exc("e2", category="FEE_DEDUCTION", by="rule:r_fee_drift", impact=420),
        _exc("e3", category="DUPLICATE", by="rule:r_dup", impact=50_000_00),
    ]
    clusters = cluster_exceptions(excs)
    assert len(clusters) == 2
    # largest ₹ first
    assert clusters[0].key.category == "DUPLICATE"
    fee = clusters[1]
    assert fee.count == 2
    assert fee.gross_impact_minor == 720
    assert fee.exception_ids == ["e1", "e2"]


def test_direction_and_terminal_status_are_respected():
    excs = [
        _exc("short", category="UNEXPLAINED", by="unclassified", impact=-2_000_00),
        _exc("over", category="UNEXPLAINED", by="unclassified", impact=2_000_00),
        _exc("done", category="UNEXPLAINED", by="unclassified", impact=9_00_00, status="resolved"),
    ]
    clusters = cluster_exceptions(excs)
    # resolved one is dropped; short vs over do not merge
    assert {c.key.direction for c in clusters} == {"short", "over"}
    assert all(c.count == 1 for c in clusters)


def test_summary_totals_are_deterministic():
    excs = [
        _exc("e1", category="TIMING", by="rule:r_timing", impact=10_00_00),
        _exc("e2", category="TIMING", by="rule:r_timing", impact=-4_00_00),
    ]
    s = summarize(excs)
    assert s["cluster_count"] == 2
    assert s["total_gross_minor"] == 14_00_00
    assert s["total_net_minor"] == 6_00_00
    assert summarize(excs) == s  # pure function


def test_clusters_a_real_run(adversarial_dataset: Path, spec_path: Path):
    store = EventStore("sqlite://")
    proj = execute(store, RunInputs(spec_path=spec_path, dataset_dir=adversarial_dataset))
    s = summarize(proj.exceptions)
    assert s["cluster_count"] >= 1
    open_gross = sum(
        abs(e.amount_impact_minor)
        for e in proj.exceptions
        if e.status in {"open", "proposed", "escalated", "security_review", "budget_exceeded"}
    )
    assert s["total_gross_minor"] == open_gross
    # clusters are sorted by descending ₹
    grosses = [c["gross_impact_minor"] for c in s["clusters"]]
    assert grosses == sorted(grosses, reverse=True)

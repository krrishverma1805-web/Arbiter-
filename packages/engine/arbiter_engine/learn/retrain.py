"""Per-tenant Fellegi–Sunter retraining behind an eval gate (docs/28 §3 item 14).

Every confirmed match a tenant accumulates is a labelled positive; a random
bank↔batch pair that was *not* matched is a negative. From those we re-estimate
the m/u table (`FSModel.from_labeled`) — the model literally gets better at *this*
tenant's data.

**Nothing is promoted on faith.** The labelled pairs are split; the candidate
must beat the incumbent on the held-out ROC-AUC by `margin` or it is rejected.
Both outcomes are written to the event log (`FS_MODEL_PROMOTED` /
`FS_MODEL_REJECTED`) so the decision is auditable, and the next run over this
spec loads the promoted table via `fs_store.load_fs_model`.

Deterministic: the shuffle is seeded from the spec hash, so a retrain over the
same history always makes the same decision.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from arbiter_engine.events.fold import RunProjection, fold_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.match.compare import compare_bank_to_group
from arbiter_engine.match.engine import _Tol, _tolerances
from arbiter_engine.match.fellegi_sunter import FSModel
from arbiter_engine.models import Decomposition, Record
from arbiter_engine.specs import ReconSpec, spec_hash

_MIN_PAIRS = 40
_MARGIN = 0.01
_HOLDOUT = 0.3
_PRIOR = 0.5


@dataclass
class RetrainResult:
    promoted: bool
    reason: str
    auc_before: float = 0.0
    auc_after: float = 0.0
    n_pairs: int = 0


def _comparison(
    br: Record, group: list[Record], decomp: Decomposition | None, tol: _Tol
) -> dict[str, str]:
    expected = (
        decomp.expected_minor
        if decomp is not None
        else sum(r.amount_minor for r in group if r.kind == "payment")
        - sum(r.fee_minor + r.tax_minor for r in group)
    )
    group_settled = max((r.settled_at for r in group if r.settled_at), default=None)
    utr = (decomp.settlement_utr if decomp else None) or br.external_ids.get("utr")
    bank_ids = set(br.external_ids.values())
    shared = any(v in bank_ids for g in group for v in g.external_ids.values())
    return compare_bank_to_group(
        delta_minor=br.amount_minor - expected,
        expected_minor=expected,
        bank_date=br.value_date,
        group_settled=group_settled,
        bank_ref=br.external_ids.get("utr"),
        group_ref=utr,
        shared_ids=shared,
        rounding=tol.rounding_minor,
        tol=tol.amount_minor,
        window=tol.date_window_days,
    )


def _pairs_from_run(
    proj: RunProjection, tol: _Tol
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    by_id = {r.id: r for r in proj.records}
    decomp_by_utr = {d.settlement_utr: d for d in proj.decompositions if d.settlement_utr}
    pos: list[dict[str, str]] = []
    banks: list[Record] = []
    groups: list[list[Record]] = []
    for m in proj.matches:
        bank = [by_id[i] for i in m.right_ids if i in by_id]
        group = [by_id[i] for i in m.left_ids if i in by_id]
        if not bank or not group:
            continue
        br = min(bank, key=lambda r: r.id)
        utr = br.external_ids.get("utr", "")
        pos.append(_comparison(br, group, decomp_by_utr.get(utr), tol))
        banks.append(br)
        groups.append(group)

    # negatives: each matched bank record paired with the *next* run's batch —
    # a real bank credit against a real batch that is not its counterpart.
    neg: list[dict[str, str]] = []
    for i, br in enumerate(banks):
        if len(groups) < 2:
            break
        other = groups[(i + 1) % len(groups)]
        if br.id in {g.id for g in other} or other is groups[i]:
            continue
        neg.append(_comparison(br, other, None, tol))
    return pos, neg


def gather_pairs(
    store: EventStore, spec: ReconSpec
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    sh = spec_hash(spec)
    tol = _tolerances(spec)
    pos: list[dict[str, str]] = []
    neg: list[dict[str, str]] = []
    for rid in store.runs(include_internal=True):
        types = {t for t, _ in store.iter_payloads(rid)}
        if EventType.MATCH_CONFIRMED not in types:
            continue
        started = next((p for t, p in store.iter_payloads(rid) if t == EventType.RUN_STARTED), None)
        if not started or started.get("spec_hash") != sh:
            continue
        proj = fold_run(store, rid)
        p, n = _pairs_from_run(proj, tol)
        pos.extend(p)
        neg.extend(n)
    return pos, neg


def _auc(model: FSModel, pos: list[dict[str, str]], neg: list[dict[str, str]]) -> float:
    if not pos or not neg:
        return 0.5

    def score(comp: dict[str, str]) -> float:
        w, _ = model.weight(comp)
        return model.probability(w, prior=_PRIOR)

    ps = sorted(score(c) for c in pos)
    ns = [score(c) for c in neg]
    wins = 0.0
    for n in ns:
        lo, hi = 0, len(ps)
        while lo < hi:
            mid = (lo + hi) // 2
            if ps[mid] <= n:
                lo = mid + 1
            else:
                hi = mid
        # Mann–Whitney U: positives ranked above this negative, ties count half
        greater = len(ps) - lo
        ties = sum(1 for x in ps if x == n)
        wins += greater + 0.5 * ties
    return wins / (len(ps) * len(ns))


def retrain(
    store: EventStore,
    spec: ReconSpec,
    *,
    trained_by: str = "nightly",
    min_pairs: int = _MIN_PAIRS,
    margin: float = _MARGIN,
) -> RetrainResult:
    from arbiter_engine.match.fs_store import load_fs_model

    sh = spec_hash(spec)
    pos, neg = gather_pairs(store, spec)
    if len(pos) < min_pairs or len(neg) < min_pairs // 2:
        return RetrainResult(False, "insufficient_data", n_pairs=len(pos))

    rng = random.Random(int(sh, 16) % (2**32))
    rng.shuffle(pos)
    rng.shuffle(neg)
    pcut, ncut = int(len(pos) * (1 - _HOLDOUT)), int(len(neg) * (1 - _HOLDOUT))
    train_p, hold_p = pos[:pcut], pos[pcut:]
    train_n, hold_n = neg[:ncut], neg[ncut:]

    incumbent = load_fs_model(store, sh) or FSModel()
    candidate = FSModel.from_labeled(train_p, train_n)
    candidate.calibration = list(incumbent.calibration)

    auc_before = _auc(incumbent, hold_p, hold_n)
    auc_after = _auc(candidate, hold_p, hold_n)
    n_pairs = len(pos) + len(neg)
    rid = _synthetic_rid(store)

    if auc_after >= auc_before + margin:
        mu_json = {f: {lvl: [m, u] for lvl, (m, u) in lv.items()} for f, lv in candidate.mu.items()}
        store.append(
            rid,
            EventType.FS_MODEL_PROMOTED,
            {
                "spec_hash": sh,
                "mu": mu_json,
                "auc_before": round(auc_before, 6),
                "auc_after": round(auc_after, 6),
                "n_pairs": n_pairs,
                "trained_by": trained_by,
            },
            actor="learn",
        )
        return RetrainResult(True, "promoted", auc_before, auc_after, n_pairs)

    store.append(
        rid,
        EventType.FS_MODEL_REJECTED,
        {
            "spec_hash": sh,
            "auc_before": round(auc_before, 6),
            "auc_after": round(auc_after, 6),
            "n_pairs": n_pairs,
            "reason": "did not beat the incumbent by the margin",
            "trained_by": trained_by,
        },
        actor="learn",
    )
    return RetrainResult(False, "below_gate", auc_before, auc_after, n_pairs)


def _synthetic_rid(store: EventStore) -> str:
    """Retrain events don't belong to a reconciliation run; park them on a
    stable per-tenant pseudo-run so they replay cleanly and stay tenant-scoped."""
    return f"__learn__{getattr(store, 'org_id', 'local')}"

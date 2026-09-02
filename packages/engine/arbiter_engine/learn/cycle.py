"""The cycle demo (docs/02 §5.3): three monthly closes, a learned rule carried
forward, the unexplained-money line falling.

Cycle 1 runs on the base spec and leaves a large `UNEXPLAINED` settlement residual
open. A controller resolves it — "this batch was split across two settlements, the
halves net out" — as `SPLIT_SETTLEMENT / accept_variance`. That drafts a narrow
rule, it is merged into the spec, and later cycles classify the same shape
automatically. No model is involved at any step.

Batch-to-batch noise (each close is a fresh random dataset) would swamp a single
metric column, so every cycle is scored twice — once on the *base* spec, once on
the *current* (learned) spec. The gap between the two columns is the rule's doing
and nothing else.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from arbiter_engine.bench import score_run
from arbiter_engine.events.payloads import EventType
from arbiter_engine.events.store import EventStore
from arbiter_engine.learn.spec_merge import merge_rules
from arbiter_engine.learn.synthesize import draft_rule_from_resolution
from arbiter_engine.run import RunInputs, execute


@dataclass
class CycleRow:
    cycle: int
    dataset: str
    base_unexplained_count: int
    base_unexplained_minor: int
    base_unexplained_frac: float
    learned_unexplained_count: int
    learned_unexplained_minor: int
    learned_unexplained_frac: float
    learned_rule: str | None = None

    @property
    def money_recovered_minor(self) -> int:
        return self.base_unexplained_minor - self.learned_unexplained_minor


@dataclass
class CycleResult:
    rows: list[CycleRow]
    drafted_rule: dict[str, Any] | None
    spec_version_before: int
    spec_version_after: int
    spec_path: Path

    @property
    def total_recovered_minor(self) -> int:
        return sum(r.money_recovered_minor for r in self.rows)


def _unexplained(proj: Any, dataset: Path, spec_stem: str) -> tuple[int, int, float]:
    card = score_run(proj, dataset, spec_name=spec_stem, wallclock_ms=0, replay_hash_match=True)
    exc = card.exceptions
    return (
        exc.by_type.get("UNEXPLAINED", 0),
        exc.unresolved_dollar,
        card.matching.dollar_unexplained,
    )


def _biggest_unexplained_residual(proj: Any):  # type: ignore[no-untyped-def]
    """The largest UNEXPLAINED exception that is a settlement residual (has a
    decomposition) — the shape a `SPLIT_SETTLEMENT` rule can safely generalise."""
    resid_utrs = {d.settlement_utr for d in proj.decompositions}
    rec_by_id = {r.id: r for r in proj.records}
    cands = [
        e
        for e in proj.exceptions
        if e.category == "UNEXPLAINED"
        and len(e.record_ids) >= 2
        and any(
            rec_by_id[rid].external_ids.get("settlement_utr") in resid_utrs
            for rid in e.record_ids
            if rid in rec_by_id
        )
    ]
    cands.sort(key=lambda e: -abs(e.amount_impact_minor))
    return cands[0] if cands else None


def run_cycle_demo(
    spec_src: Path,
    datasets: list[Path],
    workdir: Path,
    *,
    actor: str = "controller",
) -> CycleResult:
    if len(datasets) < 2:
        raise ValueError("the cycle demo needs at least two dataset batches")
    workdir.mkdir(parents=True, exist_ok=True)
    base_spec = workdir / "spec-base.yaml"
    learned_spec = workdir / "spec.yaml"
    shutil.copy(spec_src, base_spec)
    shutil.copy(spec_src, learned_spec)
    store = EventStore(f"sqlite:///{workdir / 'cycle.db'}")

    rows: list[CycleRow] = []
    drafted: dict[str, Any] | None = None
    v_before = v_after = 0

    for i, ds in enumerate(datasets, start=1):
        base_proj = execute(store, RunInputs(spec_path=base_spec, dataset_dir=ds, no_ai=True))
        b_cnt, b_minor, b_frac = _unexplained(base_proj, ds, base_spec.stem)

        learned_proj = execute(store, RunInputs(spec_path=learned_spec, dataset_dir=ds, no_ai=True))
        l_cnt, l_minor, l_frac = _unexplained(learned_proj, ds, learned_spec.stem)

        rows.append(
            CycleRow(
                cycle=i,
                dataset=ds.name,
                base_unexplained_count=b_cnt,
                base_unexplained_minor=b_minor,
                base_unexplained_frac=b_frac,
                learned_unexplained_count=l_cnt,
                learned_unexplained_minor=l_minor,
                learned_unexplained_frac=l_frac,
                learned_rule=drafted["rule_id"] if drafted else None,
            )
        )

        if i == 1 and drafted is None:
            target = _biggest_unexplained_residual(base_proj)
            if target is None:
                continue
            store.append(
                base_proj.run_id,
                EventType.RESOLUTION_APPLIED,
                {
                    "exception_id": target.id,
                    "action": "accept_variance",
                    "detail": "batch split across two settlements; the halves net out",
                    "actor": actor,
                    "prior_status": target.status,
                    "category": "SPLIT_SETTLEMENT",
                },
            )
            drafted = draft_rule_from_resolution(
                target, "accept_variance", category="SPLIT_SETTLEMENT"
            )
            if drafted is not None:
                store.append(base_proj.run_id, EventType.RULE_DRAFTED, drafted)
                res = merge_rules(
                    store, base_proj.run_id, learned_spec, None, approved_by=f"human:{actor}"
                )
                v_before, v_after = res["version_before"], res["version_after"]

    return CycleResult(
        rows=rows,
        drafted_rule=drafted,
        spec_version_before=v_before,
        spec_version_after=v_after,
        spec_path=learned_spec,
    )

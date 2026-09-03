"""Matching engine orchestration (docs/16 §2).

Passes over the not-yet-matched remainder, in fixed order:
  1. exact     — settlement_utr join, zero residual, confidence 1.0
  2. tolerant  — settlement_utr join, Fellegi–Sunter weight over the comparison
                 vector, calibrated P(match) (docs/16 §5)
  2b. blocked  — for blocks the UTR key could not tie (a real bank statement often
                 loses or reformats the UTR): amount-within-tolerance + date-in-
                 window, greedy stable assignment, confidence from closeness alone
  2c. aggregate — one bank credit that ties the *sum* of 2–4 still-unresolved
                 settlement batches (a rolled PG payout); unique subset only
  2d. aggregate — the mirror: 2–3 bank credits summing to one settlement batch
                 (a payout the bank split into tranches)
  3. subset    — an orphan bank credit vs a subset of unmatched processor items
                 (subset-sum matching, docs/16 §6)
  4. fuzzy     — FS-ranked candidates attached to the remaining unmatched records;
                 never an auto-match (docs/16 §7)

Deterministic: every collection is iterated in sorted-id order; integer paise;
no wall-clock in any decision.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from arbiter_engine.decompose.identity import decompose_group, expected_net_minor
from arbiter_engine.match.compare import compare_bank_to_group, date_level
from arbiter_engine.match.entity import same_entity
from arbiter_engine.match.fellegi_sunter import FSModel
from arbiter_engine.match.subset import subset_sum_match
from arbiter_engine.models import Decomposition, Match, MatchCandidate, Record
from arbiter_engine.specs.model import ReconSpec


@dataclass
class MatchResult:
    matches: list[Match] = field(default_factory=list)
    decompositions: list[Decomposition] = field(default_factory=list)
    matched_ids: set[str] = field(default_factory=set)
    candidates: dict[str, list[MatchCandidate]] = field(
        default_factory=dict
    )  # record_id -> candidates

    def unmatched(self, records: list[Record]) -> list[Record]:
        return sorted((r for r in records if r.id not in self.matched_ids), key=lambda r: r.id)


@dataclass
class _Tol:
    amount_minor: int
    date_window_days: int
    rounding_minor: int
    auto: float
    review: float


def _tolerances(spec: ReconSpec) -> _Tol:
    tol = spec.passes.get("tolerant") or [{}]
    first = tol[0] if isinstance(tol, list) and tol else {}
    ident = spec.identity or {}
    thr = spec.thresholds or {}
    return _Tol(
        amount_minor=int(first.get("amount_tolerance_minor", 200)),
        date_window_days=int(first.get("date_window_days", 4)),
        rounding_minor=int(ident.get("rounding_tolerance_minor", 100)),
        auto=float(thr.get("auto", 0.90)),
        review=float(thr.get("review", 0.70)),
    )


def run_matching(
    run_id: str, records: list[Record], spec: ReconSpec, *, fs: FSModel | None = None
) -> MatchResult:
    tol = _tolerances(spec)
    model = fs or FSModel()
    result = MatchResult()

    processor = sorted((r for r in records if r.source == "razorpay_recon"), key=lambda r: r.id)
    bank = sorted((r for r in records if r.source == "bank"), key=lambda r: r.id)
    ledger = sorted((r for r in records if r.source == "ledger"), key=lambda r: r.id)

    proc_blocks: dict[str, list[Record]] = {}
    for r in processor:
        utr = r.external_ids.get("settlement_utr")
        if utr:
            proc_blocks.setdefault(utr, []).append(r)

    bank_by_utr: dict[str, list[Record]] = {}
    for b in bank:
        utr = b.external_ids.get("utr")
        if utr:
            bank_by_utr.setdefault(utr, []).append(b)

    ledger_by_order = {r.external_ids.get("order_id", r.id): r for r in ledger}
    n_batches = max(len(proc_blocks), 1)
    prior = 1.0 / n_batches  # block prior P(match) (docs/16 §5.4)

    # blocks the settlement_utr key could not tie to a bank credit — retried in
    # pass 2b by amount + date (real bank narrations lose or mangle the UTR)
    unresolved: list[tuple[str, list[Record], int, date | None, list[Record]]] = []

    # ---- passes 1 & 2: settlement_utr keyed ----
    for utr in sorted(proc_blocks):
        items = sorted(proc_blocks[utr], key=lambda r: r.id)
        expected = expected_net_minor(items)
        order_ids = [
            it.external_ids["order_id"]
            for it in items
            if it.kind == "payment" and it.external_ids.get("order_id")
        ]
        ledger_matches = [ledger_by_order[o] for o in order_ids if o in ledger_by_order]
        ledger_total = sum(m.amount_minor for m in ledger_matches) or None
        group_settled = max((it.settled_at for it in items if it.settled_at), default=None)

        cands = sorted(bank_by_utr.get(utr, []), key=lambda r: r.id)
        if not cands:
            unresolved.append((utr, items, expected, group_settled, ledger_matches))
            continue
        bank_rec = min(cands, key=lambda b: (abs(b.amount_minor - expected), b.id))
        delta = bank_rec.amount_minor - expected

        decomp = decompose_group(
            run_id,
            utr,
            items,
            bank_amount_minor=bank_rec.amount_minor,
            ledger_total_minor=ledger_total,
        )
        result.decompositions.append(decomp)

        if delta == 0 and decomp.ledger_crosscheck_ok:
            _emit(
                result,
                run_id,
                utr,
                items,
                [bank_rec],
                ledger_matches,
                match_pass="exact",
                confidence=1.0,
                weight=None,
                per_field={},
                residual=0,
                tol=tol,
            )
            continue
        if abs(delta) <= tol.amount_minor:
            comp = compare_bank_to_group(
                delta_minor=delta,
                expected_minor=expected,
                bank_date=bank_rec.value_date,
                group_settled=group_settled,
                bank_ref=bank_rec.external_ids.get("utr"),
                group_ref=utr,
                shared_ids=bool(order_ids),
                rounding=tol.rounding_minor,
                tol=tol.amount_minor,
                window=tol.date_window_days,
            )
            weight, per_field = model.weight(comp)
            conf = model.probability(weight, prior=prior)
            if not decomp.ledger_crosscheck_ok:
                conf = min(conf, tol.review)
            _emit(
                result,
                run_id,
                utr,
                items,
                [bank_rec],
                ledger_matches,
                match_pass="tolerant",
                confidence=conf,
                weight=weight,
                per_field=per_field,
                residual=decomp.residual_minor,
                tol=tol,
            )
            continue
        # settlement_utr matches but amount is out of tolerance → exception downstream

    # ---- pass 2b: amount + date blocking — for blocks the UTR key could not tie ----
    # Real bank statements routinely drop or reformat the settlement UTR. For each
    # such block, find the free bank credit whose net ties within tolerance and
    # whose date is in-window; assign greedily by closeness. This pass has no UTR
    # or reference signal by construction, so its confidence comes from amount +
    # date closeness alone and is never rated above the UTR-keyed passes.
    if unresolved:
        free_bank = sorted(
            (
                b
                for b in bank
                if b.id not in result.matched_ids and b.external_ids.get("utr") not in proc_blocks
            ),
            key=lambda r: r.id,
        )
        pairs: list[tuple[int, str, int, int, Record]] = []  # (gap, date_lvl_ord, bi, gap, bank)
        _dord = {"same_day": 0, "within_1": 1, "within_window": 2, "none": 3}
        by_block: dict[int, list[int]] = {}
        for bi, (_u0, _i0, expected0, gs0, _l0) in enumerate(unresolved):
            for b in free_bank:
                gap0 = abs(b.amount_minor - expected0)
                if gap0 > tol.amount_minor:
                    continue
                dl = date_level(b.value_date, gs0, window=tol.date_window_days)
                if dl == "none" and gap0 > tol.rounding_minor:
                    continue
                pairs.append((gap0, dl, bi, gap0, b))
                by_block.setdefault(bi, []).append(gap0)
        pairs.sort(key=lambda c: (c[0], _dord[c[1]], c[4].id))
        taken_bank: set[str] = set()
        taken_block: set[int] = set()
        for gap0, dl, bi, _g, b in pairs:
            if bi in taken_block or b.id in taken_bank:
                continue
            gaps = sorted(by_block.get(bi, []))
            ambiguous = len(gaps) > 1 and (gaps[1] - gaps[0]) <= tol.rounding_minor
            utr, items, expected, group_settled, ledger_matches = unresolved[bi]
            ledger_total = sum(m.amount_minor for m in ledger_matches) or None
            decomp = decompose_group(
                run_id,
                utr,
                items,
                bank_amount_minor=b.amount_minor,
                ledger_total_minor=ledger_total,
            )
            base = {"same_day": 0.94, "within_1": 0.9, "within_window": 0.85, "none": 0.8}[dl]
            if gap0 > tol.rounding_minor:
                base -= 0.1
            conf = base
            if ambiguous:
                conf = min(conf, tol.review - 0.01)
            if not decomp.ledger_crosscheck_ok:
                conf = min(conf, tol.review)
            if conf < tol.review:
                continue  # too weak — leave it for subset / fuzzy / an exception
            result.decompositions.append(decomp)
            _emit(
                result,
                run_id,
                utr,
                items,
                [b],
                ledger_matches,
                match_pass="blocked",
                confidence=round(conf, 4),
                weight=None,
                per_field={},
                residual=decomp.residual_minor,
                tol=tol,
            )
            taken_block.add(bi)
            taken_bank.add(b.id)

        # ---- pass 2c: aggregated payout — one credit ties a sum of blocks ----
        # Indian PGs frequently roll several small settlements into one bank
        # credit. Find a unique subset (size 2–4) of still-unresolved blocks
        # whose expected nets sum to a free credit within tolerance.
        open_idx = [bi for bi in range(len(unresolved)) if bi not in taken_block]
        for b in (bb for bb in free_bank if bb.id not in taken_bank):
            combo = _blocks_summing_to(unresolved, open_idx, b.amount_minor, tol)
            if combo is None:
                continue
            picked = [unresolved[bi] for bi in combo]
            all_items = [it for _u, its, _e2, _gs, _l in picked for it in its]
            all_ledger = [lm for _u, _i, _e2, _gs, lms in picked for lm in lms]
            for u, its, _e2, _gs, lms in picked:
                result.decompositions.append(
                    decompose_group(
                        run_id,
                        u,
                        its,
                        bank_amount_minor=None,
                        ledger_total_minor=sum(m.amount_minor for m in lms) or None,
                    )
                )
            residual = b.amount_minor - sum(e for _u, _i, e, _gs, _l in picked)
            _emit(
                result,
                run_id,
                f"agg_{b.id}",
                all_items,
                [b],
                all_ledger,
                match_pass="aggregate",
                confidence=0.85 if abs(residual) <= tol.rounding_minor else 0.78,
                weight=None,
                per_field={},
                residual=residual,
                tol=tol,
            )
            taken_bank.add(b.id)
            taken_block.update(combo)
            open_idx = [bi for bi in open_idx if bi not in taken_block]

        # ---- pass 2d: split payout — a sum of credits ties one block ----
        # The mirror of 2c: a bank splits one large payout into 2–3 tranches.
        for bi in [j for j in range(len(unresolved)) if j not in taken_block]:
            utr, items, expected, gs, ledger_matches = unresolved[bi]
            avail = [bb for bb in free_bank if bb.id not in taken_bank]
            credits = _credits_summing_to(avail, expected, tol)
            if credits is None:
                continue
            ledger_total = sum(m.amount_minor for m in ledger_matches) or None
            got = sum(c.amount_minor for c in credits)
            decomp = decompose_group(
                run_id, utr, items, bank_amount_minor=got, ledger_total_minor=ledger_total
            )
            result.decompositions.append(decomp)
            _emit(
                result,
                run_id,
                utr,
                items,
                credits,
                ledger_matches,
                match_pass="aggregate",
                confidence=0.85 if abs(got - expected) <= tol.rounding_minor else 0.78,
                weight=None,
                per_field={},
                residual=decomp.residual_minor,
                tol=tol,
            )
            taken_block.add(bi)
            taken_bank.update(c.id for c in credits)

    # ---- pass 3: subset — orphan bank credits vs unmatched processor items ----
    unmatched_proc = [r for r in processor if r.id not in result.matched_ids]
    matched_bank = result.matched_ids
    for b in sorted(bank, key=lambda r: r.id):
        if b.id in matched_bank or b.external_ids.get("utr") in proc_blocks:
            continue
        pool = sorted(
            (r for r in unmatched_proc if r.id not in result.matched_ids and r.kind == "payment"),
            key=lambda r: r.id,
        )[:40]
        sr = subset_sum_match(pool, b.amount_minor, tolerance_minor=tol.amount_minor)
        if sr is None or sr.ambiguous or not sr.items:
            continue
        conf = tol.review if sr.method == "subset_heuristic" else max(tol.auto, 0.9)
        _emit(
            result,
            run_id,
            f"subset_{b.id}",
            sr.items,
            [b],
            [],
            match_pass=sr.method,
            confidence=conf,
            weight=None,
            per_field={},
            residual=sr.residual_minor,
            tol=tol,
        )

    # ---- pass 4: fuzzy candidates for the remaining unmatched ----
    still_bank = [b for b in bank if b.id not in result.matched_ids]
    still_groups = [
        (utr, items)
        for utr, items in sorted(proc_blocks.items())
        if not any(i.id in result.matched_ids for i in items)
    ]
    for b in sorted(still_bank, key=lambda r: r.id):
        ranked: list[MatchCandidate] = []
        for utr, items in still_groups:
            expected = expected_net_minor(items)
            group_settled = max((it.settled_at for it in items if it.settled_at), default=None)
            comp = compare_bank_to_group(
                delta_minor=b.amount_minor - expected,
                expected_minor=expected,
                bank_date=b.value_date,
                group_settled=group_settled,
                bank_ref=b.external_ids.get("utr"),
                group_ref=utr,
                shared_ids=False,
                rounding=tol.rounding_minor,
                tol=tol.amount_minor,
                window=tol.date_window_days,
            )
            weight, per_field = model.weight(comp)
            # counterparty entity resolution (docs/28 §1.2): a small tiebreak when
            # the bank narration's party resolves to the batch's party
            group_cp = next((i.counterparty for i in items if i.counterparty), None)
            if same_entity(b.counterparty, group_cp):
                per_field = {**per_field, "counterparty_entity": 1.0}
                weight += 1.0
            ranked.append(
                MatchCandidate(
                    hypothesis=f"settlement batch {utr} (expected {expected})",
                    record_ids=sorted(i.id for i in items),
                    score_bits=round(weight, 3),
                    per_field_weights=per_field,
                )
            )
        ranked.sort(key=lambda c: (-c.score_bits, c.hypothesis))
        if ranked:
            result.candidates[b.id] = ranked[:3]

    result.matches.sort(key=lambda m: m.id)
    result.decompositions.sort(key=lambda d: d.group_id)
    return result


def _blocks_summing_to(
    blocks: list[tuple[str, list[Record], int, date | None, list[Record]]],
    open_idx: list[int],
    target: int,
    tol: _Tol,
) -> list[int] | None:
    """The unique subset (size 2–4) of the given block indices whose expected
    nets sum to `target` within tolerance. `None` if there is no such subset or
    more than one (ambiguous → never guess)."""
    from itertools import combinations

    pool = sorted(open_idx, key=lambda bi: blocks[bi][0])[:14]
    found: list[list[int]] = []
    for size in (2, 3, 4):
        for combo in combinations(pool, size):
            s = sum(blocks[bi][2] for bi in combo)
            if abs(s - target) <= tol.amount_minor:
                found.append(list(combo))
        if len(found) > 1:
            return None
    return found[0] if len(found) == 1 else None


def _credits_summing_to(credits: list[Record], target: int, tol: _Tol) -> list[Record] | None:
    """The unique subset (size 2–3) of bank credits summing to `target` within
    tolerance. `None` if absent or ambiguous."""
    from itertools import combinations

    pool = sorted(credits, key=lambda c: c.id)[:10]
    found: list[list[Record]] = []
    for size in (2, 3):
        for combo in combinations(pool, size):
            if abs(sum(c.amount_minor for c in combo) - target) <= tol.amount_minor:
                found.append(list(combo))
        if len(found) > 1:
            return None
    return found[0] if len(found) == 1 else None


def _emit(
    result: MatchResult,
    run_id: str,
    key: str,
    left: list[Record],
    right: list[Record],
    groups: list[Record],
    *,
    match_pass: str,
    confidence: float,
    weight: float | None,
    per_field: dict[str, float],
    residual: int,
    tol: _Tol,
) -> None:
    status = "auto" if confidence >= tol.auto else "low_confidence"
    m = Match(
        id=f"m_{key}",
        run_id=run_id,
        left_ids=sorted(r.id for r in left),
        right_ids=sorted(r.id for r in right),
        group_ids=sorted(r.id for r in groups),
        match_pass=match_pass,  # type: ignore[arg-type]
        weight_bits=round(weight, 3) if weight is not None else None,
        per_field_weights={k: round(v, 3) for k, v in per_field.items()},
        confidence=round(confidence, 4),
        rule_id=None,
        residual_minor=residual,
        status=status,  # type: ignore[arg-type]
    )
    result.matches.append(m)
    result.matched_ids.update(m.all_ids)

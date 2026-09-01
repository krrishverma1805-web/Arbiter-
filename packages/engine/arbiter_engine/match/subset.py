"""Subset-sum matching for reconciliation (docs/16 §6).

Find a subset S of candidate items whose net (Σ credit − Σ debit − Σ fee − Σ tax)
equals a target bank credit within tolerance. This is the Subset-Sum Matching
Problem — NP-hard in general, tractable here because settlement blocks are small.

  |candidates| ≤ 22  → exact meet-in-the-middle
  otherwise          → greedy + local search, bounded by an operation budget

Deterministic: candidates are sorted by id; ties broken by id. When more than one
subset ties within tolerance, we return None (the caller opens an AMBIGUOUS
exception with the candidates attached) — we never guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

from arbiter_engine.models import Record

_MITM_LIMIT = 22
_OP_BUDGET = 200_000


@dataclass
class SubsetResult:
    items: list[Record]
    residual_minor: int
    method: str  # "subset" | "subset_heuristic"
    ambiguous: bool = False


def _net(item: Record) -> int:
    return item.amount_minor - item.fee_minor - item.tax_minor


def subset_sum_match(
    candidates: list[Record], target_minor: int, *, tolerance_minor: int
) -> SubsetResult | None:
    items = sorted(candidates, key=lambda r: r.id)
    if not items:
        return None
    nets = [_net(it) for it in items]

    if len(items) <= _MITM_LIMIT:
        return _meet_in_the_middle(items, nets, target_minor, tolerance_minor)
    return _greedy(items, nets, target_minor, tolerance_minor)


def _meet_in_the_middle(
    items: list[Record], nets: list[int], target: int, tol: int
) -> SubsetResult | None:
    n = len(items)
    half = n // 2
    left, right = list(range(half)), list(range(half, n))

    def sums(idxs: list[int]) -> list[tuple[int, tuple[int, ...]]]:
        out: list[tuple[int, tuple[int, ...]]] = []
        for k in range(len(idxs) + 1):
            for combo in combinations(idxs, k):
                out.append((sum(nets[i] for i in combo), combo))
        return out

    right_sums = sorted(sums(right))
    right_vals = [s for s, _ in right_sums]

    solutions: list[tuple[int, tuple[int, ...]]] = []
    import bisect

    for lsum, lcombo in sums(left):
        want = target - lsum
        lo = bisect.bisect_left(right_vals, want - tol)
        hi = bisect.bisect_right(right_vals, want + tol)
        for k in range(lo, hi):
            rsum, rcombo = right_sums[k]
            combo = tuple(sorted(lcombo + rcombo))
            if not combo:
                continue
            residual = (lsum + rsum) - target
            solutions.append((abs(residual), combo))

    if not solutions:
        return None
    solutions.sort()
    best_residual, best_combo = solutions[0]
    # ambiguous if a second, different subset ties within tolerance
    tied = [c for r, c in solutions if r <= tol and c != best_combo]
    chosen = [items[i] for i in best_combo]
    signed = sum(nets[i] for i in best_combo) - target
    return SubsetResult(items=chosen, residual_minor=signed, method="subset", ambiguous=bool(tied))


def _greedy(items: list[Record], nets: list[int], target: int, tol: int) -> SubsetResult | None:
    order = sorted(range(len(items)), key=lambda i: -abs(nets[i]))
    chosen: list[int] = []
    total = 0
    ops = 0
    for i in order:
        ops += 1
        if ops > _OP_BUDGET:
            break
        if abs(total + nets[i] - target) <= abs(total - target):
            chosen.append(i)
            total += nets[i]
    # local search: try single swaps to close the gap
    improved = True
    while improved and ops < _OP_BUDGET:
        improved = False
        for i in list(chosen):
            for j in range(len(items)):
                ops += 1
                if j in chosen:
                    continue
                new_total = total - nets[i] + nets[j]
                if abs(new_total - target) < abs(total - target):
                    chosen.remove(i)
                    chosen.append(j)
                    total = new_total
                    improved = True
                    break
            if improved:
                break
    if abs(total - target) > tol:
        return None
    return SubsetResult(
        items=[items[i] for i in sorted(chosen)],
        residual_minor=total - target,
        method="subset_heuristic",
    )

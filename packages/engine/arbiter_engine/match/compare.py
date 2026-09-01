"""Build Fellegi–Sunter comparison vectors for candidate pairs (docs/16 §5.1)."""

from __future__ import annotations

from datetime import date


def _jaro_winkler(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if not a or not b:
        return 0.0
    max_dist = max(len(a), len(b)) // 2 - 1
    a_match = [False] * len(a)
    b_match = [False] * len(b)
    matches = 0
    for i, ca in enumerate(a):
        lo = max(0, i - max_dist)
        hi = min(i + max_dist + 1, len(b))
        for j in range(lo, hi):
            if not b_match[j] and b[j] == ca:
                a_match[i] = b_match[j] = True
                matches += 1
                break
    if matches == 0:
        return 0.0
    trans = 0
    k = 0
    for i in range(len(a)):
        if a_match[i]:
            while not b_match[k]:
                k += 1
            if a[i] != b[k]:
                trans += 1
            k += 1
    trans //= 2
    m = matches
    jaro = (m / len(a) + m / len(b) + (m - trans) / m) / 3
    prefix = 0
    for ca, cb in zip(a, b, strict=False):
        if ca == cb and prefix < 4:
            prefix += 1
        else:
            break
    return jaro + prefix * 0.1 * (1 - jaro)


def amount_level(delta_minor: int, *, rounding: int, tol: int, expected: int) -> str:
    d = abs(delta_minor)
    if d == 0:
        return "exact"
    if d <= rounding:
        return "within_rounding"
    if d <= tol:
        return "within_tol"
    if expected and d <= abs(expected) * 0.01:
        return "within_1pct"
    return "none"


def date_level(a: date | None, b: date | None, *, window: int) -> str:
    if a is None or b is None:
        return "none"
    diff = abs((a - b).days)
    if diff == 0:
        return "same_day"
    if diff <= 1:
        return "within_1"
    if diff <= window:
        return "within_window"
    return "none"


def reference_level(a: str | None, b: str | None) -> str:
    if not a or not b:
        return "none"
    if a.strip().upper() == b.strip().upper():
        return "exact"
    jw = _jaro_winkler(a.strip().upper(), b.strip().upper())
    if jw >= 0.9:
        return "jaro_hi"
    if jw >= 0.7:
        return "jaro_mid"
    return "none"


def idlink_level(shared: bool) -> str:
    return "shared" if shared else "none"


def compare_bank_to_group(
    *,
    delta_minor: int,
    expected_minor: int,
    bank_date: date | None,
    group_settled: date | None,
    bank_ref: str | None,
    group_ref: str | None,
    shared_ids: bool,
    rounding: int,
    tol: int,
    window: int,
) -> dict[str, str]:
    return {
        "amount": amount_level(delta_minor, rounding=rounding, tol=tol, expected=expected_minor),
        "date": date_level(bank_date, group_settled, window=window),
        "reference": reference_level(bank_ref, group_ref),
        "idlink": idlink_level(shared_ids),
    }

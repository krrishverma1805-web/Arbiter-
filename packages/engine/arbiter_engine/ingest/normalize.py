"""Row -> canonical Record (docs/15, docs/17 §3).

Deterministic. No LLM. Catches the data-quality problems (missing dates, bad
amounts, full card numbers) that would otherwise become fake exceptions.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from typing import Any

from dateutil import parser as dateparser

from arbiter_engine.models import Record
from arbiter_engine.money import MoneyParseError, to_minor
from arbiter_engine.specs.model import SourceSpec

_CARD_RE = re.compile(r"\b(?:\d[ -]?){13,19}\b")
# 1. a token immediately after the label "UTR" / "UTR NO" / "REF" (common bank format)
_UTR_LABELLED = re.compile(r"\b(?:UTR|RRN|REF|TXN)[\s:.#-]*(?:NO[\s:.#-]*)?([A-Z0-9]{10,25})\b")
# 2. fallback: a long alphanumeric token that contains digits (a bare reference number)
_UTR_BARE = re.compile(r"\b(?=[A-Z0-9]*\d)([A-Z]{0,6}\d[A-Z0-9]{9,24})\b")

_UNTRUSTED_DEFAULT = {"description", "notes", "narration"}


class QuarantineRow(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class NormalizeOutcome:
    __slots__ = ("record", "pii_dropped")

    def __init__(self, record: Record, pii_dropped: list[str]) -> None:
        self.record = record
        self.pii_dropped = pii_dropped


def normalize_row(
    row: dict[str, str],
    *,
    source_name: str,
    spec: SourceSpec,
    run_id: str,
    source_row_id: str,
    file_hash: str,
) -> NormalizeOutcome:
    cols = spec.columns

    def get(field: str) -> str | None:
        return _pick(row, cols.get(field, field))

    # --- amount (required) ---
    raw_amount = get("amount") or get("gross_amount") or get("order_total") or get("credit")
    if raw_amount is None or str(raw_amount).strip() == "":
        raise QuarantineRow("missing amount")
    try:
        amount_minor = to_minor(raw_amount, scale=spec.amount_scale)
        debit = get("debit")
        if debit and str(debit).strip() not in ("", "0", "0.0"):
            amount_minor = -abs(to_minor(debit, scale=spec.amount_scale))
        fee_minor = to_minor(get("fee") or 0, scale=spec.amount_scale)
        tax_minor = to_minor(get("tax") or 0, scale=spec.amount_scale)
    except MoneyParseError as exc:
        raise QuarantineRow(f"unparseable amount: {exc}") from exc

    # --- multi-currency: convert to the base currency for matching (docs/28 §1.1) ---
    row_currency = (get("currency") or "INR").upper()
    fx_orig_minor: int | None = None
    base_currency = str(spec.fx.get("base", "INR")).upper() if spec.fx else "INR"
    if row_currency != base_currency:
        rate = (spec.fx.get("rates") or {}).get(row_currency) if spec.fx else None
        if not rate:
            # a foreign-currency row with no configured rate is never silently
            # treated as base currency — it is quarantined for a human
            raise QuarantineRow(f"no FX rate for {row_currency}->{base_currency}")
        fx_orig_minor = amount_minor
        amount_minor = round(amount_minor * float(rate))
        fee_minor = round(fee_minor * float(rate))
        tax_minor = round(tax_minor * float(rate))

    # --- dates ---
    value_date = _parse_date(get("value_date") or get("order_date") or get("date"))
    posted_date = _parse_date(get("posted_date"))
    settled_at = _parse_date(get("settled_at"))
    if value_date is None and settled_at is None and posted_date is None:
        raise QuarantineRow("no parseable date on the row")

    # --- kind ---
    kind = (get("type") or spec.kind or _default_kind(source_name)).lower()
    if kind not in {
        "payment",
        "refund",
        "adjustment",
        "chargeback",
        "transfer",
        "credit",
        "order",
        "fee",
    }:
        kind = "adjustment"

    # --- external ids ---
    external_ids: dict[str, str] = {}
    for key in (
        "settlement_utr",
        "settlement_id",
        "payment_id",
        "order_id",
        "order_receipt",
        "utr",
        "dispute_id",
        "entity_id",
    ):
        val = get(key)
        if val:
            external_ids[key] = str(val).strip()
    for dkey, dexpr in spec.derive.items():
        derived = _derive(dexpr, row, cols)
        if derived:
            external_ids[dkey] = derived
    if fx_orig_minor is not None:
        external_ids["fx_orig_currency"] = row_currency
        external_ids["fx_orig_amount_minor"] = str(fx_orig_minor)

    # --- reference (normalized, used in matching) ---
    reference = _normalize_ref(get("reference") or get("narration") or external_ids.get("utr"))

    # --- untrusted fields + PII scrub ---
    untrusted_fields = set(spec.untrusted_fields) | _UNTRUSTED_DEFAULT
    untrusted: dict[str, str] = {}
    pii_dropped: list[str] = []
    for field in untrusted_fields:
        val = _pick(row, cols.get(field, field))
        if not val:
            continue
        scrubbed, had_card = _scrub_card(str(val))
        if had_card:
            pii_dropped.append(field)
        untrusted[field] = scrubbed

    # any column that looks like a bare card number anywhere -> drop + flag
    for header, val in row.items():
        if val and _CARD_RE.search(str(val)) and _luhn_ok(str(val)):
            pii_dropped.append(header)

    rec = Record(
        id=Record.make_id(source_name, source_row_id, run_id),
        run_id=run_id,
        source=source_name,
        kind=kind,  # type: ignore[arg-type]
        amount_minor=amount_minor,
        fee_minor=fee_minor,
        tax_minor=tax_minor,
        currency=base_currency if fx_orig_minor is not None else row_currency,
        value_date=value_date,
        posted_date=posted_date,
        settled_at=settled_at,
        counterparty=(get("counterparty") or get("customer") or None),
        reference=reference,
        external_ids=external_ids,
        untrusted=untrusted,
        raw={k: str(v) for k, v in row.items()},
        ingest_file_hash=file_hash,
    )
    return NormalizeOutcome(rec, sorted(set(pii_dropped)))


def _pick(row: dict[str, str], header: str) -> str | None:
    if header in row:
        return row[header]
    low = {k.lower().strip(): v for k, v in row.items()}
    return low.get(header.lower().strip())


# a settlement/bank date outside this window is corrupt or manipulated, not real
_DATE_FLOOR = date(2015, 1, 1)
_DATE_CEIL = date(2035, 1, 1)


def _parse_date(value: str | None) -> date | None:
    if value is None or value.strip() == "":
        return None
    s = value.strip()
    if s.isdigit() and len(s) >= 10:  # unix timestamp (secs or ms)
        ts = int(s)
        if ts > 1_000_000_000_000:
            ts //= 1000
        try:
            d = datetime.fromtimestamp(ts, tz=UTC).date()
        except (ValueError, OverflowError, OSError):
            raise QuarantineRow(f"unparseable timestamp: {s!r}") from None
    else:
        try:
            d = dateparser.parse(s, dayfirst=True).date()
        except (ValueError, OverflowError, TypeError):
            return None
    if not (_DATE_FLOOR <= d <= _DATE_CEIL):
        raise QuarantineRow(f"implausible date {d.isoformat()} (outside 2015–2035)")
    return d


def _default_kind(source_name: str) -> str:
    if "bank" in source_name:
        return "credit"
    if "ledger" in source_name:
        return "order"
    return "payment"


def _normalize_ref(value: Any) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", str(value)).strip().upper()
    return s or None


def _derive(expr: str, row: dict[str, str], cols: dict[str, str]) -> str | None:
    expr = expr.strip()
    m = re.fullmatch(r"extract_utr\((\w+)\)", expr)
    if m:
        src = _pick(row, cols.get(m.group(1), m.group(1)))
        return extract_utr(src)
    return None


def extract_utr(text: str | None) -> str | None:
    """Pull a bank UTR / reference number from a free-text narration.

    Prefers a token that follows an explicit label ("UTR ...", "REF NO ..."),
    then falls back to a long alphanumeric token that contains a digit. Common
    English words never contain a digit, so the fallback is safe.
    """
    if not text:
        return None
    s = text.upper()
    labelled = _UTR_LABELLED.search(s)
    if labelled:
        return labelled.group(1)
    bare = _UTR_BARE.search(s)
    return bare.group(1) if bare else None


def _scrub_card(text: str) -> tuple[str, bool]:
    had = False

    def repl(match: re.Match[str]) -> str:
        nonlocal had
        digits = re.sub(r"\D", "", match.group(0))
        if 13 <= len(digits) <= 19 and _luhn_ok(digits):
            had = True
            return "[card ****" + digits[-4:] + "]"
        return match.group(0)

    return _CARD_RE.sub(repl, text), had


def _luhn_ok(value: str) -> bool:
    digits = [int(c) for c in re.sub(r"\D", "", value)]
    if not (13 <= len(digits) <= 19):
        return False
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0

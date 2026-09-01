"""Exact money arithmetic.

All amounts in the engine are integer minor units (paise for INR). Floats never
touch the matching or decomposition path — they cause phantom exceptions
(docs/04 P6, docs/16 §9). `Decimal` is used only at the IO edge to parse and
render human-facing strings.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

_TWO_PLACES = Decimal("0.01")


class MoneyParseError(ValueError):
    """Raised when a source value cannot be parsed as an amount."""


def to_minor(value: str | int | float | Decimal, *, scale: str = "rupees_to_paise") -> int:
    """Parse a source amount into signed integer minor units.

    scale:
      - "rupees_to_paise": the value is in major units (rupees), multiply by 100
      - "already_minor" / "already_paise": the value is already in minor units
    """
    if isinstance(value, bool):  # bool is an int subclass; reject explicitly
        raise MoneyParseError(f"boolean is not an amount: {value!r}")

    if scale in ("already_minor", "already_paise"):
        if isinstance(value, float):
            if not value.is_integer():
                raise MoneyParseError(f"minor-unit amount must be integral: {value!r}")
            return int(value)
        try:
            return int(str(value).strip().replace(",", "") or "0")
        except ValueError as exc:
            raise MoneyParseError(f"cannot parse minor-unit amount: {value!r}") from exc

    if scale != "rupees_to_paise":
        raise MoneyParseError(f"unknown amount scale: {scale!r}")

    try:
        dec = Decimal(str(value).strip().replace(",", "") or "0")
    except (InvalidOperation, ValueError) as exc:
        raise MoneyParseError(f"cannot parse amount: {value!r}") from exc

    minor = (dec * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(minor)


def format_minor(minor: int, *, symbol: str = "₹") -> str:
    """Render minor units as a human string, e.g. -19470 -> '-₹194.70'."""
    sign = "-" if minor < 0 else ""
    major = (Decimal(abs(minor)) / 100).quantize(_TWO_PLACES)
    whole, _, frac = f"{major:.2f}".partition(".")
    # Indian grouping (lakh/crore) keeps the memo readable for INR.
    grouped = _indian_group(whole)
    return f"{sign}{symbol}{grouped}.{frac}"


def _indian_group(digits: str) -> str:
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    parts: list[str] = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail

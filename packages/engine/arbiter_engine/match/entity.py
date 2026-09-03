"""Counterparty entity resolution (docs/28 §1.2).

Bank narrations and ledger exports spell the same company a dozen ways —
"ACME SOFTWARE PVT LTD", "Acme Software Private Limited", "ACME SOFTWARE PVT. LTD.",
"M/S ACME SOFTWARE". `canonical_entity` folds those to one stable key so
counterparty history, the resolution memory, and the fuzzy matcher all agree
that they are the same party. Pure string normalisation — deterministic, no
LLM, no network.
"""

from __future__ import annotations

import re

# legal-form suffixes and honorifics that carry no identity
_NOISE = {
    "pvt",
    "private",
    "ltd",
    "limited",
    "llp",
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "co",
    "company",
    "plc",
    "opc",
    "and",
    "the",
    "ms",  # "M/S"
    "mss",
    "pte",
    "gmbh",
    "sa",
    "sarl",
    "bv",
}
_PREFIXES = (
    "neft cr ",
    "neft dr ",
    "rtgs cr ",
    "rtgs dr ",
    "imps ",
    "upi ",
    "ach ",
    "to ",
    "from ",
)
_TOKEN = re.compile(r"[a-z0-9]+")


def canonical_entity(name: str | None) -> str:
    """A stable, comparable key for a counterparty. Empty string for no name."""
    if not name:
        return ""
    s = name.strip().lower()
    for p in _PREFIXES:
        if s.startswith(p):
            s = s[len(p) :]
    s = s.replace("&", " and ").replace("/", " ")
    tokens = [t for t in _TOKEN.findall(s) if t not in _NOISE and not t.isdigit()]
    # drop a trailing single letter left by "pvt. ltd." style punctuation
    tokens = [t for t in tokens if len(t) > 1]
    return " ".join(tokens)


def same_entity(a: str | None, b: str | None) -> bool:
    ca, cb = canonical_entity(a), canonical_entity(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    # one being a token-subset of the other (an abbreviation / a longer legal name)
    ta, tb = set(ca.split()), set(cb.split())
    return bool(ta) and bool(tb) and (ta <= tb or tb <= ta)

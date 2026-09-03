"""Deterministic prompt-injection scanner (docs/14 C2).

Runs over untrusted record fields BEFORE any exception is sent to the agent.
A hit tags the exception SECURITY_REVIEW and routes it straight to a human —
it never reaches the model. This is defense in depth: the proposal-only tool
surface (docs/14 C3) is the real backstop.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(ignore|disregard|forget|override)\s+(all\s+|the\s+)?"
        r"(previous|prior|above|earlier|these|any)\s+"
        r"(instructions?|rules?|prompts?|context|messages?|directives?)",
        re.I,
    ),
    re.compile(r"disregard\s+(the\s+)?(system|previous|above)", re.I),
    re.compile(r"you\s+are\s+(now|actually|really)\s+", re.I),
    re.compile(r"\bnew\s+(instructions?|task|role|system\s+prompt)\b", re.I),
    re.compile(
        r"\b(mark|treat|set|flag|consider)\b.{0,30}\b"
        r"(as\s+)?(reconciled|resolved|matched|verified|approved|complete|done|clean)\b",
        re.I,
    ),
    re.compile(r"\bapprove\s+(this|all|every|the)\b", re.I),
    re.compile(r"\b(you|arbiter)\s+(are|is)\s+authori[sz]ed\s+to\b", re.I),
    re.compile(r"</?(system|assistant|user|untrusted[- ]record[- ]data)>", re.I),
    re.compile(r"^\s{0,4}(system|assistant|developer)\s*[:>]", re.I | re.M),
    re.compile(r"\bprompt\s*injection\b", re.I),
    re.compile(r"[‪-‮⁦-⁩]"),  # unicode bidi / isolate controls
)


def injection_signal(*texts: str | None) -> str | None:
    """Return a short reason string if any text looks like an injection, else None."""
    for text in texts:
        if not text:
            continue
        for pat in _PATTERNS:
            if pat.search(text):
                return f"matched {pat.pattern[:48]!r}"
    return None

"""Deterministic prompt-injection scanner (docs/14 C2).

Runs over untrusted record fields BEFORE any exception is sent to the agent.
A hit tags the exception SECURITY_REVIEW and routes it straight to a human —
it never reaches the model. This is defense in depth: the proposal-only tool
surface (docs/14 C3) is the real backstop.
"""

from __future__ import annotations

import re

_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.I),
    re.compile(r"disregard\s+(the\s+)?(system|previous|above)", re.I),
    re.compile(r"you\s+are\s+now\s+", re.I),
    re.compile(r"\bnew\s+instructions?\b", re.I),
    re.compile(r"mark\s+(this|every|all).{0,40}\b(reconciled|resolved|matched)\b", re.I),
    re.compile(r"</?(system|assistant|user|untrusted[- ]record[- ]data)>", re.I),
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

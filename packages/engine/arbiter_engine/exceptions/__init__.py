"""Exception taxonomy, the injection scanner, and the deterministic classifier
(docs/15 §3, docs/14 C2).

M1: a deterministic classifier over a fixed set of built-in predicates + the
injection scanner. M2 replaces the built-ins with the spec's safe-AST rule
engine (docs/adr/0003) so customers and the learning loop can author rules.
"""

from arbiter_engine.exceptions.classify import build_exceptions
from arbiter_engine.exceptions.injection import injection_signal
from arbiter_engine.exceptions.taxonomy import TAXONOMY

__all__ = ["TAXONOMY", "build_exceptions", "injection_signal"]

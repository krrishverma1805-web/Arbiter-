"""The Close Memo — the auditor-ready assurance artifact (docs/08 §4, docs/20 §2.6).

`arbiter memo <run-id>` renders a self-contained HTML document: the period, the
sources, the totals tied, coverage by rupees, the settlement decomposition
summary, every exception with its status and resolution, and the audit-trail
hash so anyone can later `arbiter verify` that the memo matches an untampered log.
"""

from arbiter_engine.memo.render import render_memo

__all__ = ["render_memo"]

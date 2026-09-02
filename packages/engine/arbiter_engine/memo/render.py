"""Render a run into a self-contained Close Memo (HTML)."""

from __future__ import annotations

import html
from datetime import UTC, datetime
from typing import Any

from arbiter_engine.events.fold import RunProjection
from arbiter_engine.money import format_minor

_CSS = " ".join(
    line.strip()
    for line in """
:root{--ink:#1c1917;--muted:#78716c;--line:#e7e5e4;--ok:#2f9e44;--warn:#e8a33d}
*{box-sizing:border-box}
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);
     max-width:820px;margin:40px auto;padding:0 24px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:15px;margin:28px 0 8px;text-transform:uppercase;
   letter-spacing:.04em;color:var(--muted)}
.sub{color:var(--muted);margin:0 0 24px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td.num{text-align:right;font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace}
.tot td{font-weight:600;border-top:2px solid var(--ink)}
.hash{font-family:ui-monospace,monospace;font-size:11px;color:var(--muted);word-break:break-all}
.pill{font-size:11px;padding:1px 6px;border:1px solid var(--line);border-radius:10px}
.resolved{color:var(--ok)} .open{color:var(--warn)}
.signoff{margin-top:40px;display:flex;gap:48px}
.signoff div{flex:1;border-top:1px solid var(--ink);padding-top:6px;
             font-size:12px;color:var(--muted)}
@media print{body{margin:0}}
""".splitlines()
    if line.strip()
)


def _e(x: Any) -> str:
    return html.escape(str(x))


def render_memo(
    proj: RunProjection,
    *,
    spec_name: str,
    period: tuple[str, str] | None,
    terminal_hash: str,
    scorecard: dict[str, Any] | None = None,
    mask_accounts: bool = True,
) -> str:
    p0, p1 = period or ("—", "—")
    matched = len(proj.matched_record_ids)
    total = proj.record_count

    # decomposition roll-up
    comp: dict[str, int] = {}
    tied = 0
    for d in proj.decompositions:
        for k, v in d.components.items():
            comp[k] = comp.get(k, 0) + v
        tied += d.actual_minor
    gross = comp.get("gross", 0)
    mdr = comp.get("mdr", 0)
    gst = comp.get("gst_on_mdr", 0)
    refunds = comp.get("refunds", 0)

    by_status: dict[str, int] = {}
    for e in proj.exceptions:
        by_status[e.status] = by_status.get(e.status, 0) + 1

    rows_exc = "\n".join(
        f"<tr><td>{_e(e.category or '—')}</td>"
        f"<td class=num>{format_minor(e.amount_impact_minor)}</td>"
        f"<td>{_e(e.classified_by)}</td>"
        f"<td>{_status(e)}</td>"
        f"<td>{_e((e.resolution or {}).get('action', '—'))}</td></tr>"
        for e in proj.exceptions
    )

    sc = ""
    if scorecard:
        m = scorecard.get("matching", {})
        amr = m.get("auto_match_rate", 0)
        fmr = m.get("false_match_rate", 0)
        cov = m.get("dollar_coverage", 0)
        sc = (
            f"<tr><td>auto-tied</td><td class=num>{amr:.1%}</td></tr>"
            f"<tr><td>false-match rate</td><td class=num>{fmr:.2%}</td></tr>"
            f"<tr><td>&#8377; coverage</td><td class=num>{cov:.1%}</td></tr>"
        )

    return f"""<!doctype html><html><head><meta charset=utf-8>
<title>Close Memo — {_e(spec_name)}</title><style>{_CSS}</style></head><body>
<h1>Reconciliation Close Memo</h1>
<p class=sub>{_e(spec_name)} &middot; period {_e(p0)} to {_e(p1)} &middot;
generated {datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")}</p>

<h2>Result</h2>
<table>
<tr><td>records reconciled</td><td class=num>{matched} / {total}</td></tr>
<tr><td>settlement batches</td><td class=num>{len(proj.decompositions)}</td></tr>
<tr><td>exceptions</td><td class=num>{len(proj.exceptions)}
 ({", ".join(f"{k}: {v}" for k, v in sorted(by_status.items())) or "—"})</td></tr>
{sc}
</table>

<h2>Settlement decomposition</h2>
<table>
<tr><td>gross payments</td><td class=num>{format_minor(gross)}</td></tr>
<tr><td>MDR</td><td class=num>{format_minor(-mdr)}</td></tr>
<tr><td>GST on MDR</td><td class=num>{format_minor(-gst)}</td></tr>
<tr><td>refunds</td><td class=num>{format_minor(-refunds)}</td></tr>
<tr class=tot><td>net settled (to bank)</td><td class=num>{format_minor(tied)}</td></tr>
</table>

<h2>Exception register</h2>
<table><thead><tr><th>category</th><th class=num>impact</th><th>classified by</th>
<th>status</th><th>resolution</th></tr></thead><tbody>
{rows_exc or "<tr><td colspan=5>none</td></tr>"}
</tbody></table>

<h2>Audit trail</h2>
<p>This memo corresponds to run <span class=hash>{_e(proj.run_id)}</span>.<br>
Terminal event hash: <span class=hash>{_e(terminal_hash)}</span><br>
Run <code>arbiter verify {_e(proj.run_id)}</code> to confirm the event log is intact.</p>
{"<p class=sub>Account numbers masked.</p>" if mask_accounts else ""}

<div class=signoff><div>Prepared by</div><div>Reviewed by</div></div>
</body></html>"""


def _status(e: Any) -> str:
    cls = "resolved" if e.status in ("resolved", "wont_fix") else "open"
    return f'<span class="pill {cls}">{_e(e.status)}</span>'

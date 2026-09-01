"""Fence untrusted record content before it reaches the model (docs/14 C1).

Every string that originates from a record — description, notes, bank narration —
is wrapped so the model treats it as data, never as an instruction. The system
prompt declares the convention; this module produces the wrapped form and never
lets untrusted text into a tool-call argument Arbiter constructs.
"""

from __future__ import annotations

import html


def fence(field: str, record_id: str, content: str | None) -> str:
    if not content:
        return ""
    safe = html.escape(str(content), quote=False).replace("<", "‹").replace(">", "›")
    return (
        f'<untrusted-record-data field="{field}" record="{record_id}">'
        f"{safe}</untrusted-record-data>"
    )

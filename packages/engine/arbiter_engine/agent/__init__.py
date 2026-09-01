"""The investigation agent (docs/12, docs/19, ADR-0001, ADR-0004).

A bounded, hybrid-orchestration agent: the deterministic skeleton invokes it once
per ambiguous/unexplained exception. The agent plans an investigation, gathers
evidence with read-only tools, tests a hypothesis, and either proposes a
categorization (a gated proposal a human confirms) or escalates with the single
question a human should answer.

No tool the agent can call mutates a match, a record, a ledger entry, or money.
"""

from arbiter_engine.agent.investigator import Investigation, investigate
from arbiter_engine.agent.schemas import Escalate, Proposal

__all__ = ["Escalate", "Investigation", "Proposal", "investigate"]

"""Arbiter HTTP API (docs/20 §1).

Wraps the engine: start runs, fetch scorecards / matches / exceptions, open the
evidence-drawer payload, apply resolutions, verify and replay. The cockpit
(web/) talks to this; so can a customer's pipeline.
"""

__version__ = "0.0.1"

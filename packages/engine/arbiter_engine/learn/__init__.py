"""The learning loop (docs/02 §5.3, docs/06 G).

When a human resolves an exception, Arbiter synthesises a candidate `when -> classify
/ resolve` rule from the exception's shape. The rule is reviewed as a git-style spec
diff (`arbiter rules pending` / `arbiter rules merge`) before it takes effect. Next
cycle, that pattern auto-classifies — so month 3 has a smaller queue than month 1.
"""

from arbiter_engine.learn.spec_merge import merge_rules, pending_rules
from arbiter_engine.learn.synthesize import draft_rule_from_resolution

__all__ = ["draft_rule_from_resolution", "merge_rules", "pending_rules"]

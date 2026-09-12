"""Derive the audited operator windows from the v2 rule set.

The predicates, the evaluator and the check all live in
:mod:`sybilkit.farm_windows`, which depends on no rule set and can therefore be
vendored on its own. This module is the one piece that needs the rules: it asks
``sk_v2`` for the windows it actually built, then makes the published predicates
prove they re-derive that same membership.
"""

from __future__ import annotations

from ..farm_windows import PREDICATES, evaluate, members, require_non_empty, verify
from .sk_v2 import build_extra

__all__ = ["PREDICATES", "derive", "evaluate", "members", "require_non_empty", "verify"]


def derive(dataset) -> dict[str, frozenset[str]]:
    """Every audited window over one dataset, verified against its predicates."""
    # ``hour_saved`` only feeds the rescuer metric, which windows do not use.
    windows = {
        name: frozenset(group)
        for name, group in build_extra(dataset, {"hour_saved": []})["farm_windows"].items()
    }
    verify(windows, dataset)
    require_non_empty(windows)
    return windows

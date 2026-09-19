"""Shim for the old import path.

``widgets/surf/_rowfit.py`` moved to ``widgets/rowfit.py`` (Branch 2 of
``docs/refactor_programme_2026_09.md``): the shared row-fit machinery is
imported by pool4/swarm widgets outside ``widgets/surf/``, and a shared
module may not live inside one dashboard's own package. This file re-exports
every public name so the modules and tests still importing this path are
untouched. Branch 3 removes it once every importer has moved to the new
path.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.rowfit import (
    GAP,
    budget,
    clip,
    pad,
    row_cols,
    tier_for,
)

__all__ = [
    "GAP",
    "budget",
    "clip",
    "pad",
    "row_cols",
    "tier_for",
]

"""Compatibility exports for the shared terminal table-tier helpers.

Curator established these helpers and its widgets intentionally keep their
existing import path.  The implementation is now screen-neutral so FWA and
other dashboards can reuse it without depending on the curator package.
"""

from maxpane_dashboard.widgets.table_tiers import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    tier_cost,
    title_with_hint,
    with_optional_suffix,
)

__all__ = [
    "WIDEN_HINT",
    "cells",
    "pick_tier",
    "install_columns",
    "tier_cost",
    "title_with_hint",
    "with_optional_suffix",
]

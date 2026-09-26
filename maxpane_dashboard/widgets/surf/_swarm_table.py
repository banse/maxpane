"""Re-export shim: ``SwarmTableBase`` lives in ``widgets/swarm_table.py`` since 2026-09-26.

The base was hoisted (rules/widgets.md: a helper two packages need is hoisted,
never re-declared) so the PEPEPANE dashboard can subclass it without importing from
``widgets/surf/``. Every surf body and test keeps this import path; nothing is
declared here.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.swarm_table import *  # noqa: F401,F403
from maxpane_dashboard.widgets.swarm_table import (  # noqa: F401
    CELL_PADDING,
    UNAVAILABLE_ITEM,
    SwarmTableBase,
    _EMPTY_ITEM,
    table_cols,
)
from maxpane_dashboard.widgets.swarm_table import __all__  # noqa: F401

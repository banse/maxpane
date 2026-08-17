"""Widgets for the curator dashboard — THE LIST (PRD §4).

Seven render-only widgets, one per slot of ``screens/curator.CuratorScreen``:

======================  ====================================================
Widget                  Slot
======================  ====================================================
``CuratorHero``         hero row, full width — CLOCK · THE LIST · CURVE
``CuratorLeaderboard``  middle left — top 10 by points
``CuratorSparklines``   middle right, rail top — hourly volume + contributors
``CuratorSignals``      middle right, rail bottom — the seven-row rail
``CuratorActivity``     bottom left — newest-first deposit feed
``CuratorClosestCalls`` bottom right (``c`` swap) — judged hours by margin
``CuratorClusters``     bottom right (``c`` swap) — fan-out patterns
======================  ====================================================

The classes are re-exported here because the package root is the import
surface the screen and its tests use, exactly as ``widgets/surf`` and
``widgets/talismans`` do it.  The rendered interface strings ride along —
panel titles and every explicit unavailable line — so the screen tests
import them instead of retyping the literals they assert against.

These widgets take **primitives only** and import nothing from ``data/`` or
``analytics/`` (AST-pinned by ``tests/widgets/test_curator_widgets.py``), so
this package is safe to import with no manager, no cache and no network.
"""

from ._fmt import ADDR_COLS, DASH, EMDASH, NO_STAMP
from .hero import PHASE_UNAVAILABLE, CuratorHero
from .leaderboard import (
    LEADERBOARD_EMPTY,
    LEADERBOARD_TITLE,
    LEADERBOARD_UNAVAILABLE,
    CuratorLeaderboard,
)

__all__ = [
    "ADDR_COLS",
    "DASH",
    "EMDASH",
    "NO_STAMP",
    "LEADERBOARD_EMPTY",
    "LEADERBOARD_TITLE",
    "LEADERBOARD_UNAVAILABLE",
    "PHASE_UNAVAILABLE",
    "CuratorHero",
    "CuratorLeaderboard",
]

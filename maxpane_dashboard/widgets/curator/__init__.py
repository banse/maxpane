"""Widgets for the curator dashboard — THE LIST (PRD §4).

Render-only widgets for every slot and alternate view of
``screens/curator.CuratorScreen``:

======================  ====================================================
Widget                  Slot
======================  ====================================================
``CuratorHero``         hero row, full width — CLOCK · THE LIST · CURVE
``CuratorListHero``     ``l`` hero — raw list · configured wallet · clean list
``CuratorLeaderboard``  middle left — top 10 by points
``CuratorSparklines``   middle right, rail top — hourly volume + contributors
``CuratorSignals``      middle right, rail bottom — the seven-row rail
``CuratorActivity``     bottom left — newest-first deposit feed
``CuratorClosestCalls`` bottom right (``c`` swap) — judged hours by margin
``CuratorClusters``     bottom right (``c`` swap) — fan-out patterns
``CuratorRawList``      ``l`` view, left — complete raw record list
``CuratorCleanedList``  ``l`` view, right — complete cleaned record list
======================  ====================================================

The classes are re-exported here because the package root is the import
surface the screen and its tests use, exactly as ``widgets/surf`` and
``widgets/talismans`` do it.  The rendered interface strings ride along —
panel titles and every explicit unavailable line — so the screen tests
import them instead of retyping the literals they assert against.

One function rides along with them: :func:`measure_signals_width`, which
answers "how many columns does the signal rail need for *this* payload".
The rail is the widest panel in the package and the one a screen budgets its
slot grid against, and that question has two answers — see
``signals.SIGNALS_FULL_WIDTH``, which is the worst case over every magnitude
the contract can produce and is **not** the number to size a slot from.

These widgets take **primitives only** and import nothing from ``data/`` or
``analytics/`` (AST-pinned by ``tests/widgets/test_curator_widgets.py``), so
this package is safe to import with no manager, no cache and no network.
"""

from ._fmt import ADDR_COLS, DASH, EMDASH, NO_STAMP
from .activity import (
    ACTIVITY_EMPTY,
    ACTIVITY_TITLE,
    ACTIVITY_UNAVAILABLE,
    CuratorActivity,
)
from .cleaned_list import (
    CLEAN_LIST_EMPTY,
    CLEAN_LIST_TITLE,
    CLEAN_LIST_UNAVAILABLE,
    YOU_CLEAN_UNSET,
    CuratorCleanList,
)
from .operators import (
    OPERATORS_EMPTY,
    OPERATORS_TITLE,
    OPERATORS_UNAVAILABLE,
    CuratorOperators,
)
from .segments import (
    SEGMENTS_EMPTY,
    SEGMENTS_TITLE,
    SEGMENTS_UNAVAILABLE,
    CuratorSegments,
)
from .wallet import (
    AT_THE_CAP,
    CAPPED_MARK,
    LADDER_TITLE,
    LADDER_UNAVAILABLE,
    NEXT_TITLE,
    NOT_ON_THE_LIST,
    NO_LADDER,
    STANDING_TITLE,
    TOP_OF_THE_LIST,
    CuratorWalletLadder,
    CuratorWalletNext,
    CuratorWalletStanding,
    CuratorWalletTarget,
    CuratorWalletAddress,
    CuratorWalletHero,
    HOLDS_RANK,
    TAKES_RANK,
    TARGET_TITLE,
    WALLET_TITLE,
    NO_WALLET_SET,
    NO_ENS,
    ENS_PENDING,
)
from .closest_calls import (
    CLOSEST_CALLS_TITLE,
    CLOSEST_CALLS_UNAVAILABLE,
    NO_JUDGED_HOURS,
    CuratorClosestCalls,
)
from .clusters import (
    CLUSTERS_EMPTY,
    CLUSTERS_TITLE,
    CLUSTERS_UNAVAILABLE,
    CuratorClusters,
)
from .hero import PHASE_UNAVAILABLE, CuratorHero
from .list_hero import CuratorListHero
from .list_filter import CuratorListFilterEditor
from .signals import (
    NEVER_SAVED,
    NO_WALLET,
    NO_WALLET_PARTS,
    SIGNAL_KEYS,
    SIGNAL_LABELS,
    SIGNALS_FULL_WIDTH,
    SIGNALS_TITLE,
    UNKNOWN_GLYPH,
    CuratorSignals,
    measure_signals_width,
)
from .sparklines import SPARKLINES_TITLE, WAITING, CuratorSparklines
from .leaderboard import (
    LEADERBOARD_EMPTY,
    LEADERBOARD_TITLE,
    LEADERBOARD_UNAVAILABLE,
    CuratorLeaderboard,
)
from .lists import (
    CLEANED_LIST_TITLE,
    FILTERED_LIST_EMPTY,
    FILTERED_LIST_TITLE,
    FILTERED_LIST_UNAVAILABLE,
    RAW_LIST_TITLE,
    CuratorCleanedList,
    CuratorFilteredList,
    CuratorRawList,
    ListOrderChanged,
)

__all__ = [
    "ADDR_COLS",
    "DASH",
    "EMDASH",
    "NO_STAMP",
    "ACTIVITY_EMPTY",
    "ACTIVITY_TITLE",
    "ACTIVITY_UNAVAILABLE",
    # the `f` analysis view (WP4)
    "CuratorOperators",
    "CuratorSegments",
    "CuratorCleanList",
    "OPERATORS_TITLE",
    "OPERATORS_EMPTY",
    "OPERATORS_UNAVAILABLE",
    "SEGMENTS_TITLE",
    "SEGMENTS_EMPTY",
    "SEGMENTS_UNAVAILABLE",
    "CLEAN_LIST_TITLE",
    "CLEAN_LIST_EMPTY",
    "CLEAN_LIST_UNAVAILABLE",
    "YOU_CLEAN_UNSET",
    "CLOSEST_CALLS_TITLE",
    "CLOSEST_CALLS_UNAVAILABLE",
    "CLUSTERS_EMPTY",
    "CLUSTERS_TITLE",
    "CLUSTERS_UNAVAILABLE",
    "LEADERBOARD_EMPTY",
    "LEADERBOARD_TITLE",
    "LEADERBOARD_UNAVAILABLE",
    "PHASE_UNAVAILABLE",
    "CuratorActivity",
    "CuratorClosestCalls",
    # the `y` wallet view
    "CuratorWalletLadder",
    "CuratorWalletStanding",
    "CuratorWalletNext",
    "CuratorWalletTarget",
    "CuratorWalletAddress",
    "CuratorWalletHero",
    "LADDER_TITLE",
    "STANDING_TITLE",
    "NEXT_TITLE",
    "TARGET_TITLE",
    "WALLET_TITLE",
    "NO_WALLET_SET",
    "NO_ENS",
    "ENS_PENDING",
    "HOLDS_RANK",
    "TAKES_RANK",
    "NO_LADDER",
    "NOT_ON_THE_LIST",
    "LADDER_UNAVAILABLE",
    "CAPPED_MARK",
    "AT_THE_CAP",
    "TOP_OF_THE_LIST",
    "CuratorClusters",
    "CuratorHero",
    "CuratorListHero",
    "CuratorListFilterEditor",
    "NEVER_SAVED",
    "NO_JUDGED_HOURS",
    "NO_WALLET",
    "NO_WALLET_PARTS",
    "SIGNALS_FULL_WIDTH",
    "SIGNALS_TITLE",
    "SIGNAL_KEYS",
    "SIGNAL_LABELS",
    "SPARKLINES_TITLE",
    "UNKNOWN_GLYPH",
    "WAITING",
    "CuratorLeaderboard",
    "CuratorRawList",
    "CuratorCleanedList",
    "CuratorFilteredList",
    "ListOrderChanged",
    "RAW_LIST_TITLE",
    "CLEANED_LIST_TITLE",
    "FILTERED_LIST_TITLE",
    "FILTERED_LIST_EMPTY",
    "FILTERED_LIST_UNAVAILABLE",
    "CuratorSignals",
    "CuratorSparklines",
    "measure_signals_width",
]

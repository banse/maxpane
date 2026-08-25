"""Widgets for the surf dashboard (surfsurf.eth mission control).

Six render-only widgets, one per PRD §5 panel group:

======================  ===================================================
Widget                  Slot in ``screens/surf.SurfScreen``
======================  ===================================================
``SurfHero``            hero row, left (3fr) -- experiment status
``SurfSignals``         hero row, right (2fr) -- the six detectors
``SurfFeed``            middle row -- announce channel (``c`` swaps it out)
``SurfDevActivity``     middle row -- dev wallets (``c`` swaps it in)
``SurfMarket``          bottom row, left -- price, parity, supply
``SurfNft``             bottom row, right -- IDMD collection
======================  ===================================================

Plus five more (v4 migration, 2026-08-23 / 2026-08-25) that exist in this
package and are exported here, but have **no slot yet** -- a later task wires
them behind the new ``l`` view (``screens/surf.py`` is that task's file, not
this one's):

=========================  ===============================================
Widget                     Data
=========================  ===============================================
``SurfLaunchpadCoins``     ranked coin table -- ticker, name, creator, etc.
``SurfCurveFlow``          aggregate swap/trader/creator-revenue numbers
``SurfBurnPipeline``       the permissionless bridge-and-burn executor's state
``SurfLaunchpadActivity``  the launchpad's own event feed -- buys, sells, launches
``SurfBurnkeepers``        leaderboard of callers of the burn executor
=========================  ===============================================

The classes are re-exported here because the package root is the import
surface the screen and its tests use, exactly as ``widgets/ttt`` and
``widgets/talismans`` do it and as ``screens/fwa.py`` consumes
``maxpane_dashboard.widgets.fwa``.

``DETECTOR_LABELS``, ``FEED_TITLE`` and ``FLOOR_UNAVAILABLE`` ride along:
they are *rendered interface strings* asserted against composited output by
the screen WP and by the app-level acceptance tests, so consumers import
them instead of retyping the literals.

These widgets take primitives only and import nothing from ``data/`` or
``analytics/``, so this package is safe to import with no manager, no cache
and no network present (pinned by ``tests/widgets/test_surf_widget_contract.py``).
"""

from .activity import SurfDevActivity
from .burnkeepers import SurfBurnkeepers
from .feed import FEED_TITLE, SurfFeed
from .hero import SurfHero
from .launchpad import SurfBurnPipeline, SurfCurveFlow, SurfLaunchpadCoins
from .launchpad_activity import SurfLaunchpadActivity
from .market import SurfMarket
from .nft import FLOOR_UNAVAILABLE, SurfNft
from .signals import DETECTOR_LABELS, SurfSignals

__all__ = [
    "DETECTOR_LABELS",
    "FEED_TITLE",
    "FLOOR_UNAVAILABLE",
    "SurfBurnPipeline",
    "SurfBurnkeepers",
    "SurfCurveFlow",
    "SurfDevActivity",
    "SurfFeed",
    "SurfHero",
    "SurfLaunchpadActivity",
    "SurfLaunchpadCoins",
    "SurfMarket",
    "SurfNft",
    "SurfSignals",
]

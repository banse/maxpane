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

And five more again for the ``p`` POOL4 view (2026-09-01), wired by
``screens/surf.py`` into a **third** body on the same composed-once-hidden
contract the ``l`` body uses:

=====================  ================================================
Widget                 Data
=====================  ================================================
``SurfPool4Split``     where a pool4 fee went, measured vs claimed
``SurfPool4Flow``      recent pool4 swaps and each one's three legs
``SurfPool4Ratchet``   the reserve between its floor and its ceiling
``SurfPool4Vault``     sIMD share price, drip rate and runway
``SurfPool4Hatches``   discovery state, the five addresses, the levers
=====================  ================================================

Two of those rows moved when pool4 went live on mainnet (2026-09-02): THE
RATCHET gained the inventory ceiling above the reserve (it used to have only
a floor and the backstop), and HATCHES gained a fifth address because the
reward path now runs through a Distributor before the Dripper.

And five more again for the ``4`` POOL4 MARKET view (2026-09-11) -- a
**fourth** body, wired by ``screens/surf.py`` on the same
composed-once-hidden contract, and the first surf body that swaps the hero
with it (curator's per-mode hero pattern):

=========================  ============================================
Widget                     Data
=========================  ============================================
``SurfPool4UserHero``      IMD PRICE / DOWNSIDE BID / STAKING
``SurfPool4UStakers``      the sIMD vault's depositors and its top-3 share
``SurfPool4UBurn``         daily burn sparkline, pace, retired share
``SurfPool4USignals``      the four market states a reader acts on
``SurfPool4UDepth``        IF IMD FALLS -- the depth ladder
=========================  ============================================

**Only the five classes are re-exported here, for the reason the paragraph
above gives and one more.** Every one of these modules has its own ``TITLE``
and ``UNAVAILABLE_LINE`` too, so a bare re-export would rebind
``SurfLaunchpadActivity``'s -- and ``pool4u_stakers``/``pool4u_burn`` would
then collide with each other as well. Their tests import those constants from
their own modules, which is where a per-panel string belongs.

**Only the five classes are re-exported, and no pool4 module constant is.**
That is the collision the paragraph below predicted arriving: ``pool4_flow``
has its own ``TITLE``/``UNAVAILABLE_LINE``/``EMPTY_LINE`` and so do three of
its siblings, so re-exporting any of them bare would silently rebind
``SurfLaunchpadActivity``'s -- which the app-level acceptance tests assert
against composited output. The pool4 tests import those constants from their
own modules instead, which is where a per-panel string belongs anyway.

``DETECTOR_LABELS``, ``FEED_TITLE`` and ``FLOOR_UNAVAILABLE`` ride along:
they are *rendered interface strings* asserted against composited output by
the screen WP and by the app-level acceptance tests, so consumers import
them instead of retyping the literals. ``TITLE``, ``UNAVAILABLE_LINE``,
``EMPTY_LINE`` and ``KIND_WORDS`` (``SurfLaunchpadActivity``'s own module
constants) ride along for the same reason -- unlike ``FEED_TITLE``/
``FLOOR_UNAVAILABLE``, these four keep their bare, module-local names on the
way out, so a future re-export of another widget's identically-named
constants (``activity.py`` also has its own ``TITLE``/``UNAVAILABLE_LINE``,
unexported here) would collide and has to be aliased when that day comes --
it is not a collision yet.

These widgets take primitives only and import nothing from ``data/`` or
``analytics/``, so this package is safe to import with no manager, no cache
and no network present (pinned by ``tests/widgets/test_surf_widget_contract.py``).
"""

from .activity import SurfDevActivity
from .burnkeepers import SurfBurnkeepers
from .feed import FEED_TITLE, SurfFeed
from .hero import SurfHero
from .launchpad import SurfBurnPipeline, SurfCurveFlow, SurfLaunchpadCoins
from .launchpad_activity import (
    EMPTY_LINE,
    KIND_WORDS,
    SurfLaunchpadActivity,
    TITLE,
    UNAVAILABLE_LINE,
)
from .market import SurfMarket
from .nft import FLOOR_UNAVAILABLE, SurfNft
from .pool4_flow import SurfPool4Flow
from .pool4_hatches import SurfPool4Hatches
from .pool4_ratchet import SurfPool4Ratchet
from .pool4_split import SurfPool4Split
from .pool4_vault import SurfPool4Vault
from .pool4u_burn import SurfPool4UBurn
from .pool4u_depth import SurfPool4UDepth
from .pool4u_hero import SurfPool4UserHero
from .pool4u_signals import SurfPool4USignals
from .pool4u_stakers import SurfPool4UStakers
from .signals import DETECTOR_LABELS, SurfSignals
from .swarm_agent_hero import SurfSwarmAgentHero
from .swarm_capability import SurfSwarmCapability
from .swarm_hero import SurfSwarmHero
from .swarm_inflight import SurfSwarmInFlight
from .swarm_launches import SurfSwarmLaunches
from .swarm_roster import SurfSwarmRoster
from .swarm_seat_feedback import SurfSwarmSeatFeedback
from .swarm_seat_record import SurfSwarmSeatRecord
from .swarm_seat_verdicts import SurfSwarmSeatVerdicts
from .swarm_sites import SurfSwarmSites
from .swarm_throughput import SurfSwarmThroughput

__all__ = [
    "DETECTOR_LABELS",
    "EMPTY_LINE",
    "FEED_TITLE",
    "FLOOR_UNAVAILABLE",
    "KIND_WORDS",
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
    "SurfPool4Flow",
    "SurfPool4Hatches",
    "SurfPool4Ratchet",
    "SurfPool4Split",
    "SurfPool4UBurn",
    "SurfPool4UDepth",
    "SurfPool4USignals",
    "SurfPool4UStakers",
    "SurfPool4UserHero",
    "SurfPool4Vault",
    "SurfSignals",
    "SurfSwarmAgentHero",
    "SurfSwarmCapability",
    "SurfSwarmHero",
    "SurfSwarmInFlight",
    "SurfSwarmLaunches",
    "SurfSwarmRoster",
    "SurfSwarmSeatFeedback",
    "SurfSwarmSeatRecord",
    "SurfSwarmSeatVerdicts",
    "SurfSwarmSites",
    "SurfSwarmThroughput",
    "TITLE",
    "UNAVAILABLE_LINE",
]

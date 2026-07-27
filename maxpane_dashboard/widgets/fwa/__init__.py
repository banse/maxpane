"""Fake World Assets (FWA) dashboard widgets.

Seven widgets, one per PRD §5 panel, matching the seven entries of
``FWA_WIDGET_SIGNATURES`` in ``maxpane_dashboard.data.fwa_models``:

======================  ==============================================
Widget                  Slot in :class:`~maxpane_dashboard.screens.fwa.FWAScreen`
======================  ==============================================
``FWAHeroMetrics``      hero row -- PULL EV · PRICE · CROWN
``FWAOddsBoard``        middle row, left (3fr)
``FWASparkline``        middle row, right column, top
``FWASignals``          middle row, right column, bottom
``FWAActivityFeed``     bottom row, left (3fr)
``FWAChaseBoard``       bottom row, centre (2fr)
``FWASettlementTable``  bottom row, right (2fr)
======================  ==============================================

``FWAHeroBox`` is re-exported alongside them for the same reason
``TalismansHeroBox`` is: the theme block (WP-16) styles it by class name and
tests reach for it when asserting the hero card's vertical budget.

**Its ``padding`` must stay ``0 2``.** ``FWAHeroBox`` is ``height: 7`` with a
``solid`` border, which leaves four content rows -- exactly the four lines a
hero card carries (title, band, second line, coverage badge). The Talismans
equivalent uses ``padding: 1 2`` and silently loses its fourth line today; for
FWA that fourth line is the PULL EV *coverage badge*, and an EV number rendered
without its coverage is the one thing PRD §3 forbids outright.

These widgets take primitives only and import nothing from the data layer, so
this package is safe to import without any manager or network being present.
"""

from .fwa_activity_feed import FWAActivityFeed
from .fwa_chase_board import FWAChaseBoard
from .fwa_hero_metrics import FWAHeroBox, FWAHeroMetrics
from .fwa_odds_board import FWAOddsBoard
from .fwa_settlement_table import FWASettlementTable
from .fwa_signals import FWASignals
from .fwa_sparkline import FWASparkline

__all__ = [
    "FWAActivityFeed",
    "FWAChaseBoard",
    "FWAHeroBox",
    "FWAHeroMetrics",
    "FWAOddsBoard",
    "FWASettlementTable",
    "FWASignals",
    "FWASparkline",
]

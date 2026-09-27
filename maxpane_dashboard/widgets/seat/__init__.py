"""Widgets for the PEPEPANE dashboard (the pepepane fork; spec §8).

Seven panels on ``widgets/panels.py`` bases, one per §8 panel, plus the nested
sparkline strip COST composes. The package root is the import surface
``screens/seat.py`` and the tests use, as ``widgets/ttt`` and ``widgets/talismans``
do it. Tasks 8.2–8.7 add one import each; Task 8.7 completes ``__all__`` to the
eight names contract §C.15 fixes, and ``tests/widgets/test_panels.py``
counts the seven ``update_data`` classes among them (``MIGRATED_PACKAGES["seat"] = 7``).

Purity (spec §14): every module here imports only ``maxpane_dashboard.widgets.*``
and ``analytics.{seat_redact, seat_signals, seat_tiers, seat_cost, seat_auth}``;
never ``maxpane_dashboard.data``, ``subprocess``, ``socket`` or ``httpx``.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.seat.config import SeatConfig
from maxpane_dashboard.widgets.seat.cost import SeatCost, SeatCostSpark
from maxpane_dashboard.widgets.seat.hero import SeatHero, SeatHeroBox
from maxpane_dashboard.widgets.seat.ledger import SeatLedgerTable
from maxpane_dashboard.widgets.seat.log import SeatLog
from maxpane_dashboard.widgets.seat.machine import SeatMachine
from maxpane_dashboard.widgets.seat.now import SeatNow

__all__ = ["SeatHero", "SeatNow", "SeatLedgerTable", "SeatLog", "SeatConfig", "SeatCost", "SeatMachine", "SeatCostSpark"]

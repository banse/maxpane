"""Signals panel for Defense of the Agents dashboard.

Every row is written on every ``update_data`` call (MEDI-38): a signal the
manager could not compute arrives as ``None`` and renders an explicit
``unavailable`` marker beside its label -- distinct from a signal whose own
``value_str`` is ``--``, which is the analytics saying "nothing to report".
Each row is written inside its own guard so one malformed signal dict
cannot raise into the screen's ``except`` and leave the previous poll's
rows on screen as if they were live.

The rows, the label width, the guard and the recommendation line are
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`'s (Branch 7,
WP-A) -- this panel's recommendation is the base's ``-> …`` spelling
exactly, so unlike cattown's it writes no line of its own.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SignalsPanelBase


class DOTASignals(SignalsPanelBase):
    """Panel displaying Defense of the Agents analytical signals and recommendation."""

    TITLE = "SIGNALS"

    ROWS = (
        ("dota-sig-faction", "Faction Balance"),
        ("dota-sig-lane", "Lane Pressure"),
        ("dota-sig-hero", "Hero Advantage"),
    )

    RECOMMENDATION_ID = "dota-sig-recommendation"

    def update_data(
        self,
        faction_balance_signal: dict | None = None,
        lane_pressure_signal: dict | None = None,
        hero_advantage_signal: dict | None = None,
        recommendation: str | None = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation; a missing signal says so."""
        self.render_signal("#dota-sig-faction", "Faction Balance",
                           faction_balance_signal)
        self.render_signal("#dota-sig-lane", "Lane Pressure",
                           lane_pressure_signal)
        self.render_signal("#dota-sig-hero", "Hero Advantage",
                           hero_advantage_signal)
        self.render_recommendation(recommendation)

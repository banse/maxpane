"""Signals panel for Onchain Monsters dashboard.

Every row is written on every ``update_data`` call (MEDI-38): a signal the
manager could not compute arrives as ``None`` and renders an explicit
``unavailable`` marker beside its label -- distinct from a signal whose own
``value_str`` is ``--``, which is the analytics saying "nothing to report".
Each row is written inside its own guard so one malformed signal dict
cannot raise into the screen's ``except`` and leave the previous poll's
rows on screen as if they were live.

The rows, the label width, the guard and the recommendation line are
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`'s (Branch 6).
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SignalsPanelBase


class OCMSignals(SignalsPanelBase):
    """Panel displaying Onchain Monsters analytical signals and recommendation."""

    TITLE = "SIGNALS"

    ROWS = (
        ("ocm-sig-staking", "Staking Rate"),
        ("ocm-sig-velocity", "Mint Velocity"),
        ("ocm-sig-burns", "Burn Rate"),
    )

    RECOMMENDATION_ID = "ocm-sig-recommendation"

    def update_data(
        self,
        staking_signal: dict | None = None,
        mint_velocity_signal: dict | None = None,
        burn_rate_signal: dict | None = None,
        recommendation: str | None = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation; a missing signal says so."""
        self.render_signal("#ocm-sig-staking", "Staking Rate", staking_signal)
        self.render_signal("#ocm-sig-velocity", "Mint Velocity", mint_velocity_signal)
        self.render_signal("#ocm-sig-burns", "Burn Rate", burn_rate_signal)
        self.render_recommendation(recommendation)

"""Signals panel for Cat Town dashboard.

Every row is written on every ``update_data`` call (MEDI-38): a signal the
manager could not compute arrives as ``None`` and renders an explicit
``unavailable`` marker beside its label -- distinct from a signal whose own
``value_str`` is ``--``, which is the analytics saying "nothing to report".
Each row is written inside its own guard so one malformed signal dict
cannot raise into the screen's ``except`` and leave the previous poll's
rows on screen as if they were live.

The rows, the label width, the guard and the recommendation *slot* are
:class:`~maxpane_dashboard.widgets.panels.SignalsPanelBase`'s (Branch 7,
WP-A). The recommendation **line** is not: Cat Town labels it
(``→ Recommendation: …``) where every other panel writes the base's
``-> …``, so this panel writes its own line through ``write`` rather than
the base growing an option nobody else would set. That is a pixel, and this
branch moves none.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SignalsPanelBase


class CTSignals(SignalsPanelBase):
    """Panel displaying Cat Town analytical signals and recommendation."""

    TITLE = "SIGNALS"

    ROWS = (
        ("ct-sig-conditions", "Conditions"),
        ("ct-sig-legendary", "Legendary"),
        ("ct-sig-cutoff", "Top 10 Cutoff"),
    )

    LABEL_WIDTH = 15

    DIM_LABEL = True

    RECOMMENDATION_ID = "ct-sig-recommendation"

    def update_data(
        self,
        condition_signal: dict | None = None,
        legendary_signal: dict | None = None,
        cutoff_signal: dict | None = None,
        recommendation: str | None = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation; a missing signal says so."""
        self.render_signal("#ct-sig-conditions", "Conditions", condition_signal)
        self.render_signal("#ct-sig-legendary", "Legendary", legendary_signal)
        self.render_signal("#ct-sig-cutoff", "Top 10 Cutoff", cutoff_signal)
        self.write(
            f"#{self.RECOMMENDATION_ID}",
            f"  [dim]→ Recommendation:[/] [bold]{recommendation}[/]"
            if recommendation else "",
        )

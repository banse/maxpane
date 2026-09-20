"""Sparkline charts for Cat Town dashboard.

The sparkline primitives come from
``maxpane_dashboard/widgets/sparkline_common.py``.  This module used to
carry its own pre-hardening copies, which raised ``TypeError`` on a
``None`` entry or a ``None`` value in a cached history (MEDI-36), and its
own value formatter, which
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel` now calls as
``sparkline_common.fmt_compact`` (Branch 7, WP-A). The two differ only on
negatives, ``NaN`` and at or above 1e9 -- none of them reachable for a
prize pool, a leader's catch weight or a raffle ticket count.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SparklinePanel


class CTSparklines(SparklinePanel):
    """ASCII sparkline charts for Cat Town metrics."""

    TITLE = "CAT TOWN TRENDS"

    LINE_IDS = ("ct-chart-line-0", "ct-chart-line-1", "ct-chart-line-2")

    def update_data(
        self,
        prize_pool_history: list[tuple[float, float]] | None = None,
        leader_weight_history: list[tuple[float, float]] | None = None,
        raffle_tickets_history: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for Prize Pool, Leader Weight, and Raffle Tickets."""
        self.render_series([
            ("Prize Pl", prize_pool_history, "yellow", ""),
            ("Leader  ", leader_weight_history, "green", "kg"),
            ("Raffle  ", raffle_tickets_history, "cyan", " tix"),
        ])

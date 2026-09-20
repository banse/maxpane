"""Sparkline charts for Onchain Monsters dashboard.

The sparkline primitives come from
``maxpane_dashboard/widgets/sparkline_common.py``.  This module used to
carry its own pre-hardening copies, which raised ``TypeError`` on a
``None`` entry or a ``None`` value in a cached history (MEDI-36), and its
own value formatter, which
:class:`~maxpane_dashboard.widgets.panels.SparklinePanel` now calls as
``sparkline_common.fmt_compact`` (Branch 6).
"""

from __future__ import annotations

from maxpane_dashboard.widgets.panels import SparklinePanel


class OCMSparklines(SparklinePanel):
    """ASCII sparkline charts for Onchain Monsters metrics."""

    TITLE = "TRENDS"

    LINE_IDS = ("ocm-chart-line-0", "ocm-chart-line-1", "ocm-chart-line-2")

    def update_data(
        self,
        supply_history: list[tuple[float, float]] | None = None,
        staked_history: list[tuple[float, float]] | None = None,
        ocmd_supply_history: list[tuple[float, float]] | None = None,
        **_kwargs,
    ) -> None:
        """Render sparklines for Supply, Staked, and $OCMD."""
        self.render_series([
            ("Supply", supply_history, "green", ""),
            ("Staked", staked_history, "cyan", ""),
            ("$OCMD", ocmd_supply_history, "yellow", ""),
        ])

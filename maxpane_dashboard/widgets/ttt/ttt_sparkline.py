"""Two-row sparkline widget for the TTT dashboard.

Renders two parallel ASCII sparklines sharing a single time axis:

* **BURNS** -- cumulative burn count over the last 168 hours (orange).
* **24H VOLUME $** -- total 24h USD volume across all tokens, sampled hourly (cyan).

Each input is a list of ``(unix_timestamp, value)`` tuples (or 2-element
lists -- some serializers degrade tuples to lists).  When a series has
fewer than 2 samples we render ``"waiting for data..."`` instead of an
empty bar, so the user sees the dashboard is alive but the series isn't
ready yet.

Inspired by ``maxpane_dashboard/widgets/ocm/ocm_sparklines.py`` but
adapted for two heterogeneous series (integer burn counts vs USD volume).

The sparkline primitives live in
``maxpane_dashboard/widgets/sparkline_common.py`` and are imported, not
copied (MEDI-36) -- this module used to carry its own byte-identical
``_coerce_points``/``_build_sparkline``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.sparkline_common import (
    build_sparkline as _build_sparkline,
    coerce_points as _coerce_points,
)

_WAITING = "[dim]waiting for data...[/]"


def _fmt_burns(value: float) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "--"


def _fmt_volume_usd(value: float) -> str:
    """Format USD volume with K/M/B suffix."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "--"
    if v >= 1_000_000_000:
        return f"${v / 1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v / 1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v / 1_000:.2f}K"
    return f"${v:.0f}"


class TTTSparkline(Vertical):
    """Two stacked sparklines: cumulative burns + NFT floor."""

    DEFAULT_CSS = """
    TTTSparkline > .ttt-spark-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    TTTSparkline > .ttt-spark-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("TRENDS (7d)", classes="ttt-spark-title")
        # Blank spacer between the title and the first sparkline row,
        # mirroring the pattern used in OCMSparklines (#ocm-chart-spacer).
        yield Static("", classes="ttt-spark-line", id="ttt-spark-spacer")
        yield Static(
            _WAITING,
            classes="ttt-spark-line",
            id="ttt-spark-burns",
        )
        yield Static(
            _WAITING,
            classes="ttt-spark-line",
            id="ttt-spark-volume",
        )

    def update_data(
        self,
        burns_history: list[tuple[float, float]] | None = None,
        volume_history: list[tuple[float, float]] | None = None,
        **_kwargs,  # tolerate stale floor_history kwarg from screen until B3 lands
    ) -> None:
        """Refresh both rows.

        ``*_history`` may be ``None``, an empty list, or a list of
        ``(ts, value)`` tuples / 2-element lists.  Anything shorter than
        2 points renders the ``waiting for data...`` placeholder.
        """
        # BURNS (orange)
        burns_widget = self.query_one("#ttt-spark-burns", Static)
        burns_pts = _coerce_points(burns_history)
        if len(burns_pts) < 2:
            burns_widget.update(f"  [dim]BURNS       [/]  {_WAITING}")
        else:
            spark = _build_sparkline([v for _, v in burns_pts])
            current = _fmt_burns(burns_pts[-1][1])
            burns_widget.update(
                f"  [dim]BURNS       [/]  [#ffa500]{spark}[/]  [bold]{current}[/]"
            )

        # 24H VOLUME $ (cyan)
        volume_widget = self.query_one("#ttt-spark-volume", Static)
        volume_pts = _coerce_points(volume_history)
        if len(volume_pts) < 2:
            volume_widget.update(f"  [dim]24H VOLUME $[/]  {_WAITING}")
        else:
            spark = _build_sparkline([v for _, v in volume_pts])
            current = _fmt_volume_usd(volume_pts[-1][1])
            volume_widget.update(
                f"  [dim]24H VOLUME $[/]  [cyan]{spark}[/]  [bold]{current}[/]"
            )

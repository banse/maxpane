"""$FWA price sparkline for the Fake World Assets (FWA) dashboard.

One series (the house two-row structure, so the vertical budget matches
``TalismansSparkline``):

* row 1 -- the block sparkline plus the live $FWA price.
* row 2 -- the ``price · 24h Δ`` line plus an honest statement of how
  much history actually exists.

**Why the history line matters.** The v4 pool was created 2026-07-16, so
GeckoTerminal has roughly 100 hourly candles (~10 days at spec time) and
nothing older.  A sparkline that silently pads a short series with
lowest-block characters invents a flat past that never happened, and one
that stretches a handful of points across the full width invents
resolution.  This widget does neither: a short series is left-padded with
**spaces** (real data stays right-aligned at the newest candle, the
missing hours read as missing), and a long series is bucket-averaged down
to the bar width so the whole window is represented rather than the last
22 hours only.  The candle count and day span are always printed.

``_coerce_points`` and ``_build_sparkline`` are imported from
``maxpane_dashboard/widgets/sparkline_common.py`` -- they used to be
verbatim copies of the ``talismans/tal_sparkline.py`` versions (MEDI-36).
The ``pad`` switch this widget needs for the degradation case described
above lives in the shared ``build_sparkline`` and defaults to the house
behaviour, so the other dashboards are unaffected.
Anything shorter than two points renders ``waiting for data...``, and
``spark_available is False`` renders an explicit unavailable state
(PRD §9).

Adapted to ``FWA_WIDGET_SIGNATURES["FWASparkline"]``.  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.sparkline_common import (
    SPARK_WIDTH as _SPARK_WIDTH,
    build_sparkline as _build_sparkline,
    coerce_points as _coerce_points,
)

_WAITING = "[dim]waiting for data...[/]"
_UNAVAILABLE = "[yellow]price feed unavailable[/]"
_DASH = "--"
_LABEL = "$FWA / USD "
_PAD = " " * len(_LABEL)


def _downsample(values: list[float], width: int = _SPARK_WIDTH) -> list[float]:
    """Bucket-average ``values`` down to at most ``width`` samples.

    Keeps the *whole* available window visible instead of cropping to the
    most recent ``width`` candles.  A series already at or below ``width``
    is returned unchanged -- never interpolated up.
    """
    n = len(values)
    if n <= width or width <= 0:
        return list(values)
    out: list[float] = []
    for i in range(width):
        start = (i * n) // width
        end = ((i + 1) * n) // width
        chunk = values[start:end] or values[start : start + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def _fmt_price(value) -> str:
    """USD price with enough precision for a sub-cent token."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return _DASH
    if v != v:  # NaN
        return _DASH
    a = abs(v)
    if a >= 1:
        return f"${v:,.4f}"
    if a >= 0.01:
        return f"${v:.5f}"
    if a > 0:
        return f"${v:.8f}"
    return "$0.00"


def _fmt_change(value) -> str:
    """Signed 24h change -- glyph carries the sign, colour is redundant.

    ``$success``/``$error``, never ``green``/``red``: content markup resolves
    colour *names* through Textual's CSS name table, where ``green`` is
    ``#008000`` -- 3.52:1 on the ``fwa`` surface and 4.09:1 at its best against
    pure black, so it fails WCAG AA under every theme. The theme variables are
    required ``Theme`` fields and measure 10.39 / 6.78 under ``fwa`` (WP-19).
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"[dim]{_DASH} 24h[/]"
    if v != v:
        return f"[dim]{_DASH} 24h[/]"
    if v > 0:
        return f"[$success]▲ {v:+.2f}%[/] [dim]24h[/]"
    if v < 0:
        return f"[$error]▼ {v:+.2f}%[/] [dim]24h[/]"
    return f"[dim]● {v:+.2f}% 24h[/]"


def _fmt_coverage(count: int) -> str:
    """State the real extent of the history, never imply more."""
    if count <= 0:
        return "[dim]no candles[/]"
    days = count / 24.0
    text = f"{count} candle{'s' if count != 1 else ''} · {days:.1f}d"
    if count < _SPARK_WIDTH:
        return f"[dim]{text} · short history[/]"
    return f"[dim]{text}[/]"


class FWASparkline(Vertical):
    """$FWA hourly price sparkline plus a ``price · 24h Δ`` line."""

    DEFAULT_CSS = """
    FWASparkline > .fwa-spark-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FWASparkline > .fwa-spark-line {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("$FWA PRICE (hourly)", classes="fwa-spark-title")
        yield Static("", classes="fwa-spark-line", id="fwa-spark-spacer")
        yield Static(
            _WAITING,
            classes="fwa-spark-line",
            id="fwa-spark-price",
        )
        yield Static(
            "",
            classes="fwa-spark-line",
            id="fwa-spark-meta",
        )

    def update_data(
        self,
        fwa_price_history=None,
        fwa_price_usd=None,
        fwa_price_change_24h=None,
        spark_available=None,
        **_kwargs,
    ) -> None:
        """Refresh both rows.

        ``fwa_price_history`` is ``list[[ts, close]]`` (hourly closes) --
        possibly ``None``, empty, or shorter than the bar width.
        """
        price_row = self.query_one("#fwa-spark-price", Static)
        meta_row = self.query_one("#fwa-spark-meta", Static)

        if spark_available is False:
            price_row.update(f"  [dim]{_LABEL}[/]  {_UNAVAILABLE}")
            meta_row.update(f"  [dim]{_PAD}[/]  [dim]no market data[/]")
            return

        points = _coerce_points(fwa_price_history)
        price_str = _fmt_price(
            fwa_price_usd if fwa_price_usd is not None
            else (points[-1][1] if points else None)
        )

        if len(points) < 2:
            price_row.update(f"  [dim]{_LABEL}[/]  {_WAITING}  [bold]{price_str}[/]")
            meta_row.update(
                f"  [dim]{_PAD}[/]  {_fmt_change(fwa_price_change_24h)}  "
                f"{_fmt_coverage(len(points))}"
            )
            return

        values = _downsample([v for _, v in points])
        spark = _build_sparkline(values, pad=len(values) >= _SPARK_WIDTH)
        price_row.update(
            f"  [dim]{_LABEL}[/]  [cyan]{spark}[/]  [bold]{price_str}[/]"
        )
        meta_row.update(
            f"  [dim]{_PAD}[/]  {_fmt_change(fwa_price_change_24h)}  "
            f"{_fmt_coverage(len(points))}"
        )

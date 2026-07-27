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

``_coerce_points`` is copied verbatim from
``talismans/tal_sparkline.py``; ``_build_sparkline`` is the same function
with an added ``pad`` switch for the degradation case described above.
Anything shorter than two points renders ``waiting for data...``, and
``spark_available is False`` renders an explicit unavailable state
(PRD §9).

Adapted to ``FWA_WIDGET_SIGNATURES["FWASparkline"]``.  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_SPARK_WIDTH = 22
_WAITING = "[dim]waiting for data...[/]"
_UNAVAILABLE = "[yellow]price feed unavailable[/]"
_DASH = "--"
_LABEL = "$FWA / USD "
_PAD = " " * len(_LABEL)


def _coerce_points(points) -> list[tuple[float, float]]:
    """Normalize input to a list of ``(ts, value)`` floats.

    Tolerates ``None`` entries, malformed shapes, and ``None`` values
    by skipping them.  Returns ``[]`` for any non-iterable input.
    """
    if not points:
        return []
    result: list[tuple[float, float]] = []
    try:
        iterator = list(points)
    except TypeError:
        return []
    for pt in iterator:
        if pt is None:
            continue
        try:
            ts, val = pt[0], pt[1]
        except (IndexError, TypeError, KeyError):
            continue
        if val is None:
            continue
        try:
            result.append((float(ts), float(val)))
        except (TypeError, ValueError):
            continue
    return result


def _build_sparkline(
    values: list[float],
    width: int = _SPARK_WIDTH,
    pad: bool = True,
) -> str:
    """Render a list of floats as a ``width``-wide block sparkline.

    ``pad=True`` is the house behaviour (left-pad with the lowest block).
    ``pad=False`` left-pads with spaces instead, for series that are
    genuinely shorter than the window: a hour with no candle must not be
    drawn as a low price.
    """
    if not values:
        return _SPARK_CHARS[0] * width if pad else " " * width
    sample = values[-width:] if len(values) > width else values

    lo = min(sample)
    hi = max(sample)
    span = hi - lo

    chars: list[str] = []
    for v in sample:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
            idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    # Short series stay right-aligned (newest candle at the right edge).
    filler = _SPARK_CHARS[0] if pad else " "
    while len(chars) < width:
        chars.insert(0, filler)
    return "".join(chars)


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
    """Signed 24h change -- glyph carries the sign, colour is redundant."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"[dim]{_DASH} 24h[/]"
    if v != v:
        return f"[dim]{_DASH} 24h[/]"
    if v > 0:
        return f"[green]▲ {v:+.2f}%[/] [dim]24h[/]"
    if v < 0:
        return f"[red]▼ {v:+.2f}%[/] [dim]24h[/]"
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

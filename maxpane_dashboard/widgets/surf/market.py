"""IMD market panel: price, volume, liquidity, FP parity, two sparklines.

Six rows (title + spacer + four content rows + two sparkline rows):

* price + 24h Δ (glyph carries the sign; colour is redundant, PRD §11)
* volume · pool liquidity
* FP price · parity spread -- the bridge-arbitrage health metric; a live
  value computed upstream each refresh, never a constant (PRD §6.2)
* price sparkline, supply sparkline.  The supply bar is the burn
  staircase: LP-fee burns step it down, OFT bridge-ins step it up.  Series
  come as ``list[[ts, value]]`` and are coerced through
  ``sparkline_common.coerce_points`` -- a single null point degrades to a
  skipped point, never a dead panel.

``None`` anywhere renders ``--``; a missing feed is never a zero price.

Sparkline helpers are imported from ``sparkline_common`` (house rule
MEDI-36 -- import, never copy).  Primitives only.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.sparkline_common import (
    SPARK_WIDTH,
    build_sparkline,
    coerce_points,
)
from maxpane_dashboard.widgets.surf._fmt import (
    DASH,
    as_float,
    fmt_compact,
    fmt_price,
)

_WAITING = "[dim]waiting for data...[/]"


def _fmt_change(value) -> str:
    """Signed 24h change: glyph + sign in text, theme colours only."""
    v = as_float(value)
    if v is None:
        return f"[dim]{DASH} 24h[/]"
    if v > 0:
        return f"[$success]▲ {v:+.2f}%[/] [dim]24h[/]"
    if v < 0:
        return f"[$error]▼ {v:+.2f}%[/] [dim]24h[/]"
    return f"[dim]● {v:+.2f}% 24h[/]"


def _fmt_parity(value) -> str:
    """FP↔IMD parity spread; negative means IMD trades below FP."""
    v = as_float(value)
    if v is None:
        return f"[dim]parity {DASH}[/]"
    if v > 0:
        return f"[dim]parity[/] [$success]▲ {v:+.2f}%[/]"
    if v < 0:
        return f"[dim]parity[/] [$error]▼ {v:+.2f}%[/]"
    return f"[dim]parity ● {v:+.2f}%[/]"


def _spark(series) -> str:
    """A block sparkline from ``[[ts, value]]``, or the waiting message."""
    points = coerce_points(series)
    if len(points) < 2:
        return _WAITING
    values = [v for _, v in points]
    return f"[cyan]{build_sparkline(values, pad=len(values) >= SPARK_WIDTH)}[/]"


class SurfMarket(Vertical):
    """IMD market panel."""

    DEFAULT_CSS = """
    SurfMarket > .surf-market-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfMarket > .surf-market-line {
        padding: 0 1;
        width: 100%;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("IMD MARKET", classes="surf-market-title")
        yield Static("", classes="surf-market-line", id="surf-mkt-spacer")
        yield Static(_WAITING, classes="surf-market-line", id="surf-mkt-price")
        yield Static("", classes="surf-market-line", id="surf-mkt-vol")
        yield Static("", classes="surf-market-line", id="surf-mkt-parity")
        yield Static("", classes="surf-market-line", id="surf-mkt-price-spark")
        yield Static("", classes="surf-market-line", id="surf-mkt-supply-spark")

    def update_data(
        self,
        imd_price_usd=None,
        imd_change_24h_pct=None,
        imd_vol_24h_usd=None,
        pool_liquidity_usd=None,
        fp_price_usd=None,
        parity_pct=None,
        supply_series=None,
        price_series=None,
        **_kwargs,
    ) -> None:
        """Refresh all rows.  Kwargs are exactly the PRD §5 market keys."""
        price = fmt_price(imd_price_usd)
        big = f"[bold]{price}[/]" if price != DASH else f"[dim]{DASH}[/]"
        self.query_one("#surf-mkt-price", Static).update(
            f"  {big}  {_fmt_change(imd_change_24h_pct)}"
        )

        vol = as_float(imd_vol_24h_usd)
        liq = as_float(pool_liquidity_usd)
        vol_s = f"${fmt_compact(vol)}" if vol is not None else DASH
        liq_s = f"${fmt_compact(liq)}" if liq is not None else DASH
        self.query_one("#surf-mkt-vol", Static).update(
            f"  [dim]vol 24h[/] {vol_s} [dim]·[/] [dim]pool[/] {liq_s}"
        )

        fp = fmt_price(fp_price_usd)
        fp_s = f"[dim]FP[/] {fp}" if fp != DASH else f"[dim]FP {DASH}[/]"
        self.query_one("#surf-mkt-parity", Static).update(
            f"  {fp_s} [dim]·[/] {_fmt_parity(parity_pct)}"
        )

        self.query_one("#surf-mkt-price-spark", Static).update(
            f"  [dim]price [/] {_spark(price_series)}"
        )
        supply_points = coerce_points(supply_series)
        last = f" [dim]{fmt_compact(supply_points[-1][1])}[/]" if supply_points else ""
        self.query_one("#surf-mkt-supply-spark", Static).update(
            f"  [dim]supply[/] {_spark(supply_series)}{last}"
        )

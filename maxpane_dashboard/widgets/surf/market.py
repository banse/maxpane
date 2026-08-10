"""IMD market panel: price, volume, liquidity, FP parity, the bridge spread.

Seven rows in **two columns** (title, spacer, two paired rows, a seam, and
the two-row bridge block)::

    IMD MARKET

      $0.7074  ▲ +30.89% 24h           price  ▁▁▂▃▄▅▆▇█
      vol 24h $244.2K · pool $548.7K   supply       ▁▁█ 2.4M

      FP $0.7274 · parity ▼ -2.75%     IMD $0.0200 under FP, gross of fees
      IMD is FP bridged 1:1 from Base  gap narrows as IMD bridges back

The pairing is by subject, not by convenience: the price sparkline belongs
to the price, and the supply staircase belongs beside the IMD-token
figures.  Each left-hand field used barely 31 of the panel's ~75 rendered
columns, so the sparklines moved up out of rows of their own -- which is
what freed the two rows the bridge block now occupies.

The second column starts at :func:`_second_column`, **measured** from the
rendered width of the left-hand fields rather than pinned: the fields are
live numbers and a constant that fits ``$0.7074`` collides with
``$1,234.56``.  Only rows that actually carry a right-hand segment are
measured, so the wide unavailable line below cannot drag the sparklines
across the panel.

The bridge block
----------------

IMD is FP bridged 1:1: ``BridgedFP`` is a LayerZero OFT whose mainnet
supply exists only via ``lzReceive`` from Base, where FP is the FrenPet
game token (FP locks in the Base adapter, IMD mints here -- see
``analytics/surf_signals.parity_pct``).  One asset, two chains, which is
why a *parity* percentage is a health metric at all rather than a
comparison of two unrelated tokens.

So the block states, in this order: the per-token spread in dollars and
which side is rich, then the flow that closes it.  The flow follows the
sign, because it is the sign that decides it -- IMD rich means new supply
arriving on this side (FP bridges in) narrows the gap; IMD cheap means
supply leaving it (IMD bridges back, burning here and unlocking FP on
Base) does.  It is exactly the staircase the supply sparkline two rows up
is drawing.

Three things this block deliberately does not do:

* **It never advises a transaction.**  MaxPane is read-only by
  construction -- no signer, no calldata, nothing to advise *for*.  The
  copy describes a state and the direction that would close it, and says
  nothing about what anyone should do or earn.
* **The spread is gross and says so.**  Bridge fees, mainnet and Base gas
  and both pools' slippage are not knowable keylessly, so no net figure is
  available at any price; ``gross of fees`` is what stops a 2% parity
  being read as 2% free.
* **It degrades explicitly.**  ``parity_pct`` is ``None`` whenever either
  price read fails, and then the whole block is
  :data:`SPREAD_UNAVAILABLE` -- not a blank right-hand column (which reads
  as *at parity*), not a zero, and never the last good spread presented as
  live.  :data:`BRIDGE_MECHANISM` survives that state because it is not a
  market read.

``None`` anywhere renders ``--``; a missing feed is never a zero price.

The supply bar is the other half of that story: it is the burn staircase --
LP-fee burns step it down, OFT bridge-ins step it up.  Both series arrive
as ``list[[ts, value]]`` and are coerced through
``sparkline_common.coerce_points``, so a single null point degrades to a
skipped point rather than a dead panel.

Sparkline helpers are imported from ``sparkline_common`` (house rule
MEDI-36 -- import, never copy), and widths are measured with
``markup_safety.visible_len`` for the same reason.  Primitives only, and
no third-party text reaches this panel: every field here is a number this
app computed, so there is nothing for ``safe_markup`` to guard.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import visible_len
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

#: Columns of clear space between the widest left-hand field and the second
#: column.  Two would still read as one gap on a row whose field happens to
#: end in a digit; three is the smallest that does not.
_GUTTER = 3

#: Sparkline row labels, padded to a common width so the bars themselves
#: line up as well as the labels do.
_SPARK_LABELS = ("price", "supply")
_LABEL_WIDTH = max(len(label) for label in _SPARK_LABELS)

#: What IMD *is*, stated on the panel because the parity row above is
#: meaningless without it.  Not a market number and not a documented one: the
#: 1:1 is the OFT mint/burn invariant (an ``lzReceive`` mints exactly what was
#: sent), not a rate anyone publishes and nobody can quietly change.  Every
#: *number* in this block is read live from the payload.
BRIDGE_MECHANISM = "IMD is FP bridged 1:1 from Base"

#: The explicit unavailable state for the whole bridge block.  Rendered
#: verbatim and asserted verbatim by the widget tests.
SPREAD_UNAVAILABLE = "spread unavailable"


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


def _spark_cell(label: str, series, suffix: str = "") -> str:
    """``price  ▁▁▂▃`` -- the label padded so both bars start together."""
    return f"[dim]{label:<{_LABEL_WIDTH}}[/] {_spark(series)}{suffix}"


def _bridge_cells(imd_price_usd, fp_price_usd, parity_pct) -> tuple[str, str]:
    """``(spread, direction)`` for the bridge block, or ``("", "")``.

    Both halves are derived from the same two live prices, so they cannot
    contradict each other: ``imd - fp`` and ``(imd/fp - 1) * 100`` share a
    sign for any positive FP price, which is the only case ``parity_pct``
    returns a number for.  ``parity_pct`` is the availability gate -- it is
    ``None`` exactly when the pair could not be read -- and the empty pair
    is the caller's signal to render :data:`SPREAD_UNAVAILABLE` instead.
    """
    imd = as_float(imd_price_usd)
    fp = as_float(fp_price_usd)
    if imd is None or fp is None or as_float(parity_pct) is None:
        return "", ""

    delta = imd - fp
    if delta == 0:
        return "[dim]IMD level with FP[/]", "[dim]no gap to close[/]"
    side = "over" if delta > 0 else "under"
    # Which flow narrows it: supply arriving on the rich side, or leaving
    # it.  Never phrased as an action for anyone to take.
    flow = "FP bridges in" if delta > 0 else "IMD bridges back"
    return (
        f"[dim]IMD[/] [bold]{fmt_price(abs(delta))}[/] "
        f"[dim]{side} FP, gross of fees[/]",
        f"[dim]gap narrows as {flow}[/]",
    )


def _second_column(rows: list[tuple[str, str]]) -> int:
    """Column the right-hand segments start at, from the rendered lefts.

    Measured over the rows that *have* a right-hand segment: a row rendering
    left-only (the unavailable bridge line, which is wider than any figure)
    must not push the sparklines across the panel to make room for nothing.
    """
    widths = [visible_len(left) for left, right in rows if right]
    return (max(widths) if widths else 0) + _GUTTER


def _lay_out(rows: list[tuple[str, str]], column: int) -> list[str]:
    """Pad each left segment so every right segment starts at ``column``."""
    return [
        left + " " * max(column - visible_len(left), 1) + right if right else left
        for left, right in rows
    ]


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
        yield Static("", classes="surf-market-line", id="surf-mkt-gap")
        yield Static("", classes="surf-market-line", id="surf-mkt-parity")
        yield Static("", classes="surf-market-line", id="surf-mkt-bridge")

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
        # -- left column: the figures ----------------------------------
        price = fmt_price(imd_price_usd)
        big = f"[bold]{price}[/]" if price != DASH else f"[dim]{DASH}[/]"
        left_price = f"  {big}  {_fmt_change(imd_change_24h_pct)}"

        vol = as_float(imd_vol_24h_usd)
        liq = as_float(pool_liquidity_usd)
        vol_s = f"${fmt_compact(vol)}" if vol is not None else DASH
        liq_s = f"${fmt_compact(liq)}" if liq is not None else DASH
        left_token = f"  [dim]vol 24h[/] {vol_s} [dim]·[/] [dim]pool[/] {liq_s}"

        fp = fmt_price(fp_price_usd)
        fp_s = f"[dim]FP[/] {fp}" if fp != DASH else f"[dim]FP {DASH}[/]"
        left_parity = f"  {fp_s} [dim]·[/] {_fmt_parity(parity_pct)}"

        # -- right column: the sparklines and the bridge block ----------
        supply_points = coerce_points(supply_series)
        last = f" [dim]{fmt_compact(supply_points[-1][1])}[/]" if supply_points else ""
        spread, direction = _bridge_cells(imd_price_usd, fp_price_usd, parity_pct)

        if spread:
            left_bridge = f"  [dim]{BRIDGE_MECHANISM}[/]"
        else:
            # No measurable spread: the mechanism still holds, the number
            # does not, and the row says which is which.
            left_bridge = (
                f"  [dim]{BRIDGE_MECHANISM} ·[/] "
                f"[yellow]⚠ {SPREAD_UNAVAILABLE}[/]"
            )

        rows = [
            (left_price, _spark_cell("price", price_series)),
            (left_token, _spark_cell("supply", supply_series, suffix=last)),
            (left_parity, spread),
            (left_bridge, direction),
        ]
        laid_out = _lay_out(rows, _second_column(rows))

        for line, row_id in zip(
            laid_out,
            ("#surf-mkt-price", "#surf-mkt-vol", "#surf-mkt-parity", "#surf-mkt-bridge"),
        ):
            self.query_one(row_id, Static).update(line)

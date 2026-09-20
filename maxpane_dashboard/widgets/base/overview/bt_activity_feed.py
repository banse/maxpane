"""Volume activity feed for the Base Trading Overview view.

The log, the placeholder contract and the per-row guard are
:class:`~maxpane_dashboard.widgets.panels.RichLogFeed`'s (Branch 8, WP-A),
in **stream** mode: this is the copy's own behaviour -- a poll that brings
no tokens leaves the ranking on screen -- and the placeholder is now written
once rather than once per empty poll (the pre-migration capture showed
``No activity yet`` twice after the two refreshes a mount performs). The
panel is a ranking of tokens by 24h volume, so every poll is the whole
list: ``dedupe_key`` returns ``None`` and every poll redraws.

Two things the base's ``Text`` contract had to keep from the copy's markup
strings: the column **header** the copy wrote above the rows, which is
:attr:`~maxpane_dashboard.widgets.panels.RichLogFeed.HEADER_LINE` here, and
the ``ReprHighlighter`` that ``RichLog`` applies to a ``str`` it is handed
and *not* to a ``Text`` -- the row applies it itself, so the numbers keep
the colour they had.
"""

from __future__ import annotations

from rich.highlighter import ReprHighlighter
from rich.text import Text

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import RichLogFeed

#: What ``RichLog(highlight=True)`` runs over a *string* row before painting
#: it (its own default is this same class). A ``Text`` row bypasses that, so
#: the migrated row runs it here to keep the copy's pixels.
_HIGHLIGHT = ReprHighlighter()


def _format_volume(value: float) -> str:
    """Format a dollar volume with K/M/B suffix."""
    try:
        v = float(value)
        if v >= 1_000_000:
            return f"${v / 1_000_000:.1f}M"
        elif v >= 1_000:
            return f"${v / 1_000:.1f}K"
        return f"${v:,.0f}"
    except (ValueError, TypeError):
        return "$?"


def _strip_non_ascii(text: str) -> str:
    """Remove non-ASCII for alignment."""
    return "".join(ch for ch in text if ord(ch) < 128).strip()


def _format_count(value: int) -> str:
    """Format a trade count with K suffix."""
    if value >= 1_000:
        return f"{value / 1_000:.1f}K"
    return str(value)


def _token_to_markup(token: dict) -> str:
    """Convert a token volume entry into a Rich-markup formatted line."""
    symbol = safe_markup(f'{_strip_non_ascii(token.get("symbol", "???"))[:8]:<8}')
    vol = _format_volume(token.get("volume_24h", 0))
    liq = _format_volume(token.get("liquidity", 0))
    buys = token.get("buys_24h", 0)
    sells = token.get("sells_24h", 0)
    change = token.get("price_change_24h", 0) or 0

    # Buy/sell pressure indicator
    if buys + sells > 0:
        ratio = buys / (buys + sells)
        if ratio > 0.55:
            pressure = "[green]BUY [/]"
        elif ratio < 0.45:
            pressure = "[red]SELL[/]"
        else:
            pressure = "[yellow]EVEN[/]"
    else:
        pressure = "[dim] -- [/]"

    # Price change color
    if change > 0:
        change_str = f"[green]{'+' + f'{change:.1f}':>6}%[/]"
    elif change < 0:
        change_str = f"[red]{f'{change:.1f}':>6}%[/]"
    else:
        change_str = f"[dim]{'0.0':>6}%[/]"

    # Buy/sell counts
    bs_str = f"{_format_count(buys)}/{_format_count(sells)}"

    return (
        f"  {pressure}  "
        f"[cyan]{symbol}[/]  "
        f"{vol:>8}  "
        f"{change_str}  "
        f"[dim]{liq:>8}[/]  "
        f"[dim]{bs_str:>11}[/]"
    )


class BTActivityFeed(RichLogFeed):
    """Activity feed showing trending tokens with volume and buy/sell pressure."""

    TITLE = "ACTIVITY"

    LOG_ID = "bto-activity-log"

    #: The column heading over the ranking; a ``str``, so the log parses and
    #: highlights it exactly as the copy's ``log.write`` did.
    HEADER_LINE = (
        f"  [dim]{'':4}  {'Token':<8}  {'Volume':>8}  {'Change':>7}  "
        f"{'Liq':>8}  {'Buys/Sells':>11}[/]"
    )

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this log's colours.
    DEFAULT_CSS = """
    BTActivityFeed > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def dedupe_key(self, event: dict) -> str | None:
        """Always new: the feed is a ranking, re-drawn whole every poll."""
        return None

    def format_row(self, event: dict) -> Text:
        """The copy's markup line, parsed and highlighted as the log did."""
        return _HIGHLIGHT(Text.from_markup(_token_to_markup(event)))

    def update_data(self, whale_trades: list[dict] | None = None) -> None:
        """Show tokens ranked by volume with buy/sell pressure."""
        self.render_events(whale_trades)

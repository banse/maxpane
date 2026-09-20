"""Trending tokens leaderboard for the Base Trading Overview view.

The title, its blank row, the table's cursor/zebra/columns and the
clear-then-repopulate contract are
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`'s (Branch 8,
WP-A). What stays here is what only this dashboard knows: the six column
widths, the fifteen-row cap, the address cell with its icon, the price /
change / volume / market-cap formatters and the top-three bolding. Every
row is now built inside the base's per-row guard, so one token the
formatter cannot read is one missing line rather than an exception
escaping after ``clear()`` and leaving the table empty.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.base._chain import EXPLORER
from maxpane_dashboard.widgets.panels import TableLeaderboard

#: Display budget for the token symbol label, excluding the icon -- the same
#: 10-cell window the deleted ``symbol[:10]`` slice produced. This is the
#: "Token" column on the *live* base dashboard's leaderboard (the only base
#: widget in this package actually wired to a screen); no layout pin governs
#: it, so it is grown by ICON_COLS, keeping the 2-cell gutter the column
#: already carried beyond the 10-cell label (PRD §5 recipe step 6.2): 12 -> 14.
_TOKEN_COLS = 10


def _fmt_price(price) -> str:
    try:
        p = float(price)
    except (ValueError, TypeError):
        return "..."
    if p < 0.0001:
        return f"${p:.8f}"
    if p < 1:
        return f"${p:.6f}"
    return f"${p:,.2f}"


def _fmt_change(change) -> str:
    if change is None:
        return "[dim]--[/]"
    try:
        c = float(change)
    except (ValueError, TypeError):
        return "..."
    if c >= 0:
        return f"[green]+{c:.1f}%[/]"
    return f"[red]{c:.1f}%[/]"


def _fmt_volume(volume) -> str:
    try:
        v = float(volume)
    except (ValueError, TypeError):
        return "..."
    if v >= 1_000_000:
        return f"${v / 1_000_000:.1f}M"
    if v >= 1_000:
        return f"${v / 1_000:.1f}K"
    return f"${v:,.0f}"


def _fmt_mcap(mcap) -> str:
    try:
        m = float(mcap)
    except (ValueError, TypeError):
        return "..."
    if m >= 1_000_000_000:
        return f"${m / 1_000_000_000:.1f}B"
    if m >= 1_000_000:
        return f"${m / 1_000_000:.1f}M"
    if m >= 1_000:
        return f"${m / 1_000:.1f}K"
    return f"${m:,.0f}"


class BTOverviewLeaderboard(TableLeaderboard):
    """Leaderboard panel with DataTable of trending tokens."""

    TITLE = "TRENDING TOKENS"

    TABLE_ID = "bto-lb-table"

    COLUMNS = (
        ("#", 4),
        ("Token", 14),
        ("Price", 14),
        ("24h %", 10),
        ("Volume", 12),
        ("Mcap", 12),
    )

    #: Fifteen, not the base's ten: this table has the left three-fifths of
    #: the middle row to itself.
    ROW_CAP = 15

    EMPTY_ROW = ("--", "No data", "--", "--", "--", "--")

    #: Geometry only: the title and its blank row are ``PanelBase``'s, and
    #: ``minimal.tcss`` states this table's colours and scrollbar.
    DEFAULT_CSS = """
    BTOverviewLeaderboard > DataTable {
        height: 1fr;
    }
    """

    def update_data(self, trending_tokens: list | None = None) -> None:
        """Clear and repopulate the leaderboard table with live data."""
        self.render_table(trending_tokens)

    def build_row(self, index: int, token) -> tuple:
        """One token's row. The top three symbols are bold; the symbol cell
        carries the copy icon and the explorer link.

        ``token`` is a ``dict`` or a ``BaseToken``-shaped object -- the
        payload has served both.
        """
        idx = index + 1
        if isinstance(token, dict):
            symbol = token.get("symbol", "???")
            address = token.get("address")
            price = token.get("price_usd", 0)
            change = token.get("price_change_24h")
            volume = token.get("volume_24h", 0)
            mcap = token.get("market_cap", 0)
        else:
            symbol = getattr(token, "symbol", "???")
            address = getattr(token, "address", None)
            price = getattr(token, "price_usd", 0)
            change = getattr(token, "price_change_24h", None)
            volume = getattr(token, "volume_24h", 0)
            mcap = getattr(token, "market_cap", 0)

        is_top = idx <= 3
        symbol_cell = address_text(
            address, label=symbol, width=_TOKEN_COLS,
            style="bold" if is_top else "", explorer=EXPLORER,
        )
        return (
            str(idx),
            symbol_cell,
            _fmt_price(price),
            _fmt_change(change),
            _fmt_volume(volume),
            _fmt_mcap(mcap),
        )

"""Top gainers and losers tables for the Base Trading Overview view.

A two-column text board on :class:`~maxpane_dashboard.widgets.panels.PanelBase`
(Branch 8, WP-A): the title and its blank row are the base's, the header,
the gap under it and the ten rows are this panel's own ``compose_body``
(the sixth copy of a shape the repo has no base for -- follow-up #27). Each
row is written inside the base's guard, so one entry the formatter cannot
read lands on ``unavailable`` on its own row instead of raising out of the
loop with the rows below it still showing the previous poll.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets.markup_safety import safe_markup
from maxpane_dashboard.widgets.panels import LOADING_ROW, UNAVAILABLE, PanelBase

_NUM_ROWS = 10
_NAME_WIDTH = 14


def _truncate(name: str, width: int = _NAME_WIDTH) -> str:
    """Truncate a name and pad to width."""
    clean = "".join(ch for ch in name if ord(ch) < 128).strip()
    if len(clean) > width:
        return clean[: width - 1] + "."
    return clean.ljust(width)


def _entry(item, *, gainer: bool) -> tuple[str, str]:
    """``(name, change_str)`` from a tuple, a dict or an object."""
    if isinstance(item, tuple):
        return item
    sign = "+" if gainer else ""
    if isinstance(item, dict):
        name = item.get("symbol", "???")
        pct = item.get("price_change_24h", 0)
    else:
        name = getattr(item, "symbol", "???")
        pct = getattr(item, "price_change_24h", 0)
    value = f"{sign}{float(pct):.1f}%" if pct is not None else "?"
    return name, value


def _row(i: int, gainers: list, losers: list) -> str:
    if i < len(gainers):
        g_name, g_value = _entry(gainers[i], gainer=True)
        star = "[yellow]*[/] " if i == 0 else "  "
        g_name_str = safe_markup(_truncate(g_name, _NAME_WIDTH))
        g_value_str = f"[green]{g_value:>10}[/]"
    else:
        star = "  "
        g_name_str = " " * _NAME_WIDTH
        g_value_str = " " * 10

    if i < len(losers):
        l_name, l_value = _entry(losers[i], gainer=False)
        l_star = "[yellow]*[/] " if i == 0 else "  "
        l_name_str = safe_markup(_truncate(l_name, _NAME_WIDTH))
        l_value_str = f"[red]{l_value:>10}[/]"
    else:
        l_star = "  "
        l_name_str = ""
        l_value_str = ""

    return f"{star}{g_name_str} {g_value_str}  {l_star}{l_name_str} {l_value_str}"


class BTBestPlays(PanelBase):
    """Side-by-side tables showing top gainers and top losers."""

    TITLE = "BEST PLAYS"

    def compose_body(self) -> ComposeResult:
        yield Static(
            f"  {'Top Gainers':<{_NAME_WIDTH}} {'Change':>10}"
            f"    {'Top Losers':<{_NAME_WIDTH}} {'Change':>10}",
            classes="panel-line",
            id="bto-bp-header",
        )
        # Not the title's blank row: the gap between the header and the rows.
        yield Static("", classes="panel-line")
        for i in range(_NUM_ROWS):
            yield Static(
                LOADING_ROW if i == 0 else "",
                classes="panel-line", id=f"bto-bp-row-{i}",
            )

    def update_data(
        self,
        gainers: list | None = None,
        losers: list | None = None,
    ) -> None:
        """Show top gainers and losers side by side.

        Each entry can be a tuple of (name, change_str) or an object/dict
        with symbol and price_change_24h attributes.
        """
        gainers = gainers or []
        losers = losers or []
        for i in range(_NUM_ROWS):
            self.write_guarded(
                f"#bto-bp-row-{i}",
                lambda i=i: _row(i, gainers, losers),
                f"  {UNAVAILABLE}",
            )

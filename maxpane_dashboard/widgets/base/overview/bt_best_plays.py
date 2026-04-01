"""Top gainers and losers tables for the Base Trading Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_NUM_ROWS = 10
_NAME_WIDTH = 14


def _truncate(name: str, width: int = _NAME_WIDTH) -> str:
    """Truncate a name and pad to width."""
    clean = "".join(ch for ch in name if ord(ch) < 128).strip()
    if len(clean) > width:
        return clean[: width - 1] + "."
    return clean.ljust(width)


class BTBestPlays(Vertical):
    """Side-by-side tables showing top gainers and top losers."""

    DEFAULT_CSS = """
    BTBestPlays > .bto-bp-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    BTBestPlays > .bto-bp-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("BEST PLAYS", classes="bto-bp-title")
        yield Static("", classes="bto-bp-body")
        yield Static(
            f"  {'Top Gainers':<{_NAME_WIDTH}} {'Change':>10}"
            f"    {'Top Losers':<{_NAME_WIDTH}} {'Change':>10}",
            classes="bto-bp-body",
            id="bto-bp-header",
        )
        yield Static("", classes="bto-bp-body")
        for i in range(_NUM_ROWS):
            default = "[dim]  Loading...[/]" if i == 0 else ""
            yield Static(default, classes="bto-bp-body", id=f"bto-bp-row-{i}")

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
            widget = self.query_one(f"#bto-bp-row-{i}", Static)

            # Gainer side
            if i < len(gainers):
                g = gainers[i]
                if isinstance(g, tuple):
                    g_name, g_value = g
                elif isinstance(g, dict):
                    g_name = g.get("symbol", "???")
                    pct = g.get("price_change_24h", 0)
                    g_value = f"+{float(pct):.1f}%" if pct is not None else "?"
                else:
                    g_name = getattr(g, "symbol", "???")
                    pct = getattr(g, "price_change_24h", 0)
                    g_value = f"+{float(pct):.1f}%" if pct is not None else "?"
                star = "[yellow]*[/] " if i == 0 else "  "
                g_name_str = _truncate(g_name, _NAME_WIDTH)
                g_value_str = f"[green]{g_value:>10}[/]"
            else:
                star = "  "
                g_name_str = " " * _NAME_WIDTH
                g_value_str = " " * 10

            # Loser side
            if i < len(losers):
                lo = losers[i]
                if isinstance(lo, tuple):
                    l_name, l_value = lo
                elif isinstance(lo, dict):
                    l_name = lo.get("symbol", "???")
                    pct = lo.get("price_change_24h", 0)
                    l_value = f"{float(pct):.1f}%" if pct is not None else "?"
                else:
                    l_name = getattr(lo, "symbol", "???")
                    pct = getattr(lo, "price_change_24h", 0)
                    l_value = f"{float(pct):.1f}%" if pct is not None else "?"
                l_star = "[yellow]*[/] " if i == 0 else "  "
                l_name_str = _truncate(l_name, _NAME_WIDTH)
                l_value_str = f"[red]{l_value:>10}[/]"
            else:
                l_star = "  "
                l_name_str = ""
                l_value_str = ""

            widget.update(
                f"{star}{g_name_str} {g_value_str}  {l_star}{l_name_str} {l_value_str}"
            )

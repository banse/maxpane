"""Hero metric boxes for the Base Trading Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class BTHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class BTOverviewHero(Horizontal):
    """Row of hero metric boxes: ETH Price, 24h Change, Volume, Top Gainer."""

    DEFAULT_CSS = """
    BTOverviewHero > BTHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield BTHeroBox(
            "[dim]ETH PRICE[/]\n\n"
            "[dim]Loading...[/]",
            id="bto-hero-eth",
        )
        yield BTHeroBox(
            "[dim]24H CHANGE[/]\n\n"
            "[dim]Loading...[/]",
            id="bto-hero-change",
        )
        yield BTHeroBox(
            "[dim]VOLUME[/]\n\n"
            "[dim]Loading...[/]",
            id="bto-hero-volume",
        )
        yield BTHeroBox(
            "[dim]TOP GAINER[/]\n\n"
            "[dim]Loading...[/]",
            id="bto-hero-gainer",
        )

    def update_data(
        self,
        eth_price: float | str | None = None,
        eth_change_24h: float | str | None = None,
        total_volume: float | str | None = None,
        top_gainer_name: str | None = None,
        top_gainer_pct: float | str | None = None,
    ) -> None:
        """Refresh all hero boxes with live values."""
        # -- ETH Price --
        eth_box = self.query_one("#bto-hero-eth", BTHeroBox)
        if eth_price is not None:
            try:
                price_str = f"${float(eth_price):,.2f}"
            except (ValueError, TypeError):
                price_str = str(eth_price)
        else:
            price_str = "..."
        eth_box.update(
            f"[dim]ETH PRICE[/]\n\n"
            f"[bold white]{price_str}[/]"
        )

        # -- 24h Change --
        change_box = self.query_one("#bto-hero-change", BTHeroBox)
        if eth_change_24h is not None:
            try:
                change_val = float(eth_change_24h)
                if change_val >= 0:
                    change_str = f"[green]+{change_val:.2f}%[/]"
                else:
                    change_str = f"[red]{change_val:.2f}%[/]"
            except (ValueError, TypeError):
                change_str = str(eth_change_24h)
        else:
            change_str = "[dim]...[/]"
        change_box.update(
            f"[dim]24H CHANGE[/]\n\n"
            f"[bold]{change_str}[/]"
        )

        # -- Volume --
        vol_box = self.query_one("#bto-hero-volume", BTHeroBox)
        if total_volume is not None:
            try:
                vol = float(total_volume)
                if vol >= 1_000_000_000:
                    vol_str = f"${vol / 1_000_000_000:.1f}B"
                elif vol >= 1_000_000:
                    vol_str = f"${vol / 1_000_000:.1f}M"
                elif vol >= 1_000:
                    vol_str = f"${vol / 1_000:.1f}K"
                else:
                    vol_str = f"${vol:,.0f}"
            except (ValueError, TypeError):
                vol_str = str(total_volume)
        else:
            vol_str = "..."
        vol_box.update(
            f"[dim]VOLUME[/]\n\n"
            f"[bold white]{vol_str}[/]"
        )

        # -- Top Gainer --
        gainer_box = self.query_one("#bto-hero-gainer", BTHeroBox)
        if top_gainer_name:
            try:
                pct_val = float(top_gainer_pct) if top_gainer_pct is not None else 0.0
                pct_str = f"+{pct_val:.1f}%"
            except (ValueError, TypeError):
                pct_str = str(top_gainer_pct) if top_gainer_pct else "?"
            gainer_box.update(
                f"[dim]TOP GAINER[/]\n\n"
                f"[bold white]{top_gainer_name}[/]\n"
                f"[green]{pct_str}[/]"
            )
        else:
            gainer_box.update(
                f"[dim]TOP GAINER[/]\n\n"
                f"[dim]No data[/]"
            )

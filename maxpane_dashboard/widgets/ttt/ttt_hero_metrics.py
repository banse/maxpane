"""Hero metric boxes for the Ten Thousand Tokens (TTT) dashboard.

Four boxes laid out horizontally:

* UNBURNED -- remaining NFT supply out of 10,000
* LAUNCHES -- total burns/launches with a 24h delta
* HOLDER POOL -- cumulative ETH paid to NFT holders, with a 24h delta
* FLOOR -- secondary-market NFT floor (ETH + USD)

Each value is rendered exception-safe: a missing/None scalar collapses to
``"--"`` rather than raising.  This matches the project rule that widgets
must never crash on partial data.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class TTTHeroBox(Static):
    """A single hero metric box: title, big number, subtitle."""

    DEFAULT_CSS = ""


class TTTHeroMetrics(Horizontal):
    """Row of four hero metric boxes for the TTT dashboard."""

    DEFAULT_CSS = """
    TTTHeroMetrics > TTTHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield TTTHeroBox(
            "[dim]UNBURNED[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-unburned",
            classes="ttt-hero-box",
        )
        yield TTTHeroBox(
            "[dim]LAUNCHES[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-launches",
            classes="ttt-hero-box",
        )
        yield TTTHeroBox(
            "[dim]HOLDER POOL[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-holders",
            classes="ttt-hero-box",
        )
        yield TTTHeroBox(
            "[dim]FLOOR[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-floor",
            classes="ttt-hero-box",
        )

    # -- helpers --------------------------------------------------------

    @staticmethod
    def _fmt_int(value) -> str:
        try:
            return f"{int(value):,}"
        except (TypeError, ValueError):
            return "--"

    @staticmethod
    def _fmt_float(value, fmt: str) -> str:
        try:
            return format(float(value), fmt)
        except (TypeError, ValueError):
            return "--"

    # -- update ---------------------------------------------------------

    def update_data(
        self,
        unburned=None,
        burned_pct=None,
        launches=None,
        launches_24h=None,
        holder_pool_eth_total=None,
        holder_pool_eth_24h=None,
        floor_eth=None,
        floor_usd=None,
        **_kwargs,
    ) -> None:
        """Refresh all four hero boxes from the manager's flat dict."""

        # -- UNBURNED ---------------------------------------------------
        unburned_box = self.query_one("#ttt-hero-unburned", TTTHeroBox)
        if unburned is None:
            unburned_box.update("[dim]UNBURNED[/]\n\n[dim]--[/]\n[dim]--[/]")
        else:
            big = self._fmt_int(unburned)
            try:
                remaining_pct = 100.0 - float(burned_pct or 0.0)
                sub = f"{remaining_pct:.2f}% of 10,000"
            except (TypeError, ValueError):
                sub = "--"
            unburned_box.update(
                f"[dim]UNBURNED[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
            )

        # -- LAUNCHES ---------------------------------------------------
        launches_box = self.query_one("#ttt-hero-launches", TTTHeroBox)
        if launches is None:
            launches_box.update("[dim]LAUNCHES[/]\n\n[dim]--[/]\n[dim]--[/]")
        else:
            big = self._fmt_int(launches)
            try:
                n24 = int(launches_24h or 0)
            except (TypeError, ValueError):
                n24 = 0
            if n24 > 0:
                sub = f"[green]+{n24} 24h[/]"
            else:
                sub = f"[dim]+{n24} 24h[/]"
            launches_box.update(
                f"[dim]LAUNCHES[/]\n\n[bold white]{big}[/]\n{sub}"
            )

        # -- HOLDER POOL -----------------------------------------------
        holders_box = self.query_one("#ttt-hero-holders", TTTHeroBox)
        if holder_pool_eth_total is None:
            holders_box.update(
                "[dim]HOLDER POOL[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
        else:
            big = self._fmt_float(holder_pool_eth_total, ".3f")
            sub = self._fmt_float(holder_pool_eth_24h, ".4f")
            holders_box.update(
                f"[dim]HOLDER POOL[/]\n\n"
                f"[bold white]{big} Ξ[/]\n"
                f"[dim]+{sub} Ξ 24h[/]"
            )

        # -- FLOOR ------------------------------------------------------
        floor_box = self.query_one("#ttt-hero-floor", TTTHeroBox)
        if floor_eth is None:
            big = "--"
        else:
            big = self._fmt_float(floor_eth, ".4f")
            if big != "--":
                big = f"{big} Ξ"
        if floor_usd is None:
            sub = "--"
        else:
            try:
                sub = f"${float(floor_usd):,.0f}"
            except (TypeError, ValueError):
                sub = "--"
        floor_box.update(
            f"[dim]FLOOR[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
        )

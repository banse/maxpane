"""Hero metric boxes for the Ten Thousand Tokens (TTT) dashboard.

Four boxes laid out horizontally:

* UNBURNED NFTs -- remaining NFT supply out of 10,000
* TOKEN LAUNCHES -- total burns/launches with a 24h delta
* HOLDER POOL -- cumulative ETH paid to NFT holders, with a 24h delta
* TOTAL MCAP -- aggregated market cap (USD) across launched tokens with
  data, plus the Ξ-equivalent and the count of tokens contributing to
  the sum.

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
            "[dim]UNBURNED NFTs[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-unburned",
            classes="ttt-hero-box",
        )
        yield TTTHeroBox(
            "[dim]TOKEN LAUNCHES[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-launches",
            classes="ttt-hero-box",
        )
        yield TTTHeroBox(
            "[dim]HOLDER POOL[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-holders",
            classes="ttt-hero-box",
        )
        yield TTTHeroBox(
            "[dim]TOTAL MCAP[/]\n\n[dim]Loading...[/]",
            id="ttt-hero-mcap",
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
        unburned: int | None = None,
        burned_pct: float | None = None,
        launches: int | None = None,
        launches_24h: int | None = None,
        holder_pool_eth_total: float | None = None,
        holder_pool_eth_24h: float | None = None,
        total_mcap_usd: float | None = None,
        total_mcap_eth: float | None = None,
        total_mcap_token_count: int | None = None,
        **_kwargs,
    ) -> None:
        """Refresh all four hero boxes from the manager's flat dict."""

        # -- UNBURNED NFTs ---------------------------------------------
        unburned_box = self.query_one("#ttt-hero-unburned", TTTHeroBox)
        if unburned is None:
            unburned_box.update(
                "[dim]UNBURNED NFTs[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
        else:
            big = self._fmt_int(unburned)
            try:
                remaining_pct = 100.0 - float(burned_pct or 0.0)
                sub = f"{remaining_pct:.2f}% of 10,000"
            except (TypeError, ValueError):
                sub = "--"
            unburned_box.update(
                f"[dim]UNBURNED NFTs[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
            )

        # -- TOKEN LAUNCHES --------------------------------------------
        launches_box = self.query_one("#ttt-hero-launches", TTTHeroBox)
        if launches is None:
            launches_box.update(
                "[dim]TOKEN LAUNCHES[/]\n\n[dim]--[/]\n[dim]--[/]"
            )
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
                f"[dim]TOKEN LAUNCHES[/]\n\n[bold white]{big}[/]\n{sub}"
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

        # -- TOTAL MCAP ------------------------------------------------
        mcap_box = self.query_one("#ttt-hero-mcap", TTTHeroBox)

        # Big number: USD, scaled to M or K. "--" if 0 or unavailable.
        try:
            usd_val = float(total_mcap_usd) if total_mcap_usd is not None else None
        except (TypeError, ValueError):
            usd_val = None

        if usd_val is None or usd_val == 0:
            big = "--"
        elif usd_val >= 1_000_000:
            big = f"${usd_val / 1e6:.2f}M"
        else:
            big = f"${usd_val / 1e3:.1f}K"

        # Subtitle: Ξ-equivalent + token count. Fall back to just count.
        try:
            token_count = int(total_mcap_token_count) if total_mcap_token_count is not None else 0
        except (TypeError, ValueError):
            token_count = 0

        if total_mcap_eth is None:
            sub = f"{token_count} tokens"
        else:
            try:
                eth_val = float(total_mcap_eth)
                sub = f"{eth_val:,.1f} Ξ · {token_count} tokens"
            except (TypeError, ValueError):
                sub = f"{token_count} tokens"

        mcap_box.update(
            f"[dim]TOTAL MCAP[/]\n\n[bold white]{big}[/]\n[dim]{sub}[/]"
        )

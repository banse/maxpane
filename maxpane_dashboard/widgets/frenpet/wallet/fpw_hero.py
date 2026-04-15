"""Hero metric boxes for the FrenPet Wallet view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


def _fmt_eth(wei: int) -> str:
    """Format wei to 'X.XXXX ETH'."""
    eth = wei / 1e18
    return f"{eth:.4f} ETH"


def _fmt_fp(amount: int) -> str:
    """Format FP amount with K/M/B suffix."""
    if amount >= 1_000_000_000:
        return f"{amount / 1_000_000_000:.1f}B"
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return f"{amount:,}"


class FPWHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class FPWalletHero(Horizontal):
    """Row of three hero metric boxes: ETH Rewards, Pool Share, APR."""

    DEFAULT_CSS = """
    FPWalletHero > FPWHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield FPWHeroBox(
            "[dim]ETH REWARDS[/]\n\n"
            "[dim]Loading...[/]",
            id="fpw-hero-eth",
        )
        yield FPWHeroBox(
            "[dim]POOL SHARE[/]\n\n"
            "[dim]Loading...[/]",
            id="fpw-hero-pool",
        )
        yield FPWHeroBox(
            "[dim]APR[/]\n\n"
            "[dim]Loading...[/]",
            id="fpw-hero-apr",
        )

    def update_data(
        self,
        total_eth_wei: int,
        eth_price_usd: float,
        pool_share_pct: float,
        total_fp_in_pool: int,
        apr: float,
        user_shares: int,
        pet_count: int,
    ) -> None:
        """Refresh all three hero boxes with live values."""
        # -- ETH Rewards --
        eth_box = self.query_one("#fpw-hero-eth", FPWHeroBox)
        eth_str = _fmt_eth(total_eth_wei)
        usd_value = (total_eth_wei / 1e18) * eth_price_usd
        eth_box.update(
            f"[dim]ETH REWARDS[/]\n\n"
            f"[bold white]{eth_str}[/]\n"
            f"[dim]~${usd_value:,.0f} \u00b7 {pet_count} pets[/]"
        )

        # -- Pool Share --
        pool_box = self.query_one("#fpw-hero-pool", FPWHeroBox)
        pool_str = f"{pool_share_pct:.2f}%"
        fp_pool_str = _fmt_fp(total_fp_in_pool)
        pool_box.update(
            f"[dim]POOL SHARE[/]\n\n"
            f"[bold white]{pool_str}[/]\n"
            f"[dim]of {fp_pool_str} FP pool[/]"
        )

        # -- APR --
        apr_box = self.query_one("#fpw-hero-apr", FPWHeroBox)
        apr_str = f"{apr:.1f}%"
        shares_str = _fmt_fp(user_shares)
        apr_box.update(
            f"[dim]APR[/]\n\n"
            f"[bold cyan]{apr_str}[/]\n"
            f"[dim]on {shares_str} FP staked[/]"
        )

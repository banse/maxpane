"""Hero metric boxes for the Onchain Monsters dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


class OCMHeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class OCMHeroMetrics(Horizontal):
    """Row of three hero metric boxes: Supply, Holders, Reward / Monster."""

    DEFAULT_CSS = """
    OCMHeroMetrics > OCMHeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield OCMHeroBox(
            "[dim]SUPPLY[/]\n\n"
            "[dim]Loading...[/]",
            id="ocm-hero-supply",
        )
        yield OCMHeroBox(
            "[dim]STAKED[/]\n\n"
            "[dim]Loading...[/]",
            id="ocm-hero-staked",
        )
        yield OCMHeroBox(
            "[dim]REWARD / MONSTER[/]\n\n"
            "[dim]Loading...[/]",
            id="ocm-hero-reward",
        )

    def update_data(
        self,
        total_supply: int = 0,
        minted_pct: float = 0.0,
        total_staked: int = 0,
        staking_ratio: float = 0.0,
        current_minting_cost_ocmd: float = 0.0,
        **_kwargs,
    ) -> None:
        """Refresh all three hero boxes with live values."""
        # -- Supply --
        supply_box = self.query_one("#ocm-hero-supply", OCMHeroBox)
        if total_supply > 0:
            supply_box.update(
                f"[dim]SUPPLY[/]\n\n"
                f"[bold white]{total_supply:,} / 10K[/]\n"
                f"[dim]{minted_pct:.1f}% minted[/]"
            )
        else:
            supply_box.update(
                "[dim]SUPPLY[/]\n\n"
                "[dim]Loading...[/]"
            )

        # -- Staked --
        staked_box = self.query_one("#ocm-hero-staked", OCMHeroBox)
        if total_staked > 0 or total_supply > 0:
            staked_box.update(
                f"[dim]STAKED[/]\n\n"
                f"[bold white]{total_staked:,}[/]\n"
                f"[dim]{staking_ratio:.1f}% of net supply[/]"
            )
        else:
            staked_box.update(
                "[dim]STAKED[/]\n\n"
                "[dim]Loading...[/]"
            )

        # -- Reward / Monster --
        reward_box = self.query_one("#ocm-hero-reward", OCMHeroBox)
        if current_minting_cost_ocmd > 0:
            cost = f"{current_minting_cost_ocmd:,.0f}" if current_minting_cost_ocmd >= 1 else f"{current_minting_cost_ocmd}"
            reward_box.update(
                f"[dim]REWARD / MONSTER[/]\n\n"
                f"[bold white]1 $OCMD/day[/]\n"
                f"[dim]mint cost: {cost} $OCMD[/]"
            )
        else:
            reward_box.update(
                "[dim]REWARD / MONSTER[/]\n\n"
                "[bold white]1 $OCMD/day[/]\n"
                "[dim]mint cost: -- $OCMD[/]"
            )

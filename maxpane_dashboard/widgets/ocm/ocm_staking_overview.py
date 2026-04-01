"""Staking overview panel for Onchain Monsters dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class OCMStakingOverview(Vertical):
    """Key staking metrics displayed as labeled rows."""

    DEFAULT_CSS = """
    OCMStakingOverview {
        height: auto;
        padding: 0;
    }
    OCMStakingOverview > .overview-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OCMStakingOverview > .overview-row {
        width: 100%;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("STAKING OVERVIEW", classes="overview-title")
        yield Static("", id="ocm-stake-spacer")
        yield Static("[dim]Loading...[/]", classes="overview-row", id="ocm-stake-row-0")
        yield Static("", classes="overview-row", id="ocm-stake-row-1")
        yield Static("", classes="overview-row", id="ocm-stake-row-2")
        yield Static("", classes="overview-row", id="ocm-stake-row-3")
        yield Static("", classes="overview-row", id="ocm-stake-row-4")
        yield Static("", classes="overview-row", id="ocm-stake-row-5")
        yield Static("", classes="overview-row", id="ocm-stake-row-6")

    def update_data(
        self,
        total_staked: int = 0,
        net_supply: int = 0,
        staking_ratio: float = 0.0,
        ocmd_total_supply: float = 0.0,
        daily_emission: float = 0.0,
        days_to_earn_mint: float = 0.0,
        burned_count: int = 0,
        remaining: int = 0,
        faucet_open: bool = True,
        time_to_next_tier: str = "",
        **_kwargs,
    ) -> None:
        """Refresh all metric rows with current data."""
        faucet_str = (
            "[green]Open[/]" if faucet_open else "[red]Closed[/]"
        )
        rows = [
            (
                "Total Staked",
                f"[green]{total_staked:,} / {net_supply:,} ({staking_ratio:.0f}%)[/]",
            ),
            (
                "$OCMD Supply",
                f"{ocmd_total_supply:,.0f}",
            ),
            (
                "Daily Emission",
                f"{daily_emission:,.0f} $OCMD",
            ),
            (
                "Days to Earn Mint",
                f"[yellow]{days_to_earn_mint:.1f} days[/]",
            ),
            (
                "Burned / Remaining",
                f"[red]{burned_count:,}[/] / {remaining:,}",
            ),
            (
                "Faucet",
                faucet_str,
            ),
            (
                "Next Tier",
                f"[cyan]{time_to_next_tier}[/]" if time_to_next_tier else "[dim]--[/]",
            ),
        ]

        for i, (label, value) in enumerate(rows):
            widget = self.query_one(f"#ocm-stake-row-{i}", Static)
            widget.update(f"  {label:<20} {value}")

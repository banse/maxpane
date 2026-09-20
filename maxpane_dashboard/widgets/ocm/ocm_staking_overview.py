"""Staking overview panel for Onchain Monsters dashboard.

The title, its one blank row and the guarded row write are
:class:`~maxpane_dashboard.widgets.panels.PanelBase`'s (Branch 6). This
panel used to paint **two** blank rows: the margin on its own title class in
``minimal.tcss`` *and* a ``Static("")`` spacer yielded from ``compose``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets.panels import LOADING, PanelBase


class OCMStakingOverview(PanelBase):
    """Key staking metrics displayed as labeled rows."""

    TITLE = "STAKING OVERVIEW"

    #: Geometry only -- ``height: auto`` against ``Vertical``'s ``1fr``.
    DEFAULT_CSS = """
    OCMStakingOverview {
        height: auto;
        padding: 0;
    }
    """

    #: One row per metric, in panel order.
    ROW_IDS = tuple(f"ocm-stake-row-{i}" for i in range(7))

    def compose_body(self) -> ComposeResult:
        for index, row_id in enumerate(self.ROW_IDS):
            yield Static(
                LOADING if index == 0 else "", classes="panel-line", id=row_id
            )

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

        for row_id, (label, value) in zip(self.ROW_IDS, rows):
            self.write(f"#{row_id}", f"  {label:<20} {value}")

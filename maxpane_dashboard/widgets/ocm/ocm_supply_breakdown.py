"""Supply breakdown widget for the Onchain Monsters dashboard.

The title, its blank row and the guarded write are
:class:`~maxpane_dashboard.widgets.panels.PanelBase`'s (Branch 6); the
minting-cost tiers below are this collection's own.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static

from maxpane_dashboard.widgets.panels import LOADING, PanelBase

# Minting cost tiers: (start_id, end_id, cost_ocmd)
_TIERS = [
    (0, 1999, 0),
    (2000, 3999, 1),
    (4000, 5999, 2),
    (6000, 7999, 3),
    (8000, 9999, 4),
]


def _tier_info(total_supply: int) -> tuple[str, int]:
    """Return (tier_label, mints_until_next_tier) for current supply."""
    for start, end, cost in _TIERS:
        if total_supply <= end:
            until_next = end - total_supply + 1
            return f"#{start}-#{end} ({cost} $OCMD)", until_next
    return "#8000-#9999 (4 $OCMD)", 0


class OCMSupplyBreakdown(PanelBase):
    """Displays minted / burned / net supply with a progress bar."""

    TITLE = "SUPPLY BREAKDOWN"

    def compose_body(self) -> ComposeResult:
        yield Static(LOADING, classes="panel-line", id="ocm-breakdown-stats")
        yield Static("", classes="panel-line", id="ocm-breakdown-bar")
        yield Static("", classes="panel-line", id="ocm-breakdown-tier")
        yield Static("", classes="panel-line", id="ocm-breakdown-activity")

    def update_data(
        self,
        total_supply: int = 0,
        burned_count: int = 0,
        net_supply: int = 0,
        remaining: int = 0,
        minted_pct: float = 0.0,
        recent_mints: int = 0,
        recent_burns: int = 0,
        **_kwargs,
    ) -> None:
        """Refresh the breakdown display with fresh numbers."""
        stats = (
            f"  [white]Minted:[/]     [bold]{total_supply:>6,}[/]\n"
            f"  [red]Burned:[/]     [bold]{burned_count:>6,}[/]\n"
            f"  [white]Net Supply:[/] [bold]{net_supply:>6,}[/]\n"
            f"  [dim]Remaining:[/]  [bold]{remaining:>6,}[/]"
        )
        self.write("#ocm-breakdown-stats", stats)

        bar_width = 30
        filled = int(minted_pct / 100 * bar_width)
        bar = "=" * max(0, filled - 1) + ">" + " " * max(0, bar_width - filled)
        bar_str = f"  [green][{bar}][/] [bold]{minted_pct:.1f}%[/]"
        self.write("#ocm-breakdown-bar", bar_str)

        # Current tier info
        tier_label, until_next = _tier_info(total_supply)
        tier_str = f"\n  [dim]Tier:[/]  [white]{tier_label}[/]"
        if until_next > 0:
            tier_str += f"\n  [dim]Next:[/]  [cyan]{until_next:,} mints to tier change[/]"
        self.write("#ocm-breakdown-tier", tier_str)

        # Recent activity counts
        activity_parts = []
        if recent_mints > 0:
            activity_parts.append(f"[green]{recent_mints} mints[/]")
        if recent_burns > 0:
            activity_parts.append(f"[red]{recent_burns} burns[/]")
        if activity_parts:
            activity_str = f"\n  [dim]Recent:[/] {' · '.join(activity_parts)} [dim](~100 min)[/]"
        else:
            activity_str = "\n  [dim]Recent:[/] [dim]no activity (~100 min)[/]"
        self.write("#ocm-breakdown-activity", activity_str)

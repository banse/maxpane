"""Supply breakdown widget for the Onchain Monsters dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


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


class OCMSupplyBreakdown(Vertical):
    """Displays minted / burned / net supply with a progress bar."""

    DEFAULT_CSS = """
    OCMSupplyBreakdown > .breakdown-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OCMSupplyBreakdown > .breakdown-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SUPPLY BREAKDOWN", classes="breakdown-title")
        yield Static("", id="ocm-breakdown-spacer")
        yield Static("[dim]Loading...[/]", classes="breakdown-body", id="ocm-breakdown-stats")
        yield Static("", classes="breakdown-body", id="ocm-breakdown-bar")
        yield Static("", classes="breakdown-body", id="ocm-breakdown-tier")
        yield Static("", classes="breakdown-body", id="ocm-breakdown-activity")

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
        self.query_one("#ocm-breakdown-stats", Static).update(stats)

        bar_width = 30
        filled = int(minted_pct / 100 * bar_width)
        bar = "=" * max(0, filled - 1) + ">" + " " * max(0, bar_width - filled)
        bar_str = f"  [green][{bar}][/] [bold]{minted_pct:.1f}%[/]"
        self.query_one("#ocm-breakdown-bar", Static).update(bar_str)

        # Current tier info
        tier_label, until_next = _tier_info(total_supply)
        tier_str = f"\n  [dim]Tier:[/]  [white]{tier_label}[/]"
        if until_next > 0:
            tier_str += f"\n  [dim]Next:[/]  [cyan]{until_next:,} mints to tier change[/]"
        self.query_one("#ocm-breakdown-tier", Static).update(tier_str)

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
        self.query_one("#ocm-breakdown-activity", Static).update(activity_str)

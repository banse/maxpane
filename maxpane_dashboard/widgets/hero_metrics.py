"""Hero metric boxes displayed across the top of the dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard.analytics.leaderboard import format_cookies
from maxpane_dashboard.analytics.production import format_rate


class HeroBox(Static):
    """A single hero metric box with label and value."""

    DEFAULT_CSS = ""


class HeroMetrics(Horizontal):
    """Row of three hero metric boxes: Prize Pool, Season Countdown, Leader."""

    DEFAULT_CSS = """
    HeroMetrics > HeroBox {
        margin: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield HeroBox(
            "[dim]PRIZE POOL[/]\n\n"
            "[dim]Loading...[/]",
            id="hero-prize",
        )
        yield HeroBox(
            "[dim]SEASON COUNTDOWN[/]\n\n"
            "[dim]Loading...[/]",
            id="hero-countdown",
        )
        yield HeroBox(
            "[dim]LEADER[/]\n\n"
            "[dim]Loading...[/]",
            id="hero-leader",
        )

    def update_data(
        self,
        prize_pool_eth: float,
        prize_pool_usd: float,
        hours_remaining: float,
        season_id: int,
        season_active: bool,
        leader_name: str,
        leader_cookies: float,
        leader_rate: float,
    ) -> None:
        """Refresh all three hero boxes with live values."""
        # -- Prize Pool --
        prize_box = self.query_one("#hero-prize", HeroBox)
        prize_box.update(
            f"[dim]PRIZE POOL[/]\n\n"
            f"[bold white]{prize_pool_eth:.2f} ETH[/]\n"
            f"[dim]${prize_pool_usd:,.0f}[/]"
        )

        # -- Season Countdown --
        countdown_box = self.query_one("#hero-countdown", HeroBox)
        if not season_active:
            countdown_box.update(
                f"[dim]SEASON {season_id}[/]\n\n"
                f"[bold yellow]Season Ended[/]"
            )
        else:
            total_seconds = int(hours_remaining * 3600)
            days = total_seconds // 86400
            hours = (total_seconds % 86400) // 3600
            minutes = (total_seconds % 3600) // 60
            countdown_str = f"{days}d {hours}h {minutes}m"

            # Progress bar (assume ~30-day seasons)
            total_season_hours = 30 * 24
            elapsed_fraction = max(
                0.0, min(1.0, 1.0 - hours_remaining / total_season_hours)
            )
            filled = int(elapsed_fraction * 12)
            bar = "\u2588" * filled + "\u2591" * (12 - filled)
            pct = int(elapsed_fraction * 100)

            countdown_box.update(
                f"[dim]SEASON COUNTDOWN[/]\n\n"
                f"[bold white]{countdown_str}[/]\n"
                f"[dim]{bar} {pct}%[/]"
            )

        # -- Leader --
        leader_box = self.query_one("#hero-leader", HeroBox)
        cookies_str = format_cookies(leader_cookies)
        rate_str = format_rate(leader_rate)
        leader_box.update(
            f"[dim]LEADER[/]\n\n"
            f"[bold white]{cookies_str} cookies[/]\n"
            f"[dim]{leader_name}  {rate_str}[/]"
        )

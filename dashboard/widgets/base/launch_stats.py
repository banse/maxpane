"""Launch statistics panel for the Base Terminal Launch Radar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class LaunchStats(Vertical):
    """Static panel showing launch rate and statistics."""

    DEFAULT_CSS = """
    LaunchStats > .launch-stats-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    LaunchStats > .launch-stats-body {
        width: 100%;
        padding: 0 1;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("LAUNCH STATS", classes="launch-stats-title")
        yield Static("[dim]Loading...[/]", id="launch-stats-body", classes="launch-stats-body")

    def update_data(self, launch_stats: dict) -> None:
        """Update the stats display.

        Expected keys:
            launches_1h, graduated_count, launch_rate, avg_age_minutes.
        """
        body = self.query_one("#launch-stats-body", Static)

        if not launch_stats:
            body.update("[dim]No launches[/]")
            return

        launches_1h = launch_stats.get("launches_1h", 0)
        graduated = launch_stats.get("graduated_count", 0)
        rate = launch_stats.get("launch_rate", 0)
        avg_age = launch_stats.get("avg_age_minutes", 0)

        # Format avg age as readable string
        if avg_age >= 60:
            hours = int(avg_age // 60)
            mins = int(avg_age % 60)
            age_str = f"{hours}h {mins}m" if mins else f"{hours}h"
        else:
            age_str = f"{int(avg_age)}m"

        lines = [
            f"  Launches (1h):  [bold]{launches_1h}[/]",
            f"  Graduated:      [bold]{graduated}[/]",
            f"  Launch rate:    [bold]{rate}/hr[/]",
            f"  Avg age:        [bold]{age_str}[/]",
        ]
        body.update("\n".join(lines))

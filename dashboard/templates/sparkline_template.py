"""Cookie trend sparkline charts."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from dashboard.analytics.leaderboard import format_cookies

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 30


def _build_sparkline(points: list[tuple[float, float]], width: int = _SPARK_WIDTH) -> str:
    """Convert time-series points into a sparkline string.

    Each point is ``(timestamp, value)``.  The Y axis is scaled
    relative to the bakery's own min/max range so short-range
    movements are still visible.
    """
    if len(points) < 2:
        return "\u2581" * width

    values = [p[1] for p in points]

    # Take the last `width` values if we have more
    if len(values) > width:
        values = values[-width:]

    lo = min(values)
    hi = max(values)
    span = hi - lo

    chars: list[str] = []
    for v in values:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
            idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    # Pad to width if fewer samples
    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])

    return "".join(chars)


class CookieChart(Vertical):
    """ASCII sparkline chart showing cookie production trends."""

    DEFAULT_CSS = """
    CookieChart > .chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CookieChart > .chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("COOKIE TRENDS (30m)", classes="chart-title")
        yield Static("", classes="chart-line", id="chart-spacer")
        yield Static("[dim]Loading...[/]", classes="chart-line", id="chart-line-0")
        yield Static("", classes="chart-line", id="chart-line-1")
        yield Static("", classes="chart-line", id="chart-line-2")

    def update_data(
        self,
        histories: dict[str, list[tuple[float, float]]],
    ) -> None:
        """Render sparklines for the top 3 bakeries."""
        names = list(histories.keys())[:3]
        line_ids = ["chart-line-0", "chart-line-1", "chart-line-2"]

        colors = ["green", "cyan", "yellow"]

        for i, line_id in enumerate(line_ids):
            widget = self.query_one(f"#{line_id}", Static)
            if i >= len(names):
                widget.update("")
                continue

            name = names[i]
            points = histories[name]
            sparkline = _build_sparkline(points)

            # Current value from last point
            current = points[-1][1] if points else 0.0
            current_str = format_cookies(current)

            # Determine trend arrow
            if len(points) >= 2 and points[-1][1] > points[-2][1]:
                arrow = f"[green]\u25b2[/]"
            elif len(points) >= 2 and points[-1][1] < points[-2][1]:
                arrow = f"[red]\u25bc[/]"
            else:
                arrow = "[dim]\u25cf[/]"

            # Truncate display name to 8 chars, pad to 8
            short_name = name[:8].ljust(8)
            color = colors[i]

            widget.update(
                f"  [dim]{short_name}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )

"""Score sparkline with trend for FrenPet Pet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 32


def _sparkline(values: list[float], width: int = _SPARK_WIDTH) -> str:
    """Build a sparkline string from a list of numeric values.

    Resamples *values* to *width* buckets and maps each to a block
    character from ``_SPARK_CHARS``.
    """
    if not values:
        return "[dim]no data[/]"

    # Resample to width buckets
    n = len(values)
    if n > width:
        step = n / width
        buckets = [values[int(i * step)] for i in range(width)]
    else:
        buckets = list(values)

    lo = min(buckets)
    hi = max(buckets)
    span = hi - lo if hi != lo else 1.0

    chars = []
    for v in buckets:
        idx = int((v - lo) / span * (len(_SPARK_CHARS) - 1))
        idx = max(0, min(len(_SPARK_CHARS) - 1, idx))
        chars.append(_SPARK_CHARS[idx])

    return "".join(chars)


def _format_score_short(score: float) -> str:
    """Format score as compact string: 77200 -> '77.2K'."""
    if abs(score) >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    if abs(score) >= 1_000:
        return f"{score / 1_000:.1f}K"
    return f"{int(score)}"


class ScoreTrend(Vertical):
    """Sparkline chart of score over time with net-today summary."""

    DEFAULT_CSS = """
    ScoreTrend {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    ScoreTrend > .st-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    ScoreTrend > .st-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SCORE TREND (24h)", classes="st-title")
        yield Static("[dim]  Loading...[/]", id="st-content", classes="st-body")

    def update_data(
        self,
        score_history: list[tuple[float, float]],
        velocity: float,
    ) -> None:
        """Update sparkline and net-today display.

        Parameters
        ----------
        score_history:
            List of ``(timestamp, score)`` tuples, oldest first.
        velocity:
            Score velocity in points per day.
        """
        if not score_history:
            self.query_one("#st-content", Static).update("[dim]  No history[/]")
            return

        scores = [s for _, s in score_history]
        spark = _sparkline(scores)
        current = scores[-1]
        current_str = _format_score_short(current)

        # Net change: difference between first and last sample
        net = scores[-1] - scores[0]
        if net >= 0:
            net_str = f"[green]+{_format_score_short(net)}[/]"
        else:
            net_str = f"[red]{_format_score_short(net)}[/]"

        # Velocity
        if velocity >= 0:
            vel_str = f"[green]+{_format_score_short(velocity)}/day[/]"
        else:
            vel_str = f"[red]{_format_score_short(velocity)}/day[/]"

        lines = [
            "",
            f"  [green]{spark}[/]  [bold white]{current_str}[/]",
            "",
            f"  [dim]Net today:[/] {net_str}   [dim]Vel:[/] {vel_str}",
        ]

        self.query_one("#st-content", Static).update("\n".join(lines))

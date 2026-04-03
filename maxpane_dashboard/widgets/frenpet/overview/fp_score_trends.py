"""Population-level trend sparklines for the FrenPet Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 30


def _build_sparkline(values: list[float], width: int = _SPARK_WIDTH) -> str:
    """Convert a list of float values into a sparkline string.

    The Y axis is scaled relative to the series min/max range so
    short-range movements are still visible.
    """
    if len(values) < 2:
        return "\u2581" * width

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


def _format_value(value: float, suffix: str = "") -> str:
    """Format a value with K/M/B suffix."""
    if value >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B{suffix}"
    elif value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{suffix}"
    elif value >= 1_000:
        return f"{value / 1_000:.1f}K{suffix}"
    return f"{value:,.0f}{suffix}"


def _trend_arrow(values: list[float]) -> str:
    """Return a trend arrow based on the last two values."""
    if len(values) >= 2 and values[-1] > values[-2]:
        return "[green]\u25b2[/]"
    elif len(values) >= 2 and values[-1] < values[-2]:
        return "[red]\u25bc[/]"
    return "[dim]\u25cf[/]"


class FPScoreTrends(Vertical):
    """Population-level sparklines: Active pets, Total score, Battle rate."""

    DEFAULT_CSS = """
    FPScoreTrends > .fpo-chart-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPScoreTrends > .fpo-chart-line {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("POPULATION TRENDS", classes="fpo-chart-title")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="fpo-chart-line", id="fpo-chart-active")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-score")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-battles")

    def update_data(
        self,
        top_pets: list,
        score_histories: dict,
        active_pets_history: list[tuple[float, float]] | None = None,
        total_score_history: list[tuple[float, float]] | None = None,
        battle_rate_history: list[tuple[float, float]] | None = None,
    ) -> None:
        """Render population-level sparklines."""
        metrics = [
            ("fpo-chart-active", "Active Pets", active_pets_history or [], ""),
            ("fpo-chart-score", "Total Score", total_score_history or [], ""),
            ("fpo-chart-battles", "Battle Rate", battle_rate_history or [], "/h"),
        ]

        colors = ["green", "cyan", "yellow"]

        for (widget_id, label, history, suffix), color in zip(metrics, colors):
            widget = self.query_one(f"#{widget_id}", Static)

            if not history:
                widget.update(f"  [dim]{label:<14}[/]  [dim]no data[/]")
                continue

            values = [p[1] for p in history]
            sparkline = _build_sparkline(values)
            current = values[-1] if values else 0.0
            current_str = _format_value(current, suffix)
            arrow = _trend_arrow(values)

            padded_label = label[:14].ljust(14)
            widget.update(
                f"  [dim]{padded_label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )

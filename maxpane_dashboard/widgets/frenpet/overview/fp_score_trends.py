"""Pet score trend sparklines for the FrenPet Overview view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 30


def _build_sparkline(points: list[tuple[float, float]], width: int = _SPARK_WIDTH) -> str:
    """Convert time-series points into a sparkline string.

    Each point is ``(timestamp, value)``.  The Y axis is scaled
    relative to the pet's own min/max range so short-range
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


def _format_score(score: float) -> str:
    """Format a score with M/B/K suffix."""
    if score >= 1_000_000_000:
        return f"{score / 1_000_000_000:.1f}B"
    elif score >= 1_000_000:
        return f"{score / 1_000_000:.1f}M"
    elif score >= 1_000:
        return f"{score / 1_000:.1f}K"
    return f"{score:,.0f}"


class FPScoreTrends(Vertical):
    """ASCII sparkline chart showing pet score trends."""

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
        yield Static("PET TRENDS", classes="fpo-chart-title")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-spacer")
        yield Static("[dim]Loading...[/]", classes="fpo-chart-line", id="fpo-chart-line-0")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-line-1")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-line-2")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-line-3")
        yield Static("", classes="fpo-chart-line", id="fpo-chart-line-4")

    def update_data(
        self,
        top_pets: list,
        score_histories: dict,
    ) -> None:
        """Render sparklines for the top 3-5 pets."""
        # Build ordered list of (pet_id, points) from top_pets that have histories
        entries: list[tuple[int, list[tuple[float, float]]]] = []
        for pet in top_pets[:5]:
            pet_id = getattr(pet, "id", None)
            if pet_id is None:
                continue
            points = score_histories.get(pet_id, [])
            entries.append((pet_id, points))

        line_ids = [
            "fpo-chart-line-0",
            "fpo-chart-line-1",
            "fpo-chart-line-2",
            "fpo-chart-line-3",
            "fpo-chart-line-4",
        ]

        colors = ["green", "cyan", "yellow", "magenta", "blue"]

        for i, line_id in enumerate(line_ids):
            widget = self.query_one(f"#{line_id}", Static)
            if i >= len(entries):
                widget.update("")
                continue

            pet_id, points = entries[i]
            sparkline = _build_sparkline(points)

            # Current value from last point
            current = points[-1][1] if points else 0.0
            current_str = _format_score(current)

            # Determine trend arrow
            if len(points) >= 2 and points[-1][1] > points[-2][1]:
                arrow = "[green]\u25b2[/]"
            elif len(points) >= 2 and points[-1][1] < points[-2][1]:
                arrow = "[red]\u25bc[/]"
            else:
                arrow = "[dim]\u25cf[/]"

            # Format pet ID label, pad to 8 chars
            label = f"#{pet_id}"[:8].ljust(8)
            color = colors[i]

            widget.update(
                f"  [dim]{label}[/]  [{color}]{sparkline}[/]  "
                f"[bold]{current_str}[/] {arrow}"
            )

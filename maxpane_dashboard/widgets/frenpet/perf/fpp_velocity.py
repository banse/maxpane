"""Per-pet velocity sparklines for the FrenPet Performance view."""

from __future__ import annotations

import re

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # Misc symbols, emoticons, etc.
    "\U00002702-\U000027b0"  # Dingbats
    "\U0000fe00-\U0000fe0f"  # Variation selectors
    "\U0000200d"             # Zero-width joiner
    "\U000020e3"             # Combining enclosing keycap
    "]+",
    flags=re.UNICODE,
)

_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"
_SPARK_WIDTH = 10


def _build_sparkline(values: list[float], width: int = _SPARK_WIDTH) -> str:
    """Convert a list of float values into a mini sparkline string."""
    if len(values) < 2:
        return "\u2581" * width

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

    while len(chars) < width:
        chars.insert(0, _SPARK_CHARS[0])

    return "".join(chars)


def _velocity_color(velocity: float) -> str:
    """Return color name based on velocity magnitude."""
    if velocity >= 200:
        return "green"
    if velocity >= 100:
        return "cyan"
    if velocity >= 50:
        return "yellow"
    return "dim"


def _truncate(name: str, width: int = 10) -> str:
    """Truncate a name and pad/clip to width."""
    if len(name) > width:
        return name[: width - 1] + "."
    return name.ljust(width)


class FPPerfVelocity(Vertical):
    """Per-pet velocity sparklines showing individual score velocity over time."""

    DEFAULT_CSS = """
    FPPerfVelocity > .fpp-vel-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    FPPerfVelocity > .fpp-vel-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("PET VELOCITY", classes="fpp-vel-title")
        yield Static("[dim]  Loading...[/]", classes="fpp-vel-body", id="fpp-vel-content")

    def update_data(
        self,
        pets: list,
        pet_velocities: dict[int, float] | None = None,
        pet_score_histories: dict[int, list[tuple[float, float]]] | None = None,
    ) -> None:
        """Rebuild per-pet velocity sparklines sorted by velocity descending."""
        velocities = pet_velocities or {}
        histories = pet_score_histories or {}
        content_widget = self.query_one("#fpp-vel-content", Static)

        if not pets:
            content_widget.update("[dim]  No pets[/]")
            return

        # Build pet entries with velocity for sorting
        entries: list[tuple[str, float, list[float]]] = []
        for pet in pets:
            pet_id = int(pet.get("id", 0))
            raw_name = pet.get("name", "") or f"#{pet_id}"
            pet_name = _EMOJI_RE.sub("", raw_name).strip()
            if not pet_name:
                pet_name = f"#{pet_id}"

            velocity = velocities.get(pet_id, 0.0)
            history = histories.get(pet_id, [])
            score_values = [p[1] for p in history] if history else []
            entries.append((pet_name, velocity, score_values))

        # Sort by velocity descending
        entries.sort(key=lambda e: e[1], reverse=True)

        lines: list[str] = []
        for pet_name, velocity, score_values in entries:
            name_str = _truncate(pet_name, 10)
            sparkline = _build_sparkline(score_values)
            color = _velocity_color(velocity)

            if abs(velocity) >= 1_000:
                vel_str = f"+{velocity / 1_000:.1f}K/hr"
            else:
                vel_str = f"+{velocity:,.0f}/hr"

            lines.append(
                f"  [bold white]{name_str}[/]  [{color}]{sparkline}[/]  "
                f"[{color}]{vel_str}[/]"
            )

        content_widget.update("\n".join(lines) if lines else "[dim]  No data[/]")

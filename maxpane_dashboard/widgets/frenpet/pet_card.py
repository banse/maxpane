"""Compact pet card widget for the Wallet View."""

from __future__ import annotations

from textual.widgets import Static


# Sparkline block characters ordered by height.
_SPARK_CHARS = "\u2581\u2582\u2583\u2584\u2585\u2586\u2587\u2588"


def _sparkline(values: list[float], width: int = 12) -> str:
    """Render a list of values as a sparkline string of *width* characters."""
    if not values:
        return "\u2581" * width

    # Sample or pad to *width* points.
    if len(values) > width:
        step = len(values) / width
        sampled = [values[int(i * step)] for i in range(width)]
    else:
        sampled = list(values)
        while len(sampled) < width:
            sampled.insert(0, sampled[0])

    lo = min(sampled)
    hi = max(sampled)
    span = hi - lo if hi != lo else 1.0

    return "".join(
        _SPARK_CHARS[min(int((v - lo) / span * 7), 7)] for v in sampled
    )


def _tod_bar(hours: float, total: float = 72.0, width: int = 10) -> str:
    """Render a TOD progress bar: filled blocks + empty blocks."""
    fraction = max(0.0, min(hours / total, 1.0))
    filled = int(fraction * width)
    empty = width - filled
    return "\u2588" * filled + "\u2591" * empty


def _format_score(score: int | float) -> str:
    """Format a score with commas."""
    return f"{int(score):,}"


class PetCard(Static):
    """Compact card showing one pet's key stats.

    Displayed inside a Horizontal container in the wallet view's pet row.
    """

    DEFAULT_CSS = """
    PetCard {
        width: 32;
        height: 9;
        border: solid $secondary;
        padding: 0 1;
        margin: 0 1 0 0;
    }
    """

    def __init__(self, pet_id: int, **kwargs) -> None:
        super().__init__(**kwargs)
        self.pet_id = pet_id

    def update_data(
        self,
        pet,
        phase: str,
        tod_status: dict,
        velocity: float,
        win_rate: float,
        score_history: list[tuple[float, float]],
    ) -> None:
        """Update the card content with live data.

        Parameters
        ----------
        pet:
            FrenPet model instance.
        phase:
            Growth phase string (Hatchling/Growing/Competitive/Apex).
        tod_status:
            Dict with ``hours_remaining``, ``status``, ``color``.
        velocity:
            Score change in points per day.
        win_rate:
            Win percentage 0-100.
        score_history:
            List of ``(timestamp, score)`` for sparkline rendering.
        """
        hours = tod_status.get("hours_remaining", 0.0)
        color = tod_status.get("color", "dim")
        bar = _tod_bar(hours)

        # Build sparkline from score values.
        scores = [s for _, s in score_history] if score_history else []
        spark = _sparkline(scores)

        # Last delta: difference between last two score samples.
        if len(scores) >= 2:
            delta = int(scores[-1] - scores[-2])
            arrow = "\u25b2" if delta >= 0 else "\u25bc"
            delta_str = f"{arrow} {'+' if delta >= 0 else ''}{delta:,}"
        else:
            delta_str = ""

        # Velocity formatting.
        vel_sign = "+" if velocity >= 0 else ""
        vel_str = f"{vel_sign}{int(velocity):,}/day"

        title = f"PET #{pet.id}"
        lines = [
            f"[bold]{title}[/]",
            f"  {phase} [dim]\u00b7[/] {_format_score(pet.score)} pts",
            f"  ATK {pet.attack_points} / DEF {pet.defense_points}",
            f"  TOD: [{color}]{hours:.0f}h {bar}[/{color}]",
            f"  Win: {win_rate:.0f}%  {vel_str}",
            f"  [dim]{spark}[/]  {delta_str}",
        ]

        self.update("\n".join(lines))

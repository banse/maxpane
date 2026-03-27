"""Per-pet strategic signals for FrenPet Pet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


def _efficiency_color(efficiency: float) -> str:
    """Return color based on battle efficiency percentage."""
    if efficiency >= 70.0:
        return "green"
    elif efficiency >= 50.0:
        return "yellow"
    return "red"


def _threat_color(threat_level: str) -> str:
    """Return color based on threat level."""
    if threat_level == "low":
        return "green"
    elif threat_level == "medium":
        return "yellow"
    return "red"


def _velocity_indicator(velocity: float) -> tuple[str, str]:
    """Return (arrow, color) based on velocity direction."""
    if velocity > 0:
        return "\u25b2 rising", "green"
    elif velocity < 0:
        return "\u25bc falling", "red"
    return "\u25cf stable", "white"


def _format_velocity(velocity: float) -> str:
    """Format velocity as compact string."""
    if abs(velocity) >= 1_000_000:
        return f"{velocity / 1_000_000:+.1f}M"
    if abs(velocity) >= 1_000:
        return f"{velocity / 1_000:+.1f}K"
    return f"{velocity:+.0f}"


class PetSignals(Vertical):
    """Panel displaying per-pet analytical signals and recommendation."""

    DEFAULT_CSS = """
    PetSignals {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    PetSignals > .psig-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    PetSignals > .psig-row {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="psig-title")
        yield Static("", id="psig-spacer")
        yield Static("[dim]  Loading...[/]", classes="psig-row", id="psig-efficiency")
        yield Static("", classes="psig-row", id="psig-staking")
        yield Static("", classes="psig-row", id="psig-rank")
        yield Static("", classes="psig-row", id="psig-threats")
        yield Static("", id="psig-spacer-2")
        yield Static("", classes="psig-row", id="psig-velocity")
        yield Static("", classes="psig-row", id="psig-recommendation")

    def update_data(
        self,
        evaluation: dict,
        threat_level: dict,
        velocity: float,
        rank_info: dict,
        recommendation: str,
    ) -> None:
        """Update all signal lines.

        Parameters
        ----------
        evaluation:
            Dict with ``battle_efficiency``, ``phase``, ``tod_status`` keys.
        threat_level:
            Dict with ``threat_count``, ``threat_level`` keys.
        velocity:
            Score velocity in points per day.
        rank_info:
            Dict with ``rank``, ``total``, ``distance_to_next`` keys.
        recommendation:
            One-line tactical recommendation string.
        """
        efficiency = evaluation.get("battle_efficiency", 0.0)
        eff_col = _efficiency_color(efficiency)
        eff_label = "good" if efficiency >= 60 else "low"

        self.query_one("#psig-efficiency", Static).update(
            f"  [dim]Battle Efficiency[/]   [bold white]{efficiency:.0f}%[/]"
            f"    [{eff_col}]\u25cf {eff_label}[/]"
        )

        # Staking Health
        tod_status = evaluation.get("tod_status", {})
        tod_str = tod_status.get("status", "safe")
        tod_col = tod_status.get("color", "green")

        self.query_one("#psig-staking", Static).update(
            f"  [dim]Staking Health[/]      [{tod_col}]{tod_str.upper()}[/]"
            f"     [{tod_col}]\u25cf {tod_str}[/]"
        )

        # Rank
        rank = rank_info.get("rank", 0)
        total = rank_info.get("total", 0)

        self.query_one("#psig-rank", Static).update(
            f"  [dim]Rank[/] [bold white]#{rank}[/] of {total:,}"
        )

        # Threats
        threat_str = threat_level.get("threat_level", "low")
        threat_count = threat_level.get("threat_count", 0)
        thr_col = _threat_color(threat_str)

        self.query_one("#psig-threats", Static).update(
            f"  [dim]Threats:[/] [bold white]{threat_count}[/] pets"
            f"          [{thr_col}]\u25cf {threat_str}[/]"
        )

        # Velocity
        vel_indicator, vel_col = _velocity_indicator(velocity)
        vel_str = _format_velocity(velocity)

        self.query_one("#psig-velocity", Static).update(
            f"  [dim]Velocity:[/] [bold white]{vel_str}/day[/]"
            f"       [{vel_col}]{vel_indicator}[/]"
        )

        # Recommendation
        self.query_one("#psig-recommendation", Static).update(
            f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]"
        )

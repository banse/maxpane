"""Signals panel for Defense of the Agents dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class DOTASignals(Vertical):
    """Panel displaying DOTA analytical signals and recommendation."""

    DEFAULT_CSS = """
    DOTASignals > .dota-sig-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    DOTASignals > .dota-sig-body {
        padding: 0 1;
        width: 100%;
    }
    DOTASignals > .dota-sig-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="dota-sig-title")
        yield Static("", id="dota-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="dota-sig-body", id="dota-sig-faction")
        yield Static("", classes="dota-sig-body", id="dota-sig-lane")
        yield Static("", classes="dota-sig-body", id="dota-sig-hero")
        yield Static("", id="dota-sig-spacer-2")
        yield Static("", classes="dota-sig-rec", id="dota-sig-recommendation")

    def update_data(
        self,
        faction_balance_signal: dict | None = None,
        lane_pressure_signal: dict | None = None,
        hero_advantage_signal: dict | None = None,
        recommendation: str = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation."""
        # Faction balance
        w = self.query_one("#dota-sig-faction", Static)
        if faction_balance_signal:
            w.update(_fmt(faction_balance_signal))
        else:
            w.update(_fmt({"label": "Faction Balance", "value_str": "--", "color": "dim"}))

        # Lane pressure
        w = self.query_one("#dota-sig-lane", Static)
        if lane_pressure_signal:
            w.update(_fmt(lane_pressure_signal))
        else:
            w.update(_fmt({"label": "Lane Pressure", "value_str": "--", "color": "dim"}))

        # Hero advantage
        w = self.query_one("#dota-sig-hero", Static)
        if hero_advantage_signal:
            w.update(_fmt(hero_advantage_signal))
        else:
            w.update(_fmt({"label": "Hero Advantage", "value_str": "--", "color": "dim"}))

        # Recommendation
        w = self.query_one("#dota-sig-recommendation", Static)
        if recommendation:
            w.update(f"  [bold]-> {recommendation}[/]")
        else:
            w.update("")


def _fmt(sig: dict) -> str:
    """Format a signal row: indicator, label, colored value."""
    label = sig.get("label", "")
    value = sig.get("value_str", "")
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "\u25cf")
    return f"  [{color}]{indicator}[/] {label:<18} [{color}]{value}[/]"

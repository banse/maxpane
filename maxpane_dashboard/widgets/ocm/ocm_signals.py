"""Signals panel for Onchain Monsters dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


class OCMSignals(Vertical):
    """Panel displaying Onchain Monsters analytical signals and recommendation."""

    DEFAULT_CSS = """
    OCMSignals > .signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    OCMSignals > .signals-body {
        padding: 0 1;
        width: 100%;
    }
    OCMSignals > .signals-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="signals-title")
        yield Static("", id="ocm-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="signals-body", id="ocm-sig-staking")
        yield Static("", classes="signals-body", id="ocm-sig-velocity")
        yield Static("", classes="signals-body", id="ocm-sig-burns")
        yield Static("", id="ocm-sig-spacer-2")
        yield Static("", classes="signals-rec", id="ocm-sig-recommendation")

    def update_data(
        self,
        staking_signal: dict | None = None,
        mint_velocity_signal: dict | None = None,
        burn_rate_signal: dict | None = None,
        recommendation: str = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation."""
        # Staking rate
        w = self.query_one("#ocm-sig-staking", Static)
        if staking_signal:
            w.update(_fmt(staking_signal))
        else:
            w.update(_fmt({"label": "Staking Rate", "value_str": "--", "color": "dim"}))

        # Mint velocity
        w = self.query_one("#ocm-sig-velocity", Static)
        if mint_velocity_signal:
            w.update(_fmt(mint_velocity_signal))
        else:
            w.update(_fmt({"label": "Mint Velocity", "value_str": "--", "color": "dim"}))

        # Burn rate
        w = self.query_one("#ocm-sig-burns", Static)
        if burn_rate_signal:
            w.update(_fmt(burn_rate_signal))
        else:
            w.update(_fmt({"label": "Burn Rate", "value_str": "--", "color": "dim"}))

        # Recommendation
        w = self.query_one("#ocm-sig-recommendation", Static)
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

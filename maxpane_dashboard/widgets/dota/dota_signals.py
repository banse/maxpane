"""Signals panel for Defense of the Agents dashboard.

Every row is written on every ``update_data`` call (MEDI-38): a signal the
manager could not compute arrives as ``None`` and renders an explicit
``unavailable`` marker beside its label -- distinct from a signal whose own
``value_str`` is ``--``, which is the analytics saying "nothing to report".
Each row is written inside its own guard so one malformed signal dict
cannot raise into the screen's ``except`` and leave the previous poll's
rows on screen as if they were live.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

#: Shown in place of a signal the backend could not compute this poll.
_UNAVAILABLE = "[yellow]unavailable[/]"


class DOTASignals(Vertical):
    """Panel displaying Defense of the Agents analytical signals and recommendation."""

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
        recommendation: str | None = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation; a missing signal says so."""
        self._render_row("#dota-sig-faction", "Faction Balance", faction_balance_signal)
        self._render_row("#dota-sig-lane", "Lane Pressure", lane_pressure_signal)
        self._render_row("#dota-sig-hero", "Hero Advantage", hero_advantage_signal)

        try:
            w = self.query_one("#dota-sig-recommendation", Static)
            w.update(f"  [bold]-> {recommendation}[/]" if recommendation else "")
        except Exception:
            pass

    def _render_row(self, selector: str, label: str, sig: dict | None) -> None:
        """Write one signal row, degrading to an explicit unavailable state."""
        try:
            w = self.query_one(selector, Static)
        except Exception:
            return
        try:
            if isinstance(sig, dict) and sig:
                w.update(_fmt(sig))
            else:
                w.update(_fmt({"label": label, "value_str": "unavailable",
                               "color": "yellow"}))
        except Exception:
            try:
                w.update(f"  [yellow]\u25cf[/] {label} {_UNAVAILABLE}")
            except Exception:
                pass


def _fmt(sig: dict) -> str:
    """Format a signal row: indicator, label, colored value."""
    label = sig.get("label", "")
    value = sig.get("value_str", "")
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "\u25cf")
    return f"  [{color}]{indicator}[/] {label:<18} [{color}]{value}[/]"

"""Signals panel for Cat Town dashboard.

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


class CTSignals(Vertical):
    """Panel displaying Cat Town analytical signals and recommendation."""

    DEFAULT_CSS = """
    CTSignals > .signals-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CTSignals > .signals-body {
        padding: 0 1;
        width: 100%;
    }
    CTSignals > .signals-rec {
        padding: 0 1;
        width: 100%;
        text-align: center;
        content-align: center middle;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("SIGNALS", classes="signals-title")
        yield Static("", id="ct-sig-spacer")
        yield Static("[dim]  Loading...[/]", classes="signals-body", id="ct-sig-conditions")
        yield Static("", classes="signals-body", id="ct-sig-legendary")
        yield Static("", classes="signals-body", id="ct-sig-cutoff")
        yield Static("", id="ct-sig-spacer-2")
        yield Static("", classes="signals-rec", id="ct-sig-recommendation")

    def update_data(
        self,
        condition_signal: dict | None = None,
        legendary_signal: dict | None = None,
        cutoff_signal: dict | None = None,
        recommendation: str | None = "",
        **_kwargs,
    ) -> None:
        """Update signal lines and recommendation; a missing signal says so."""
        self._render_row("#ct-sig-conditions", "Conditions", condition_signal)
        self._render_row("#ct-sig-legendary", "Legendary", legendary_signal)
        self._render_row("#ct-sig-cutoff", "Top 10 Cutoff", cutoff_signal)

        try:
            w = self.query_one("#ct-sig-recommendation", Static)
            w.update(f"  [dim]\u2192 Recommendation:[/] [bold]{recommendation}[/]" if recommendation else "")
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
    """Format a signal row: label, value, colored indicator."""
    label = sig.get("label", "")
    value = sig.get("value_str", "")
    color = sig.get("color", "dim")
    indicator = sig.get("indicator", "\u25cf")
    return f"  [{color}]{indicator}[/] [dim]{label:<15}[/] [{color}]{value}[/]"

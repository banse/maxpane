"""Alert panel for the Wallet View."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static


# Severity-to-markup mapping.
_SEVERITY_STYLE = {
    "critical": ("red", "\u25cf"),
    "warning": ("dark_orange", "\u25cf"),
    "info": ("dim", "\u25cb"),
}


class AlertsPanel(Vertical):
    """Panel showing warning and critical alerts for managed pets."""

    DEFAULT_CSS = """
    AlertsPanel {
        width: 1fr;
        height: auto;
        padding: 0 1;
    }
    AlertsPanel > .alert-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    AlertsPanel > .alert-body {
        padding: 0 1;
        width: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static("ALERTS", classes="alert-title")
        yield Static("[dim]  No alerts[/]", id="alert-content", classes="alert-body")

    def update_data(self, alerts: list[dict]) -> None:
        """Display warning/critical alerts.

        Each alert dict should contain:
        - ``pet_id``: int
        - ``type``: str (e.g. ``tod_critical``, ``tod_warning``)
        - ``message``: str
        - ``severity``: ``'critical'`` | ``'warning'`` | ``'info'``
        """
        if not alerts:
            self.query_one("#alert-content", Static).update(
                "[dim]  No alerts[/]"
            )
            return

        lines: list[str] = []
        for alert in alerts:
            severity = alert.get("severity", "info")
            color, dot = _SEVERITY_STYLE.get(severity, ("dim", "\u25cb"))
            message = alert.get("message", "")
            lines.append(f"  [{color}]{dot}[/{color}] {message}")

        self.query_one("#alert-content", Static).update("\n".join(lines))

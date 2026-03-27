"""Bottom status bar with key bindings and connection info."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static


def _staleness_color(seconds: float) -> str:
    """Return a color name based on data freshness."""
    if seconds < 30:
        return "green"
    elif seconds < 60:
        return "yellow"
    return "red"


class StatusBar(Horizontal):
    """Footer status bar showing key bindings and connection state."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        width: 100%;
        height: 1;
        background: $surface;
        padding: 0 1;
    }
    StatusBar > .status-left {
        width: 1fr;
        content-align: left middle;
    }
    StatusBar > .status-right {
        width: auto;
        content-align: right middle;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._theme_name = "minimal"
        self._game_name = ""

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]q[/] quit [dim]\u00b7[/] [dim]r[/] refresh [dim]\u00b7[/] "
            "[dim]t[/] theme [dim]\u00b7[/] [dim]tab[/] switch [dim]\u00b7[/] "
            "connecting...",
            classes="status-left",
            id="status-left",
        )
        yield Static(
            f"[dim]maxpane v0.1 \u00b7 {self._theme_name}[/]",
            classes="status-right",
            id="status-right",
        )

    def set_game_name(self, name: str) -> None:
        """Update the displayed game name."""
        self._game_name = name
        self._update_right()

    def set_theme_name(self, name: str) -> None:
        """Update the displayed theme name."""
        self._theme_name = name
        self._update_right()

    def _update_right(self) -> None:
        """Refresh the right-side label."""
        try:
            game_part = f" \u00b7 {self._game_name}" if self._game_name else ""
            self.query_one("#status-right", Static).update(
                f"[dim]maxpane v0.1 \u00b7 {self._theme_name}{game_part}[/]"
            )
        except Exception:
            pass

    def update_data(
        self,
        last_updated_seconds_ago: float,
        error_count: int,
        poll_interval: int,
    ) -> None:
        """Update the status bar with freshness and error info."""
        color = _staleness_color(last_updated_seconds_ago)
        seconds_int = int(last_updated_seconds_ago)

        error_str = ""
        if error_count > 0:
            error_str = f" [dim]\u00b7[/] [red]{error_count} errors[/]"

        self.query_one("#status-left", Static).update(
            f"[dim]q[/] quit [dim]\u00b7[/] [dim]r[/] refresh [dim]\u00b7[/] "
            f"[dim]t[/] theme [dim]\u00b7[/] [dim]tab[/] switch [dim]\u00b7[/] "
            f"{poll_interval}s poll [dim]\u00b7[/] "
            f"[{color}]updated {seconds_int}s ago[/]"
            f"{error_str}"
        )

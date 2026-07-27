"""Bottom status bar with key bindings and connection info."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard import __version__


def _staleness_color(seconds: float) -> str:
    """Return a theme colour variable based on data freshness.

    Theme variables, not CSS colour names.  Textual resolves content markup
    through the CSS name table, where ``green`` is ``#008000`` -- whose
    contrast peaks at 4.09:1 against pure black, so it fails WCAG AA on
    *every* background and no theme can rescue it.  This bar is shared by all
    nine dashboards, and ``updated Ns ago`` measured 2.53-3.68 across all ten
    themes: the worst text in the app.  ``$success``/``$warning``/``$error``
    are required ``Theme`` fields, so they resolve per theme everywhere.

    This is a ``Static``/Content surface, which does resolve ``$`` variables.
    ``RichLog`` and ``DataTable`` cells parse *Rich* markup and would raise
    ``MarkupError`` on the same string -- three dialects, not two.
    """
    if seconds < 30:
        return "$success"
    elif seconds < 60:
        return "$warning"
    return "$error"


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
        self._active_view: str = ""

    def compose(self) -> ComposeResult:
        yield Static(
            "[dim]q[/] quit [dim]\u00b7[/] [dim]r[/] refresh [dim]\u00b7[/] "
            "[dim]m[/] menu [dim]\u00b7[/] [dim]tab[/] switch [dim]\u00b7[/] "
            "connecting...",
            classes="status-left",
            id="status-left",
        )
        yield Static(
            f"[dim]maxpane v{__version__} \u00b7 {self._theme_name}[/]",
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

    def set_active_view(self, view: str) -> None:
        """Update an optional 'active view' marker shown in the right label.

        Screens that toggle between sub-views (e.g. TTT's Fees/Claims) call this
        so the bar surfaces the current state. Screens without a sub-view leave
        this empty and nothing is rendered.
        """
        self._active_view = view or ""
        self._update_right()

    def _update_right(self) -> None:
        """Refresh the right-side label."""
        try:
            game_part = f" \u00b7 {self._game_name}" if self._game_name else ""
            view_part = (
                f" \u00b7 view: {self._active_view}" if self._active_view else ""
            )
            self.query_one("#status-right", Static).update(
                f"[dim]maxpane v{__version__} \u00b7 "
                f"{self._theme_name}{game_part}{view_part}[/]"
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
            f"[dim]m[/] menu [dim]\u00b7[/] [dim]tab[/] switch [dim]\u00b7[/] "
            f"{poll_interval}s poll [dim]\u00b7[/] "
            f"[{color}]updated {seconds_int}s ago[/]"
            f"{error_str}"
        )

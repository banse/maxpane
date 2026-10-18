"""Shared compact footer with a centred indicator for active reads."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from maxpane_dashboard import __version__
from maxpane_dashboard.widgets.markup_safety import flatten


class StatusBar(Horizontal):
    """Keep loading centred independently of the two footer labels."""

    DEFAULT_CSS = """
    StatusBar {
        dock: bottom;
        width: 100%;
        height: 1;
        background: $surface;
        color: $text-muted;
        padding: 0 1;
    }
    StatusBar > Static {
        height: 1;
        min-width: 0;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    StatusBar > .status-left {
        width: 1fr;
        content-align: left middle;
    }
    StatusBar > .status-message {
        width: auto;
        max-width: 100%;
        content-align: center middle;
    }
    StatusBar > .status-message.has-message {
        color: $warning;
    }
    StatusBar > .status-right {
        width: 1fr;
        content-align: right middle;
    }
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._theme_name = "minimal"
        self._game_name = ""
        self._active_view = ""
        self._key_hints = ""
        self._message = ""
        self._last_update: tuple[float, int, int] | None = None
        self._busy = False
        self._loading_frame = 0
        self._loading_timer = None

    def compose(self) -> ComposeResult:
        yield Static(self._ordinary_status(0, 0, 0), classes="status-left", id="status-left")
        yield Static(Text(""), classes="status-message", id="status-message")
        yield Static(Text(""), classes="status-right", id="status-right")

    def on_mount(self) -> None:
        self.call_after_refresh(self._prime_footer)

    def _prime_footer(self) -> None:
        self._update_right()
        self.set_loading(self._busy)
        self._update_message()

    def on_unmount(self) -> None:
        self._busy = False
        self._stop_loading_timer()

    def set_game_name(self, name: str) -> None:
        self._game_name = name
        self._update_right()

    def set_theme_name(self, name: str) -> None:
        self._theme_name = name
        self._update_right()

    def set_active_view(self, view: str) -> None:
        self._active_view = view or ""
        self._update_right()

    def set_key_hints(self, hints: str) -> None:
        """Retain compatibility; dashboard keys are no longer footer content."""
        self._key_hints = hints or ""

    @property
    def message(self) -> str:
        return self._message

    def set_message(self, message: str) -> None:
        """Preserve operation feedback while active reads take visual priority."""
        self._message = flatten(message)
        self._update_message()

    def set_loading(self, busy: bool) -> None:
        """Animate only while a screen reports an active request."""
        busy = bool(busy)
        if busy == self._busy and (not busy or self._loading_timer is not None):
            return
        self._busy = busy
        if not self._busy:
            self._stop_loading_timer()
        elif self.is_mounted and self._loading_timer is None:
            self._loading_frame = 0
            self._loading_timer = self.set_interval(0.2, self._tick_loading)
        self._update_message()

    def _stop_loading_timer(self) -> None:
        if self._loading_timer is not None:
            self._loading_timer.stop()
            self._loading_timer = None

    def _tick_loading(self) -> None:
        if self._busy and self.is_mounted:
            self._loading_frame = (self._loading_frame + 1) % 4
            self._update_message()

    def _update_message(self) -> None:
        if not self.is_mounted:
            return
        text = f"{'◐◓◑◒'[self._loading_frame]} loading" if self._busy else self._message
        widget = self.query_one("#status-message", Static)
        widget.set_class(bool(self._message) and not self._busy, "has-message")
        widget.update(Text(text))

    def _update_left(self) -> None:
        self.query_one("#status-left", Static).update(self._ordinary_status(0, 0, 0))

    def _ordinary_status(self, last_updated_seconds_ago, error_count, poll_interval) -> Text:
        """Age and source errors belong to data diagnostics, not the footer."""
        return Text("q quit · m menu · tab switch")

    def _update_right(self) -> None:
        if not self.is_mounted:
            return
        parts = [f"maxpane v{__version__}", self._theme_name]
        if self._game_name:
            parts.append(self._game_name)
        if self._active_view:
            parts.append(f"view: {self._active_view}")
        self.query_one("#status-right", Static).update(Text(flatten(" · ".join(parts))))

    def update_data(self, last_updated_seconds_ago: float, error_count: int, poll_interval: int) -> None:
        """Accept the existing screen contract without painting source status."""
        self._last_update = (last_updated_seconds_ago, error_count, poll_interval)
        self._update_left()

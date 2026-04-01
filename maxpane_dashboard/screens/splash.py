"""Splash screen shown on startup before the main dashboard."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Middle, Vertical
from textual.screen import Screen
from textual.widgets import Static


LOGO = """\
███╗   ███╗ █████╗ ██╗  ██╗██████╗  █████╗ ███╗   ██╗███████╗
████╗ ████║██╔══██╗╚██╗██╔╝██╔══██╗██╔══██╗████╗  ██║██╔════╝
██╔████╔██║███████║ ╚███╔╝ ██████╔╝███████║██╔██╗ ██║█████╗
██║╚██╔╝██║██╔══██║ ██╔██╗ ██╔═══╝ ██╔══██║██║╚██╗██║██╔══╝
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██║     ██║  ██║██║ ╚████║███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝"""

TAGLINE = "\u30de\u30af\u30b7\u30de\u30a4\u30ba \u30e6\u30a2 \u30da\u30fc\u30f3 \u00b7 \u30df\u30cb\u30de\u30a4\u30ba \u30e6\u30a2 \u30da\u30a4\u30f3"

PROMPT = "press any key"

NOTICE = "\u262e 2026 hisdudeness.eth \u2014 The Dude Abides."


class SplashScreen(Screen):
    """Fullscreen centered splash with logo, shown until any key is pressed."""

    DEFAULT_CSS = """
    SplashScreen {
        background: $background;
    }

    SplashScreen #splash-wrap {
        width: 1fr;
        height: auto;
        align: center middle;
    }

    SplashScreen #logo {
        width: 100%;
        content-align: center middle;
        color: $primary;
        text-style: bold;
    }

    SplashScreen #tagline {
        width: 100%;
        content-align: center middle;
        color: $text-muted;
        margin-top: 1;
    }

    SplashScreen #prompt {
        width: 100%;
        content-align: center middle;
        color: $accent;
        margin-top: 3;
    }

    SplashScreen #notice {
        width: 100%;
        content-align: center middle;
        color: $text-muted;
        dock: bottom;
        height: 1;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Middle():
            with Vertical(id="splash-wrap"):
                yield Static(LOGO, id="logo")
                yield Static(TAGLINE, id="tagline")
                yield Static(PROMPT, id="prompt")
        yield Static(NOTICE, id="notice")

    def on_key(self, event) -> None:
        """Any keypress dismisses the splash and shows the dashboard."""
        self.dismiss(True)

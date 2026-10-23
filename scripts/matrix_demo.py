"""Offline native Matrix animation preview; leaves MaxPane's startup untouched.

Run: .venv/bin/python scripts/matrix_demo.py
Space pauses, R replays, Enter reveals the logo, Q/Escape exits.
"""
from __future__ import annotations

from pathlib import Path
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.text import Text
from textual.app import App, ComposeResult
from textual.widgets import Static


from maxpane_dashboard.intro.matrix import BACKGROUND, DURATION, GREEN, THEME, frame


class Rain(Static):
    def render(self) -> Text:
        return frame(self.size.width, self.size.height, self.app.elapsed)


class MatrixDemo(App):
    TITLE = "MAXPANE · Native Matrix demo"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [("q,escape", "quit", "Quit"), ("space", "pause", "Pause"),
                ("r", "replay", "Replay"), ("enter", "reveal", "Reveal")]
    CSS = """
    Screen { background: $background; }
    #rain { width: 1fr; height: 1fr; overflow: hidden; text-wrap: nowrap; }
    #keys { height: 1; background: $surface; color: $text-muted;
            content-align: center middle; text-wrap: nowrap; }
    """

    def __init__(self, clock=monotonic):
        super().__init__()
        self.register_theme(THEME)
        self.theme = "matrix"
        self.clock = clock
        self.elapsed = 0.0
        self.paused = False

    def compose(self) -> ComposeResult:
        yield Rain(id="rain")
        yield Static("space pause · r replay · ↵ reveal · esc exit", id="keys")

    def on_mount(self):
        self.prepare()
        self.last_tick = self.clock()
        self.timer = self.set_interval(1 / 20, self.tick)
        self.paint()

    def prepare(self):
        """Optional offline scene setup before starting the animation."""

    def paint(self):
        self.query_one(Rain).refresh()

    def tick(self):
        now = self.clock()
        self.elapsed = min(DURATION, self.elapsed + max(0, now - self.last_tick))
        self.last_tick = now
        self.paint()
        if self.elapsed >= DURATION:
            self.timer.pause()

    def action_pause(self):
        if self.elapsed >= DURATION:
            return
        self.paused = not self.paused
        if self.paused:
            self.timer.pause()
        else:
            self.last_tick = self.clock()
            self.timer.resume()

    def action_replay(self):
        self.elapsed, self.paused, self.last_tick = 0.0, False, self.clock()
        self.timer.resume()
        self.paint()

    def action_reveal(self):
        self.elapsed, self.paused = DURATION, False
        self.timer.pause()
        self.paint()


if __name__ == "__main__":
    MatrixDemo().run()

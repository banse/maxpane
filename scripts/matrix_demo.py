"""Offline native Matrix animation preview; leaves MaxPane's startup untouched.

Run: .venv/bin/python scripts/matrix_demo.py
Space pauses, R replays, Enter reveals the logo, Q/Escape exits.
"""
from __future__ import annotations

from pathlib import Path
import random
import sys
from time import monotonic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Color
from textual.widgets import Static

from maxpane_dashboard.screens.splash import LOGO
from maxpane_dashboard.themes import THEMES

CHARS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜ012345789"
TAGLINE = "キープビルディング"
DURATION = 5.0
THEME = THEMES["matrix"]
BACKGROUND = Color.parse(THEME.background)
GREEN = Color.parse(THEME.accent)
INK = [Style(color=BACKGROUND.blend(GREEN, level / 15).rich_color) for level in range(16)]


def frame(width: int, height: int, elapsed: float) -> Text:
    """A deterministic frame, in terminal cells; no I/O or animation state."""
    width, height = max(1, width), max(1, height)
    cells = [[(" ", 0) for _ in range(width)] for _ in range(height)]
    fade = min(1.0, max(0.0, (DURATION - elapsed) / 1.8))
    for x in range(0, width, 2):
        rng = random.Random(x + 42)
        tail = rng.randint(6, max(6, min(20, height)))
        speed = rng.uniform(7, 17)
        head = int(elapsed * speed + rng.randrange(height + tail)) % (height + tail)
        for distance in range(tail):
            y = head - distance
            if 0 <= y < height:
                char = CHARS[(x * 13 + y * 7 + int(elapsed * 7)) % len(CHARS)]
                level = round(15 * (1 - distance / tail) ** 1.6 * fade)
                cells[y][x] = (char if level else " ", level)

    lines = LOGO.splitlines() if width >= 64 and height >= 12 else ["MAXPANE"]
    logo_rows, logo_width = len(lines), max(map(cell_len, lines))
    lines = [*lines, "", TAGLINE]
    top = max(0, (height - len(lines)) // 2)
    for row, line in enumerate(lines):
        label = Text(line)
        label.truncate(width)
        line_width = logo_width if row < logo_rows else label.cell_len
        x = max(0, (width - line_width) // 2)
        y = top + row
        if y >= height:
            break
        for char in label.plain:
            size = cell_len(char)
            reveal = min(1.0, max(0.0, (elapsed - 2.2 - ((x * 7 + row * 11) % 19) / 19) / .8))
            if char != " " and reveal and x + size <= width:
                cells[y][x] = (char, max(1, round(15 * reveal)))
                for extra in range(1, size):
                    cells[y][x + extra] = ("", 0)
            x += size

    result = Text()
    for y, row in enumerate(cells):
        for char, level in row:
            result.append(char, style=INK[level])
        if y < height - 1:
            result.append("\n")
    return result


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
        self.last_tick = self.clock()
        self.timer = self.set_interval(1 / 20, self.tick)
        self.paint()

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

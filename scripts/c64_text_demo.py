"""Offline C64 boot-screen preview, not a BASIC interpreter or hardware emulator.

Run: .venv/bin/python scripts/c64_text_demo.py
40×25 logical characters; terminal glyphs with double-column spacing.
R resets the blinking cursor; Q/Escape exits. Needs 88×34 terminal cells.
"""
from __future__ import annotations

from time import monotonic

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Static


COLUMNS, ROWS = 40, 25
BLUE, LIGHT_BLUE = '#352879', '#6c5eb5'
# Two terminal columns per logical character; four cells of border on every
# side. At a typical 1:2 terminal-cell aspect, this 88×33 frame appears 4:3.
BORDER = 4
MONITOR_WIDTH, MONITOR_HEIGHT = COLUMNS * 2 + BORDER * 2, ROWS + BORDER * 2


def boot_screen() -> tuple[str, ...]:
    rows = [' ' * COLUMNS for _ in range(ROWS)]
    rows[1] = '**** COMMODORE 64 BASIC V2 ****'.center(COLUMNS)
    rows[3] = '64K RAM SYSTEM  38911 BASIC BYTES FREE'.center(COLUMNS)
    rows[5] = 'READY.'.ljust(COLUMNS)
    return tuple(rows)


def monitor_text(cursor_visible: bool) -> Text:
    text = Text()
    border_style = f'{LIGHT_BLUE} on {LIGHT_BLUE}'
    screen_style = f'{LIGHT_BLUE} on {BLUE}'
    border_row = ' ' * MONITOR_WIDTH + '\n'
    text.append(border_row * BORDER, border_style)
    for y, row in enumerate(boot_screen()):
        text.append(' ' * BORDER, border_style)
        for x, char in enumerate(row):
            is_cursor = cursor_visible and y == 6 and x == 0
            text.append(char + ' ', border_style if is_cursor else screen_style)
        text.append(' ' * BORDER + '\n', border_style)
    text.append((border_row * BORDER).rstrip('\n'), border_style)
    return text


class MonitorArea(Container):
    def on_resize(self):
        # The area receives its final size after the screen's layout pass.
        self.call_after_refresh(self.app.fit)


class C64TextDemo(App):
    TITLE = 'C64 · 40×25 text-mode demo'
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [('q,escape', 'quit', 'Quit'), ('r', 'reset', 'Reset')]
    CSS = f"""
    Screen {{ background: #1d1d1d; }}
    #stage {{ width: 1fr; height: 1fr; align: center middle; overflow: hidden; }}
    #monitor {{ width: {MONITOR_WIDTH}; height: {MONITOR_HEIGHT};
                text-wrap: nowrap; overflow: hidden; }}
    #notice {{ width: 100%; height: auto; text-align: center; color: #6c5eb5; }}
    #keys {{ height: 1; background: #252525; color: #999999;
             content-align: center middle; text-wrap: nowrap; }}
    """

    def __init__(self, *, clock=monotonic):
        super().__init__()
        self.clock = clock
        self.started = 0.0
        self.cursor_visible = True

    def compose(self) -> ComposeResult:
        with MonitorArea(id='stage'):
            yield Static(monitor_text(True), id='monitor')
            yield Static(Text('Enlarge terminal to 88×34 cells for the full 40×25 screen.'),
                         id='notice')
        yield Static(Text('C64 · 40×25 · text preview · r reset · q / esc quit'), id='keys')

    def on_mount(self):
        self.started = self.clock()
        self.set_interval(0.1, self.tick)
        self.call_after_refresh(self.fit)

    def fit(self):
        stage = self.query_one('#stage')
        fits = stage.size.width >= MONITOR_WIDTH and stage.size.height >= MONITOR_HEIGHT
        self.query_one('#monitor').display = fits
        self.query_one('#notice').display = not fits

    def tick(self):
        visible = int(max(0, self.clock() - self.started) * 2) % 2 == 0
        if visible != self.cursor_visible:
            self.cursor_visible = visible
            self.query_one('#monitor', Static).update(monitor_text(visible))

    def action_reset(self):
        self.started = self.clock()
        self.tick()


if __name__ == '__main__':
    C64TextDemo().run()

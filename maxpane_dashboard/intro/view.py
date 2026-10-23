"""Native terminal rendering and input adapter for the intro sequence."""
from itertools import groupby
from math import exp, sin
import random
from time import monotonic

from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.color import Color
from textual.constants import DIM_FACTOR
from textual.widgets import Static

from maxpane_dashboard.screens.splash import LOGO, TAGLINE, NOTICE, PROMPT
from maxpane_dashboard.themes import THEMES
from .sequence import IntroSequence
from .settings import IntroConfig, palette

COMPACT = """\
███╗   ███╗ █████╗ ██╗  ██╗
████╗ ████║██╔══██╗╚██╗██╔╝
██╔████╔██║███████║ ╚███╔╝
██║╚██╔╝██║██╔══██║ ██╔██╗
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝"""
TAGLINE_EN = 'maximize your pane · minimize your pain'
RAIN_CHARS = '╔═║╗╚╝╠╣╬╦╩█▓▒░▄▀▌▐0123456789:."=*+-<>¦Ξ₿'


def fit_tail(text: str, width: int) -> str:
    if cell_len(text) <= width:
        return text
    if width < 1:
        return ''
    tail, used = '', 1  # reserve the truncation mark
    for char in reversed(text):
        used += cell_len(char)
        if used > width:
            break
        tail = char + tail
    return '…' + tail


class IntroRenderer:
    """Deterministic elapsed-time frames. Work is bounded by visible cells."""
    def __init__(self, config: IntroConfig, seed=42):
        self.config, self.seed = config, seed
        self.colors = palette(config)
        bg = Color.parse(self.colors['background'])
        self.inks = {key: Style(color=value, bgcolor=self.colors['background'])
                     for key, value in self.colors.items()}
        boardroom = THEMES['matrix']
        subtext = Color.parse(boardroom.background).blend(Color.parse(boardroom.foreground), DIM_FACTOR)
        self.inks['subtext'] = Style(color=subtext.rich_color, bgcolor=bg.rich_color)
        self.gradients = {}
        for key, value in self.colors.items():
            steps = 15 if key == 'logo' else 31
            self.gradients[key] = [Style(color=bg.blend(Color.parse(value), i / steps).rich_color,
                                        bgcolor=bg.rich_color) for i in range(steps + 1)]
        dim, bright = Color.parse(self.colors['rain_dim']), Color.parse(self.colors['rain_bright'])
        self.rain_inks = [Style(color=dim.blend(bright, i / 31).rich_color, bgcolor=bg.rich_color)
                          for i in range(32)]

    def frame(self, seq: IntroSequence, width: int, height: int) -> Text:
        width, height = max(1, width), max(1, height)
        cells = [[(' ', self.inks['background']) for _ in range(width)] for _ in range(height)]

        def put(text, x, y, ink):
            if not 0 <= y < height:
                return
            for char in text:
                size = cell_len(char)
                if not char.isprintable():
                    continue
                if size == 0:
                    # Keep combining marks attached to their preceding cell.
                    previous = x - 1
                    while previous >= 0 and cells[y][previous][0] == '':
                        previous -= 1
                    if previous >= 0:
                        base, style = cells[y][previous]
                        cells[y][previous] = (base + char, style)
                    continue
                if x + size > width:
                    break
                if x >= 0:
                    cells[y][x] = (char, ink)
                    for offset in range(1, size):
                        cells[y][x + offset] = ('', ink)
                x += size

        def centered(text, y, ink):
            put(text, max(0, (width - cell_len(text)) // 2), y, ink)

        if seq.stage == 'typewriter':
            visible, full, typing = seq.typewriter_text()
            if typing and seq.blink:
                visible += '▌'
            put(visible, max(0, (width - cell_len(full)) // 2), height // 2, self.inks['text'])
        elif seq.stage == 'prompt':
            top = max(0, (height - (5 if seq.response is not None else 3)) // 2)
            centered('> Are you ready to enter the Swarm?', top, self.inks['text'])
            cursor = '_' if seq.response is None and seq.blink else ' '
            marker = ' [max]' if len(seq.buffer) >= 64 else ''
            line = fit_tail('> [Y/N]: ' + seq.buffer, max(0, width - 1 - len(marker))) + marker + cursor
            if seq.response is not None:
                line = fit_tail('> [Y/N]: ' + seq.buffer, width)
            centered(line, top + 2, self.inks['text'])
            if seq.response is not None:
                centered(seq.response, top + 4, self.inks['text'])
        elif seq.stage in ('rain', 'logo'):
            full, compact = width >= 100 and height >= 30, width >= 80 and height >= 24
            lines = (LOGO if full else COMPACT if compact else 'M A X P A N E').splitlines()
            logo_width = max(map(cell_len, lines))
            left, top = max(0, (width - logo_width) // 2), max(0, (height - len(lines)) // 2)
            elapsed = seq.elapsed
            if seq.stage == 'rain':
                duration = self.config.rain_duration_ms / 1000
                reveal = min(4.0, max(0.0, elapsed - duration))
                # Smoothly decelerate during the four-second logo transition.
                movement = min(elapsed, duration) + (1 - exp(-reveal))
                fade = (1 - reveal / 4) ** 2
                for x in range(0, width, 1 if compact else 2):
                    rng = random.Random(self.seed + x)
                    speed, tail = rng.uniform(4, 12), rng.randint(5, 20)
                    offset = rng.uniform(0, height)
                    position = movement * speed - offset
                    head = int(position if position < height + tail else position % (height + tail))
                    for distance in range(tail):
                        y = head - distance
                        level = round(31 * .85 ** (distance * 30 / speed) * fade)
                        if 0 <= y < height and level >= 2:
                            char = RAIN_CHARS[(x * 13 + y * 7 + int(movement * 15)) % len(RAIN_CHARS)]
                            put(char, x, y, self.rain_inks[level])
                for row, line in enumerate(lines):
                    for col, char in enumerate(line):
                        # Keep the demo's scattered starts; only the logo fades more slowly.
                        delay = (((left + col) * 7 + row * 11) % 19) / 19
                        opacity = min(1.0, max(0.0, (reveal - delay) / 2.0))
                        if char != ' ' and opacity > 0:
                            put(char, left + col, top + row,
                                self.gradients['logo'][max(1, round(15 * opacity))])
            else:
                if height >= 6:
                    rng = random.Random(self.seed)
                    for _ in range(25):
                        x, edge = rng.randrange(width), rng.randrange(6)
                        y = edge if edge < 3 else height - 1 - (edge - 3)
                        level = round(31 * (1 + sin(elapsed * rng.uniform(.5, 2) + rng.random() * 6.28)) / 2)
                        put(rng.choice('|│'), x, y, self.gradients['rain_dim'][level])
                for row, line in enumerate(lines):
                    put(line, left, top + row, self.inks['logo'])
                tagline_y = top + len(lines) + 2
                tagline = TAGLINE_EN if self.config.tagline == 'english' else TAGLINE
                centered(tagline, tagline_y, self.inks['subtext'])
                if elapsed >= 3:
                    if int((elapsed - 3) / .53) % 2 == 0:
                        centered(PROMPT, tagline_y + 3, self.inks['text'])
                    # Tiny terminals must not have a footer painted over the logo.
                    occupied = max(y for y in (top + len(lines) - 1, tagline_y, tagline_y + 3) if y < height)
                    if height - 2 > occupied:
                        centered(NOTICE, height - 2, self.inks['rain_dim'])

        result = Text(no_wrap=True)
        for y, row in enumerate(cells):
            for style, run in groupby(row, key=lambda cell: cell[1]):
                result.append(''.join(char for char, _ in run), style=style)
            if y < height - 1:
                result.append('\n')
        return result


class IntroCanvas(Static):
    def render(self) -> Text:
        return self.app.renderer.frame(self.app.sequence, self.size.width, self.size.height)


class IntroApp(App[str], inherit_bindings=False):
    """One native UI timer; all sequencing lives in the clock-injected model."""
    TITLE = 'MAXPANE · Python intro'
    ENABLE_COMMAND_PALETTE = False
    CSS = 'IntroCanvas { width: 1fr; height: 1fr; overflow: hidden; text-wrap: nowrap; }'

    def __init__(self, config: IntroConfig, *, clock=monotonic, seed=None,
                 start_at='typewriter', on_accept=None):
        super().__init__()
        self._start_at, self._on_accept = start_at, on_accept
        self.sequence = IntroSequence(config, clock=clock)
        self.sequence.enter(start_at)
        self.renderer = IntroRenderer(config, random.randrange(2**32) if seed is None else seed)

    def compose(self) -> ComposeResult:
        yield IntroCanvas()

    def on_mount(self):
        self.screen.styles.background = self.renderer.colors['background']
        self.sequence.enter(self._start_at)
        self.set_interval(1 / 30, self.tick)

    def tick(self):
        self.sequence.tick()
        if self.sequence.result is not None:
            self.exit(self.sequence.result)
        else:
            self.query_one(IntroCanvas).refresh()

    def on_key(self, event):
        event.stop()
        accepted = self.sequence.accepted
        self.sequence.key(event.key, event.character)
        if not accepted and self.sequence.accepted and self._on_accept is not None:
            self._on_accept()
        self.tick()

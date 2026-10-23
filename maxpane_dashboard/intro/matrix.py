"""Pure Matrix frames shared by the saved demos and dashboard entry effect."""
from __future__ import annotations

import random
from rich.cells import cell_len
from rich.style import Style
from rich.text import Text
from textual.color import Color
from maxpane_dashboard.screens.splash import LOGO
from maxpane_dashboard.themes import THEMES

CHARS = "ｱｲｳｴｵｶｷｸｹｺｻｼｽｾｿﾀﾁﾂﾃﾄﾅﾆﾇﾈﾉﾊﾋﾌﾍﾎﾏﾐﾑﾒﾓﾔﾕﾖﾗﾘﾙﾚﾛﾜ012345789"
TAGLINE = "キープビルディング"
DURATION = 5.0
THEME = THEMES["matrix"]
BACKGROUND = Color.parse(THEME.background)
GREEN = Color.parse(THEME.accent)
INK = [Style(color=BACKGROUND.blend(GREEN, level / 15).rich_color) for level in range(16)]


def frame(width: int, height: int, elapsed: float, *, logo: bool = True) -> Text:
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
    lines = [*lines, "", TAGLINE] if logo else []
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



def reveal_frame(rain, snapshot, width, elapsed, ansi_theme, *,
                 reveal_start=lambda x, y: 2.2, reveal_spaces=False):
    """Blend a terminal snapshot into rain without changing its text or links."""
    chars = list(rain.plain)
    styles = [None] * len(chars)
    for span in rain.spans:
        styles[span.start:span.end] = [span.style] * (span.end - span.start)
    for y, source in enumerate(snapshot):
        x = 0
        previous_offset = None
        for segment in source:
            style = segment.style or Style()
            ink = Color.from_rich_color(style.color or GREEN.rich_color, ansi_theme)
            paper = (Color.from_rich_color(style.bgcolor, ansi_theme, foreground=False)
                     if reveal_spaces and style.bgcolor else None)
            for char in segment.text:
                char_width = cell_len(char)
                if char_width == 0:
                    if previous_offset is not None:
                        chars[previous_offset] += char
                    continue
                previous_offset = None
                reveal = min(1.0, max(0.0, (elapsed - reveal_start(x, y) - ((x * 7 + y * 11) % 19) / 19) / .8))
                if (reveal_spaces or not char.isspace()) and reveal:
                    offset = y * (width + 1) + x
                    chars[offset] = char
                    previous_offset = offset
                    styles[offset] = style + Style(color=BACKGROUND.blend(ink, reveal).rich_color,
                        bgcolor=BACKGROUND.blend(paper, reveal).rich_color if paper else None)
                    for extra in range(1, char_width):
                        chars[offset + extra] = ''
                x += char_width
    result = Text()
    for char, style in zip(chars, styles):
        result.append(char, style)
    return result

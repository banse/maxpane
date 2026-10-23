"""Shared demo/production paint primitives use terminal cells, not code points."""
from rich.console import Console
from rich.segment import Segment
from rich.style import Style
from rich.terminal_theme import DEFAULT_TERMINAL_THEME
from textual.strip import Strip

from maxpane_dashboard.intro.matrix import frame, reveal_frame


def test_reveal_keeps_wide_combining_glyphs_and_link_metadata():
    label = 'A界e\u0301Z'
    style = Style(color='white', link='https://example.com', meta={'copy': 'value'})
    result = reveal_frame(frame(6, 1, 4.99, logo=False),
                          [Strip([Segment(label, style)])], 6, 4.99,
                          DEFAULT_TERMINAL_THEME)
    assert result.plain == label + ' '
    assert result.cell_len == 6
    ink = result.get_style_at_offset(Console(), 1)
    assert ink.link == style.link and ink.meta == style.meta

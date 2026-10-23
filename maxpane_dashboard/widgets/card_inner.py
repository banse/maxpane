"""Shared body colors and rich text padding for Surf card insets."""
import re

from rich.color import Color, blend_rgb
from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets.panels import HeroBoxBase


class LoadingCard(HeroBoxBase):
    """A missing-value pulse driven by the screen's existing local clock."""

    _card_loading = False
    _card_loading_frame = 0
    _has_missing_value = False

    def _can_load_card(self):
        return True

    def set_card_loading(self, busy: bool, frame: int):
        busy = bool(busy and self._can_load_card())
        changed = busy != self._card_loading or busy and frame != self._card_loading_frame
        self._card_loading, self._card_loading_frame = busy, frame
        if changed and self._has_missing_value:
            self.refresh()

    def loading_value(self, value: Text) -> Text:
        """Replace an explicit whole missing field, never punctuation in prose."""
        if value.plain.strip() not in ('-', '--', '—'):
            return value
        self._has_missing_value = True
        if not self._card_loading or not self._can_load_card():
            return value
        palette = self.app.get_css_variables()
        background = Color.parse(palette['background']).get_truecolor()
        accent = Color.parse(palette['accent']).get_truecolor()
        strength = (.35, .5, .7, .9, 1, .9, .7, .5)[self._card_loading_frame % 8]
        ink = Style(color=Color.from_triplet(blend_rgb(background, accent, strength)),
                    bgcolor=palette['background'], dim=False, bold=False)
        return Text('⛋', style=ink)

    def loading_caption(self, value: Text) -> Text:
        """Pulse missing numbers in a generated numeric caption, never prose/dates."""
        matches = list(re.finditer(r'(?<![\w-])(?:--|—|-)(?![\w-])', value.plain))
        if not matches:
            return value
        result = value.copy()
        for match in reversed(matches):
            start, end = match.span()
            result = result[:start] + self.loading_value(result[start:end]) + result[end:]
        return result


def inner_styles(palette, *, active=False, frame_color=None, ansi_theme=None, text_color="white"):
    """Return label, value and numeric-readout styles for the final frame."""
    label = Style(color=text_color, bgcolor=palette["background"], dim=False)
    value = Style(color=palette["foreground"], bgcolor=palette["background"], dim=False)
    if frame_color is not None and frame_color.get_truecolor(ansi_theme) == Color.parse("red").get_truecolor(ansi_theme):
        return label, value, value + Style(color="yellow")
    digit = value + Style(color="green") if active else value
    if not active and frame_color is None:
        digit = value + Style(color=text_color)
    return label, value, digit


def padded_inner_row(row: Text, inside: int, *, align="left") -> Text:
    """Fit a copied rich row between one blank cell at each inset edge."""
    inside = max(0, inside)
    if inside < 2:
        return Text(" " * inside, style=row.style)
    fitted = row.copy()
    fitted.truncate(inside - 2, overflow="ellipsis")
    fitted.align(align, inside - 2)
    return Text(" ", style=row.style).append_text(fitted).append(" ")

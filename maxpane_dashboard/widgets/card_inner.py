"""Shared body colors and rich text padding for Surf card insets."""
import re

from rich.color import Color
from rich.style import Style
from rich.text import Text
from textual.color import Color as TextualColor

from maxpane_dashboard.widgets.panels import HeroBoxBase

_COUNT_CAPTION = re.compile(
    r'(?:^|(?<=·))\s*(?P<number>--|—|-)(?=\s*(?:'
    r'(?:agent|workflow|chain|token|job|seat|wallet|model|request|collection|collaborator|contributor|record|pool|signal)s?'
    r'|working|building|build|bld|open|new|cached|online|accepted|attempts)\b)',
    re.IGNORECASE,
)


def loading_fraction(frame: int) -> float:
    """One shared fade curve for the screen-driven loading animations."""
    return (0, .25, .5, .75, 1, .75, .5, .25)[frame % 8]


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
        return self._loading_text('◇')

    def loading_block(self, value: Text, width: int) -> list[Text] | None:
        """Use the existing three body rows; keep a compact mark if too narrow."""
        indicator = self.loading_value(value)
        if indicator is value:
            return None
        if width < 6:
            return [Text(''), indicator, Text('')]
        return [self._loading_text(row) for row in ('      ', '  <>  ', '      ')]

    def _loading_text(self, characters: str) -> Text:
        palette = self.app.get_css_variables()
        dark = TextualColor.parse(palette['background']).monochrome
        light = TextualColor.from_rich_color(self.rich_style.color, self.app.ansi_theme).monochrome
        fraction = loading_fraction(self._card_loading_frame)
        shade = dark.blend(light, fraction)
        ink = Style(color=shade.rich_color,
                    bgcolor=palette['background'], dim=False, bold=False)
        indicator = Text(characters, style=ink)
        # A span keeps the inverse background off alignment/padding cells.
        indicator.stylize(Style(bgcolor=dark.blend(light, 1 - fraction).rich_color), 0, len(indicator))
        return indicator

    @staticmethod
    def count_caption(value: Text) -> Text:
        """Owner display fallback for count footers; source facts stay unknown."""
        result = value.copy()
        for match in reversed(list(_COUNT_CAPTION.finditer(value.plain))):
            start, end = match.span('number')
            zero = result[start:start + 1]
            zero.plain = '0'
            result = result[:start] + zero + result[end:]
        return result

    def loading_caption(self, value: Text) -> Text:
        """Pulse missing numbers in a generated numeric caption, never prose/dates."""
        value = self.count_caption(value)
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

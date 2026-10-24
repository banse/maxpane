"""Shared body colors and rich text padding for Surf card insets."""
import re

from rich.color import Color
from rich.style import Style
from rich.text import Text

from maxpane_dashboard.widgets.panels import HeroBoxBase
from maxpane_dashboard.widgets.card_values import CardValues, MISSING

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
    """Presentation memory shared by the boardroom and dashboard cards."""

    _card_loading = False
    _card_loading_frame = 0
    _has_missing_value = False

    def _can_load_card(self):
        return True

    def __init__(self, *args, **kwargs):
        self._values = CardValues()
        self._value_scope = None
        super().__init__(*args, **kwargs)

    def reset_display_values(self):
        self._values.clear()

    def set_value_scope(self, scope):
        if scope != self._value_scope:
            self.reset_display_values()
            self._value_scope = scope

    def set_card_loading(self, busy: bool, frame: int):
        # The screen still owns its footer/caption clock; cards never pulse.
        self._card_loading, self._card_loading_frame = bool(busy), frame

    def loading_value(self, value: Text) -> Text:
        return Text('', style=value.style) if MISSING.fullmatch(value.plain.strip()) else value

    def retained_meter(self, value: Text) -> Text:
        previous = self._values.retain('meter-rich', value, missing=bool(MISSING.search(value.plain)))
        if previous is not None:
            return previous
        result = value.copy()
        for match in reversed(list(MISSING.finditer(value.plain))):
            result = result[:match.start()] + result[match.end():]
        result.rstrip()
        return result

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
        # Compatibility for generated numeric captions; observations are retained
        # at set_record/set_data, before this final formatting step.
        text = CardValues().field('caption', value.plain, numeric=True)
        return Text(text, style=value.style)


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

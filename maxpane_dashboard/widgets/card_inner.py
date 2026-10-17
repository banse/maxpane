"""Shared body colors and rich text padding for Surf card insets."""
from rich.color import Color
from rich.style import Style
from rich.text import Text


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

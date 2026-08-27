"""Pure terminal-cell fitting primitives shared by text widgets.

Python string length is not terminal width: CJK and most emoji occupy two
cells.  These helpers use Rich's cell implementation for both decisions and
cuts so a widget can fit content before handing it to a non-wrapping
compositor.  Values are plain text; callers escape or style them afterwards.
"""

from __future__ import annotations

from rich.cells import cell_len, set_cell_size

__all__ = ["fit_cell", "pad_cell"]

_ELLIPSIS = "…"


def fit_cell(value: str, width: int) -> tuple[str, bool]:
    """Fit ``value`` into at most ``width`` cells and report truncation.

    A truncated value ends in one cell-wide ``…``.  If a double-width glyph
    straddles the boundary, Rich replaces the partial cell with padding; it
    is stripped before the marker so a half glyph is never emitted.
    """
    if width <= 0:
        return "", bool(value)
    if cell_len(value) <= width:
        return value, False
    fitted = set_cell_size(value, max(width - cell_len(_ELLIPSIS), 0)).rstrip()
    return fitted + _ELLIPSIS, True


def pad_cell(value: str, width: int) -> str:
    """Right-pad ``value`` to at least ``width`` terminal cells.

    Padding never truncates an oversized value; fitting remains the explicit
    job of :func:`fit_cell`.  Keeping those operations separate preserves the
    original Surf helper's behaviour while replacing character-counted
    format padding with cell-aware ``set_cell_size``.
    """
    return set_cell_size(value, max(width, cell_len(value), 0))

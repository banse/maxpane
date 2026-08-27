"""Pure helpers for width-tiered terminal tables.

The curator tables established the repository's width-tier contract: choose
the widest complete column set that fits, rebuild a ``DataTable`` only when
that set changes, and always advertise columns that were shed.  NETWORK
tables need the same rules, so the implementation lives at the widget
package boundary instead of under one screen.

This module owns no data, clock, or I/O.  ``install_columns`` uses only the
small ``DataTable``-shaped protocol supplied by its caller, which also keeps
the remaining helpers straightforward to unit test without a Textual app.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.errors import MarkupError
from rich.text import Text

__all__ = [
    "WIDEN_HINT",
    "cells",
    "install_columns",
    "pick_tier",
    "tier_cost",
    "title_with_hint",
    "with_optional_suffix",
]

#: The shortest honest notice that a width tier omitted something.
WIDEN_HINT = "‹ widen"


def tier_cost(columns) -> int:
    """Return the rendered width of ``columns``, including table padding.

    A Textual ``DataTable`` adds one cell of padding on each side of every
    declared column.  Empty column sets cost nothing; no phantom inter-cell
    gap is introduced.
    """
    return sum(width + 2 for _key, _header, width in columns)


def pick_tier(tiers, width: int):
    """Return ``(name, columns, hint)`` for the widest tier that fits.

    ``width <= 0`` is Textual's pre-layout state and optimistically selects
    the widest tier.  The final tier is the explicit too-narrow fallback.
    """
    for name, cost, columns, hint in tiers:
        if width <= 0 or width >= cost:
            return name, columns, hint
    name, _cost, columns, hint = tiers[-1]
    return name, columns, hint


def install_columns(table, columns, current) -> bool:
    """Install ``columns`` on ``table`` and report whether they changed.

    Rows are always cleared.  Columns are rebuilt only for a different tier,
    preserving cursor and scroll state on ordinary data refreshes.
    """
    if columns != current:
        table.clear(columns=True)
        for _key, header, width in columns:
            table.add_column(header, width=width)
        return True
    table.clear()
    return False


def cells(values: dict, columns, default: str = "") -> list:
    """Project ``values`` onto ``columns`` in declaration order."""
    return [values.get(key, default) for key, _header, _width in columns]


def _markup_cell_len(markup: str) -> int:
    """Measure trusted title markup as the terminal paints it.

    Titles normally contain only module-owned markup.  The fallback keeps a
    malformed title measurable without letting a presentation helper raise;
    it deliberately treats the malformed markup-looking text as literal.
    """
    try:
        return Text.from_markup(markup).cell_len
    except MarkupError:
        return cell_len(markup)


def title_with_hint(title: str, hint: str, width: int) -> tuple[str, bool]:
    """Return ``(markup, placed)`` for a title and its width-loss hint.

    The descriptive hint first degrades to :data:`WIDEN_HINT`.  ``placed``
    is false only when neither fits, telling the caller to put the marker in
    the body instead.  Measurements use terminal cells, so CJK and emoji do
    not cross a boundary that ASCII-only ``len`` arithmetic said was safe.
    """
    if not hint:
        return title, True
    for candidate in (hint, WIDEN_HINT):
        text = f"{title}  [yellow]{candidate}[/]"
        if width <= 0 or _markup_cell_len(text) <= width:
            return text, True
    return title, False


def with_optional_suffix(base: str, suffix: str, width: int) -> str:
    """Append ``suffix`` only when the raw rendered text fits ``width``."""
    if not suffix:
        return base
    if width <= 0 or cell_len(base + suffix) <= width:
        return base + suffix
    return base

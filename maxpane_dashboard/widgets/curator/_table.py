"""Width-tier plumbing shared by the three curator ``DataTable`` panels.

The leaderboard, the closest-calls board and the cluster table all do the
same four things: pick the widest column set that fits, install it only when
it changed, project a row dict onto it, and append a ``‹ widen`` marker to
the title naming what was shed.  Written three times they drift — that is
how ``coerce_points`` ended up with six copies and three of them unhardened
(MEDI-36) — so they are written once here.

A **tier** is ``(name, cost, columns, hint)``:

* ``columns`` is a tuple of ``(key, header, width)``;
* ``cost`` is the rendered width the tier needs.  ``DataTable`` pads every
  cell by one column on each side, so a tier's cost is
  ``sum(width) + 2 * len(columns)`` — :func:`tier_cost` computes it and
  ``test_every_declared_tier_cost_is_the_measured_one`` asserts each
  declaration against it, because a hand-typed cost that drifts low makes a
  panel choose a layout it cannot render and clip in silence;
* ``hint`` names the columns this tier gave up, and is empty for the widest.

Pure functions and one ``DataTable`` mutation; no Textual layout knowledge,
no data-layer imports.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.markup_safety import visible_len

__all__ = [
    "WIDEN_HINT",
    "cells",
    "has_column",
    "pick_tier",
    "install_columns",
    "tier_cost",
    "title_with_hint",
    "width_of",
]

#: The bare marker, for a title bar too narrow to carry the descriptive one.
#: Never nothing: "columns were dropped here" is the contract.
WIDEN_HINT = "‹ widen"


def tier_cost(columns) -> int:
    """Rendered columns a column set needs, ``DataTable`` cell padding included."""
    return sum(width for _key, _header, width in columns) + 2 * len(columns)


def pick_tier(tiers, width: int):
    """``(name, columns, hint)`` — the widest tier that fits ``width``.

    ``width <= 0`` means "not laid out yet" and optimistically picks the
    widest; every panel here re-renders from ``on_resize`` once it has a size.
    """
    for name, cost, columns, hint in tiers:
        if width <= 0 or width >= cost:
            return name, columns, hint
    name, _cost, columns, hint = tiers[-1]
    return name, columns, hint


def install_columns(table, columns, current) -> bool:
    """Give ``table`` this column set; return whether it had to be rebuilt.

    ``DataTable.clear(columns=True)`` is only paid when the set actually
    changed — rebuilding the columns on every refresh resets the cursor and
    the scroll position under the reader's hands.
    """
    if columns != current:
        table.clear(columns=True)
        for _key, header, width in columns:
            table.add_column(header, width=width)
        return True
    table.clear()
    return False


def cells(values: dict, columns, default: str = "") -> list:
    """Project ``values`` onto the active columns, in their order."""
    return [values.get(key, default) for key, _header, _width in columns]


def has_column(columns, key: str) -> bool:
    return any(col_key == key for col_key, _header, _width in columns)


def width_of(columns, key: str, fallback: int) -> int:
    for col_key, _header, width in columns:
        if col_key == key:
            return width
    return fallback


def title_with_hint(title: str, hint: str, width: int) -> tuple[str, bool]:
    """``(markup, placed)`` — the title with as much of the hint as fits.

    The title itself is never abbreviated (the screen tests look for it, and
    so does a reader scanning the row); the *hint* degrades to the bare
    :data:`WIDEN_HINT`.

    ``placed`` is False when even that did not fit, and the caller **must**
    put the marker somewhere else — the note line.  Going silent is not an
    option this codebase allows: a shed column that is not announced is
    indistinguishable from data that is not there, which is the whole reason
    the tiers exist.  A 26-column cluster panel reaches this case, so it is
    not theoretical.
    """
    if not hint:
        return title, True
    for candidate in (hint, WIDEN_HINT):
        text = f"{title}  [yellow]{candidate}[/]"
        if width <= 0 or visible_len(text) <= width:
            return text, True
    return title, False

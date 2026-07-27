"""Escaping helpers for third-party text rendered through Rich markup.

Textual's ``DataTable`` does **not** parse markup when you call ``add_row``.
It stores the raw ``str`` and defers ``Text.from_markup`` to
``_on_idle -> _update_dimensions -> default_cell_formatter``. A cell value
containing invalid markup (e.g. a player-chosen name like ``"[/x] Bakers"``)
therefore raises ``rich.errors.MarkupError`` *inside the message pump*, well
outside any ``try/except`` around the refresh call that added the row --
which crashes the whole app, on every refresh.

Every string that originates from an HTTP API, an onchain string field, or
any other party's keyboard must go through :func:`safe_markup` before it is
interpolated into a markup string or handed to ``add_row`` / ``Static.update``.

Use :func:`safe_markup` for the value; keep the markup tags around it::

    name = safe_markup(bakery.name)
    table.add_row(f"[bold]{name}[/]", ...)
"""

from __future__ import annotations

from rich.markup import escape

__all__ = ["safe_markup"]


def safe_markup(value: object) -> str:
    """Return ``value`` as a string that Rich will render literally.

    ``None`` becomes an empty string; everything else is coerced with
    ``str()`` and then escaped so square brackets are shown rather than
    parsed as markup tags.
    """
    if value is None:
        return ""
    return escape(str(value))

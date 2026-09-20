"""Formatters shared by more than one ttt widget.

The dashboard-specific layer over ``widgets/fmt.py``, in the shape
``widgets/surf/``, ``widgets/curator/`` and ``widgets/cattown/`` already
use: a helper that two modules in this package need is hoisted here in
the same change rather than declared twice (Branch 7, WP-B --
``_safe_symbol`` was a byte-identical copy in ``ttt_leaderboard.py`` and
``ttt_fees_table.py``, which is how a fix to one of them would have
reached neither the other nor the reader).
"""

from __future__ import annotations

from maxpane_dashboard.widgets.fmt import DASH

__all__ = ["safe_symbol"]


def safe_symbol(sym) -> str:
    """Strip non-printable chars from a token symbol; truncate to 8 chars.

    **:data:`~maxpane_dashboard.widgets.fmt.DASH`, not ``None``** -- the
    two tables that call this hand the result to ``address_text`` as a
    ``label``, and a ``None`` label would make the cell fall back to the
    bare address, which needs ``address_text``'s ``MIN_SHORT_COLS`` floor
    (11 cells). ``ttt_fees_table``'s real, CSS-constrained region cannot
    afford that at the app's 143-column pin (see its ``_SYM_WIDTH``
    ``#:`` block). The icon copies the real address regardless of which
    label it is given, so a placeholder costs nothing the address rule
    requires -- it is the same "a name stands in for the address" shape as
    a known symbol, with ``--`` as the name.

    No ``safe_markup``: the cleaned string is appended by ``address_text``
    as plain ``Text``, never parsed as markup.
    """
    if sym is None:
        return DASH
    try:
        cleaned = "".join(ch for ch in str(sym) if ch.isprintable())
    except Exception:
        return DASH
    cleaned = cleaned.strip()
    return cleaned[:8] if cleaned else DASH

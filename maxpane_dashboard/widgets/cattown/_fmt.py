"""Cat Town-specific pure formatters, shared inside this package.

Branch 7 of the refactor programme (WP-A). ``_RARITY_COLORS`` was written
out **three times** in this package -- in ``ct_leaderboard``, in
``ct_best_plays`` and, dead, in ``ct_activity_feed``, which never coloured
anything by rarity. Three copies of one mapping means a rarity tier added to
one of them reaches neither of the others; this is the one.

``_fmt_kibble`` and ``_countdown`` live here for the same reason rather than
because two modules need them today: they are Cat Town's own number words,
and the hero box is not a better place to look for them than the package's
formatter module. Nothing dashboard-agnostic belongs here -- ``widgets/fmt.py``
already owns the ages, the countdowns, the dashes and ``hhmm``, and
``sparkline_common.fmt_compact`` owns the K/M/B suffix; ``_fmt_kibble``
differs from it (no ``B``, ``,`` grouping under 1000) and is kept because a
prize pool's digits are a pixel, not a refactor.

Pure functions: no I/O, no clock, no Textual. Escaping is the caller's job
(``markup_safety.safe_markup``), as in ``widgets/curator/_fmt.py``.
"""

from __future__ import annotations

__all__ = ["_RARITY_COLORS", "_fmt_kibble", "_countdown"]

#: Catch rarity -> Rich colour. The one copy.
_RARITY_COLORS = {
    "Common": "dim",
    "Uncommon": "white",
    "Rare": "cyan",
    "Epic": "magenta",
    "Legendary": "yellow",
}


def _fmt_kibble(amount: float) -> str:
    """Format a KIBBLE amount with a K/M suffix."""
    if amount >= 1_000_000:
        return f"{amount / 1_000_000:.1f}M"
    if amount >= 1_000:
        return f"{amount / 1_000:.1f}K"
    return f"{amount:,.0f}"


def _countdown(seconds: int) -> str:
    """``3d 4h 5m`` / ``4h 5m`` / ``5m`` -- the largest two units that apply."""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    mins = (seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {mins}m"
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins}m"

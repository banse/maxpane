"""Shared pure formatters for the surf widgets.

These live in one private module because ``fmt_age`` is needed by both the
signals panel (``FIRED 2h ago``) and the feed title (``last 2h ago``), and a
second copy is how the sparkline helpers drifted apart before MEDI-36.
Pure functions, no I/O, no Textual imports, nothing raises.

**Escaping contract: callers escape, not this module.** Every function here
returns plain text, never markup-safe text. ``long_addr`` is the one
formatter that can carry attacker-controlled bytes through unchanged (an
on-chain address string, in the pathological case a display name or symbol
misrouted through it) — it does **not** call ``safe_markup`` on its output.
The calling widget owns escaping: pass every value this module returns
through ``widgets.markup_safety.safe_markup`` before it reaches
``Text.from_markup`` or a ``DataTable`` cell. Escaping here as well as at the
widget would double-escape and print literal ``\\[`` to the user, so this
module deliberately does not import ``safe_markup`` at all.
"""

from __future__ import annotations

import time

from maxpane_dashboard.widgets.sparkline_common import fmt_compact

__all__ = [
    "DASH",
    "EMDASH",
    "as_float",
    "fmt_age",
    "fmt_price",
    "fmt_compact",
    "fmt_liquidity",
    "long_addr",
    "hhmm",
    "mmdd",
]

DASH = "--"
EMDASH = "—"


def as_float(value):
    """Coerce to ``float`` or return ``None`` -- never raise, never 0-coerce."""
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return out


def fmt_age(seconds) -> str:
    """``45s`` / ``12m`` / ``2h`` / ``3d``; ``--`` for unknown or negative.

    A negative age would mean an event from the future -- that is a corrupt
    input, and rendering it as ``0s`` would claim "right now" about garbage.
    """
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    if s < 90:
        return f"{s:.0f}s"
    if s < 90 * 60:
        return f"{s / 60:.0f}m"
    if s < 36 * 3600:
        return f"{s / 3600:.0f}h"
    return f"{s / 86400:.0f}d"


def fmt_price(value) -> str:
    """USD price at IMD-scale precision (a ~$0.71 token, not a sub-cent one)."""
    v = as_float(value)
    if v is None:
        return DASH
    a = abs(v)
    if a >= 1:
        return f"${v:,.2f}"
    if a >= 0.01:
        return f"${v:.4f}"
    if a > 0:
        return f"${v:.6f}"
    return "$0.00"


def fmt_liquidity(value) -> str:
    """Raw v3 liquidity is a uint128 ~1e19; suffixes lie at that magnitude."""
    v = as_float(value)
    if v is None:
        return DASH
    if abs(v) >= 1e12:
        return f"{v:.2e}"
    return fmt_compact(v)


def long_addr(value) -> str:
    """``0x`` + first 8 hex + ``…`` + last 6 -- the anti-poisoning form.

    Live spoofs of both fee recipients exist in frenpet.eth's history today;
    they collide with the real addresses on first-6/last-4 (what ``0xAB..CD``
    shorteners show) but not on this window (PRD §4).

    Returns raw, unescaped text -- including for short (<=17 char) inputs
    that pass through verbatim. The calling widget must pass the result
    through ``safe_markup`` before handing it to markup or a table; this
    formatter never escapes, so it never double-escapes either.
    """
    if not value:
        return DASH
    s = str(value).strip()
    if not s:
        return DASH
    if len(s) <= 17:
        return s
    return f"{s[:10]}…{s[-6:]}"


def hhmm(timestamp) -> str:
    """``HH:MM`` local time from unix seconds; ``??:??`` when unusable."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??:??"
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??:??"


def mmdd(timestamp) -> str:
    """``MM-DD`` local time from unix seconds; ``??-??`` when unusable."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return "??-??"
        t = time.localtime(ts)
        return f"{t.tm_mon:02d}-{t.tm_mday:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return "??-??"

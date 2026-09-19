"""Shared pure formatters for every dashboard's widgets.

What lives here is the formatting every dashboard needs and none owns: the
unknown markers, ``as_float``, ages, countdowns, points, percentages, the
local ``HH:MM`` / ``MM-DD`` stamps and a plain ETH quantity.  It was hoisted on
2026-09-20 (HANDOVER §3, ``docs/refactor_programme_2026_09.md`` Branch 3 WP-B)
out of ``widgets/surf/_fmt.py`` and ``widgets/curator/_fmt.py``, whose
``as_float`` and ``fmt_age`` were byte-identical copies and whose ``hhmm``
differed only in its unknown marker -- and in that the curator copy raised
``OverflowError`` on ``float("inf")`` where surf's returned the marker; the
non-raising body is the one kept.  Those two modules now re-export these names
and keep only their dashboard-specific formatters.  The same change replaced
the private ``_as_float`` copies in ``widgets/fwa/`` and, where a golden test
proved the rendering identical, the private ``_fmt_eth`` copies across the
fwa, surf and screens packages; a copy whose semantics ``fmt_eth`` cannot
express (frenpet's wei input, ttt's ungrouped ``Ξ`` form, a copy that renders
``True`` as ``1.00``) stayed where it was with a comment naming the probe
that differs.

Primitives only: no ``data/``, no ``analytics/``, no Textual.  ``time`` is
used only by :func:`hhmm` / :func:`mmdd` for local-time rendering of a
caller-supplied timestamp, never to read the clock -- every countdown and age
on every dashboard is poll-anchored and arrives in the payload already
computed against the manager's injected clock.  Nothing here raises: a widget
that raises inside Textual's message pump takes the app down.

Two rules the dashboards make load-bearing
------------------------------------------

**A missing value is a dash, never a zero.**  Every formatter here returns
:data:`DASH` for ``None`` and a real number for ``0`` -- ``WhitelistCurator``
has three legitimate zeros, a safe hour among them, and rendering "we could
not read it" as ``0`` hides the healthiest state the game has.

**Escaping is the caller's job.**  Everything here returns plain text, never
markup-safe text; the calling widget passes the result through
``widgets.markup_safety.safe_markup`` before it reaches ``Text.from_markup``
or a ``DataTable`` cell.  Escaping in both places would double-escape and
print a literal ``\\[`` to the user, so this module deliberately does not
import ``safe_markup`` at all.
"""

from __future__ import annotations

import time

__all__ = [
    "DASH",
    "EMDASH",
    "as_float",
    "fmt_age",
    "fmt_countdown",
    "fmt_eth",
    "fmt_pct",
    "fmt_points",
    "hhmm",
    "mmdd",
]

#: Unknown scalar.  Two columns, so a dashed cell never re-flows a table.
DASH = "--"

#: "Nothing here, and that is the expected state" -- the FORCED ETH row's
#: healthy rendering on THE LIST (H5).  Deliberately distinct from
#: :data:`DASH`, which means "we could not read it".
EMDASH = "—"


def as_float(value):
    """Coerce to ``float`` or return ``None`` -- never raise, never 0-coerce.

    ``bool`` is rejected on purpose: ``True`` is not ``1.0`` ETH, and
    ``isSettled()`` reaching an amount field is a bug worth rendering as
    unknown rather than as a quantity.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out or out in (float("inf"), float("-inf")):  # NaN / ±inf
        return None
    return out


def fmt_eth(value, places: int = 2, unit: str = "") -> str:
    """``3.60`` / ``8,401.00`` -- a plain ETH quantity; ``unit`` optional.

    ``0`` renders ``0.00``: on THE LIST a zero is frequently the real answer
    (an hour that needs nothing is a *safe* hour), and rendering it as
    unknown would hide the healthiest state the game has.  ``unit`` is
    appended after one space when non-empty (``fmt_eth(1.5, unit="ETH")`` is
    ``1.50 ETH``); the unknown marker never carries a unit.
    """
    v = as_float(value)
    if v is None:
        return DASH
    text = f"{v:,.{places}f}"
    return f"{text} {unit}" if unit else text


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


def fmt_countdown(seconds) -> str:
    """``H:MM:SS`` at or above an hour, ``MM:SS`` below it.

    Two contract edges shape this (THE LIST, H12): ``timeLeftInHour()``
    returns ``hourDuration`` -- 3600, not 0 -- at an exact hour boundary, and
    ``grace_seconds_left`` is clamped at 0 by the analytics layer once grace
    is over.  So ``3600`` renders ``1:00:00`` and ``0`` renders ``00:00``,
    and both are real states.

    A **negative** input is nonsense rather than an edge (nothing upstream
    may produce one), so it renders :data:`DASH`.  It is never rendered as a
    negative clock: ``-00:05`` reads as a deadline five seconds gone, which
    is a claim this widget has no evidence for.
    """
    s = as_float(seconds)
    if s is None or s < 0:
        return DASH
    total = int(s)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def fmt_points(value) -> str:
    """``31,622`` -- a curve score.  ``0`` is a real score; ``None`` is not.

    Zero points is reachable on chain: any weight under 1e18 floors to zero
    through ``(isqrt(weight) * 1000) // 1e9``, so a real contributor can sit
    at 0.  It renders as the number.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{int(v):,}"


def fmt_pct(value) -> str:
    """``12.4%``; ``--`` when the share could not be computed.

    Never ``0.0%`` for an unknown: the flagged-points share is ``None``
    whenever total points are unknown (a division we refuse to do), and
    ``0.0%`` would assert that the flagged wallets scored nothing.
    """
    v = as_float(value)
    if v is None:
        return DASH
    return f"{v:.1f}%"


def hhmm(timestamp, unknown: str = "??:??") -> str:
    """``HH:MM`` local time from unix seconds; ``unknown`` when unusable.

    Local, like every other MaxPane feed stamp.  The one absolute instant on
    THE LIST -- the end of grace -- arrives from the manager already
    formatted as a UTC string, so the two never mix in one cell.

    ``None`` **and** ``0`` both render ``unknown``: the log-timestamp read
    can fail, and an epoch-zero stamp would print ``00:00`` on 1970-01-01,
    which looks like data (H14).  ``float("inf")`` renders it too: ``int()``
    raises ``OverflowError`` on it, and the curator copy of this function
    let that escape into the message pump until 2026-09-20.
    """
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return unknown
        t = time.localtime(ts)
        return f"{t.tm_hour:02d}:{t.tm_min:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return unknown


def mmdd(timestamp, unknown: str = "??-??") -> str:
    """``MM-DD`` local time from unix seconds; ``unknown`` when unusable."""
    try:
        ts = int(timestamp or 0)
        if ts <= 0:
            return unknown
        t = time.localtime(ts)
        return f"{t.tm_mon:02d}-{t.tm_mday:02d}"
    except (TypeError, ValueError, OSError, OverflowError):
        return unknown

"""Validation for persisted ``[timestamp, value]`` time-series points.

Every cache module in this package persists its sparkline histories as
JSON arrays of two-element ``[timestamp, value]`` pairs and reloads them
in ``load_from_file``.  Those loaders used to do a bare ``float(pt[1])``
on whatever the file happened to contain, so a single ``null`` -- or a
string, or a ``NaN`` -- raised ``TypeError`` straight out of the loader::

    TypeError: float() argument must be a string or a real number, not 'NoneType'

That broke the loaders' own documented contract ("silently does nothing
if the file is missing or corrupted") and, because every manager loads
its cache in ``__init__``, one bad value in one file aborted MaxPane
startup for *every* dashboard -- not just the one owning the file.  The
user saw a traceback instead of an app and had no way to recover without
knowing to delete a file under ``~/.maxpane/``.

The fix lives here rather than in each cache module because eight
near-identical copies of the guard are exactly how this drifted apart in
the first place.  A corrupt point is dropped, never fatal, and the
caller logs the drop count so a silently truncated history stays
discoverable.

``ocm_cache`` still carries a private copy (``_coerce_point``) with the
same semantics, as do ``ttt_cache`` and ``talismans_cache``; they should
be folded into this module once their in-flight edits land.
"""

from __future__ import annotations

import math
import time
from typing import Any

# Type alias for a single time-series data point: (epoch_seconds, value).
TimeSeriesPoint = tuple[float, float]

# Tolerance for clock skew when rejecting future-dated points.  A machine
# whose clock is a couple of minutes fast must not throw away the samples
# it just wrote itself.
CLOCK_SKEW_TOLERANCE_SECONDS = 300.0


def coerce_point(
    pt: Any,
    *,
    now: float,
    max_age: float | None = None,
    allow_negative: bool = False,
) -> TimeSeriesPoint | None:
    """Validate one persisted ``[timestamp, value]`` pair.

    Returns ``None`` -- meaning "drop this point" -- for anything that is
    not a usable sample: a wrong-length or non-sequence entry, a value
    that is not a real number (``null``, a string, a bool), ``NaN`` or
    infinity, a non-positive timestamp, a negative value, a future-dated
    timestamp, or (when ``max_age`` is given) a point older than the
    series' window.

    Parameters
    ----------
    now:
        Reference wall-clock time, in epoch seconds.
    max_age:
        Series window in seconds.  ``None`` -- the default -- disables
        the age check, which is correct for series whose only bound is
        their deque's ``maxlen`` rather than a time window.
    allow_negative:
        Set for series that can legitimately go below zero (deltas,
        P&L).  Counts, prices and pool balances cannot, and a negative
        one is corruption.
    """
    if not isinstance(pt, (list, tuple)) or len(pt) != 2:
        return None
    # bools are ints in Python; ``[ts, True]`` is corruption, not a 1.0.
    if isinstance(pt[0], bool) or isinstance(pt[1], bool):
        return None
    try:
        ts = float(pt[0])
        val = float(pt[1])
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(ts) and math.isfinite(val)):
        return None
    if ts <= 0:
        return None
    if val < 0 and not allow_negative:
        return None
    if ts > now + CLOCK_SKEW_TOLERANCE_SECONDS:
        return None
    if max_age is not None and ts < now - max_age:
        return None
    return (ts, val)


def coerce_points(
    raw: Any,
    *,
    now: float | None = None,
    max_age: float | None = None,
    allow_negative: bool = False,
) -> tuple[list[TimeSeriesPoint], int]:
    """Validate a persisted series, returning ``(good_points, dropped)``.

    Never raises.  Anything that is not a sequence yields ``([], 0)`` so
    a hand-mangled file degrades to an empty series instead of a crash.
    """
    if not isinstance(raw, (list, tuple)):
        return [], 0

    reference = time.time() if now is None else now
    good: list[TimeSeriesPoint] = []
    dropped = 0
    for pt in raw:
        coerced = coerce_point(
            pt,
            now=reference,
            max_age=max_age,
            allow_negative=allow_negative,
        )
        if coerced is None:
            dropped += 1
            continue
        good.append(coerced)
    return good, dropped


__all__ = [
    "CLOCK_SKEW_TOLERANCE_SECONDS",
    "TimeSeriesPoint",
    "coerce_point",
    "coerce_points",
]

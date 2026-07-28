"""Canonical sparkline helpers -- **import these, do not copy them** (MEDI-36).

Every dashboard draws the same block sparkline, and for eight dashboards the
way that happened was copy-and-adapt: ``tal_sparkline.py`` was copied from
``ttt_sparkline.py``, ``fwa_sparkline.py`` was copied from
``tal_sparkline.py``.  The result was three byte-identical copies of
``_coerce_points`` (md5 ``4c8351f5...``) alongside three *older* copies in
``ocm``/``cattown``/``dota`` that never received the hardening at all, so a
``None`` entry in a cached history still raised ``TypeError`` there.  A fix
applied to one copy reached none of the others, and
``templates/sparkline_template.py`` -- the file every ninth dashboard is
seeded from -- had the unhardened version, which is how the defect propagates
into dashboards that do not exist yet.

This module is the single definition.  ``templates/sparkline_template.py``
imports from here rather than restating the helpers, so a new dashboard
copied from the template inherits the import, not a fork.

Converged so far: ``ocm``, ``cattown``, ``dota``, ``ttt``, ``talismans``,
``fwa`` and ``templates/sparkline_template.py`` -- the set named in the
finding, pinned by ``tests/widgets/test_sparkline_common.py``.  Eleven
older copies with divergent widths and semantics are **not** yet on this
module and still need review: ``widgets/cookie_chart.py``,
``widgets/base/{overview.py, price_sparklines.py, volume_sparklines.py,
token_chart.py, overview/bt_sparklines.py, overview/_legacy_overview.py}``
and ``widgets/frenpet/{score_trend.py, pet_card.py, wallet/fpw_trends.py,
perf/fpp_trends.py, perf/fpp_velocity.py, overview/fp_score_trends.py}``.
New dashboards must import from here regardless.

Contract
--------
``coerce_points`` is the boundary: it accepts anything a JSON cache, an HTTP
payload, or a serializer that degraded tuples to lists can produce, and
returns only well-formed ``(float, float)`` pairs.  Everything downstream may
therefore assume clean floats.  None of these helpers raise -- a widget that
raises inside Textual's message pump takes the app down (HIGH-7), so
malformed input degrades to an empty series or ``"--"`` instead.
"""

from __future__ import annotations

__all__ = [
    "SPARK_CHARS",
    "SPARK_WIDTH",
    "coerce_points",
    "build_sparkline",
    "build_sparkline_from_points",
    "trend_arrow",
    "fmt_compact",
]

SPARK_CHARS = "▁▂▃▄▅▆▇█"
SPARK_WIDTH = 22


def coerce_points(points) -> list[tuple[float, float]]:
    """Normalize input to a list of ``(ts, value)`` floats.

    Tolerates ``None`` entries, malformed shapes, and ``None`` values
    by skipping them.  Returns ``[]`` for any non-iterable input.
    """
    if not points:
        return []
    result: list[tuple[float, float]] = []
    try:
        iterator = list(points)
    except TypeError:
        return []
    for pt in iterator:
        if pt is None:
            continue
        try:
            ts, val = pt[0], pt[1]
        except (IndexError, TypeError, KeyError):
            continue
        if val is None:
            continue
        try:
            result.append((float(ts), float(val)))
        except (TypeError, ValueError):
            continue
    return result


def build_sparkline(
    values: list[float],
    width: int = SPARK_WIDTH,
    pad: bool = True,
) -> str:
    """Render a list of floats as a ``width``-wide block sparkline.

    ``pad=True`` is the house behaviour (left-pad with the lowest block).
    ``pad=False`` left-pads with spaces instead, for series that are
    genuinely shorter than the window: an hour with no sample must not be
    drawn as a low value.
    """
    if not values:
        return SPARK_CHARS[0] * width if pad else " " * width
    sample = values[-width:] if len(values) > width else values

    lo = min(sample)
    hi = max(sample)
    span = hi - lo

    chars: list[str] = []
    for v in sample:
        if span == 0:
            idx = 0
        else:
            idx = int((v - lo) / span * (len(SPARK_CHARS) - 1))
            idx = max(0, min(len(SPARK_CHARS) - 1, idx))
        chars.append(SPARK_CHARS[idx])

    # Short series stay right-aligned (newest sample at the right edge).
    filler = SPARK_CHARS[0] if pad else " "
    while len(chars) < width:
        chars.insert(0, filler)
    return "".join(chars)


def build_sparkline_from_points(
    points,
    width: int = SPARK_WIDTH,
    min_points: int = 2,
) -> str:
    """``build_sparkline`` for callers that hold ``(ts, value)`` pairs.

    The input is coerced first, so ``None`` entries and malformed pairs are
    dropped rather than raising.  Series shorter than *min_points* render as
    a flat baseline, matching the pre-existing ocm/cattown/dota behaviour.
    """
    pts = coerce_points(points)
    if len(pts) < min_points:
        return SPARK_CHARS[0] * width
    return build_sparkline([v for _, v in pts], width)


def trend_arrow(points) -> str:
    """Return a coloured trend arrow based on the last two coerced points."""
    pts = coerce_points(points)
    if len(pts) >= 2 and pts[-1][1] > pts[-2][1]:
        return "[green]▲[/]"
    if len(pts) >= 2 and pts[-1][1] < pts[-2][1]:
        return "[red]▼[/]"
    return "[dim]●[/]"


def fmt_compact(value, unit: str = "") -> str:
    """Format a numeric value with a K/M/B suffix.

    Non-numeric, ``None``, ``NaN`` and infinite values render ``"--"`` rather
    than raising or printing ``nan``.
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return "--"
    if v != v or v in (float("inf"), float("-inf")):
        return "--"
    magnitude = abs(v)
    if magnitude >= 1_000_000_000:
        return f"{v / 1_000_000_000:.1f}B{unit}"
    if magnitude >= 1_000_000:
        return f"{v / 1_000_000:.1f}M{unit}"
    if magnitude >= 1_000:
        return f"{v / 1_000:.1f}K{unit}"
    if magnitude >= 1:
        return f"{v:.1f}{unit}"
    return f"{v:.0f}{unit}"

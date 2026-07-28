"""Shared velocity formatting for the FrenPet Performance view.

Score velocities on this screen originate from
``analytics.frenpet_signals.calculate_velocity``, which regresses over
*days* and therefore returns points per day.  Every velocity rendered on
the Performance screen goes through :func:`format_velocity` so the unit
label can never drift away from the value again (it used to read
``/hr``, a 24x overstatement, while the Wallet and Pet views showed
``/day`` for the very same number).
"""

from __future__ import annotations

#: Unit suffix shared by every velocity readout on the Performance screen.
VELOCITY_UNIT = "/day"


def format_velocity(value: float, *, compact: bool = True) -> str:
    """Format a points-per-day velocity as ``+1.2K/day`` / ``-500/day``.

    Parameters
    ----------
    value:
        Velocity in points per day.  Negative values keep their own
        minus sign; only non-negative values get a ``+`` prefix.
    compact:
        When ``True`` (default) values >= 1M/1K collapse to ``M``/``K``
        suffixes.  When ``False`` only the ``K`` step is applied.
    """
    sign = "+" if value >= 0 else ""
    magnitude = abs(value)
    if compact and magnitude >= 1_000_000:
        return f"{sign}{value / 1_000_000:.1f}M{VELOCITY_UNIT}"
    if magnitude >= 1_000:
        return f"{sign}{value / 1_000:.1f}K{VELOCITY_UNIT}"
    return f"{sign}{value:,.0f}{VELOCITY_UNIT}"


__all__ = ["VELOCITY_UNIT", "format_velocity"]

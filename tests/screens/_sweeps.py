"""Boundary sets for layout-pin sweeps.

A pin used to be certified by walking every integer width or height in a
band (``range(60, 160)``): ~930 whole-screen composites at 0.3-1.3 s each,
most of them at widths where nothing is under pressure.  What caught the
shipped defects (``7df2e8c``, ``f51a528``) was never the enumeration -- it
was the geometry invariants asserted at each size: region overflow, hidden
``DataTable`` columns, clipped lines, wrap-shed flags.  Those invariants
are unchanged; only the set of sizes they run at is.

A pin is certified by its *boundary set*: the band's two ends, the pin and
its two neighbours, and every declared tier threshold or per-payload
whole-from width with its two neighbours.  Anything the `#:` block beside
the pin names as a measured onset belongs here too.  See the
terminal-layout skill, "Certifying a pin".
"""

from __future__ import annotations


def boundary_set(pin: int, lo: int, hi: int, *thresholds: int) -> list[int]:
    """Sizes to sweep: ``lo``, ``hi``, and ``pin`` / every threshold ±1.

    ``hi`` is inclusive, unlike the ``range()`` it replaces; the result is
    sorted and clipped to ``[lo, hi]`` so a threshold outside the band
    (a widget floor below the sweep's own minimum) is dropped rather than
    rendered at a size the band never claimed.
    """
    if lo > hi:
        raise ValueError(f"empty band {lo}..{hi}")
    sizes = {lo, hi}
    for t in (pin, *thresholds):
        sizes.update((t - 1, t, t + 1))
    return sorted(s for s in sizes if lo <= s <= hi)

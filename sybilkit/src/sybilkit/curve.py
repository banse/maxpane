"""The points curve.  One function, one implementation, wei-exact.

Frozen in WP0; the body is WP1's.

This lives in its own module rather than inside WP2's ``curator.py`` for a
scheduling reason that is also a correctness reason: ``report.Cluster.points``
is the summed curve points of the cluster's members, so **wave 1** needs the
curve before the curator preset exists.  WP2's ``sybilkit.curator`` re-exports
*this* function.  There is deliberately never a second implementation — the
second one is always the one nobody mutation-tests, and the two drift in the
last digits where nobody looks.

The arithmetic, and why each part of it is load-bearing::

    isqrt(weight_wei) * points_per_eth // 10**9

* ``isqrt``, not ``sqrt``.  The curve is concave and the protocol floors an
  **integer** square root; a float ``sqrt`` of 1.3e21 loses the low digits and
  every score downstream is off by an amount nobody can reconstruct.
* **Multiply before dividing.**  ``isqrt(w) // 10**9 * ppe`` floors twice and
  lands somewhere else.
* ``10**9`` is an ``int``.  ``1e9`` is a float and silently turns the whole
  expression into float arithmetic.
* ``points_per_eth`` is a **parameter**, because it is read live from the chain
  (``POINTS_PER_ETH``).  CLAUDE.md hard constraint 4: never hardcode a
  documented value — it happens to be 1000 on this deployment, and that is a
  measurement, not a constant.
"""

from __future__ import annotations


def curve_points(weight_wei: int, points_per_eth: int) -> int:
    """Curve points for *weight_wei* at a live *points_per_eth* rate.

    Neither argument has a default: a caller that does not know the chain's
    current rate must go and read it, not inherit someone's memory of it.

    WP1 fills this in.
    """
    raise NotImplementedError("WP1")


__all__ = ["curve_points"]

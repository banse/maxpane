"""The ``gas`` family: fee/limit uniformity over a behavioural component.

**The uniformity is the signal, never the value** (research §5.2): 0.035 gwei
is a common honest default; the same default across a whole wave that some
*other* family already grouped is machine tooling.  Gas therefore corroborates
existing components and never groups the population itself — keyed on a value,
(0.1 gwei, 91 600) alone would weld the 0.45 and 10.0 farms into one blob and
every honest wallet on the same default into it.

The axes are ``max_priority_fee_wei`` / ``max_fee_wei`` / ``gas_limit``, and
an axis is **judgeable only when every participant carries a value**: a legacy
type-0 transaction has no fee fields at all, and folding its ``None`` into a
class would invent a shared value nobody sent (controller ruling 3).
``tx_type`` never counts toward uniformity — the population is nearly all
type 2, so a collapsed type says nothing.

Fires when

* **two** of the three axes collapse to one value (strength 0.85), or
* the gas limit collapses and a fully-judgeable priority fee spreads over at
  most two values (strength 0.7) — the 14.0 drip's shape: one 150 000 limit
  under two fees, one of them the fingerprint-odd 11 500 001 wei.
"""

from __future__ import annotations

from math import ceil

from ..cluster import Edge
from ..model import Dataset, Deposit, Tx
from ..report import Reason
from . import first_rows, tier_a_components

#: A component only speaks for itself if fingerprints cover ≥ 90% of it (and
#: at least ``min_size`` rows) — a sampled sliver cannot vouch for a crowd.
MIN_COVERAGE = 0.9

STRENGTH_TWO_AXES = 0.85
STRENGTH_LIMIT_AND_QUANTIZED_FEE = 0.7


def gas_edges(ds: Dataset, cfg, *, groups=None) -> list[Edge]:
    """Uniformity classes over *groups* (default: the tier-A components)."""
    if not ds.txs:
        return []  # tier B not run: silent, never synthetic
    firsts = first_rows(ds)
    if groups is None:
        groups = tier_a_components(ds, cfg)

    edges: list[Edge] = []
    for group in groups:
        if len(group) < cfg.min_size:
            continue
        fingerprints = [
            tx
            for member in group
            if (dep := firsts.get(member)) is not None
            and (tx := ds.txs.get(dep.tx_hash)) is not None
        ]
        if len(fingerprints) < max(cfg.min_size, ceil(MIN_COVERAGE * len(group))):
            continue

        pf = _axis(fingerprints, "max_priority_fee_wei")
        mf = _axis(fingerprints, "max_fee_wei")
        gl = _axis(fingerprints, "gas_limit")
        collapsed = sum(1 for axis in (pf, mf, gl) if axis is not None and len(axis) == 1)

        if collapsed >= 2:
            strength = STRENGTH_TWO_AXES
            text = (
                f"one fee fingerprint across ×{len(fingerprints)} "
                f"(controls spread over dozens)"
            )
        elif gl is not None and len(gl) == 1 and pf is not None and len(pf) <= 2:
            strength = STRENGTH_LIMIT_AND_QUANTIZED_FEE
            text = (
                f"one gas limit + ≤2 priority fees across ×{len(fingerprints)}"
            )
        else:
            continue
        reason = Reason("gas", text, strength)
        members = sorted(group)
        for a, b in zip(members, members[1:]):
            edges.append(Edge(a, b, "gas", strength, reason))
    return edges


def _axis(fingerprints: list[Tx], name: str) -> set[int] | None:
    """The axis's distinct values, or ``None`` when unjudgeable (any ``None``
    present — a missing word must not join a uniformity class)."""
    values = [getattr(tx, name) for tx in fingerprints]
    if any(v is None for v in values):
        return None
    return set(values)


__all__ = ["gas_edges"]

"""The optimal-split ``≈ W/k`` weight signature — amount-family corroboration.

Under a square-root curve, an operator with a pot W maximises points by
splitting it into many equal deposits; the residue is *k* byte-identical
amounts whose implied pot ``k · amount`` is machine-scale.  1 995 × 0.45 ETH
is an 897.75 ETH pot at a 44.6× subsidy (the research's worked example);
five friends sending 0.45 each is 2.25 ETH and a Tuesday.

The edges stay in the **amount** family on purpose.  A split is evidence
*about* an amount group — it raises the family's strength — but it must never
be the second family the ≥2-family gate needs, or amount evidence would
convict wearing two hats.

And it counts inside the same wave windows ``amounts.py`` uses (review I4 /
ruling R13a, via :func:`sybilkit.signals.identical_amount_windows`): an
all-time tally would weld every wallet that ever sent a popular value into
one component — the ~1 990-wallet 0.05-minimum crowd being the measured
false-positive class — so *k* and the pot are per wave, never per lifetime,
and the protocol minimum (ruling R13b) yields no split group at all.
"""

from __future__ import annotations

from ..cluster import Edge
from ..model import Dataset
from ..report import Reason
from . import eth_str, identical_amount_windows, single_first_rows

#: The implied pot ``k · amount`` above which an equal split stops being a
#: human coincidence.  50 ETH is far above every measured control ladder and
#: far below every measured farm pot (73.4 ETH is the smallest).
MIN_POT_WEI = 50 * 10**18

STRENGTH_SPLIT = 0.8


def split_edges(ds: Dataset, cfg, *, firsts=None) -> list[Edge]:
    """Equal-split groups: ≥ ``cfg.min_size`` byte-identical single-deposit
    amounts in one wave window whose implied pot clears :data:`MIN_POT_WEI`.

    *firsts* is the :func:`sybilkit.signals.first_rows` map when the caller
    already holds one; ``None`` derives it.
    """
    edges: list[Edge] = []
    windows = identical_amount_windows(
        ds, cfg, singles=single_first_rows(ds, firsts=firsts)
    )
    for amount, window in windows:
        k = len(window)
        if k < cfg.min_size or amount * k < MIN_POT_WEI:
            continue
        pot = amount * k
        reason = Reason(
            "amount",
            f"≈ W/k equal split: {eth_str(pot)}Ξ across ×{k} of {eth_str(amount)}Ξ",
            STRENGTH_SPLIT,
        )
        for (_, _, a), (_, _, b) in zip(window, window[1:]):
            edges.append(Edge(a, b, "amount", STRENGTH_SPLIT, reason))
    return edges


__all__ = ["split_edges"]

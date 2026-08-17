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
"""

from __future__ import annotations

from collections import defaultdict

from ..cluster import Edge
from ..model import Dataset
from ..report import Reason
from . import eth_str, single_first_rows

#: The implied pot ``k · amount`` above which an equal split stops being a
#: human coincidence.  50 ETH is far above every measured control ladder and
#: far below every measured farm pot (73.4 ETH is the smallest).
MIN_POT_WEI = 50 * 10**18

STRENGTH_SPLIT = 0.8


def split_edges(ds: Dataset, cfg) -> list[Edge]:
    """Equal-split groups: ≥ ``cfg.min_size`` byte-identical single-deposit
    amounts whose implied pot clears :data:`MIN_POT_WEI`."""
    singles = single_first_rows(ds)
    by_amount: dict[int, list[str]] = defaultdict(list)
    for addr, dep in singles.items():
        by_amount[dep.amount_wei].append(addr)

    edges: list[Edge] = []
    for amount, addrs in sorted(by_amount.items()):
        k = len(addrs)
        if k < cfg.min_size or amount * k < MIN_POT_WEI:
            continue
        pot = amount * k
        reason = Reason(
            "amount",
            f"≈ W/k equal split: {eth_str(pot)}Ξ across ×{k} of {eth_str(amount)}Ξ",
            STRENGTH_SPLIT,
        )
        addrs.sort()
        for a, b in zip(addrs, addrs[1:]):
            edges.append(Edge(a, b, "amount", STRENGTH_SPLIT, reason))
    return edges


__all__ = ["split_edges"]

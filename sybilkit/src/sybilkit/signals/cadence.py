"""The ``cadence`` family: per-block burst quantization and the metronomic drip.

Two machine rhythms, both measured on this population (research §4/§5.4):

**Burst** — a submission engine drains a queue, so a wave lands *exactly* 20
or 30 byte-identical deposits per block, block after block.  Rule:
≥ ``min_size`` single-deposit wallets sending the **same integer wei** in one
block, and that amount must have **≥ 2 distinct qualifying blocks** — the
repetition is the rhythm.  A single block proves only that a block was busy,
and (review I3 / ruling R12) the same-block *near-chained* configuration is
exactly the amounts-near signal, so cadence deliberately does not fire on it
at all: one block must never hand a crowd two families by itself.  Jitter
runs are covered by ``sequence`` (the join counter) and by ``amounts`` (the
near rule), not by cadence.

**Drip** — a rate-limited engine sends one deposit every N blocks for hours.
Rule: ≥ 8 consecutive same-amount deposits whose gaps stay small (≤ 8 blocks)
*and* regular (range ≤ 4) — smallness alone is churn; the regularity is the
metronome.
"""

from __future__ import annotations

from collections import defaultdict

from ..cluster import Edge
from ..model import Dataset
from ..report import Reason
from . import eth_str, single_first_rows

#: Drip: minimum run length, maximum inter-deposit gap, maximum gap range.
DRIP_MIN_RUN = 8
DRIP_MAX_GAP = 8
DRIP_MAX_GAP_RANGE = 4

STRENGTH_BURST = 0.85
STRENGTH_DRIP = 0.8


def cadence_edges(ds: Dataset, cfg, *, firsts=None) -> list[Edge]:
    """Burst and drip edges over the single-deposit wallets.

    *firsts* is the :func:`sybilkit.signals.first_rows` map when the caller
    already holds one; ``None`` derives it.
    """
    singles = single_first_rows(ds, firsts=firsts)
    edges: list[Edge] = []

    # ---- burst: same integer wei, >= min_size per block, >= 2 blocks ----
    per_amount_block: dict[int, dict[int, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for addr, dep in singles.items():
        per_amount_block[dep.amount_wei][dep.block_number].append(addr)
    for amount, blocks in sorted(per_amount_block.items()):
        qualifying = {
            block: addrs
            for block, addrs in blocks.items()
            if len(addrs) >= cfg.min_size
        }
        if len(qualifying) < 2:
            continue  # a single block is a busy block, not a rhythm
        for block, addrs in sorted(qualifying.items()):
            reason = Reason(
                "cadence",
                f"burst ×{len(addrs)} of {eth_str(amount)}Ξ in one block, "
                f"repeated over {len(qualifying)} blocks",
                STRENGTH_BURST,
            )
            addrs.sort()
            for a, b in zip(addrs, addrs[1:]):
                edges.append(Edge(a, b, "cadence", STRENGTH_BURST, reason))

    # ---- drip: same exact amount, small *regular* gaps ------------------
    by_amount: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for addr, dep in singles.items():
        by_amount[dep.amount_wei].append((dep.block_number, addr))
    for amount, rows in sorted(by_amount.items()):
        if len(rows) < DRIP_MIN_RUN:
            continue
        rows.sort()
        run = [rows[0]]

        def flush_drip(run: list[tuple[int, str]], amount: int = amount) -> None:
            if len(run) < DRIP_MIN_RUN:
                return
            gaps = [b2 - b1 for (b1, _), (b2, _) in zip(run, run[1:])]
            if max(gaps) - min(gaps) > DRIP_MAX_GAP_RANGE:
                return  # small but irregular: churn, not a metronome
            reason = Reason(
                "cadence",
                f"metronomic drip ×{len(run)} of {eth_str(amount)}Ξ every "
                f"~{sorted(gaps)[len(gaps) // 2]} blocks",
                STRENGTH_DRIP,
            )
            for (_, a), (_, b) in zip(run, run[1:]):
                edges.append(Edge(a, b, "cadence", STRENGTH_DRIP, reason))

        for row in rows[1:]:
            gap = row[0] - run[-1][0]
            if 1 <= gap <= DRIP_MAX_GAP:
                run.append(row)
            else:
                flush_drip(run)
                run = [row]
        flush_drip(run)

    return edges


__all__ = ["cadence_edges"]

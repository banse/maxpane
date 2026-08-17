"""The ``cadence`` family: per-block burst quantization and the metronomic drip.

Two machine rhythms, both measured on this population (research §4/§5.4):

**Burst** — a submission engine drains a queue, so a wave lands *exactly* 20
or 30 near-identical deposits per block.  Rule: ≥ ``min_size`` single-deposit
wallets in **one block** whose amounts chain within ±tol.

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
from . import eth_str, near, single_first_rows, tol_bps_of

#: Drip: minimum run length, maximum inter-deposit gap, maximum gap range.
DRIP_MIN_RUN = 8
DRIP_MAX_GAP = 8
DRIP_MAX_GAP_RANGE = 4

STRENGTH_BURST = 0.85
STRENGTH_DRIP = 0.8


def cadence_edges(ds: Dataset, cfg) -> list[Edge]:
    singles = single_first_rows(ds)
    tol_bps = tol_bps_of(cfg.near_amount_tol)
    edges: list[Edge] = []

    # ---- burst: >= min_size near-identical amounts in one block ---------
    by_block: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for addr, dep in singles.items():
        by_block[dep.block_number].append((dep.amount_wei, addr))
    for block, rows in sorted(by_block.items()):
        if len(rows) < cfg.min_size:
            continue
        rows.sort()
        group = [rows[0]]

        def flush_burst(group: list[tuple[int, str]]) -> None:
            if len(group) < cfg.min_size:
                return
            reason = Reason(
                "cadence",
                f"burst ×{len(group)} in one block "
                f"(~{eth_str(group[0][0])}Ξ each)",
                STRENGTH_BURST,
            )
            for (_, a), (_, b) in zip(group, group[1:]):
                edges.append(Edge(a, b, "cadence", STRENGTH_BURST, reason))

        for row in rows[1:]:
            if near(group[-1][0], row[0], tol_bps):
                group.append(row)
            else:
                flush_burst(group)
                group = [row]
        flush_burst(group)

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

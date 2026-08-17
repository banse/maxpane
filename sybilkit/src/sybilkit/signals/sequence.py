"""The ``sequence`` family: consecutive ``FirstDeposit``-index runs.

The protocol's own join counter is the fingerprint: a farm registering its
wallets back-to-back receives consecutive 1-based indices, lands them within
a couple of blocks, and (near-)identical amounts ride along — "180 consecutive
indices in 7 blocks" (research §5.3).  Organic joiners interleave, so their
indices are consecutive only with hours of block-space or unrelated amounts
between them; both break the run.
"""

from __future__ import annotations

from ..cluster import Edge
from ..model import Dataset
from ..report import Reason
from . import first_rows, near, tol_bps_of

#: Two consecutive indices more than this many blocks apart are not one
#: registration burst.  The measured runs sit at 0–2.
MAX_BLOCK_GAP = 2

STRENGTH_SEQUENCE = 0.9


def sequence_edges(ds: Dataset, cfg) -> list[Edge]:
    """Maximal consecutive-index runs (≥ ``cfg.min_size``) with ≤ 2-block
    spacing and near-identical amounts, as spanning chains."""
    firsts = first_rows(ds)
    tol_bps = tol_bps_of(cfg.near_amount_tol)
    by_index = sorted(
        (index, addr) for addr, index in ds.first_index.items() if addr in firsts
    )

    edges: list[Edge] = []
    run: list[tuple[int, str]] = []

    def flush(run: list[tuple[int, str]]) -> None:
        if len(run) < cfg.min_size:
            return
        first_i, last_i = run[0][0], run[-1][0]
        blocks = [firsts[a].block_number for _, a in run]
        span = max(blocks) - min(blocks)
        reason = Reason(
            "sequence",
            f"consecutive join indices {first_i:,}–{last_i:,} · "
            f"{span}-block span",
            STRENGTH_SEQUENCE,
        )
        for (_, a), (_, b) in zip(run, run[1:]):
            edges.append(Edge(a, b, "sequence", STRENGTH_SEQUENCE, reason))

    for index, addr in by_index:
        if run:
            prev_index, prev_addr = run[-1]
            prev_dep, dep = firsts[prev_addr], firsts[addr]
            if (
                index == prev_index + 1
                and abs(dep.block_number - prev_dep.block_number) <= MAX_BLOCK_GAP
                and near(dep.amount_wei, prev_dep.amount_wei, tol_bps)
            ):
                run.append((index, addr))
                continue
            flush(run)
        run = [(index, addr)]
    flush(run)
    return edges


__all__ = ["sequence_edges"]

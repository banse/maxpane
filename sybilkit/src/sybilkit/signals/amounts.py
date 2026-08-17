"""The ``amount`` family: byte-identical and near-identical (±tol) groups.

Three rules, each a measured decision:

* **Single-deposit wallets only.**  The controls that touch farm amounts are
  multi-deposit ladder humans (0.05, 0.15, ..., 0.45, ...); a farm wallet
  deposits once.
* **Round amounts group only inside a wave window.**  A round value (whole
  multiple of 0.01 ETH) is a value humans also pick, so byte-equality reaches
  only across a *contiguous-hour* window — the shape of an operator's wave —
  and a straggler six hours later is somebody else.  An **odd** amount
  (2.067, 171.99-style, jitters) is a machine fingerprint and reaches across
  the whole population: the identical odd amount is what links the 2.067
  operator's two window-separated waves (research §3).
* **Near-identical groups only inside one block.**  The randomized batches a
  byte-identical rule misses (research §3) are submitted as bursts; a ±tol
  rule allowed to reach across blocks chains unrelated wallets through the
  population's dense round values.  The measured adversarial controls sit
  1–17 blocks *after* a burst with in-band amounts — same-block is the line
  the audit drew.
"""

from __future__ import annotations

from collections import defaultdict

from ..cluster import Edge
from ..model import Dataset
from ..report import Reason
from . import eth_str, near, single_first_rows, tol_bps_of

#: A "round" amount is a whole multiple of 0.01 ETH — a value a human picks.
ROUND_WEI = 10**16

#: Round-amount groups split where the gap between neighbouring deposit hours
#: exceeds this — one wave, one window.
MAX_HOUR_GAP = 1

STRENGTH_EXACT_ODD = 0.9
STRENGTH_EXACT_ROUND = 0.75
STRENGTH_NEAR = 0.7


def amount_edges(ds: Dataset, cfg) -> list[Edge]:
    """Byte-identical and ±tol amount groups among single-deposit wallets."""
    singles = single_first_rows(ds)
    edges: list[Edge] = []

    # ---- byte-identical groups, on the integer wei ----------------------
    by_amount: dict[int, list[tuple[int, int, str]]] = defaultdict(list)
    for addr, dep in singles.items():
        by_amount[dep.amount_wei].append((dep.hour, dep.block_number, addr))

    for amount, rows in sorted(by_amount.items()):
        if len(rows) < 2:
            continue
        rows.sort()
        if amount % ROUND_WEI:
            # odd: a machine fingerprint, reaches across every window
            reason = Reason(
                "amount",
                f"identical odd {eth_str(amount)}Ξ send ×{len(rows)}",
                STRENGTH_EXACT_ODD,
            )
            for (_, _, a), (_, _, b) in zip(rows, rows[1:]):
                edges.append(Edge(a, b, "amount", STRENGTH_EXACT_ODD, reason))
        else:
            # round: group only inside a contiguous-hour wave window
            window = [rows[0]]
            for row in rows[1:]:
                if row[0] - window[-1][0] > MAX_HOUR_GAP:
                    _emit_round_window(edges, amount, window)
                    window = [row]
                else:
                    window.append(row)
            _emit_round_window(edges, amount, window)

    # ---- near-identical (±tol), same block only -------------------------
    tol_bps = tol_bps_of(cfg.near_amount_tol)
    by_block: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for addr, dep in singles.items():
        by_block[dep.block_number].append((dep.amount_wei, addr))
    for block, rows in sorted(by_block.items()):
        if len(rows) < 2:
            continue
        rows.sort()
        for (a_amt, a), (b_amt, b) in zip(rows, rows[1:]):
            if a_amt != b_amt and near(a_amt, b_amt, tol_bps):
                reason = Reason(
                    "amount",
                    f"near-identical {eth_str(a_amt)}Ξ–{eth_str(b_amt)}Ξ in one block",
                    STRENGTH_NEAR,
                )
                edges.append(Edge(a, b, "amount", STRENGTH_NEAR, reason))
    return edges


def _emit_round_window(
    edges: list[Edge], amount: int, window: list[tuple[int, int, str]]
) -> None:
    if len(window) < 2:
        return
    reason = Reason(
        "amount",
        f"identical {eth_str(amount)}Ξ send ×{len(window)} in one wave",
        STRENGTH_EXACT_ROUND,
    )
    for (_, _, a), (_, _, b) in zip(window, window[1:]):
        edges.append(Edge(a, b, "amount", STRENGTH_EXACT_ROUND, reason))


__all__ = ["amount_edges"]

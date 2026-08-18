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
from . import (
    ROUND_WEI,
    eth_str,
    identical_amount_windows,
    near,
    single_first_rows,
    tol_bps_of,
)

STRENGTH_EXACT_ODD = 0.9
STRENGTH_EXACT_ROUND = 0.75
STRENGTH_NEAR = 0.7


def amount_edges(ds: Dataset, cfg) -> list[Edge]:
    """Byte-identical and ±tol amount groups among single-deposit wallets.

    The byte-identical groups come from
    :func:`sybilkit.signals.identical_amount_windows` — the one windowing
    discipline this family and ``split`` share — so the protocol-minimum
    exemption (``cfg.protocol_min_amount_wei``, ruling R13) applies here for
    free: identicalness at the minimum is not evidence.

    The **near** pass applies the same exemption explicitly, because it does
    not go through that helper.  It sorts each block's rows by
    ``(amount, address)`` and compares adjacent pairs, so a run of byte-equal
    minimum rows beside a near neighbour would hand exactly one of the crowd
    an edge and let lowercase address order decide which — an arbitrary
    conviction on the one value that identifies nobody.  Exempt rows are
    therefore dropped from the near pass entirely (review #13, ruling D5-A),
    which costs a genuine near-neighbour of the minimum its edge and buys
    order-independence for the ~2 000 wallets sitting on that value.

    **Ruling D5-A scoped that to the protocol minimum, and only to it**, so a
    run of byte-equal *non-exempt* rows still picks its near partner
    lexically: equal amounts are skipped, so the run's **lowest**-addressed
    member is the one that can reach the near neighbour below it and its
    **highest**-addressed member the one that can reach the neighbour above.
    Which wallet that is is decided by lowercase address order, which is not a
    fact about anybody.

    It is nonetheless harmless, and structurally rather than luckily so.  A
    byte-equal run of two or more non-exempt single-deposit rows *in one block*
    is already one component before the near pass runs —
    :func:`sybilkit.signals.identical_amount_windows` welds it, globally for an
    odd amount and inside the block's own hour window for a round one (one
    block is one timestamp, so its rows share an hour) — so the near edge
    merges the **same two components** whichever member of the run carries it.
    Membership is therefore order-independent, and membership is what every
    count, share and reason a caller ever sees is computed from; all that moves
    is which two addresses sit on an ``Edge`` object inside this function's
    return list.  The rendered ``Reason`` names amounts, never addresses, and
    at :data:`STRENGTH_NEAR` it is dominated by the welding rule's own
    :data:`STRENGTH_EXACT_ODD` / :data:`STRENGTH_EXACT_ROUND` in any case.
    ``test_which_member_of_a_byte_equal_run_carries_the_near_edge_changes_nothing``
    pins that equality — and reddens if the welding rule ever stops holding it
    up, which is the assumption doing the work here.
    """
    singles = single_first_rows(ds)
    edges: list[Edge] = []

    # ---- byte-identical groups, on the integer wei ----------------------
    for amount, window in identical_amount_windows(ds, cfg):
        if amount % ROUND_WEI:
            reason = Reason(
                "amount",
                f"identical odd {eth_str(amount)}Ξ send ×{len(window)}",
                STRENGTH_EXACT_ODD,
            )
            strength = STRENGTH_EXACT_ODD
        else:
            reason = Reason(
                "amount",
                f"identical {eth_str(amount)}Ξ send ×{len(window)} in one wave",
                STRENGTH_EXACT_ROUND,
            )
            strength = STRENGTH_EXACT_ROUND
        for (_, _, a), (_, _, b) in zip(window, window[1:]):
            edges.append(Edge(a, b, "amount", strength, reason))

    # ---- near-identical (±tol), same block only -------------------------
    tol_bps = tol_bps_of(cfg.near_amount_tol)
    exempt = cfg.protocol_min_amount_wei
    by_block: dict[int, list[tuple[int, str]]] = defaultdict(list)
    for addr, dep in singles.items():
        if exempt is not None and dep.amount_wei == exempt:
            # R13b, and the near pass obeys it too: a run of byte-equal
            # minimum rows sits between two near neighbours, so leaving it in
            # hands exactly one of the crowd an edge and lets lowercase
            # address order pick which.  Nobody at the minimum is identified
            # by being at the minimum, from either rule.
            continue
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


__all__ = ["amount_edges"]

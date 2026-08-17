"""The combiner: edges in, clusters out.  Config and entry point frozen here.

Frozen in WP0; :func:`detect`'s body is WP1's.

How it works, so that WP1 fills in the shape WP2 and WP3 are coding against:
each signal module in ``sybilkit.signals`` is a pure
``(Dataset, DetectConfig) -> list[Edge]``.  This module unions those edges
(union-find) and keeps only the components that clear **both** gates:

* ``>= min_families`` **distinct** edge families, and
* ``>= min_size`` members.

That compound condition is the design, not an optimisation.  No single
per-wallet signal separated farms from power users in any measured study
(ChainCred: 42% of sybils against 32% of ordinary wallets share a
distributor-range funder — statistically identical, precision stuck at the base
rate).  Score clusters, not wallets, and never on one family.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Dataset
from .report import DetectResult

#: The five independent signal families, and the **authority** for the name of
#: each.  ``cluster.py`` owns this tuple because ``cluster.py`` is what counts
#: distinct families for the gate; a sixth spelling anywhere else is a family
#: that never counts and a gate that has quietly loosened.
#:
#: * ``amount``   — identical and near-identical (±tol) send amounts
#: * ``sequence`` — consecutive ``FirstDeposit``-index runs, ladder shape
#: * ``cadence``  — per-block burst quantization, metronomic drip
#: * ``gas``      — priority-fee / max-fee / gas-limit / tx-type uniformity
#: * ``funding``  — first-funder graph; peel chains; funder ∈ cluster
FAMILIES: tuple[str, ...] = ("amount", "sequence", "cadence", "gas", "funding")


@dataclass(frozen=True, slots=True)
class DetectConfig:
    """The four knobs, with the measured defaults.

    ``min_size = 5``
        Hop used ≥10 and LayerZero ≥20.  Five is the floor that still keeps
        one-human-a-few-wallets out of the result.

    ``min_families = 2``
        One family alone never convicts (PRD §3.1).  This is the single most
        load-bearing default in the library: dropping it to 1 turns every
        honest wallet that happened to send a round number into a cluster
        member.

    ``near_amount_tol = 0.10``
        ±10% catches the jitter-amount batches a byte-identical rule cannot —
        measured on this population, 499 runs / 7 369 wallets at ±10% against
        281 runs / 3 779 wallets byte-identical.

    ``confidence_threshold = 0.5``
        The ``DetectResult.flagged`` cut.  Confidence stays graduated either
        side of it; the threshold decides only what the word "flagged" covers.
    """

    min_size: int = 5
    min_families: int = 2
    near_amount_tol: float = 0.10
    confidence_threshold: float = 0.5


def detect(ds: Dataset, config: DetectConfig = DetectConfig()) -> DetectResult:
    """Run every signal over *ds* and combine the edges into clusters.

    Pure: no I/O, no clock, no network.  Two runs over one :class:`Dataset`
    return equal results, which is what makes the benchmark gate meaningful.

    The default *config* is a frozen dataclass instance, so sharing one across
    calls is safe.

    WP1 fills this in.
    """
    raise NotImplementedError("WP1")


__all__ = ["FAMILIES", "DetectConfig", "detect"]

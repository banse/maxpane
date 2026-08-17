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

from .curve import curve_points
from .model import Dataset
from .report import Cluster, DetectResult, Reason

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
class Edge:
    """One pairwise link between two lowercase addresses.

    The combiner unions edges, so a signal describing a *group* emits a
    **spanning chain** over the group's sorted members rather than a clique —
    identical connectivity, linear cost, and the whole population stays
    analyzable in one pass.  ``family`` is one of :data:`FAMILIES` (what the
    ≥2-family gate counts); ``strength`` is the graduated weight the cluster's
    multiplicative confidence is built from; ``reason`` is the pattern-language
    sentence that reaches the screen.
    """

    a: str
    b: str
    family: str
    strength: float
    reason: Reason


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


#: The rate the committed population fixture was swept at.  ``detect`` uses
#: ``getattr(ds, "points_per_eth", DEFAULT_POINTS_PER_ETH)`` — a producer that
#: has read the live rate carries it on a ``Dataset`` subclass and this
#: default never applies; an offline run over committed data gets the rate
#: that data was measured under.  Every *share* is rate-invariant either way.
DEFAULT_POINTS_PER_ETH = 1000

#: Freshness discounts, never convicts: a cluster of aged wallets keeps its
#: families and loses a slice of confidence.  All-fresh → factor 1.0
#: (no discount); all-aged → :data:`FRESHNESS_FLOOR`.
FRESHNESS_FLOOR = 0.85


class _UnionFind:
    """Path-halving union-find over lowercase addresses."""

    __slots__ = ("_parent",)

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        parent = self._parent
        parent.setdefault(x, x)
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[rb] = ra


def detect(ds: Dataset, config: DetectConfig = DetectConfig()) -> DetectResult:
    """Run every signal over *ds* and combine the edges into clusters.

    Pure: no I/O, no clock, no network.  Two runs over one :class:`Dataset`
    return equal results, which is what makes the benchmark gate meaningful.

    The default *config* is a frozen dataclass instance, so sharing one across
    calls is safe.

    The shape of the run:

    1. the four tier-A signals draw the behavioural components (union-find);
    2. ``gas`` and ``funding`` corroborate *inside* those components — they
       are handed the component list, so they can strengthen a group but
       never merge two or pull a stranger in;
    3. a component survives only with ``>= config.min_families`` **distinct**
       families and ``>= config.min_size`` members — one family never
       convicts, however loudly;
    4. confidence is the product of the per-family best strengths times a
       freshness factor (all-aged wallets discount to
       :data:`FRESHNESS_FLOOR`), clamped to [0, 1] — graduated, never binary.
    """
    # imported here, not at module top: the signal modules import ``Edge``
    # from this module, and a load-time import would be the cycle.
    from .signals import first_rows
    from .signals.amounts import amount_edges
    from .signals.cadence import cadence_edges
    from .signals.funding import funding_edges
    from .signals.gas import gas_edges
    from .signals.sequence import sequence_edges
    from .signals.split import split_edges

    contributors = {dep.contributor for dep in ds.deposits}

    # ---- 1. tier A draws the components ---------------------------------
    uf = _UnionFind()
    for addr in contributors:
        uf.find(addr)
    tier_a: list[Edge] = []
    for edge_fn in (amount_edges, split_edges, sequence_edges, cadence_edges):
        tier_a.extend(edge_fn(ds, config))
    for edge in tier_a:
        uf.union(edge.a, edge.b)
    components: dict[str, set[str]] = {}
    for addr in contributors:
        components.setdefault(uf.find(addr), set()).add(addr)
    groups = [g for g in components.values() if len(g) >= 2]

    # ---- 2. tier B/C corroborate inside them ----------------------------
    all_edges = list(tier_a)
    all_edges.extend(gas_edges(ds, config, groups=groups))
    all_edges.extend(funding_edges(ds, config, groups=groups))

    # ---- 3. the compound gate -------------------------------------------
    # The gate counts *distinct families*, so the family vocabulary is
    # enforced right where the counting happens: an edge whose family is not
    # in FAMILIES is a programming error in a signal (a misspelling would
    # otherwise silently count as a second family and quietly loosen the
    # gate), and a programming error raises — it never convicts.
    known_families = frozenset(FAMILIES)
    best_by_family: dict[str, dict[str, Reason]] = {}
    for edge in all_edges:
        if edge.family not in known_families:
            raise ValueError(
                f"unknown edge family {edge.family!r} (not in FAMILIES); "
                "a misspelt family must never count toward the gate"
            )
        root = uf.find(edge.a)
        families = best_by_family.setdefault(root, {})
        cur = families.get(edge.family)
        if cur is None or edge.reason.strength > cur.strength:
            families[edge.family] = edge.reason

    firsts = first_rows(ds)
    last_weight: dict[str, int] = {}
    for dep in ds.deposits:  # chain order: the last write is the final weight
        last_weight[dep.contributor] = dep.new_weight_wei
    points_per_eth = getattr(ds, "points_per_eth", DEFAULT_POINTS_PER_ETH)
    total_points = sum(
        curve_points(w, points_per_eth) for w in last_weight.values()
    )

    kept: list[tuple[tuple[str, ...], tuple[Reason, ...], float, int, int]] = []
    for root, members in components.items():
        families = best_by_family.get(root, {})
        if len(members) < config.min_size or len(families) < config.min_families:
            continue
        reasons = tuple(
            sorted(families.values(), key=lambda r: (-r.strength, r.family))
        )
        confidence = 1.0
        for reason in reasons:
            confidence *= reason.strength
        nonces = [
            tx.nonce
            for member in members
            if (dep := firsts.get(member)) is not None
            and (tx := ds.txs.get(dep.tx_hash)) is not None
            and tx.nonce is not None
        ]
        if nonces:
            fresh_fraction = sum(1 for n in nonces if n == 0) / len(nonces)
            confidence *= FRESHNESS_FLOOR + (1.0 - FRESHNESS_FLOOR) * fresh_fraction
        confidence = min(1.0, max(0.0, confidence))
        points = sum(curve_points(last_weight[m], points_per_eth) for m in members)
        blocks = [firsts[m].block_number for m in members]
        span = max(blocks) - min(blocks)
        kept.append((tuple(sorted(members)), reasons, confidence, points, span))

    # ---- 4. ids by share, counters, the result --------------------------
    kept.sort(key=lambda item: (-item[3], item[0]))
    clusters = [
        Cluster(
            cluster_id=i,
            members=members,
            reasons=reasons,
            confidence=confidence,
            points=points,
            points_share=(points / total_points) if total_points else 0.0,
            span_blocks=span,
            size=len(members),
        )
        for i, (members, reasons, confidence, points, span) in enumerate(kept)
    ]
    flagged_points = sum(
        c.points for c in clusters if c.confidence >= config.confidence_threshold
    )
    result = DetectResult(
        clusters,
        total_points,
        flagged_points,
        total_points - flagged_points,
        confidence_threshold=config.confidence_threshold,
    )
    result.analyzed = frozenset(contributors)
    return result


__all__ = ["FAMILIES", "DEFAULT_POINTS_PER_ETH", "DetectConfig", "Edge", "detect"]

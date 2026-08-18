"""What the analysis says.  Reasons, a graduated confidence, and four counters.

Frozen in WP0; the bodies are WP1's.

The one rule this module exists to enforce
    **Reasons, never verdicts.**  Nothing here is called a sybil, a cheat or a
    fraud, and nothing is a boolean judgement.  A :class:`Cluster` carries the
    *pattern-language* reasons it was formed from and a ``confidence`` in
    [0, 1] that is multiplicative and graduated.  Freshness discounts a
    confidence; it never convicts.  The reader is shown the shape and draws
    their own conclusion.

The negative that has to be representable
    ``DetectResult.wallet(addr)`` returns ``None`` for a wallet that was **not
    analyzed** and a ``WalletVerdict(in_cluster=False, …)`` for one that was
    analyzed and found clean.  Collapsing those two is exactly the defect
    CLAUDE.md records from curator's own rail: a row whose real negative has no
    representable value renders identically for "we looked and there was
    nothing" and "we could not look", and so reads confident and green through
    an outage.

``report.py`` must not import ``cluster.py``
    The dependency runs the other way — ``cluster.detect`` builds
    :class:`Cluster` objects.  That is why :class:`Reason` does not validate its
    ``family`` against ``cluster.FAMILIES`` at construction; the constraint is
    pinned in ``tests/test_public_api.py`` instead.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The default ``flagged`` cut.  Deliberately a **second literal**, agreeing
#: with ``cluster.DetectConfig.confidence_threshold`` rather than importing it
#: (that import would be a cycle).  ``test_the_flagged_threshold_travels_with_
#: the_result`` is the agreement test between the two.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


@dataclass(frozen=True, slots=True)
class Reason:
    """One pattern-language link, and how strongly it links.

    ``family`` is one of ``cluster.FAMILIES`` — ``amount``, ``sequence``,
    ``cadence``, ``gas``, ``funding``.  The family is what the ≥2-family gate
    counts; two reasons from the same family are one family, however different
    they sound.

    ``human_string`` is what reaches the screen, so it is written in the
    dashboard's own pattern-language ("identical 0.45Ξ send ×1,995", "shared
    funder chain") and never in the language of an accusation.

    ``strength`` is in [0, 1] and is a float, not a bool, so that a cluster's
    confidence can be a graduated product rather than a verdict.
    """

    family: str
    human_string: str
    strength: float


@dataclass(frozen=True, slots=True)
class Cluster:
    """One linked group: who, why, how strongly, and what it is worth.

    ``members`` are **lowercase** addresses.  ``size`` is ``len(members)`` and
    is carried explicitly so a row can render a size without the caller having
    to hold the whole membership tuple in memory — the widest real operator has
    1 995 of them.

    ``points`` is the summed curve points of the members, wei-floored exactly
    like the contract (``curve.curve_points``), and ``points_share`` is that
    over ``DetectResult.total_points``, in [0, 1].  A *share* rather than a
    percentage: the presentation boundary multiplies by 100, once, where every
    other percentage in the dashboard is made.

    ``span_blocks`` is ``int | None``.  ``0`` is a real and very incriminating
    measurement — a whole cluster inside one block — so "we do not know the
    span" needs a value of its own.
    """

    cluster_id: int
    members: tuple[str, ...]
    reasons: tuple[Reason, ...]
    confidence: float
    points: int
    points_share: float
    span_blocks: int | None
    size: int


@dataclass(frozen=True, slots=True)
class WalletVerdict:
    """One wallet's standing, as the `y` view renders it.

    ``in_cluster=False`` with empty ``reasons`` is the **representable
    negative**: analyzed, not linked.  It is not the same object as the
    ``None`` :meth:`DetectResult.wallet` returns for a wallet outside the
    analysed population, and the two must render differently.
    """

    in_cluster: bool
    cluster_id: int | None
    reasons: tuple[Reason, ...]
    confidence: float


class DetectResult:
    """The result of one :func:`sybilkit.cluster.detect` run.

    A small value object rather than a dataclass, because it has behaviour:
    :meth:`wallet` is a lookup and :attr:`flagged` is derived from the
    threshold.  Its state is the cluster list, the three point counters, the
    threshold, the ``analyzed`` population and a private member index; each
    counter is an ``int`` rather than an ``int | None`` — a detector that ran
    always knows how many points it looked at.  A run that could *not* happen
    produces no ``DetectResult`` at all; the caller reports that as its own
    unavailable state.

    ``clusters`` is ordered by ``points_share`` descending — widest operator
    first, which is the row the OPERATORS panel leads with.

    ``analyzed`` is the population the producing ``detect`` run looked at
    (lowercase), and it is what lets :meth:`wallet` return the *representable
    negative* — analyzed, not linked — instead of collapsing it into the
    stranger's ``None``.  ``detect`` sets it after construction; a hand-built
    result defaults to ``frozenset()``, so its non-members read as "not
    analyzed" — the safe default is never a confident clean.

    **Every membership test here is lowercased on both sides.**  :meth:`wallet`
    lowercases its query, so an ``analyzed`` set or a ``Cluster.members`` tuple
    spelled any other way makes the object disagree with itself — and with
    ``curator.clean_list``, which lowercases both on read.  ``analyzed`` is
    therefore normalised in its setter and the member index and :attr:`flagged`
    are built lowercase.  ``detect`` already produces lowercase for all three,
    so this is a no-op on every live path and defence on the hand-built one
    that ruling D1-B made first-class.
    """

    __slots__ = (
        "clusters",
        "total_points",
        "flagged_points",
        "clean_points",
        "confidence_threshold",
        "_analyzed",
        "_by_member",
    )

    def __init__(
        self,
        clusters,
        total_points: int,
        flagged_points: int,
        clean_points: int,
        *,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    ) -> None:
        self.clusters: list[Cluster] = sorted(
            clusters, key=lambda c: c.points_share, reverse=True
        )
        self.total_points = total_points
        self.flagged_points = flagged_points
        self.clean_points = clean_points
        self.confidence_threshold = confidence_threshold
        self.analyzed = frozenset()
        self._by_member: dict[str, Cluster] = {
            member.lower(): cluster
            for cluster in self.clusters
            for member in cluster.members
        }

    @property
    def analyzed(self) -> frozenset[str]:
        """The population the producing run looked at, lowercase."""
        return self._analyzed

    @analyzed.setter
    def analyzed(self, population) -> None:
        # Normalised once, on write, rather than on every lookup: `wallet` is a
        # per-address call and the analysed population is the whole
        # contributor set, so lowercasing on read would make an O(1) membership
        # test O(n).  `detect` assigns a lowercase frozenset, so this changes
        # nothing it produces.
        self._analyzed: frozenset[str] = frozenset(
            addr.lower() for addr in population
        )

    def wallet(self, addr: str) -> WalletVerdict | None:
        """This wallet's verdict, or ``None`` if it was not analyzed.

        Three honest answers, never collapsed:

        * a cluster member — ``in_cluster=True`` with the cluster's reasons
          and its graduated confidence (below-threshold clusters included:
          linked-with-reasons is not the same word as "flagged");
        * analyzed and not linked — ``in_cluster=False``, empty reasons,
          confidence ``0.0`` (the representable negative);
        * never analyzed — ``None``.  A stranger is not a wallet scored clean.
        """
        key = addr.lower()
        cluster = self._by_member.get(key)
        if cluster is not None:
            return WalletVerdict(
                in_cluster=True,
                cluster_id=cluster.cluster_id,
                reasons=cluster.reasons,
                confidence=cluster.confidence,
            )
        if key in self.analyzed:
            return WalletVerdict(
                in_cluster=False, cluster_id=None, reasons=(), confidence=0.0
            )
        return None

    @property
    def flagged(self) -> set[str]:
        """Lowercase members of every cluster at or above the threshold.

        Confidence stays graduated on both sides of the cut; the threshold
        decides only what the word "flagged" covers.

        Lowercased here rather than trusted from the cluster, because every
        consumer writes ``addr not in res.flagged`` against a lowercase address
        and a raw spelling walks a flagged member straight through the filter
        that exists to remove it.
        """
        return {
            member.lower()
            for cluster in self.clusters
            if cluster.confidence >= self.confidence_threshold
            for member in cluster.members
        }


__all__ = [
    "DEFAULT_CONFIDENCE_THRESHOLD",
    "Reason",
    "Cluster",
    "WalletVerdict",
    "DetectResult",
]

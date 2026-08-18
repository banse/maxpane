"""The labeled-benchmark regression gate.  Two bars, because one is gameable.

Adapted from ChainCred's own pattern (research §7), which is the one thing in
that codebase that made heuristic drift *visible*: a committed labeled list,
a **precision floor**, and a **median-gap ceiling**.

Why both
    A precision floor alone is met perfectly by a detector that convicts
    nobody — no false positives when there are no positives — and "tuned to
    zero recall" is the failure mode a threshold change reaches by accident.
    A gap ceiling alone is met by a detector that convicts everybody.  The pair
    brackets the useful region and nothing else does.

Why a *median* gap
    Per audited operator, the gap is how many of its sampled members the
    detector failed to place in **one** cluster together.  A median rather than
    a mean, because two of the sixteen audited operators are minimum-amount
    crowds that only exist as crowds on the **full population** — in a
    220-address slice they are ten strangers who each sent 0.05 ETH, and a mean
    would let those two dictate the bar for the other fourteen.

Offline, and core
    This module reads the labeled subset the caller hands it and nothing else.
    It imports no transport, takes no URL, and holds no clock: the gate is a
    *measurement*, and a measurement that reached the network would move on its
    own between two runs of the same suite.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any, Mapping

from .cluster import DetectConfig, detect
from .model import Dataset


@dataclass(frozen=True, slots=True)
class OperatorScore:
    """One audited operator, and how nearly whole the detector recovered it.

    ``found`` is the largest number of this operator's sampled members that
    landed in a **single** detected cluster — not the number flagged.  A
    detector that scattered ten members across ten clusters found none of them
    in the sense that matters: the claim the dashboard renders is "these
    wallets are one operator", and a scattering does not support it.

    ``cluster_id`` is ``None`` when nothing was found — never ``0``, which is a
    real cluster id (the widest one, in fact).
    """

    name: str
    sampled: int
    found: int
    gap: int
    cluster_id: int | None
    flagged: int


@dataclass(frozen=True, slots=True)
class BenchResult:
    """What one gate run measured.  Counters are ``int``; ratios are in [0, 1].

    ``precision`` is ``0.0`` — not ``1.0``, and not ``None`` — for a run that
    flagged nothing.  Vacuous precision is the exact hole the ceiling exists to
    plug, and reporting it as perfect would let a silent detector pass the
    floor on its way to failing the ceiling, which reads like a near miss
    rather than a collapse.
    """

    precision: float
    recall: float
    median_gap: float
    flagged: int
    true_positives: int
    false_positives: int
    controls_flagged: int
    members: int
    controls: int
    operators_audited: int
    operators_whole: int
    total_points: int
    flagged_points: int
    operators: tuple[OperatorScore, ...]

    def passes(self, floor: float, ceiling: float) -> bool:
        """Both bars, together.  Neither alone is a gate."""
        return self.precision >= floor and self.median_gap <= ceiling


def dataset_from_labeled(
    labeled: Mapping[str, Any], *, tiers: str = "abc"
) -> Dataset:
    """The committed labeled subset as a :class:`Dataset`.

    *tiers* selects which of the three evidence tiers reach the detector:
    ``"a"`` is logs only, ``"ab"`` adds the transaction fingerprints, ``"abc"``
    adds the funding lookups.  Dropping a tier is how the gate exercises the
    real first-cycle state — a dashboard that has swept logs but not yet run
    its background enrichment — against the same population.

    Built through the public ``Dataset.from_events``, deliberately: the gate
    should exercise the coercion path every real producer goes through, not a
    private shortcut that only the fixture takes.
    """
    tiers = tiers.lower()
    rows = list(labeled.get("members", ())) + list(labeled.get("controls", ()))
    deposits: list[dict] = []
    firsts: list[dict] = []
    tx_rows: list[dict] = []
    funding_rows: list[dict] = []
    for entry in rows:
        addr = entry["address"]
        firsts.append({"contributor": addr, "index": entry["first_index"]})
        for dep in entry.get("deposits", ()):
            deposits.append({"contributor": addr, **dep})
        if "b" in tiers and entry.get("tx"):
            tx_rows.append(entry["tx"])
        if "c" in tiers and entry.get("funding"):
            funding_rows.append({"address": addr, **entry["funding"]})
    return Dataset.from_events(
        deposits,
        firsts,
        txs=tx_rows if "b" in tiers else None,
        funding=funding_rows if "c" in tiers else None,
    )


def run_benchmark(
    labeled: Mapping[str, Any],
    *,
    config: DetectConfig | None = None,
    tiers: str = "abc",
) -> BenchResult:
    """Score the detector against the committed labeled subset.

    *config* defaults to ``DetectConfig()``.  The curve rate only scales the
    two point counters — precision, recall and every gap are rate-invariant —
    so the gate does not require a live read to be meaningful; a caller that
    wants the production configuration passes
    ``CuratorPreset(...).detect_config()`` and gets the production answer,
    which is a different and equally real number (ruling R13 removes the
    minimum-amount crowds' only evidence, so recall falls and the gap doubles).
    """
    ds = dataset_from_labeled(labeled, tiers=tiers)
    res = detect(ds, config or DetectConfig())

    member_of: dict[str, str] = {
        m["address"].lower(): m["cluster"] for m in labeled.get("members", ())
    }
    controls = {c["address"].lower() for c in labeled.get("controls", ())}
    flagged = {a.lower() for a in res.flagged}

    true_positives = len(flagged & set(member_of))
    false_positives = len(flagged & controls)
    denominator = true_positives + false_positives
    # A run that flagged nothing has NO precision to report, and reporting the
    # vacuous 1.0 would dress a collapse up as a perfect score.
    precision = (true_positives / denominator) if denominator else 0.0
    recall = (true_positives / len(member_of)) if member_of else 0.0

    by_operator: dict[str, set[str]] = {}
    for addr, name in member_of.items():
        by_operator.setdefault(name, set()).add(addr)

    scores: list[OperatorScore] = []
    for name in sorted(by_operator):
        sampled = by_operator[name]
        best_found = 0
        best_id: int | None = None
        for cluster in res.clusters:
            overlap = len(sampled.intersection(cluster.members))
            if overlap > best_found:
                best_found, best_id = overlap, cluster.cluster_id
        scores.append(
            OperatorScore(
                name=name,
                sampled=len(sampled),
                found=best_found,
                gap=len(sampled) - best_found,
                cluster_id=best_id,
                flagged=len(sampled & flagged),
            )
        )

    gaps = [s.gap for s in scores]
    return BenchResult(
        precision=precision,
        recall=recall,
        median_gap=float(statistics.median(gaps)) if gaps else 0.0,
        flagged=len(flagged),
        true_positives=true_positives,
        false_positives=false_positives,
        controls_flagged=false_positives,
        members=len(member_of),
        controls=len(controls),
        operators_audited=len(scores),
        operators_whole=sum(1 for s in scores if s.gap == 0),
        total_points=res.total_points,
        flagged_points=res.flagged_points,
        operators=tuple(scores),
    )


__all__ = ["BenchResult", "OperatorScore", "dataset_from_labeled", "run_benchmark"]

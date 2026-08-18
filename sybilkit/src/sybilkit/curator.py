"""THE LIST's preset — the curve, the segments, the cleaned list.

``sybilkit`` is a general tool; this module is the one place that knows what
*this* game is.  It is still pure, still wei-native, still stdlib-only, and it
still imports nothing from maxpane: a preset is a bag of **measurements** plus
three folds over a :class:`~sybilkit.model.Dataset` and a
:class:`~sybilkit.report.DetectResult`.

The rule that shapes the whole module
    **Every chain constant is an input.**  ``POINTS_PER_ETH`` and
    ``minDeposit`` are read off the chain by whoever builds the preset (the CLI
    does it with an ``eth_call``, the maxpane adapter with its own client) and
    handed to :class:`CuratorPreset`, which has **no default for either**.
    CLAUDE.md hard constraint 4 is not a style rule here: one protocol in this
    repo documents a 5 % fee that is 1 % on chain, and a "4.0×" ratio quoted in
    research measured 3.885×, then 3.49×, then 2.956× on three consecutive
    days.  A preset that remembered ``1000`` would be right until the day it
    silently was not, and every point in the analysis would move with it.

    Ruling R13 makes the minimum the same kind of input for a sharper reason:
    with ``protocol_min_amount_wei`` unset, the crowd that all paid the
    protocol floor is byte-identical by construction and welds into one
    enormous group — WP1 measured **1 468 of 1 468** minimum-payers flagged
    with the knob off against **272** with it on.  Everyone sends the minimum,
    so the minimum identifies nobody.

The curve is not re-implemented here
    :func:`curve_points` is :func:`sybilkit.curve.curve_points`, re-exported
    (ruling R1).  There is deliberately exactly one implementation and one
    mutation-tested suite for it; a second copy is always the one nobody
    mutates, and the two drift in the last digits where nobody looks.

Pattern language, in the labels
    A preset's ``label`` strings are what a consumer renders.  The library may
    say "sybil" in its own name and docstrings — it is a general sybil-analysis
    toolkit and lives outside every scanned surface — but the *segment labels*
    are written in the dashboard's own vocabulary ("linked groups", "early
    cohort") so that an adapter never has to translate an accusation into a
    description.  :data:`FORBIDDEN_LABEL_WORDS` names what may not appear and
    ``tests/test_curator.py`` scans every produced string for it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .cluster import DetectConfig
from .curve import curve_points  # re-export, ruling R1 — never a second copy
from .model import Dataset
from .report import Cluster, DetectResult
from .signals import first_rows  # the one first-deposit fold, ruling R1's rule

#: Words a rendered ``label`` or ``detail`` may never contain.  The chain
#: cannot prove intent — one person spreading a deposit and nine people copying
#: a trade produce identical logs — so the preset describes shapes and lets the
#: reader draw the conclusion.  Mirrors the three forbidden-word tests the
#: curator dashboard already enforces on its own surfaces.
FORBIDDEN_LABEL_WORDS: tuple[str, ...] = (
    "sybil",
    "cheat",
    "fraud",
    "attack",
    "abuse",
    "farmer",
    "wash",
)

#: Multiplier bands, in basis points, **descending** — each band is
#: ``[edge, previous_edge)``.  The early-bird multiplier decays 2.0× → 1.0×
#: across the grace period, so these four bands split the population into
#: "arrived at nearly double" through "arrived at par".  A default, not a
#: measurement: the *edges* are a presentation choice and the preset takes
#: them as a field so a caller with a different decay can say so.
DEFAULT_MULTIPLIER_BAND_BPS: tuple[int, ...] = (17_500, 15_000, 12_500, 10_000)

_ETH = 10**18


#: Decimals kept by :func:`_eth_str`.  **Presentation only**, and lossy on
#: purpose: a jitter-batch amount is 0.082193701937108305 ETH and no label
#: wants eighteen decimals.  Nothing in this module computes with the string —
#: every arithmetic path is wei-native ``int`` — so the truncation cannot reach
#: a number anybody adds up.
LABEL_ETH_DECIMALS = 6


def _eth_str(wei: int) -> str:
    """A wei amount as a short ETH string.  Presentation only.

    Truncated rather than rounded (a label should not claim more than the value
    has), trailing zeros trimmed, one decimal always kept: ``0.45``, ``14.0``,
    ``2.067``, ``0.082193``.
    """
    whole, frac = divmod(wei, _ETH)
    text = f"{whole}.{frac:018d}"[: -(18 - LABEL_ETH_DECIMALS) or None].rstrip("0")
    return text + "0" if text.endswith(".") else text


# ---------------------------------------------------------------------------
# The preset
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CuratorPreset:
    """THE LIST's constants, as the caller measured them.

    ``points_per_eth``
        The chain's own ``POINTS_PER_ETH``.  **No default.**  It is 1000 on
        this deployment and that is a measurement, not a constant.

    ``min_deposit_wei``
        The chain's own ``minDeposit``.  **No default**, ruling R13: it becomes
        ``DetectConfig.protocol_min_amount_wei``, and without it the whole
        minimum-paying crowd is flagged wholesale on an identicalness that
        identifies nobody.

    The remaining fields are *analysis* choices rather than chain readings, so
    they carry documented defaults: the four ``DetectConfig`` gate knobs, the
    size of the "early cohort" (the research's index-1000 slice), how many
    trailing grace hours count as the late cohort, the combined-credit line
    above which an operator is one of the "largest", and the multiplier band
    edges.  Every one of them is still a field, so a caller who measured
    something different is never arguing with a literal.
    """

    points_per_eth: int
    min_deposit_wei: int
    min_size: int = 5
    min_families: int = 2
    near_amount_tol: float = 0.10
    confidence_threshold: float = 0.5
    early_cohort_size: int = 1_000
    late_cohort_hours: int = 2
    largest_operator_credit_wei: int = 800 * _ETH
    multiplier_band_bps: tuple[int, ...] = field(
        default=DEFAULT_MULTIPLIER_BAND_BPS
    )

    def __post_init__(self) -> None:
        # A programming error raises; it never produces a plausible analysis.
        if not isinstance(self.points_per_eth, int) or self.points_per_eth <= 0:
            raise ValueError(
                f"points_per_eth must be a positive int read from the chain, "
                f"got {self.points_per_eth!r}"
            )
        if not isinstance(self.min_deposit_wei, int) or self.min_deposit_wei < 0:
            raise ValueError(
                f"min_deposit_wei must be a non-negative wei int read from the "
                f"chain, got {self.min_deposit_wei!r}"
            )
        if self.early_cohort_size < 1:
            raise ValueError("early_cohort_size must be >= 1")
        if self.late_cohort_hours < 1:
            raise ValueError("late_cohort_hours must be >= 1")

    def detect_config(self) -> DetectConfig:
        """The gate configuration, with both live reads threaded in.

        This is the **only** path the rate has (ruling R10 removed the dataset
        attribute and its fallback), and the only path the minimum has
        (R13).  A caller that drives ``detect`` with anything else is driving
        it without the chain's own numbers.
        """
        return DetectConfig(
            min_size=self.min_size,
            min_families=self.min_families,
            near_amount_tol=self.near_amount_tol,
            confidence_threshold=self.confidence_threshold,
            points_per_eth=self.points_per_eth,
            protocol_min_amount_wei=self.min_deposit_wei,
        )

    def points(self, weight_wei: int) -> int:
        """Curve points for *weight_wei* at **this preset's** measured rate."""
        return curve_points(weight_wei, self.points_per_eth)

    def segments(
        self, ds: Dataset, res: DetectResult, *, weights=None, credits=None
    ) -> "Segments":
        """:func:`segments`, bound to this preset.  Forwards the shared folds."""
        return segments(ds, res, self, weights=weights, credits=credits)

    def clean_list(
        self, ds: Dataset, res: DetectResult, *, weights=None, credits=None
    ) -> "CleanList":
        """:func:`clean_list`, bound to this preset.  Forwards the shared folds."""
        return clean_list(ds, res, self, weights=weights, credits=credits)


# ---------------------------------------------------------------------------
# Derived per-contributor facts
# ---------------------------------------------------------------------------


def multiplier_bps(deposit) -> int | None:
    """The early-bird multiplier a deposit was credited at, in basis points.

    Derived from the deposit's **own words** — ``weight_added / credited_delta``
    — rather than from a remembered decay curve, which is the same discipline
    the rate and the minimum follow.  ``19_975`` is 1.9975×.

    ``None`` when ``credited_delta_wei`` is ``0``: that is a real and
    legitimate measurement (a deposit above the protocol's credit cap credits
    nothing) and nothing may divide by it.  A ``0`` here would be a *value*,
    and it would read as "credited at zero times", which is not what happened.
    """
    credited = deposit.credited_delta_wei
    if credited <= 0:
        return None
    return deposit.weight_added_wei * 10_000 // credited


def final_weights(ds: Dataset) -> dict[str, int]:
    """Each contributor's final high-water weight, in wei.

    The *last* ``new_weight_wei`` in chain order, never a sum: the contract
    writes a running high-water mark, so summing the deltas of a laddering
    wallet double-counts every rung.
    """
    weights: dict[str, int] = {}
    for dep in sorted(ds.deposits, key=lambda d: (d.block_number, d.log_index)):
        weights[dep.contributor] = dep.new_weight_wei
    return weights


def credited_totals(ds: Dataset) -> dict[str, int]:
    """Each contributor's total credited ETH, in wei — the sum of the deltas.

    A *sum* here and a *last* for the weight, deliberately: credit is what the
    contract accepted (a delta per deposit) and weight is a high-water mark.
    """
    credits: dict[str, int] = {}
    for dep in ds.deposits:
        credits[dep.contributor] = credits.get(dep.contributor, 0) + dep.credited_delta_wei
    return credits


def first_deposits(ds: Dataset):
    """Each contributor's first deposit, in chain order.

    :func:`sybilkit.signals.first_rows` under the preset's own name.  It was a
    second implementation of that fold — sort-then-``setdefault`` against a
    min-comparison — agreeing only because nobody had changed either, which is
    exactly the shape ruling R1 refused for the curve: the second copy is the
    one nobody mutation-tests, and the two drift where nobody looks.  The
    detector and the preset key their whole output off this map, so there is
    one of it.
    """
    return first_rows(ds)


# ---------------------------------------------------------------------------
# Segments
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OperatorSegment:
    """One linked group, as a *segment* rather than as evidence.

    ``credit_wei`` is the group's **combined** credited ETH, which is the whole
    point of the shape: a credit-threshold whale list at 800 ETH finds two
    wallets holding 0.25 % of the points on this population, because real whale
    capital here is split across hundreds of wallets.  Combining it on the
    operator is what makes a whale list mean anything (research §5).

    ``subsidy_x`` is the sqrt curve's own invitation, measured: the points the
    group earned split, over the points the same combined weight would have
    earned in one wallet.  ``None`` when the single-wallet fold is ``0`` (a
    group whose whole combined weight still floors to no points) — a zero there
    would be a division, not an answer.
    """

    cluster_id: int
    size: int
    credit_wei: int
    weight_wei: int
    points: int
    points_share: float
    subsidy_x: float | None
    confidence: float
    label: str
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Segment:
    """One band of the population: who is in it and what it is worth.

    ``key`` is machine-stable and is what a consumer keys on.  The whole
    vocabulary, exactly as emitted: ``linked_groups`` (every linked cluster
    aggregated — *not* the credit-line slice, which is
    :attr:`Segments.largest_operators` and is never a band), ``early_cohort``,
    ``late_cohort``, ``hour_<h>`` (``hour_9``), ``multiplier_<edge_bps>``
    (``multiplier_17500`` — the band's **lower** edge, since the upper one is
    the previous band's lower edge and naming both would let the two drift),
    and ``multiplier_unknown``.  ``label`` and
    ``detail`` are the human strings and are pattern language.  ``points`` and
    ``contributors`` are counts, and ``points_share`` is a *share* in [0, 1] —
    the presentation boundary multiplies by 100, once, where every other
    percentage is made.
    """

    key: str
    kind: str
    label: str
    contributors: int
    points: int
    points_share: float
    detail: str


@dataclass(frozen=True, slots=True)
class Segments:
    """Adam's ask, as data: the operators and the bands.

    ``operators`` is every linked group, ranked by **combined credit**;
    ``largest_operators`` is the slice of it at or above the preset's line.
    ``bands`` is the flat list a consumer renders: the ``linked_groups``
    aggregate, the early and late cohorts, one band per join hour and one per
    multiplier band.

    ``largest_operator_credit_wei`` gates :attr:`largest_operators` and
    **nothing else** — no band's membership moves with it.  The aggregate band
    used to carry that property's name while carrying every linked cluster,
    small ones included, so the row a consumer renders first claimed a whale
    fact and measured a linkage one; it is ``linked_groups`` / "linked groups"
    now, and the numbers on it are unchanged.
    """

    total_points: int
    total_contributors: int
    operators: tuple[OperatorSegment, ...]
    bands: tuple[Segment, ...]
    largest_operator_credit_wei: int

    @property
    def largest_operators(self) -> tuple[OperatorSegment, ...]:
        return tuple(
            op
            for op in self.operators
            if op.credit_wei >= self.largest_operator_credit_wei
        )

    def by_kind(self, kind: str) -> tuple[Segment, ...]:
        return tuple(s for s in self.bands if s.kind == kind)


def _dominant_amount(ds_firsts, members: tuple[str, ...]) -> int | None:
    """The first-deposit amount the most members of *members* share."""
    counts: dict[int, int] = {}
    for member in members:
        dep = ds_firsts.get(member)
        if dep is not None:
            counts[dep.amount_wei] = counts.get(dep.amount_wei, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda kv: (kv[1], -kv[0]))[0]


def _operator_segment(
    cluster: Cluster,
    preset: CuratorPreset,
    weights: dict[str, int],
    credits: dict[str, int],
    firsts,
    total_points: int,
) -> OperatorSegment:
    combined_weight = sum(weights.get(m, 0) for m in cluster.members)
    combined_credit = sum(credits.get(m, 0) for m in cluster.members)
    alone = curve_points(combined_weight, preset.points_per_eth)
    amount = _dominant_amount(firsts, cluster.members)
    shape = f"{_eth_str(amount)}Ξ send shape" if amount is not None else "mixed send shapes"
    return OperatorSegment(
        cluster_id=cluster.cluster_id,
        size=cluster.size,
        credit_wei=combined_credit,
        weight_wei=combined_weight,
        points=cluster.points,
        points_share=(cluster.points / total_points) if total_points else 0.0,
        subsidy_x=(cluster.points / alone) if alone else None,
        confidence=cluster.confidence,
        label=f"{shape} · {cluster.size:,} linked",
        reasons=tuple(r.human_string for r in cluster.reasons),
    )


def _band(
    key: str,
    kind: str,
    label: str,
    detail: str,
    members,
    points_of: dict[str, int],
    total_points: int,
) -> Segment:
    members = list(members)
    points = sum(points_of.get(m, 0) for m in members)
    return Segment(
        key=key,
        kind=kind,
        label=label,
        contributors=len(members),
        points=points,
        points_share=(points / total_points) if total_points else 0.0,
        detail=detail,
    )


def segments(
    ds: Dataset,
    res: DetectResult,
    preset: CuratorPreset,
    *,
    weights=None,
    credits=None,
) -> Segments:
    """The population, cut the ways Adam asked for.

    *preset* is required and is the third argument rather than the two the PRD
    sketched, for one reason that has no way around it: every band is a fold of
    **curve points**, and after ruling R10 the curve rate lives only in the
    caller's ``DetectConfig`` — a :class:`DetectResult` does not carry it and a
    :class:`Dataset` never did.  Deriving a rate here would be exactly the
    remembered constant the whole preset exists to avoid, so the measurement
    travels instead.

    Pure: no clock, no I/O.  Two calls over one ``(ds, res)`` return equal
    objects.

    *weights* and *credits* are :func:`final_weights` and
    :func:`credited_totals` when the caller already holds them; ``None``
    derives them.  :func:`clean_list` folds the same two things, and a consumer
    that renders the SEGMENTS panel *and* exports the CLEANED LIST calls both —
    four walks of the population's deposits for two answers.  Keyword-only and
    defaulted, exactly like the signals' shared folds: passing one is an
    optimisation, never a second opinion.
    """
    if weights is None:
        weights = final_weights(ds)
    if credits is None:
        credits = credited_totals(ds)
    firsts = first_deposits(ds)
    points_of = {addr: preset.points(w) for addr, w in weights.items()}
    total_points = sum(points_of.values())
    contributors = sorted(points_of)

    operators = sorted(
        (
            _operator_segment(c, preset, weights, credits, firsts, total_points)
            for c in res.clusters
        ),
        key=lambda op: (-op.credit_wei, -op.points, op.cluster_id),
    )

    bands: list[Segment] = []

    # --- the linked groups, as one aggregate row -------------------------
    if operators:
        amounts = [
            a
            for a in (_dominant_amount(firsts, c.members) for c in res.clusters)
            if a is not None
        ]
        if amounts:
            shape_detail = (
                f"{_eth_str(min(amounts))}Ξ–{_eth_str(max(amounts))}Ξ send shapes"
            )
        else:
            shape_detail = "mixed send shapes"
        linked = {m for c in res.clusters for m in c.members}
        bands.append(
            _band(
                # NOT "largest_operators": this row is every linked cluster,
                # however small, while `Segments.largest_operators` is the
                # credit-line slice.  Sharing a name made the headline row
                # claim a fact about whales while measuring one about linked
                # groups.  `kind` stays "operators" so consumer ordering does
                # not move with the name.
                "linked_groups",
                "operators",
                "linked groups",
                f"{len(operators):,} linked groups · {shape_detail}",
                linked,
                points_of,
                total_points,
            )
        )

    # --- the early cohort -------------------------------------------------
    cutoff = preset.early_cohort_size
    early = [a for a in contributors if 0 < ds.first_index.get(a, 0) <= cutoff]
    if early:
        bands.append(
            _band(
                "early_cohort",
                "cohort",
                f"early cohort · join index ≤{cutoff:,}",
                # NOT "the first N addresses on the list": N is how many of the
                # first `cutoff` join indices are in *this dataset*, which on a
                # partial sweep is a fact about the sample, not about the list.
                f"{len(early):,} of the first {cutoff:,} join indices present",
                early,
                points_of,
                total_points,
            )
        )

    # --- the late-grace cohort -------------------------------------------
    hours = {a: firsts[a].hour for a in contributors if a in firsts}
    if hours:
        last_hour = max(hours.values())
        # Clamped at 0: on a dataset younger than the window the unclamped
        # arithmetic names hours that do not exist ("joined in hours -1–1").
        # Nothing can be filed under a negative hour, so the only thing the
        # missing floor ever produced was a fabricated string.
        start = max(0, last_hour - preset.late_cohort_hours + 1)
        window = range(start, last_hour + 1)
        late = [a for a, h in hours.items() if h in window]
        if late:
            span = (
                f"hour {window[0]}"
                if len(window) == 1
                else f"hours {window[0]}–{window[-1]}"
            )
            bands.append(
                _band(
                    "late_cohort",
                    "cohort",
                    f"late cohort · last {preset.late_cohort_hours} grace hours",
                    f"joined in {span}",
                    late,
                    points_of,
                    total_points,
                )
            )

    # --- one band per join hour ------------------------------------------
    by_hour: dict[int, list[str]] = {}
    for addr, hour in hours.items():
        by_hour.setdefault(hour, []).append(addr)
    for hour in sorted(by_hour):
        credited = sum(credits.get(a, 0) for a in by_hour[hour])
        bands.append(
            _band(
                f"hour_{hour}",
                "hour",
                f"per-hour band · joined in hour {hour}",
                f"{len(by_hour[hour]):,} joined · {_eth_str(credited)}Ξ credited",
                by_hour[hour],
                points_of,
                total_points,
            )
        )

    # --- one band per multiplier band ------------------------------------
    edges = tuple(sorted(preset.multiplier_band_bps, reverse=True))
    by_band: dict[int | None, list[str]] = {}
    for addr in contributors:
        dep = firsts.get(addr)
        bps = None if dep is None else multiplier_bps(dep)
        chosen: int | None = None
        if bps is not None:
            for edge in edges:
                if bps >= edge:
                    chosen = edge
                    break
            # No edge matched, so this deposit's multiplier is BELOW the
            # lowest band.  It cannot happen on a decay curve that bottoms out
            # at 1.0x, which is exactly why it must not be filed under the
            # lowest band: a value the model says is impossible is either a
            # different deployment or a decode fault, and either way calling it
            # "1.00x-1.25x" is a fabricated fact.  It goes to the unknown
            # bucket with everything else that has no representable multiplier.
            if chosen is None:
                bps = None
        by_band.setdefault(chosen, []).append(addr)
    for i, edge in enumerate(edges):
        members = by_band.get(edge)
        if not members:
            continue
        upper = edges[i - 1] if i else None
        top = "" if upper is None else f"–{upper / 10_000:.2f}×"
        bands.append(
            _band(
                f"multiplier_{edge}",
                "multiplier",
                f"multiplier band · {edge / 10_000:.2f}×{top}",
                f"{len(members):,} joined at this early-bird band",
                members,
                points_of,
                total_points,
            )
        )
    unknown = by_band.get(None)
    if unknown:
        bands.append(
            _band(
                "multiplier_unknown",
                "multiplier",
                "multiplier band · unknown",
                "no representable multiplier — credited nothing at the cap, "
                "or below the lowest band",
                unknown,
                points_of,
                total_points,
            )
        )

    return Segments(
        total_points=total_points,
        total_contributors=len(contributors),
        operators=tuple(operators),
        bands=tuple(bands),
        largest_operator_credit_wei=preset.largest_operator_credit_wei,
    )


# ---------------------------------------------------------------------------
# The cleaned list
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CleanEntry:
    """One survivor of the de-sybilled list.  Wei-native; nothing divides."""

    clean_rank: int
    address: str
    points: int
    credit_wei: int
    weight_wei: int


@dataclass(frozen=True, slots=True)
class CleanList:
    """The list with the flagged groups removed, ranked, plus its counters."""

    entries: tuple[CleanEntry, ...]
    total_points: int
    flagged_points: int
    clean_points: int
    contributors_total: int
    flagged_contributors: int
    clean_contributors: int
    _rank_by_address: dict[str, int]
    _removed: frozenset[str]

    def clean_rank(self, addr: str) -> int | None:
        """This address's rank in the de-sybilled list, or ``None``.

        ``None`` covers two different facts — removed, and never analyzed — so
        a consumer that needs to tell them apart asks :meth:`standing` instead.
        """
        return self._rank_by_address.get(addr.lower())

    def standing(self, addr: str) -> str:
        """``"clean"`` · ``"removed"`` · ``"unknown"`` — never collapsed.

        The curator rail already shipped the collapsed version once: a row
        whose real negative has no representable value renders identically for
        "we looked and there was nothing" and "we could not look", and so reads
        confident and green through an outage.  A rank of ``None`` is that same
        hazard, so the three answers get three words.
        """
        key = addr.lower()
        if key in self._rank_by_address:
            return "clean"
        if key in self._removed:
            return "removed"
        return "unknown"


def clean_list(
    ds: Dataset,
    res: DetectResult,
    preset: CuratorPreset,
    *,
    weights=None,
    credits=None,
) -> CleanList:
    """The list with every flagged group's members removed, ranked densely.

    *preset* is required for the same reason :func:`segments` needs it — the
    ranking is by curve points and the rate is the caller's measurement.

    Ranking is ``(-points, address)``: points descending, ties broken on the
    lowercase address, so two wallets with identical points always rank in the
    same order and a re-run never reshuffles the export.

    **The survivors come from ``res.analyzed``, never from the dataset.**  This
    used to fall back to every contributor in *ds* when ``analyzed`` was empty,
    which rewrote "analyzed nobody" into "everybody analyzed and clean" — so
    :meth:`CleanList.standing` answered ``"clean"`` for a wallet
    :meth:`DetectResult.wallet` said was never looked at.  A result that
    analyzed nobody therefore has no survivors and a ``contributors_total`` of
    ``0``: the population is not the analysis, and an unanalyzed wallet's
    honest word is ``"unknown"``.

    ``analyzed`` is **lowercased on read**, exactly as ``flagged`` is.
    :class:`DetectResult` documents the set as lowercase, so this changes
    nothing a ``detect`` run can produce; on a hand-built result it is what
    keeps the object agreeing with itself, since :meth:`CleanList.standing` and
    :meth:`CleanList.clean_rank` lowercase every query they are given.

    *weights* and *credits* are :func:`final_weights` and
    :func:`credited_totals` when the caller already holds them — see
    :func:`segments`, which folds the same two things — and ``None`` derives
    them.
    """
    if weights is None:
        weights = final_weights(ds)
    if credits is None:
        credits = credited_totals(ds)
    flagged = {a.lower() for a in res.flagged}
    # Lowercased on read for the same reason `flagged` is, and it has to be the
    # same reason: `standing` and `clean_rank` lowercase every query, so an
    # analyzed set spelled any other way both leaks a flagged member past the
    # filter below and exports a survivor under a key its own accessors cannot
    # resolve.  `DetectResult` documents `analyzed` as lowercase, so this is a
    # no-op on every path `detect` produces and defence on the hand-built one.
    analyzed = {a.lower() for a in res.analyzed}

    survivors = sorted(
        (a for a in analyzed if a not in flagged),
        key=lambda a: (-preset.points(weights.get(a, 0)), a),
    )
    entries = tuple(
        CleanEntry(
            clean_rank=i,
            address=addr,
            points=preset.points(weights.get(addr, 0)),
            credit_wei=credits.get(addr, 0),
            weight_wei=weights.get(addr, 0),
        )
        for i, addr in enumerate(survivors, start=1)
    )
    return CleanList(
        entries=entries,
        total_points=res.total_points,
        flagged_points=res.flagged_points,
        clean_points=res.clean_points,
        contributors_total=len(analyzed),
        flagged_contributors=len(flagged),
        clean_contributors=len(entries),
        _rank_by_address={e.address: e.clean_rank for e in entries},
        _removed=frozenset(flagged),
    )


__all__ = [
    "CleanEntry",
    "CleanList",
    "CuratorPreset",
    "DEFAULT_MULTIPLIER_BAND_BPS",
    "FORBIDDEN_LABEL_WORDS",
    "OperatorSegment",
    "Segment",
    "Segments",
    "clean_list",
    "credited_totals",
    "curve_points",
    "final_weights",
    "first_deposits",
    "multiplier_bps",
    "segments",
]

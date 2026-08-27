"""The sybilkit adapter for THE LIST — the only maxpane import of ``sybilkit``.

One seam, two jobs:

* **Pure analysis** (:func:`build_analysis`, :func:`build_analysis_from_published`):
  the cache's decoded ``DepositEvent`` history — plus, for the local build,
  whatever ``txs``/``funding`` the caller already holds — in, an
  :class:`AnalysisResult` out, already shaped into the flat-dict rows
  ``CURATOR_ROW_KEYS`` freezes.  No I/O, no clock: two calls over one input
  return equal results.
* **The translation boundary** (:func:`pattern_language`): the library is a
  general sybil-analysis toolkit and may use its own vocabulary in its own
  docstrings; nothing it says reaches a rendered string unfiltered.  Every
  reason, label and detail passes this boundary — including strings read back
  from a **persisted** payload, because a hand-edited cache file is third-party
  input too.

Import discipline
    ``data/curator_clusters.py`` is the **only** maxpane module that may import
    ``sybilkit`` (guardrail-tested).  ``analytics/curator_signals.py`` stays
    byte-identical to what shipped and never learns the library exists.

Unit discipline
    Wei in, ETH out, divided **exactly once** — at :data:`_ETH`, the module's
    single division site.  The manager's own division count is pinned at zero,
    so this is where ``credit_eth`` is made.

Verdict discipline
    Nothing here emits a boolean judgement.  ``conf`` is a *band* derived from
    the **evidence structure**, not the raw confidence: noisy-OR puts every
    gated cluster at ≥ 0.77, so a numeric boundary would band nothing.
    ``"high"`` is ≥ :data:`HIGH_MIN_FAMILIES` distinct families **or** the
    funding family present (money provenance is the strongest measured
    discriminator); ``"low"`` is exactly two families; ``"clean"`` is analyzed
    and in no cluster; ``None`` is "the sweep has not run", which must never
    render as a confident clean.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

try:
    from sybilkit import Cluster, Dataset, DetectResult, Reason, detect
    from sybilkit.curator import CleanList, CuratorPreset, Segments
    from sybilkit.curator import clean_list as _clean_list
    from sybilkit.curator import segments as _segments
except ImportError:  # pragma: no cover — exercised through the flag in tests
    #: ``sybilkit`` published to PyPI as 0.1.0 on 2026-08-19 and 0.1.1 is the
    #: latest released version; the in-tree 0.2.0 has **not** been published,
    #: which is why ``pyproject.toml`` still pins ``sybilkit>=0.1.0`` rather
    #: than the newer floor. The import stays guarded regardless: this flag
    #: is the compatibility story — an older install, a partial environment
    #: or a future name change all treat absence as the analysis's cannot-run
    #: state (spaced retry, no banner), while the merge, the R9 ``link_conf``
    #: seeding and a HELD last-good keep working — they read persisted
    #: payloads, never the library.
    SYBILKIT_AVAILABLE = False
else:
    SYBILKIT_AVAILABLE = True

#: The evidence-family allowlist for strings read back out of a payload.
#: Taken from ``curator_list_filters`` (stdlib-only) and **not** from
#: ``sybilkit.cluster.FAMILIES``: the persisted-read paths in this module run
#: when the library is absent, and an allowlist that vanishes with it is not
#: an allowlist.  The two hold the same five words; the filter module's copy
#: is the one that is always importable.
from maxpane_dashboard.data.curator_list_filters import FILTER_FAMILIES
from maxpane_dashboard.data.curator_models import CURATOR_ANALYSIS_KEYS


def _require_sybilkit() -> None:
    """A clear raise for the analysis entry points when the library is gone.

    The manager checks :data:`SYBILKIT_AVAILABLE` before calling any of them,
    so in production this never fires; it exists so a direct caller gets a
    named error instead of a ``NameError`` from a half-imported module.
    """
    if not SYBILKIT_AVAILABLE:
        raise ModuleNotFoundError(
            "sybilkit is not installed; the linked-wallet analysis is "
            "unavailable (pip install sybilkit)"
        )

#: Wei per ETH — the module's ONLY division site (see the module docstring).
_ETH = 10**18


def _eth(wei: int) -> float:
    return wei / _ETH


#: Words that may never reach a rendered string.  The chain cannot prove
#: intent, so the adapter describes shapes and lets the reader judge — the same
#: rule the widgets and ``curator_signals`` already enforce on their surfaces.
#: A **superset of** ``sybilkit.curator.FORBIDDEN_LABEL_WORDS`` (order mirrored):
#: the library screens its own labels and this adapter re-filters everything on
#: the way out, so the only input this boundary alone guards is a hand-edited
#: cache — for which the two lists must not drift.  ``"farmer"`` is here for
#: that parity even though the library never emits it; the derived parity test
#: (``test_the_adapter_forbidden_words_cover_the_librarys_label_words``) catches
#: the next omission on either side.
FORBIDDEN_WORDS: tuple[str, ...] = (
    "sybil",
    "cheat",
    "fraud",
    "attack",
    "abuse",
    "farmer",
    "wash",
)

#: Per-family fallback phrases — what a reason renders as when the library's
#: own string cannot pass the boundary.  Family names are
#: ``sybilkit.cluster.FAMILIES``'s; a reason from a family this table has never
#: heard of falls back to :data:`_GENERIC_PHRASE`.
_REASON_PHRASES: dict[str, str] = {
    "amount": "matching send amounts",
    "sequence": "consecutive join indices",
    "cadence": "matching send rhythm",
    "gas": "uniform fee fingerprint",
    "funding": "shared funder chain",
}

_GENERIC_PHRASE = "linked send shape"

#: ``"high"`` needs this many distinct families, unless funding is present.
HIGH_MIN_FAMILIES = 3

#: How many survivors the rendered clean list carries.  The widget caps its
#: table well below this; the *full* ranking travels in ``clean_ranks`` so the
#: reader's own rank is answerable for any wallet.
CLEAN_LIST_LIMIT = 1_000


def pattern_language(
    text: Any, family: str | None = None, *, fallback: str | None = None
) -> str:
    """*text* if it is a clean string, else the family's pattern phrase.

    The translation boundary.  A reason spelled in the library's vocabulary —
    or in a hand-edited cache file's — is replaced, never shipped: the replaced
    phrase still names the evidence family, so the reader loses adjectives,
    not information.
    """
    if fallback is None:
        fallback = _REASON_PHRASES.get(family or "", _GENERIC_PHRASE)
    if not isinstance(text, str) or not text.strip():
        return fallback
    low = text.lower()
    if any(word in low for word in FORBIDDEN_WORDS):
        return fallback
    return text


def build_preset(points_per_eth: Any, min_deposit_wei: Any) -> CuratorPreset:
    """The curator preset from the two **live** chain reads.

    No defaults on purpose (rulings R10/R13): ``POINTS_PER_ETH()`` and
    ``minDeposit()`` come off the ``once`` tier, and a remembered 1000 or
    0.05 ETH is exactly the constant this preset exists to refuse.  A missing
    or malformed read raises — the caller reports "could not analyze" rather
    than analyzing with a guess.
    """
    _require_sybilkit()
    if not isinstance(points_per_eth, int) or isinstance(points_per_eth, bool):
        raise ValueError(
            f"points_per_eth must be the live-read rate, got {points_per_eth!r}"
        )
    if not isinstance(min_deposit_wei, int) or isinstance(min_deposit_wei, bool):
        raise ValueError(
            f"min_deposit_wei must be the live-read minimum, got {min_deposit_wei!r}"
        )
    return CuratorPreset(
        points_per_eth=points_per_eth, min_deposit_wei=min_deposit_wei
    )


# ---------------------------------------------------------------------------
# The pure analysis
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AnalysisResult:
    """Everything the manager needs to fill the fourteen analysis keys.

    Holds the library objects (for the agreement tests and the linkage
    lookups) *and* the already-shaped rows, so the manager never touches a
    sybilkit type.  ``groups`` and ``clean_ranks`` are the compact revisable
    lookups the slot payload persists: enough to re-answer "is this wallet
    linked, and at what clean rank" for **any** wallet after a restart,
    without re-running the analysis.
    """

    result: DetectResult
    segments: Segments
    clean: CleanList
    preset: CuratorPreset
    wallet: str | None
    operator_rows: list[dict]
    segment_rows: list[dict]
    clean_list_rows: list[dict]
    operators_count: int
    clean_points: int
    clean_contributors: int
    points_total: int
    flagged_points_share_pct: float | None
    groups: list[dict] = field(default_factory=list)
    clean_ranks: dict[str, int] = field(default_factory=dict)

    @property
    def flagged(self) -> set[str]:
        return self.result.flagged


def _families_of(cluster: Any) -> set[str]:
    return {reason.family for reason in cluster.reasons}


def _grade_families(families: Iterable[str]) -> str:
    """The evidence-structure band — see the module docstring."""
    fams = set(families)
    if len(fams) >= HIGH_MIN_FAMILIES or "funding" in fams:
        return "high"
    return "low"


def _reason_strings(reasons: Iterable[Any]) -> list[str]:
    out: list[str] = []
    for reason in reasons:
        family = getattr(reason, "family", None)
        text = getattr(reason, "human_string", reason)
        out.append(pattern_language(text, family))
    return out


def _finish(
    ds: Any,
    res: Any,
    seg: Any,
    clean: Any,
    preset: CuratorPreset,
    wallet: str | None,
    operator_rows: list[dict],
    segment_rows: list[dict],
    groups: list[dict],
) -> AnalysisResult:
    """The tail both builders share: the clean rows and the result object.

    :func:`build_analysis` and :func:`build_analysis_from_published` fork at
    ``detect``, and their *heads* genuinely differ — the band word, the
    reasons, the extra group key.  Their **tails** did not differ by a
    character, and 45 duplicated lines is how a fix reaches one of two
    dashboards: T7 and T10 render ``clean_list_rows``, so a field added
    there, a change to the :data:`CLEAN_LIST_LIMIT` slice, or a different
    ENS hand-off than ``"name": None`` would have had to be made twice —
    and the published path would silently ship different rows than the
    local one the day it was not.  CLAUDE.md's "reuse before you build"
    names this exact failure and this branch has already paid it once.

    Pure, like both its callers: it reads ``ds``/``res``/``seg``/``clean``
    and holds no clock.
    """
    first_hours: dict[str, int] = {}
    tx_counts: dict[str, int] = {}
    for deposit in sorted(
        ds.deposits, key=lambda row: (row.block_number, row.log_index)
    ):
        first_hours.setdefault(deposit.contributor, deposit.hour)
        tx_counts[deposit.contributor] = deposit.tx_count

    clean_list_rows = [
        {
            "clean_rank": entry.clean_rank,
            "address": entry.address,
            "points": entry.points,
            "credit_eth": _eth(entry.credit_wei),
            # The manager's ENS merge fills this, exactly like the leaderboard.
            "name": None,
            "weight_eth": _eth(entry.weight_wei),
            "tx_count": tx_counts.get(entry.address),
            "first_hour": first_hours.get(entry.address),
            "first_index": ds.first_index.get(entry.address),
        }
        for entry in clean.entries[:CLEAN_LIST_LIMIT]
    ]

    share = (
        res.flagged_points / res.total_points * 100 if res.total_points else None
    )
    return AnalysisResult(
        result=res,
        segments=seg,
        clean=clean,
        preset=preset,
        wallet=wallet.lower() if isinstance(wallet, str) else None,
        operator_rows=operator_rows,
        segment_rows=segment_rows,
        clean_list_rows=clean_list_rows,
        operators_count=len(res.clusters),
        clean_points=res.clean_points,
        clean_contributors=clean.clean_contributors,
        points_total=res.total_points,
        flagged_points_share_pct=share,
        groups=groups,
        clean_ranks={e.address: e.clean_rank for e in clean.entries},
    )


# ---------------------------------------------------------------------------
# Reconstructing sybilkit objects from published cluster membership
# ---------------------------------------------------------------------------
#
# THE LIST's linked-wallet analysis reads a published, immutable dataset
# instead of computing its own sweep.  The functions below turn that
# dataset's cluster metadata and per-wallet membership into real
# ``sybilkit.Cluster`` / ``sybilkit.DetectResult`` objects so the library's
# own pure ``segments()`` and ``clean_list()`` run over them unchanged.  Every
# input here is third-party (an HTTP service, or a hand-edited export file
# read back), so a malformed row costs the ROW, never the sweep.


def _opt_int(value: Any) -> int | None:
    """An ``int`` or ``None``.  ``bool`` is not an int here: ``True`` in a JSON
    payload is a type error, not the number one."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _opt_float(value: Any) -> float | None:
    """A finite ``float`` or ``None``.  ``nan``/``inf`` survive ``json.loads``
    and would poison every share and confidence they touch."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _valid_address(value: Any) -> str | None:
    """Lowercased ``0x``-prefixed 40-hex address, or ``None``.

    The endpoint is third-party input.  A row whose address will not parse
    costs the ROW, never the sweep -- the same rule the list source already
    applies to a hand-edited export file.
    """
    if not isinstance(value, str) or len(value) != 42 or not value.startswith("0x"):
        return None
    try:
        int(value[2:], 16)
    except ValueError:
        return None
    return value.lower()


def published_band(cluster: Mapping) -> str:
    """The group's band word: the publisher's, or ours derived from families.

    Measured 2026-08-27: over all 160 published clusters the publisher's
    ``band`` and :func:`_grade_families` agree exactly, so this is not a
    reconciliation -- it is a guard.  ``band`` is a string from an HTTP
    service and the vocabulary beside it (``risk``: ``critical``/``elevated``)
    is one this dashboard does not speak; only ``high`` and ``low`` are
    passed through, and anything else falls back to the grading we can
    defend from the families we also read.
    """
    band = cluster.get("band")
    if band in ("high", "low"):
        return band
    families = cluster.get("families")
    return _grade_families(set(families) if isinstance(families, list) else set())


def review_members_of(rows: Iterable[Any]) -> dict[int, dict[str, list[str]]]:
    """Cluster id -> ``{address: families}`` for every ``status == "review"`` row."""
    out: dict[int, dict[str, list[str]]] = {}
    for row in rows:
        if not isinstance(row, Mapping) or row.get("status") != "review":
            continue
        address = _valid_address(row.get("address"))
        cluster_id = row.get("cluster_id")
        if address is None or not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            continue
        families = row.get("member_families")
        out.setdefault(cluster_id, {})[address] = (
            [f for f in families if isinstance(f, str)] if isinstance(families, list) else []
        )
    return out


def clusters_from_published(clusters: Iterable[Any], rows: Iterable[Any]) -> list[Any]:
    """``sybilkit.Cluster`` objects carrying the published membership.

    The published data supplies membership and reasons; every number
    downstream of here is still computed by the library's own pure code over
    the LOCAL dataset, so a cluster that the endpoint describes but our fold
    has never seen simply contributes no members and no points.
    """
    _require_sybilkit()
    members: dict[int, list[str]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        cluster_id = row.get("cluster_id")
        address = _valid_address(row.get("address"))
        if address is None or not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            continue
        members.setdefault(cluster_id, []).append(address)

    out: list[Any] = []
    for cluster in clusters:
        if not isinstance(cluster, Mapping):
            continue
        cluster_id = cluster.get("id")
        if not isinstance(cluster_id, int) or isinstance(cluster_id, bool):
            continue
        reasons = tuple(
            Reason(
                family=r.get("family") if isinstance(r.get("family"), str) else "",
                human_string=pattern_language(r.get("text"), r.get("family")),
                strength=_opt_float(r.get("strength")) or 0.0,
            )
            for r in (cluster.get("reasons") or ())
            if isinstance(r, Mapping)
        )
        seats = tuple(sorted(members.get(cluster_id, ())))
        out.append(
            Cluster(
                cluster_id=cluster_id,
                members=seats,
                reasons=reasons,
                confidence=_opt_float(cluster.get("confidence")) or 0.0,
                points=_opt_int(cluster.get("points")) or 0,
                points_share=_opt_float(cluster.get("points_share")) or 0.0,
                span_blocks=_opt_int(cluster.get("span_blocks")),
                size=len(seats),
            )
        )
    return out


def detect_result_from_published(
    clusters: Iterable[Any], rows: Iterable[Any], totals: Mapping
) -> Any:
    """A hand-built :class:`DetectResult` over published membership.

    ``sybilkit`` documents the hand-built result as first-class (ruling D1-B)
    and ``DetectResult.__init__`` sorts by ``points_share`` and lowercases its
    member index, so this object answers ``wallet()`` and feeds ``segments()``
    / ``clean_list()`` identically to one ``detect()`` produced.

    ``analyzed`` is left at its ``frozenset()`` default here and is set by the
    caller from the LOCAL dataset -- the population this build actually
    folded, not the one the publisher folded.  A wallet in neither reads "not
    analyzed", which is the safe default the library chose on purpose.
    """
    _require_sybilkit()
    built = clusters_from_published(clusters, rows)
    total = _opt_int(totals.get("points")) or 0
    linked = _opt_int(totals.get("linked_points")) or 0
    return DetectResult(built, total, linked, max(total - linked, 0))


def build_analysis(
    events: Iterable[Any],
    first_deposits: Iterable[Any],
    *,
    txs: Mapping[str, Any] | None = None,
    funding: Mapping[str, Any] | None = None,
    points_per_eth: int | None = None,
    min_deposit_wei: int | None = None,
    wallet: str | None = None,
    config: CuratorPreset | None = None,
) -> AnalysisResult:
    """The whole pure pipeline: dataset → detect → segments → clean list → rows.

    *events* and *first_deposits* are whatever the cache holds (the decoded
    ``DepositEvent`` models, or mapping rows — ``Dataset.from_events`` reads
    both).  *txs*/*funding* are whatever tx-fingerprint and first-funder maps
    the caller already holds — nothing in this module fetches them (T11
    removed the detached enrichment sweep that once did); tier A alone is a
    legal run whose losses are honest (the ≥2-family gate simply finds less).

    *config* is a ready :class:`CuratorPreset`; without one, both live reads
    are **required** and a missing one raises (see :func:`build_preset`).
    ``min_deposit_wei`` is not in the WP3 brief's sketched signature — ruling
    R13 landed after it was written, and the preset refuses to exist without
    the minimum, so the honest signature carries it.
    """
    _require_sybilkit()
    preset = config if config is not None else build_preset(
        points_per_eth, min_deposit_wei
    )
    ds = Dataset.from_events(events, first_deposits, txs=txs, funding=funding)
    res = detect(ds, preset.detect_config())
    seg = _segments(ds, res, preset)
    clean = _clean_list(ds, res, preset)

    # --- operator rows: widest share first, the panel's own lead order ------
    seg_by_id = {op.cluster_id: op for op in seg.operators}
    operator_rows: list[dict] = []
    groups: list[dict] = []
    for cluster in res.clusters:                       # already share-desc
        op = seg_by_id.get(cluster.cluster_id)
        families = _families_of(cluster)
        conf = _grade_families(families)
        reasons = _reason_strings(cluster.reasons)
        operator_rows.append(
            {
                "size": cluster.size,
                "reasons": reasons,
                "points": cluster.points,
                "points_share_pct": cluster.points_share * 100,
                "sqrt_subsidy_x": op.subsidy_x if op is not None else None,
                "conf": conf,
            }
        )
        groups.append(
            {
                "size": cluster.size,
                "conf": conf,
                "families": sorted(families),
                "reasons": reasons,
                "members": list(cluster.members),
            }
        )

    # --- segment rows: operators, cohorts, multiplier bands, then the hours.
    # The widget renders the first MAX_ROWS only, so the twenty-odd hour bands
    # go last rather than burying the aggregate (WP4's ordering hand-off).
    ordered = [b for b in seg.bands if b.kind == "operators"]
    ordered += [b for b in seg.bands if b.kind == "cohort"]
    ordered += [b for b in seg.bands if b.kind == "multiplier"]
    ordered += [b for b in seg.bands if b.kind == "hour"]
    segment_rows = [
        {
            "label": pattern_language(b.label, fallback="population band"),
            "contributors": b.contributors,
            "points_share_pct": (
                b.points_share * 100 if b.points_share is not None else None
            ),
            "detail": pattern_language(b.detail, fallback=""),
        }
        for b in ordered
    ]

    return _finish(
        ds, res, seg, clean, preset, wallet, operator_rows, segment_rows, groups
    )


# ---------------------------------------------------------------------------
# The same pipeline, over PUBLISHED membership
# ---------------------------------------------------------------------------


def _review_suffix(reasons: list[str], cluster: Mapping) -> list[str]:
    """Append ``under review`` to a group the publisher has flagged as such.

    Group review and MEMBER review are disjoint on the live service (measured
    2026-08-27: the 5 ``review_flag`` groups hold zero review members, and all
    26 groups that hold them are unflagged).  So this is a sentence in the
    group's reasons, never a band word -- a group row reading ``~`` while every
    one of its members reads ``⚑`` would be a contradiction the publisher never
    made.
    """
    if not cluster.get("review_flag"):
        return reasons
    # OUR sentence, not the payload's, so it does not go through
    # `pattern_language`: `pattern_language(expr, None, fallback=expr)` is an
    # idiom that turns the boundary off silently the moment `expr` becomes a
    # payload value (both sides move together, so no test can see it), and it
    # makes `grep "pattern_language("` useless as a boundary audit.  The
    # payload's own strings -- the reasons this is appended to -- pass the
    # boundary twice, in `clusters_from_published` and in `_reason_strings`.
    return [*reasons, "under review"]


def _review_segment_row(
    reviews: Mapping[int, Mapping[str, Any]],
    rows: Iterable[Any],
    total_points: int,
) -> dict | None:
    """The ``under review`` band, folded from the payload — or ``None``.

    ``None`` when the payload reviews nobody: an empty band would claim a
    population that does not exist.  Both numbers on the row are folds over
    the rows that were actually read — the count the live service happens to
    publish today, and its share of the points, are written down nowhere in
    this file, so a later snapshot moves them without an edit.

    Per-wallet points come from the published rows, which agreed with our own
    fold to the digit on every shared address.  :func:`build_analysis` has no
    per-address points map in scope — ``segments()`` builds one privately —
    and reaching for one would mean a second fold of the population for one
    number.
    """
    # `len(review_addresses)`, not `sum(len(m) for m in reviews.values())`:
    # the points below are folded over the union, so counting the per-cluster
    # lists would let one address filed under two cluster ids -- impossible
    # live, reachable from a hand-edited cache -- be two contributors holding
    # one wallet's points.
    review_addresses = {addr for m in reviews.values() for addr in m}
    if not review_addresses:
        return None
    # Folded per ADDRESS, not per row, for the same reason `contributors` is:
    # summing the rows makes a wallet listed twice worth twice its points,
    # which puts the two folds back in disagreement from the other side.
    # First row wins, so the answer does not depend on payload order.
    points_by_address: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        address = _valid_address(row.get("address"))
        if address is None or address not in review_addresses:
            continue
        points_by_address.setdefault(address, _opt_int(row.get("points")) or 0)
    review_points = sum(points_by_address.values())
    return {
        "label": "under review",
        "contributors": len(review_addresses),
        "points_share_pct": (
            review_points / total_points * 100 if total_points else None
        ),
        # NOT "fewer than two evidence families".  The publisher names the
        # gate ``v2h (v2g + aged-weak periphery)``; most review wallets carry
        # one family (``amount``, then ``sequence``, then ``cadence``) but a
        # measured handful carry **two**, so a family count is a rule we
        # would have invented.  What a reader can act on is that the evidence
        # is thin and the wallet is still on the list.
        # Ours, not the payload's -- see `_review_suffix` for why that means
        # a plain literal rather than a `pattern_language` round trip.
        "detail": "thin evidence · shown, never removed",
    }


def build_analysis_from_published(
    events: Iterable[Any],
    first_deposits: Iterable[Any],
    *,
    clusters: Iterable[Any],
    rows: Iterable[Any],
    totals: Mapping,
    wallet: str | None = None,
    config: CuratorPreset,
) -> AnalysisResult:
    """:func:`build_analysis`, with the clusters read instead of detected.

    Everything downstream of ``detect`` is the same code over the same local
    dataset: the published payload supplies **membership and its metadata**,
    and the library's own pure ``segments()`` and ``clean_list()`` still fold
    *our* events for every number a reader sees.  A wallet the publisher
    describes but our fold has never seen therefore contributes no points and
    no clean rank, which is the honest answer rather than a borrowed one.

    Three things this build has that :func:`build_analysis` does not:

    * ``groups[].review_members`` — the publisher's per-wallet review rows,
      indexed to the group they sit in;
    * one appended ``under review`` segment band, folded from those rows;
    * ``conf`` taken from :func:`published_band` rather than
      :func:`_grade_families` — the publisher's word when it is one we speak,
      and our own grading when it is not.

    *config* is required: there is no live-read fallback here, because a
    preset that remembered ``1000`` would move every point in the analysis on
    the day the chain stopped agreeing with it.
    """
    _require_sybilkit()
    # Materialised once: both are iterated three times below (the
    # reconstruction, the review index and the review fold), and a caller
    # handing over a generator would otherwise silently analyse an empty
    # population on the second pass.
    published = list(clusters)
    member_rows = list(rows)
    preset = config

    ds = Dataset.from_events(events, first_deposits)
    res = detect_result_from_published(published, member_rows, totals)
    # `detect_result_from_published` leaves `analyzed` at DetectResult's
    # frozenset() default ON PURPOSE, and setting it is this caller's job:
    # the analysed population is the one THIS build folded, never the one the
    # publisher folded.  Dropping this line does not raise — `clean_list`
    # takes its survivors from `analyzed` and nothing else, so every
    # non-member would read "not analyzed" instead of "analyzed and clean"
    # and the clean list would come back empty with every other counter
    # still looking plausible.
    res.analyzed = frozenset(d.contributor for d in ds.deposits)
    seg = _segments(ds, res, preset)
    clean = _clean_list(ds, res, preset)
    # `member_families` is a payload-sourced STRING channel that ends up on a
    # widget, and `review_members_of` keeps entries on an `isinstance(str)`
    # check alone -- so a hand-edited cache, explicitly in this module's
    # threat model, can put any word at all in there.  Filtered once, here,
    # at the only site that stores them.  (This protects the WRITE path;
    # anything reading `review_members` back out of a persisted payload needs
    # its own filter, and that surface is not this function's.)
    reviews = {
        cluster_id: {
            address: [f for f in families if f in FILTER_FAMILIES]
            for address, families in members.items()
        }
        for cluster_id, members in review_members_of(member_rows).items()
    }

    published_by_id: dict[int, Mapping] = {}
    for cluster in published:
        if not isinstance(cluster, Mapping):
            continue
        cluster_id = cluster.get("id")
        if isinstance(cluster_id, int) and not isinstance(cluster_id, bool):
            published_by_id.setdefault(cluster_id, cluster)

    # --- operator rows: widest share first, the panel's own lead order ------
    seg_by_id = {op.cluster_id: op for op in seg.operators}
    operator_rows: list[dict] = []
    groups: list[dict] = []
    for cluster in res.clusters:                       # already share-desc
        op = seg_by_id.get(cluster.cluster_id)
        source = published_by_id.get(cluster.cluster_id, {})
        families = _families_of(cluster)
        conf = published_band(source)
        reasons = _review_suffix(_reason_strings(cluster.reasons), source)
        operator_rows.append(
            {
                "size": cluster.size,
                "reasons": reasons,
                "points": cluster.points,
                "points_share_pct": cluster.points_share * 100,
                "sqrt_subsidy_x": op.subsidy_x if op is not None else None,
                "conf": conf,
            }
        )
        groups.append(
            {
                "size": cluster.size,
                "conf": conf,
                "families": sorted(families),
                "reasons": reasons,
                "members": list(cluster.members),
                # ``{}``, never ``None``: "we looked and there were none" is a
                # representable answer and must not render as "unknown".
                "review_members": reviews.get(cluster.cluster_id, {}),
            }
        )

    # --- segment rows: operators, cohorts, multiplier bands, then the hours.
    # The widget renders the first MAX_ROWS only, so the twenty-odd hour bands
    # go last rather than burying the aggregate (WP4's ordering hand-off).
    ordered = [b for b in seg.bands if b.kind == "operators"]
    ordered += [b for b in seg.bands if b.kind == "cohort"]
    ordered += [b for b in seg.bands if b.kind == "multiplier"]
    ordered += [b for b in seg.bands if b.kind == "hour"]
    segment_rows = [
        {
            "label": pattern_language(b.label, fallback="population band"),
            "contributors": b.contributors,
            "points_share_pct": (
                b.points_share * 100 if b.points_share is not None else None
            ),
            "detail": pattern_language(b.detail, fallback=""),
        }
        for b in ordered
    ]
    # `seg.total_points`, NOT `res.total_points`.  The two are the publisher's
    # base and the local fold's base, and they agree only when this build
    # folded the same population the publisher did.  Every other row in
    # `segment_rows` gets its share from `_segments`, i.e. from the LOCAL
    # fold, so the publisher's base would put one row in the column on a
    # different denominator than its neighbours -- on the trimmed fixture, a
    # 48x gap rendering 0.132 % beside siblings that say 6.346 % for the same
    # wallets.  The argument does cut both ways: when the local fold is
    # INCOMPLETE the publisher's base is the truthful one and the siblings are
    # the overstated ones.  Internal consistency inside a single column wins,
    # because that is the comparison a reader actually makes -- but it was
    # weighed, not defaulted.  (The numerator stays the published per-wallet
    # points, which agreed with our own fold to the digit on every shared
    # address, so the two halves of the ratio remain commensurable.)
    review_row = _review_segment_row(reviews, member_rows, seg.total_points)
    if review_row is not None:
        # After the LAST operators-kind band, not at a remembered index 1:
        # when `seg.operators` is empty `ordered` starts with a cohort band
        # and a hardcoded 1 would drop this row into the middle of the
        # cohorts, where it means nothing.
        segment_rows.insert(
            sum(1 for b in ordered if b.kind == "operators"), review_row
        )

    return _finish(
        ds, res, seg, clean, preset, wallet, operator_rows, segment_rows, groups
    )


# ---------------------------------------------------------------------------
# Lookups that work identically off the live result and the persisted payload
# ---------------------------------------------------------------------------


def _groups_of(analysis: Any) -> list[dict]:
    if isinstance(analysis, AnalysisResult):
        return analysis.groups
    if isinstance(analysis, Mapping):
        raw = analysis.get("groups")
        return [g for g in raw if isinstance(g, Mapping)] if isinstance(
            raw, list
        ) else []
    return []


def _clean_ranks_of(analysis: Any) -> Mapping[str, Any]:
    if isinstance(analysis, AnalysisResult):
        return analysis.clean_ranks
    if isinstance(analysis, Mapping):
        raw = analysis.get("clean_ranks")
        return raw if isinstance(raw, Mapping) else {}
    return {}


def clean_list_rows_from_fold(
    analysis: Any,
    rows: Iterable[Any],
    *,
    limit: int | None = CLEAN_LIST_LIMIT,
) -> list[dict[str, Any]]:
    """Rebuild clean rows from persisted ranks and contributor fold rows."""
    cap = None if limit is None else max(0, int(limit))
    ranks = {
        address.lower(): rank
        for address, rank in _clean_ranks_of(analysis).items()
        if isinstance(address, str)
        and isinstance(rank, int)
        and not isinstance(rank, bool)
        and rank >= 1
        and (cap is None or rank <= cap)
    }
    rebuilt: list[dict[str, Any]] = []
    seen_ranks: set[int] = set()
    for row in rows:
        address = getattr(row, "address", None)
        points = getattr(row, "points", None)
        credit_wei = getattr(row, "credit_wei", None)
        weight_wei = getattr(row, "weight_wei", None)
        if not isinstance(address, str):
            continue
        rank = ranks.get(address.lower())
        if rank is None or rank in seen_ranks:
            continue
        if not isinstance(points, int) or isinstance(points, bool):
            continue
        if not isinstance(credit_wei, int) or isinstance(credit_wei, bool):
            continue
        if not isinstance(weight_wei, int) or isinstance(weight_wei, bool):
            continue
        rebuilt.append(
            {
                "clean_rank": rank,
                "address": address,
                "points": points,
                "credit_eth": _eth(credit_wei),
                "name": None,
                "weight_eth": _eth(weight_wei),
                "tx_count": getattr(row, "tx_count", None),
                "first_hour": getattr(row, "first_hour", None),
                "first_index": getattr(row, "first_index", None),
            }
        )
        seen_ranks.add(rank)
    return sorted(rebuilt, key=lambda row: row["clean_rank"])


def _group_of(address: str, analysis: Any) -> Mapping | None:
    """The first group whose ``members`` contains *address*, or ``None``.

    Both sides lowercased, not just the query: ``sybilkit/report.py``
    documents the convention this module lives under — "every membership
    test here is lowercased on both sides" — and a stored ``members`` entry
    of any other case (a hand-edited cache, exactly this module's threat
    model) used to make this raw comparison miss a real member.  Measured
    2026-08-27: `bands_by_address` already lowercased its own copy of each
    member before keying its map, so it disagreed with this half-normalised
    comparison on exactly that input; this fix is what makes the two agree
    by construction rather than by coincidence of fixture casing.
    """
    key = address.lower()
    for group in _groups_of(analysis):
        members = group.get("members")
        if not isinstance(members, (list, tuple)):
            continue
        if key in {m.lower() for m in members if isinstance(m, str)}:
            return group
    return None


def grade_of(address: Any, analysis: Any) -> str | None:
    """``"high"`` · ``"low"`` · ``"review"`` · ``"clean"`` · ``None`` for one address.

    ``None`` covers both "no analysis has run" and "this wallet was not in the
    analyzed population" — either way the honest rendering is ``?``, never the
    empty cell that means *clean*.  ``"review"`` is T4's third wallet state:
    thin evidence, shown rather than removed — a per-WALLET mark, checked
    before the group's own band, never the group's own ``review_flag``
    (measured 2026-08-27: over all 26 clusters holding review members, the 5
    ``review_flag`` clusters hold zero of them — group review and member
    review are disjoint on the live service).
    """
    if not isinstance(address, str) or analysis is None:
        return None
    group = _group_of(address, analysis)
    if group is not None:
        review = group.get("review_members")
        # `isinstance` first: a malformed `review_members` (not even a
        # mapping — a hand-edited cache is exactly this module's threat
        # model) must not raise, and costs only the review distinction —
        # the group's own `conf` still answers below, and the membership
        # FACT (linked, size, reasons) is `you_linkage`'s and is untouched.
        if isinstance(review, Mapping) and address.lower() in review:
            return "review"
        conf = group.get("conf")
        # An unknown band in a persisted group is bad data, and a confidence
        # word derived from bad data is a claim: it renders `?` (None) — the
        # membership FACT (linked, size, reasons) is `you_linkage`'s and is
        # untouched by the band being unreadable.
        return conf if conf in ("high", "low") else None
    if address.lower() in _clean_ranks_of(analysis):
        return "clean"
    return None


def bands_by_address(analysis: Any) -> dict[str, str]:
    """Every analysed address -> ``"high"``/``"low"``/``"review"``/``"clean"``.

    The bulk form of :func:`grade_of` — built in ONE pass over ``groups`` and
    ``clean_ranks``, rather than :func:`grade_of`'s O(address × groups) (it
    scans every group's member list per address).  ``merge_leaderboard_grade``
    uses this instead of calling :func:`grade_of` per row, which is what lets
    a several-thousand-row archive write finish in reasonable time.

    An address absent from the returned mapping means ``None`` — "no analysis
    has run" or "unreadable band" — exactly what :func:`grade_of` returns for
    it; the two must never disagree (``.get(address)`` on this map and
    ``grade_of(address, analysis)`` are the same question asked two ways).
    A stranger is therefore never a *key* here, not a key mapped to ``None``:
    the return type is ``dict[str, str]``, and the caller's ``.get()`` default
    supplies the ``None``.
    """
    out: dict[str, str] = {}
    grouped: set[str] = set()
    for group in _groups_of(analysis):
        members = group.get("members")
        if not isinstance(members, (list, tuple)):
            continue
        review = group.get("review_members")
        review_map = review if isinstance(review, Mapping) else {}
        conf = group.get("conf")
        band = conf if conf in ("high", "low") else None
        for member in members:
            if not isinstance(member, str):
                continue
            key = member.lower()
            if key in grouped:
                # `_group_of` returns the FIRST group containing an address;
                # a later group listing the same address (duplicate/
                # contradictory membership, unreachable live but not from a
                # hand-edited cache) must not overrule that first answer.
                continue
            grouped.add(key)
            if key in review_map:
                out[key] = "review"
            elif band is not None:
                out[key] = band
            # else: leave the key absent — `grade_of` returns None for a
            # group member whose band is unreadable, and never falls back
            # to `clean_ranks` once a group is found, so neither does this.
    for address in _clean_ranks_of(analysis):
        if isinstance(address, str):
            key = address.lower()
            if key not in grouped:
                out.setdefault(key, "clean")
    return out


def you_linkage(wallet: Any, analysis: Any) -> dict[str, Any]:
    """The four ``you_linked_*``/``you_clean_rank`` keys for one wallet.

    Answers identically from a live :class:`AnalysisResult` and from the
    persisted slot payload — which is what lets ``set_wallet`` recompute the
    reader's standing from the **already-held** last-good instead of forcing a
    fresh B+C sweep (the sweep is about the population, not about one wallet).
    Reasons pass :func:`pattern_language` again on the way out: the payload may
    have been persisted by an older build or edited by hand.

    ``you_linked_state`` gains a third value, ``"review"``, for a wallet T4
    filed under a group's ``review_members``: thin evidence, shown rather than
    removed.  Its reasons are the wallet's OWN families — never the group's,
    which describe evidence a review wallet does not carry — and
    ``you_linked_group_size`` stays the group's own size either way.
    """
    out: dict[str, Any] = {
        "you_linked_state": None,
        "you_linked_reasons": None,
        "you_linked_group_size": None,
        "you_clean_rank": None,
    }
    if not isinstance(wallet, str) or not wallet or analysis is None:
        return out
    group = _group_of(wallet, analysis)
    if group is not None:
        size = group.get("size")
        members = group.get("members")
        group_size = (
            size
            if isinstance(size, int) and not isinstance(size, bool)
            else (len(members) if isinstance(members, (list, tuple)) else None)
        )
        review = group.get("review_members")
        # Same malformed-input guard as `grade_of`: a `review_members` that
        # is not even a mapping must not raise, and falls through to the
        # ordinary "linked" branch below rather than losing the row.
        if isinstance(review, Mapping) and wallet.lower() in review:
            families = review.get(wallet.lower())
            # THE CARRY-FORWARD: T4's `FILTER_FAMILIES` allowlist guards the
            # WRITE site only (`build_analysis_from_published`).  This reads
            # the PERSISTED payload — a hand-edited cache file is
            # third-party input too (see the module docstring) — so a
            # forbidden word smuggled into a family list must be dropped
            # here, on the way out, not merely softened by
            # `pattern_language` into one generic phrase per bogus entry.
            allowed = (
                [f for f in families if isinstance(f, str) and f in FILTER_FAMILIES]
                if isinstance(families, list)
                else []
            )
            # A review wallet's reasons are its OWN families, not the
            # group's: the group's reasons describe evidence this wallet
            # does not carry (that is what "periphery" means).
            # `pattern_language(None, family)` always takes the fallback
            # branch, which resolves to the family's own phrase.
            out["you_linked_state"] = "review"
            out["you_linked_reasons"] = [
                pattern_language(None, family) for family in allowed
            ]
            out["you_linked_group_size"] = group_size  # unchanged: the group's own size
            return out
        reasons = group.get("reasons")
        out["you_linked_state"] = "linked"
        out["you_linked_reasons"] = [
            pattern_language(text, None) for text in (reasons or ())
        ]
        out["you_linked_group_size"] = group_size
        return out
    rank = _clean_ranks_of(analysis).get(wallet.lower())
    if isinstance(rank, int) and not isinstance(rank, bool):
        out["you_linked_state"] = "clean"
        out["you_linked_reasons"] = []
        out["you_clean_rank"] = rank
    return out


def analysis_keys(result: AnalysisResult, *, wallet: str | None = None) -> dict:
    """Exactly :data:`CURATOR_ANALYSIS_KEYS`, filled from one result.

    ``analysis_as_of_hhmm`` stays ``None`` here on purpose: the adapter is
    pure and holds no clock, so the freshness marker is stamped by the manager
    from the cache slot's own timestamp — the only place that knows when the
    sweep was spawned.
    """
    who = wallet if wallet is not None else result.wallet
    out: dict[str, Any] = dict.fromkeys(CURATOR_ANALYSIS_KEYS)
    out["operator_rows"] = [dict(row) for row in result.operator_rows]
    out["segment_rows"] = [dict(row) for row in result.segment_rows]
    out["clean_list_rows"] = [dict(row) for row in result.clean_list_rows]
    out["operators_count"] = result.operators_count
    out["clean_points"] = result.clean_points
    out["clean_contributors"] = result.clean_contributors
    out["points_total"] = result.points_total
    if who:
        out.update(you_linkage(who, result))
    return out


def merge_leaderboard_grade(leaderboard_rows: Any, analysis: Any) -> None:
    """Fill ``link_conf`` on the leaderboard rows, in place — the ENS-merge shape.

    ``build_signals`` emits rows **without** the key (R9: ``curator_signals``
    is frozen and gets no placeholder), so every row is seeded here — ``None``
    when no analysis has run, which renders ``?`` rather than the empty cell
    that means *clean*.  ``flagged`` (Tier A's bool) is never touched.

    Builds :func:`bands_by_address` ONCE and indexes it per row, rather than
    calling :func:`grade_of` per row (O(address × groups) each) — the
    difference between this finishing and not on a several-thousand-row
    leaderboard.
    """
    if not isinstance(leaderboard_rows, list):
        return
    bands = bands_by_address(analysis)
    for row in leaderboard_rows:
        if not isinstance(row, dict):
            continue
        address = row.get("address")
        row["link_conf"] = bands.get(address.lower()) if isinstance(address, str) else None


# ---------------------------------------------------------------------------
# The persisted slot payload
# ---------------------------------------------------------------------------


def slot_payload(
    result: AnalysisResult,
    *,
    published: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The JSON-safe shape ``SLOT_CLUSTERS`` persists.  Revisable rows only.

    No boolean verdict enters the file: the groups carry membership, families
    and a *band word*, all of which the next sweep may revise.

    ``published`` is the analysis's provenance -- ``{version_id, content_hash,
    detector_version, rule_set, rules_sha256, snapshot_block, status_counts,
    fetched_at, archived_version}`` -- and it is the **manager**'s to
    assemble, never this function's: nothing here computes it, stamps a
    clock into it, or reaches into it.  It is copied in whole and left out of
    the payload entirely when absent, so an older reader (or a round trip
    taken before the first successful fetch) sees no key at all rather than a
    ``null``.

    A payload written before T11 removed the detached tier-B/C sweep still
    carries an ``enrichment`` key instead of (or beside) this one -- this
    function no longer writes that key, but a reader must still load one
    that has it: ignored, not rejected (this repo already paid for the
    opposite defect once, for persisted series -- see
    ``data/series_points.coerce_points``).
    """
    payload: dict[str, Any] = {
        "operator_rows": [dict(row) for row in result.operator_rows],
        "segment_rows": [dict(row) for row in result.segment_rows],
        "clean_list_rows": [dict(row) for row in result.clean_list_rows],
        "operators_count": result.operators_count,
        "clean_points": result.clean_points,
        "clean_contributors": result.clean_contributors,
        "points_total": result.points_total,
        "flagged_points_share_pct": result.flagged_points_share_pct,
        "groups": [dict(group) for group in result.groups],
        "clean_ranks": dict(result.clean_ranks),
    }
    if published is not None:
        payload["published"] = dict(published)
    return payload


__all__ = [
    "AnalysisResult",
    "CLEAN_LIST_LIMIT",
    "FORBIDDEN_WORDS",
    "HIGH_MIN_FAMILIES",
    "analysis_keys",
    "build_analysis",
    "build_preset",
    "grade_of",
    "merge_leaderboard_grade",
    "pattern_language",
    "slot_payload",
    "you_linkage",
]

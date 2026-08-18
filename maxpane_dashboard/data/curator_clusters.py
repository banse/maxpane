"""The sybilkit adapter for THE LIST — the only maxpane import of ``sybilkit``.

One seam, three jobs:

* **Pure analysis** (:func:`build_analysis`): the cache's decoded
  ``DepositEvent`` history — plus whatever tier-B/C enrichment the detached
  sweep has accumulated — in, an :class:`AnalysisResult` out, already shaped
  into the flat-dict rows ``CURATOR_ROW_KEYS`` freezes.  No I/O, no clock: two
  calls over one input return equal results.
* **The translation boundary** (:func:`pattern_language`): the library is a
  general sybil-analysis toolkit and may use its own vocabulary in its own
  docstrings; nothing it says reaches a rendered string unfiltered.  Every
  reason, label and detail passes this boundary — including strings read back
  from a **persisted** payload, because a hand-edited cache file is third-party
  input too.
* **The bounded enrichment fetch** (:func:`fetch_enrichment`, WP3.3): drives
  ``sybilkit.sources`` for tx fingerprints and first funders, candidates-only
  and budgeted, resumable across sweeps via the cursor the slot payload
  carries.  It never opens a socket of its own accord: with neither a
  ``client`` nor a ``transport`` it returns the carried state untouched, which
  is what keeps every manager test socket-free by construction.

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

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from sybilkit import Dataset, DetectResult, detect
from sybilkit.curator import CleanList, CuratorPreset, Segments
from sybilkit.curator import clean_list as _clean_list
from sybilkit.curator import segments as _segments

from maxpane_dashboard.data.curator_models import CURATOR_ANALYSIS_KEYS

#: Wei per ETH — the module's ONLY division site (see the module docstring).
_ETH = 10**18

#: Words that may never reach a rendered string.  The chain cannot prove
#: intent, so the adapter describes shapes and lets the reader judge — the same
#: rule the widgets and ``curator_signals`` already enforce on their surfaces.
FORBIDDEN_WORDS: tuple[str, ...] = (
    "sybil",
    "cheat",
    "fraud",
    "attack",
    "abuse",
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
CLEAN_LIST_LIMIT = 20


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
    """Everything the manager needs to fill the twelve analysis keys.

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
    both).  *txs*/*funding* are the detached sweep's accumulated enrichment;
    tier A alone is a legal run whose losses are honest (the ≥2-family gate
    simply finds less).

    *config* is a ready :class:`CuratorPreset`; without one, both live reads
    are **required** and a missing one raises (see :func:`build_preset`).
    ``min_deposit_wei`` is not in the WP3 brief's sketched signature — ruling
    R13 landed after it was written, and the preset refuses to exist without
    the minimum, so the honest signature carries it.
    """
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

    clean_list_rows = [
        {
            "clean_rank": entry.clean_rank,
            "address": entry.address,
            "points": entry.points,
            "credit_eth": entry.credit_wei / _ETH,
            # The manager's ENS merge fills this, exactly like the leaderboard.
            "name": None,
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


def _group_of(address: str, analysis: Any) -> Mapping | None:
    key = address.lower()
    for group in _groups_of(analysis):
        members = group.get("members")
        if isinstance(members, (list, tuple)) and key in members:
            return group
    return None


def grade_of(address: Any, analysis: Any) -> str | None:
    """``"high"`` · ``"low"`` · ``"clean"`` · ``None`` for one address.

    ``None`` covers both "no analysis has run" and "this wallet was not in the
    analyzed population" — either way the honest rendering is ``?``, never the
    empty cell that means *clean*.
    """
    if not isinstance(address, str) or analysis is None:
        return None
    group = _group_of(address, analysis)
    if group is not None:
        conf = group.get("conf")
        return conf if conf in ("high", "low") else "low"
    if address.lower() in _clean_ranks_of(analysis):
        return "clean"
    return None


def you_linkage(wallet: Any, analysis: Any) -> dict[str, Any]:
    """The four ``you_linked_*``/``you_clean_rank`` keys for one wallet.

    Answers identically from a live :class:`AnalysisResult` and from the
    persisted slot payload — which is what lets ``set_wallet`` recompute the
    reader's standing from the **already-held** last-good instead of forcing a
    fresh B+C sweep (the sweep is about the population, not about one wallet).
    Reasons pass :func:`pattern_language` again on the way out: the payload may
    have been persisted by an older build or edited by hand.
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
        reasons = group.get("reasons")
        out["you_linked_state"] = "linked"
        out["you_linked_reasons"] = [
            pattern_language(text, None) for text in (reasons or ())
        ]
        out["you_linked_group_size"] = (
            size
            if isinstance(size, int) and not isinstance(size, bool)
            else (len(members) if isinstance(members, (list, tuple)) else None)
        )
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
    """
    if not isinstance(leaderboard_rows, list):
        return
    for row in leaderboard_rows:
        if not isinstance(row, dict):
            continue
        row["link_conf"] = grade_of(row.get("address"), analysis)


# ---------------------------------------------------------------------------
# The persisted slot payload
# ---------------------------------------------------------------------------


def slot_payload(
    result: AnalysisResult, *, enrichment: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    """The JSON-safe shape ``SLOT_CLUSTERS`` persists.  Revisable rows only.

    No boolean verdict enters the file: the groups carry membership, families
    and a *band word*, all of which the next sweep may revise.  The
    ``enrichment`` cursor (accumulated fingerprints, resolved funders, the
    pending set and the page bound) rides in the same payload so coverage
    extends incrementally across sweeps — and across restarts.
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
    if enrichment is not None:
        payload["enrichment"] = dict(enrichment)
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

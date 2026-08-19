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

try:
    from sybilkit import Dataset, DetectResult, detect
    from sybilkit.curator import CleanList, CuratorPreset, Segments
    from sybilkit.curator import clean_list as _clean_list
    from sybilkit.curator import segments as _segments
    from sybilkit.model import Funding, Tx
    from sybilkit.signals import first_rows, tier_a_components
    from sybilkit.sources import blockscout as _blockscout
    from sybilkit.sources import txs as _tx_sources
    from sybilkit.sources import DEFAULT_CONFIG as _SOURCE_DEFAULTS
    from sybilkit.sources.blockscout import PENDING_PAGES
except ImportError:  # pragma: no cover — exercised through the flag in tests
    #: ``sybilkit`` is not on PyPI yet, so until maxpane's own dependency list
    #: can name it (WP6/packaging: the pyproject gains ``sybilkit`` at the
    #: first release AFTER the library publishes), the import is guarded and
    #: this flag is the compatibility story: the manager treats absence as
    #: the analysis's cannot-run state (spaced retry, no banner), while the
    #: merge, the R9 ``link_conf`` seeding and a HELD last-good keep working —
    #: they read persisted payloads, never the library.
    SYBILKIT_AVAILABLE = False
else:
    SYBILKIT_AVAILABLE = True

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
CLEAN_LIST_LIMIT = 100


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
        # An unknown band in a persisted group is bad data, and a confidence
        # word derived from bad data is a claim: it renders `?` (None) — the
        # membership FACT (linked, size, reasons) is `you_linkage`'s and is
        # untouched by the band being unreadable.
        return conf if conf in ("high", "low") else None
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
    pending set, the page bound and the per-address page cursors) rides in
    the same payload so coverage extends incrementally across sweeps — and
    across restarts.  Everything new goes **inside** that dict, which is why
    this payload's own key set has not changed since it was frozen.
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


# ---------------------------------------------------------------------------
# The bounded, resumable enrichment fetch (the detached sweep's network half)
# ---------------------------------------------------------------------------

#: First-deposit fingerprints fetched per sweep: ten 40-call batches.  The gas
#: family needs >= 90 % coverage of a component before it may corroborate, so
#: a big component reaches judgeability over several sweeps rather than in one
#: unbounded burst against a keyless pool.
TX_BUDGET = 400

#: Funder lookups per sweep: ~200 addresses at Blockscout's measured ~3 req/s
#: is ~70 s of paced work, comfortably inside the analysis tier's 1800 s TTL.
#: R3: candidates only, never the 15.5k population (~90 min).
FUNDING_BUDGET = 200

#: Non-candidate contributors resolved alongside the candidates, in chain
#: order — a small fixed control margin so the funding evidence is measured
#: against a baseline rather than only against suspects.
CONTROL_MARGIN = 24

#: The funding page bound's ceiling.  The bound starts at the sources default
#: (20 pages = 1 000 transactions) and doubles only when a sweep reports
#: ``"pages"`` pendings — the one truncation raising it can fix.  80 pages is
#: 4 000 transactions, far beyond any 1–5-tx farm wallet; a history longer
#: than that stays honestly pending rather than eating the whole budget.
MAX_FUNDING_PAGES = 80


def _tx_dict(tx: Any) -> dict[str, Any]:
    if isinstance(tx, Tx):
        return {
            "tx_hash": tx.tx_hash,
            "nonce": tx.nonce,
            "max_priority_fee_wei": tx.max_priority_fee_wei,
            "max_fee_wei": tx.max_fee_wei,
            "gas_limit": tx.gas_limit,
            "tx_type": tx.tx_type,
        }
    return dict(tx)


def _funding_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Funding):
        return {"address": row.address, "funder": row.funder, "hops": row.hops}
    return dict(row)


def _persisted_map(value: Any) -> Mapping:
    """One sub-map of a carried sweep state, or ``{}`` if it is not a map.

    The four maps :func:`fetch_enrichment` carries forward arrive out of
    ``~/.maxpane/curator_cache.json``, and this module treats a hand-edited
    cache file as third-party input like any other.  ``(x or {}).items()``
    does not: a key edited into a JSON list is a list, a list has no
    ``.items()``, and the ``AttributeError`` aborts the whole read — every
    map, not just the torn one — inside the *detached* sweep, where it
    surfaces as an analysis tier that fails and backs off forever, because a
    backoff cannot repair a file.  ``{}`` is the honest reading of "these
    bytes are not a map": that map is re-derived by the next sweep, the
    other three survive, and the panels keep rendering.

    Deliberately not ``or {}``-shaped: an *empty* map and an unreadable one
    both yield ``{}`` here because both mean the same thing to the caller —
    nothing accumulated to carry — and neither is a measurement.
    """
    return value if isinstance(value, Mapping) else {}


def _persisted_addresses(value: Any) -> tuple[str, ...]:
    """One carried address list, or ``()`` if it is not a list.

    The sequence half of :func:`_persisted_map`, and it needs the *type* check
    rather than a plain iteration for a second reason: ``for addr in value``
    over a bare string yields one single-character "address" per character,
    and those would be silently accepted as pendings — which **head the
    funding budget** — so a one-character edit would crowd real wallets out
    of every sweep and nothing would say so.  A crash at least announces
    itself; this does not.
    """
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(addr for addr in value if isinstance(addr, str))


def _funding_object(address: str, row: Any) -> Funding:
    if isinstance(row, Funding):
        return row
    funder = row.get("funder") if isinstance(row, Mapping) else None
    hops = row.get("hops") if isinstance(row, Mapping) else None
    return Funding(
        address=address,
        funder=funder if isinstance(funder, str) else None,
        hops=hops if isinstance(hops, int) and not isinstance(hops, bool) else None,
    )


@dataclass(slots=True)
class EnrichmentSweep:
    """One bounded pass's accumulated enrichment, plus its cursor and health.

    ``txs``/``funding`` are the **accumulated** maps (prior state carried
    forward, this pass's answers merged in), already serialized to the plain
    dicts the slot payload persists.  ``fetched`` is False when no session was
    available and nothing was attempted — which is a different fact from
    ``tx_ok``/``funding_ok`` being ``False`` (attempted and the source did not
    answer) or ``None`` (nothing to ask, or skipped).

    ``funding_cursors`` is ``sybilkit``'s per-address
    :attr:`~sybilkit.sources.blockscout.FundingSweep.page_cursors`, carried
    through so a **page-bounded** address resumes where it stopped instead of
    re-walking its first pages every sweep forever.  ``pending`` alone said
    "come back to this one" without saying where, and pendings head the
    budget, so one long history crowded out addresses nobody had looked at
    yet.  It is defaulted and last, so a persisted payload written before it
    existed still constructs — that consumer simply restarts each walk at
    page 1, which is what it did anyway.
    """

    txs: dict[str, dict]
    funding: dict[str, dict]
    funding_pending: tuple[str, ...]
    funding_reasons: dict[str, str]
    page_bound: int
    fetched: bool
    tx_ok: bool | None
    funding_ok: bool | None
    funding_cursors: dict[str, dict] = field(default_factory=dict)

    def state(self) -> dict[str, Any]:
        """The cursor the slot payload persists and the next sweep resumes.

        ``"cursors"`` rides **inside** this dict, which is itself the
        ``enrichment`` entry of :func:`slot_payload` — so ``SLOT_CLUSTERS``'s
        own shape does not change and ``curator_cache`` needs no version bump.
        """
        return {
            "txs": dict(self.txs),
            "funding": dict(self.funding),
            "pending": list(self.funding_pending),
            "reasons": dict(self.funding_reasons),
            "page_bound": self.page_bound,
            "cursors": {
                addr: dict(entry) for addr, entry in self.funding_cursors.items()
            },
        }


def candidate_targets(
    events: Iterable[Any],
    first_deposits: Iterable[Any],
    preset: CuratorPreset,
    *,
    margin: int = CONTROL_MARGIN,
) -> tuple[list[str], list[str]]:
    """Who the enrichment is about: ``(funding_addresses, first_tx_hashes)``.

    R3 — candidates only, never the population: the members of every tier-A
    component of at least ``min_size``, in chain order, plus a deterministic
    control margin of the first *margin* non-candidate contributors.  The tx
    hashes are the candidates' **first-deposit** transactions, which is what
    the gas family and the freshness discount actually read.
    """
    _require_sybilkit()
    ds = Dataset.from_events(events, first_deposits)
    cfg = preset.detect_config()
    components = [
        comp for comp in tier_a_components(ds, cfg) if len(comp) >= cfg.min_size
    ]
    firsts = first_rows(ds)

    def chain_order(addr: str) -> tuple[int, int]:
        dep = firsts.get(addr)
        return (dep.block_number, dep.log_index) if dep is not None else (2**63, 0)

    members = sorted({m for comp in components for m in comp}, key=chain_order)
    member_set = set(members)
    controls = sorted(
        (a for a in firsts if a not in member_set), key=chain_order
    )[: max(0, margin)]
    tx_hashes = [firsts[m].tx_hash for m in members if m in firsts]
    return members + controls, tx_hashes


async def fetch_enrichment(
    *,
    tx_wanted: Iterable[str],
    funding_wanted: Iterable[str],
    state: Mapping[str, Any] | None = None,
    client: Any = None,
    transport: Any = None,
    sleep: Any = None,
    tx_budget: int = TX_BUDGET,
    funding_budget: int = FUNDING_BUDGET,
) -> EnrichmentSweep:
    """Extend the accumulated tier-B/C coverage by one bounded pass.

    *state* is the previous :meth:`EnrichmentSweep.state` (or ``None`` on the
    first sweep).  Known fingerprints and resolved funders are **never**
    re-read; the funding cursor's pendings go first, so a deferred address is
    picked up before a new one.  A ``"pages"`` pending raises the page bound
    for the next pass (doubled, capped at :data:`MAX_FUNDING_PAGES`); an
    ``"unreadable"`` one is retried as-is — spending more pages on a failing
    endpoint is the one action that cannot help.

    ``state["cursors"]`` is the **per-address** half of that resume, handed
    to ``fetch_funding(cursors=…)``: a page-bounded address continues where
    it stopped rather than re-reading its first pages every sweep.  It is
    read with ``.get``, exactly like the four keys above it, so a payload
    persisted before the cursor existed loads and resumes from page 1.

    **No session, no fetch.**  With neither *client* nor *transport* the
    carried state comes back untouched (``fetched=False``): production hands
    the manager's own HTTP session in, tests hand a MockTransport in, and a
    bare double hands nothing in — which is what keeps every FakeClient-driven
    test socket-free structurally.  ``fetch_funding`` is **never** called with
    a zero budget (it would still open a session; WP2's warning): the skip
    switch is not calling it.
    """
    _require_sybilkit()
    prior = state if isinstance(state, Mapping) else {}
    known_txs: dict[str, dict] = {
        str(key).lower(): dict(value)
        for key, value in _persisted_map(prior.get("txs")).items()
        if isinstance(value, Mapping)
    }
    known_funding: dict[str, dict] = {
        str(key).lower(): dict(value)
        for key, value in _persisted_map(prior.get("funding")).items()
        if isinstance(value, Mapping)
    }
    pending: tuple[str, ...] = _persisted_addresses(prior.get("pending"))
    reasons: dict[str, str] = {
        str(key): str(value)
        for key, value in _persisted_map(prior.get("reasons")).items()
    }
    # The per-address page cursor, read with the SAME tolerant shape as the
    # four above: a payload written before it existed has no such key, and
    # `.get` is the whole compatibility story — that cache file must load and
    # simply resume each walk from page 1.  The library reads each *entry*
    # tolerantly too, so a hand-edited one costs a restart, not a crash — and
    # the `isinstance(value, Mapping)` below is what keeps that true here:
    # `dict(entry)` raises on an entry hand-edited into a JSON list.
    cursors: dict[str, dict] = {
        str(key).lower(): dict(value)
        for key, value in _persisted_map(prior.get("cursors")).items()
        if isinstance(value, Mapping)
    }

    bound = prior.get("page_bound")
    if not isinstance(bound, int) or isinstance(bound, bool) or bound < 1:
        bound = _SOURCE_DEFAULTS.blockscout_max_pages
    if any(reason == PENDING_PAGES for reason in reasons.values()):
        bound = min(bound * 2, MAX_FUNDING_PAGES)

    fetched = client is not None or transport is not None
    tx_ok: bool | None = None
    funding_ok: bool | None = None
    if not fetched:
        return EnrichmentSweep(
            txs=known_txs,
            funding=known_funding,
            funding_pending=pending,
            funding_reasons=reasons,
            page_bound=bound,
            fetched=False,
            tx_ok=None,
            funding_ok=None,
            funding_cursors=cursors,
        )

    wanted_hashes: list[str] = []
    seen: set[str] = set()
    for raw in tx_wanted:
        if not isinstance(raw, str):
            continue
        key = raw.lower()
        if key in seen or key in known_txs:
            continue
        seen.add(key)
        wanted_hashes.append(key)
    wanted_hashes = wanted_hashes[: max(0, tx_budget)]
    if wanted_hashes:
        sweep = await _tx_sources.fetch_tx_fingerprints(
            wanted_hashes, client=client, transport=transport, sleep=sleep
        )
        if sweep is None:                      # is None == outage; keep last-good
            tx_ok = False
        else:
            tx_ok = True
            for tx_hash, tx in sweep.fingerprints.items():
                known_txs[tx_hash] = _tx_dict(tx)
            # `sweep.pending` needs no bookkeeping: an unresolved hash is
            # simply still absent from `known_txs`, so it is re-wanted next
            # sweep by construction.

    todo: list[str] = []
    seen = set()
    for raw in (*pending, *funding_wanted):
        if not isinstance(raw, str):
            continue
        key = raw.lower()
        if key in seen or key in known_funding:
            continue
        seen.add(key)
        todo.append(key)
    if todo and funding_budget and funding_budget > 0:
        fsweep = await _blockscout.fetch_funding(
            todo,
            known={
                addr: _funding_object(addr, row)
                for addr, row in known_funding.items()
            },
            budget=funding_budget,
            max_pages=bound,
            cursors=cursors,
            client=client,
            transport=transport,
            sleep=sleep,
        )
        if fsweep is None:                     # is None == outage; keep last-good
            funding_ok = False
        else:
            funding_ok = True
            known_funding = {
                addr: _funding_dict(row) for addr, row in fsweep.funding.items()
            }
            pending = fsweep.pending
            reasons = dict(fsweep.pending_reasons)
            # Replaced, not merged: the sweep returns the cursors of exactly
            # the addresses that still need one, so an address it finished
            # drops its resume point rather than carrying a dead walk
            # position in the cache file forever.
            cursors = {
                addr: dict(entry)
                for addr, entry in fsweep.page_cursors.items()
            }

    return EnrichmentSweep(
        txs=known_txs,
        funding=known_funding,
        funding_pending=pending,
        funding_reasons=reasons,
        page_bound=bound,
        fetched=True,
        tx_ok=tx_ok,
        funding_ok=funding_ok,
        funding_cursors=cursors,
    )


__all__ = [
    "AnalysisResult",
    "CLEAN_LIST_LIMIT",
    "CONTROL_MARGIN",
    "EnrichmentSweep",
    "FORBIDDEN_WORDS",
    "FUNDING_BUDGET",
    "HIGH_MIN_FAMILIES",
    "MAX_FUNDING_PAGES",
    "TX_BUDGET",
    "analysis_keys",
    "build_analysis",
    "build_preset",
    "candidate_targets",
    "fetch_enrichment",
    "grade_of",
    "merge_leaderboard_grade",
    "pattern_language",
    "slot_payload",
    "you_linkage",
]

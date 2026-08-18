"""Fact pins for the sybil research datasets, and for the fixtures cut from them.

Every number a later work package quotes — in a widget, in a doc, in a
benchmark floor — is asserted here, once, against the file it came from.  A
re-run of the research that moves one of them fails in this file, which owns the
fact, instead of drifting silently through six work packages.

The datasets live in ``docs/curator_sybil_data/`` and are read, never retyped.
The fixtures live in ``tests/fixtures/curator/sybil/`` and are read through
``tests/curator_sybil_fixtures.py``.  **Nothing here touches the network**, and
nothing here writes: the gzipped population archives are decompressed in memory
and no uncompressed copy is ever put on disk.

The load-bearing one is
:func:`test_the_points_curve_reproduces_the_whole_population_wei_exactly`.  It
recomputes 15 576 contributors' scores from 22 319 raw deposit rows with the
contract's own floored integer square root and matches ``population.json``'s
totals **to the digit** — which is what makes every derived number in the
worst-case fixtures provable rather than merely plausible, and what lets the
one-shot script that wrote them stay uncommitted.
"""

from __future__ import annotations

import gzip
import inspect
import json
import math
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from maxpane_dashboard.data.curator_models import CURATOR_ROW_KEYS
from tests.curator_fixtures import CURATOR_FIXTURES
from tests.curator_sybil_fixtures import (
    PROVENANCE_FIELDS,
    SYBIL,
    SYNTHETIC_MARKER,
    WORST_CASE,
    labeled_subset,
    load,
    rendered_strings,
    row_payloads,
    slices,
    worst_case_envelope,
    worst_case_rows,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
DATA = _REPO_ROOT / "docs" / "curator_sybil_data"

#: The sybilkit distribution's mirror of the same benchmark subset (PRD §8).
SYBILKIT_FIXTURES = _REPO_ROOT / "sybilkit" / "tests" / "fixtures"


@lru_cache(maxsize=None)
def research(name: str):
    """One raw research dataset.  ``.gz`` is decompressed **in memory**.

    Cached because ``deposits.json.gz`` is 22 319 rows and half the tests in
    this file want it; uncached, the suite would decompress it eight times.
    """
    path = DATA / name
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cluster membership: the join that makes the funding signal checkable
# ---------------------------------------------------------------------------


def _full_members(cluster_id: str, size: int) -> set[str]:
    """Every member of one audited operator, lowercase.

    ``suspects.json`` carries only **ten sampled** members per cluster, and the
    funding signal is "the funder is a member of the same cluster" — of the
    *whole* cluster, 1 995 wallets wide, not of the ten we happened to sample.
    Checking against the sample instead of the population scores the strongest
    discriminator in the study at 0/10 rather than 10/10, which is exactly the
    mistake this helper exists to make impossible.

    Matched on shape **and** size, so the lookup is unambiguous: the
    same-amount file holds several clusters that share an amount and an hour.
    """
    if cluster_id.startswith("amt_"):
        _, amount, hour = cluster_id.split("_")
        hits = [
            c
            for c in research("same_amount_clusters.json")["v1_clusters"]
            if c["amount_eth"] == float(amount)
            and c["hours"][0] == int(hour[1:])
            and c["size"] == size
        ]
    else:
        start = int(cluster_id.split("_")[1])
        hits = [
            run
            for grid in research("index_runs.json").values()
            for run in grid["biggest"]
            if run["index_range"][0] == start and run["size"] == size
        ]
    assert len(hits) == 1, f"{cluster_id} matched {len(hits)} clusters"
    return {m.lower() for m in hits[0]["members"]}


@lru_cache(maxsize=None)
def _membership() -> dict[str, frozenset[str]]:
    return {
        e["cluster"]: frozenset(_full_members(e["cluster"], e["wallets"]))
        for e in research("cluster_economics.json")
    }


def _by_shape(econ: list[dict], amount: str) -> dict:
    """The audited operator whose id names *amount*, e.g. ``"0.45"``."""
    hits = [e for e in econ if e["cluster"].startswith(f"amt_{amount}_")]
    assert len(hits) == 1, f"{amount} matched {[h['cluster'] for h in hits]}"
    return hits[0]


def _audited_count(econ: list[dict]) -> int:
    return len({e["cluster"] for e in econ})


# ---------------------------------------------------------------------------
# The research numbers every later WP quotes
# ---------------------------------------------------------------------------


def test_the_operator_economics_are_the_research_numbers() -> None:
    """The widest operator, and the row WP4/WP5 size their columns against."""
    econ = research("cluster_economics.json")
    # The 0.45 ETH operator: 1,995 wallets, 6.81% of points, 44.6x sqrt subsidy.
    top = _by_shape(econ, "0.45")
    assert top["wallets"] == 1995
    assert round(top["share_pct"], 2) == 6.81
    assert round(top["sybil_multiplier"], 1) == 44.6
    # 897.75 ETH in, and the subsidy is the whole argument: one wallet sending
    # the same money would have scored 40 573 points, the 1 995 scored
    # 1 811 322.  The curve pays sqrt(k) for splitting a bankroll k ways.
    assert top["eth_in"] == 897.75
    assert top["points"] == 1_811_322
    assert top["points_if_one_wallet"] == 40_573
    assert round(top["points"] / top["points_if_one_wallet"], 1) == 44.6


def test_the_conservative_floor_is_16_operators() -> None:
    econ = research("cluster_economics.json")
    assert _audited_count(econ) == 16          # 6,303 wallets, 43.3% of points
    assert sum(e["wallets"] for e in econ) == 6303
    # 43.25, which is what the research narrative's "43.3%" is a rounding of.
    # Pinned at the measured precision: the wei-exact fold in
    # ``test_the_linked_and_clean_halves_of_the_list_add_up`` lands on the same
    # 43.25 from raw logs, so the two agree at two decimals and neither has to
    # inherit the other's rounding.
    assert round(sum(e["share_pct"] for e in econ), 2) == 43.25
    # And every one of them clears the library's own floors, so the benchmark
    # subset is not asking the detector for anything it was not designed to do.
    assert min(e["wallets"] for e in econ) >= 5      # DetectConfig.min_size
    assert len({e["cluster"] for e in econ}) == len(econ)


def test_the_funding_signal_is_10_of_10_on_farms_and_0_of_47_on_controls() -> None:
    """The single strongest discriminator measured on this population.

    A *shared* funder (a hub) is weak here — these operators use serial peel
    chains, not hubs, and distance-2 found almost nothing.  What is near-perfect
    is *the funder is itself a member of the same behavioural cluster*: the
    funder deposited a block or two earlier and then paid the next wallet.

    The control side is the half that makes it a signal rather than a
    coincidence: 35 of the 47 resolvable controls **were** funded by a
    contributor — people funding from their own main wallet, which is normal
    and explicitly not the pattern — and **none** of those funders belongs to
    any audited cluster.
    """
    f = research("funding.json")
    assert _farm_funder_in_cluster(f) == (10, 10)
    assert _control_funder_in_cluster(f) == (0, 47)


def _stage1(f: dict) -> dict[str, dict]:
    return {a.lower(): v for a, v in f["stage1"].items()}


def _farm_funder_in_cluster(f: dict, cluster_id: str = "amt_0.45_h3") -> tuple[int, int]:
    """``(funders inside the cluster, funders resolved)`` for one operator."""
    members = _membership()[cluster_id]
    hit = total = 0
    for row in _stage1(f).values():
        if row.get("group") != cluster_id or not row.get("funder"):
            continue
        total += 1
        hit += row["funder"].lower() in members
    return hit, total


def _control_funder_in_cluster(f: dict) -> tuple[int, int]:
    """``(controls funded from inside any audited cluster, controls resolved)``."""
    linked: set[str] = set().union(*_membership().values())
    hit = total = 0
    for row in _stage1(f).values():
        if row.get("group") != "CONTROL" or not row.get("funder"):
            continue
        total += 1
        hit += row["funder"].lower() in linked
    return hit, total


def test_the_funding_signal_holds_on_every_fully_resolved_operator() -> None:
    """Not just the 0.45 one: **eleven** of the sixteen sampled operators had
    all ten funders resolve, and every one of the eleven is 10/10.

    The five that are not fully resolved are not counter-examples — they are
    bounded lookups (an aged funder with 50+ transactions is not peeled) — and
    the three that score below their resolved total are all ``0.05`` groups,
    the minimum-deposit crowd the research calls provably mixed.  Stated here
    so WP1 does not read a 2/5 as a failure of the signal.
    """
    f = research("funding.json")
    scores = {
        cid: _farm_funder_in_cluster(f, cid) for cid in _membership()
    }
    fully_resolved = {cid: s for cid, s in scores.items() if s[1] == 10}
    assert len(fully_resolved) == 11
    assert all(s == (10, 10) for s in fully_resolved.values()), fully_resolved
    below = {cid for cid, (hit, tot) in scores.items() if tot and hit < tot}
    assert all(cid.startswith("amt_0.05_") for cid in below), below


def test_the_gas_uniformity_signal_is_the_uniformity_not_the_value() -> None:
    """60 controls show 27 distinct priority fees and 15 gas limits; the 0.45
    and 10.0 operators collapse to **one** of each — and to the *same* one,
    which is what makes them one operator running 2 764 sampled-from wallets
    rather than two.

    Counting distinct **non-None** values matters: 18 of the 220 sampled
    transactions are legacy type-0 and carry no priority fee at all, and
    folding those into a shared ``None`` would invent a uniformity.
    """
    rows = research("tx_fingerprints.json")["fingerprints"]
    assert len(rows) == 220

    def spread(group: str) -> tuple[int, int]:
        sample = [r for r in rows if r["group"] == group]
        fees = {r["prio_fee_wei"] for r in sample if r["prio_fee_wei"] is not None}
        return len(fees), len({r["gas"] for r in sample})

    assert spread("CONTROL") == (27, 15)
    assert spread("amt_0.45_h3") == (1, 1)
    assert spread("amt_10.0_h5") == (1, 1)
    shared = {
        (r["prio_fee_wei"], r["gas"])
        for r in rows
        if r["group"] in ("amt_0.45_h3", "amt_10.0_h5")
    }
    assert shared == {(100_000_000, 91_600)}  # 0.1 gwei, gas limit 91 600


def test_the_sweep_meta_describes_the_population_the_fixtures_are_cut_from() -> None:
    """One sweep, one moment.  Every fixture in this build is a slice of it."""
    meta = research("sweep_meta.json")
    assert meta["n_deposits"] == 22_319
    assert meta["n_first_deposits"] == 15_576
    assert meta["latest_block"] == 25_776_962
    assert meta["is_settled"] is False and meta["n_settled_logs"] == 0
    assert meta["sweep_utc"] == "2026-08-17 19:44:40"
    # The log fold and the contract's own counters agree on the contributor
    # count, which is what makes the sweep complete rather than merely large.
    assert meta["distinct_contributors_in_deposits"] == meta["n_first_deposits"]
    assert meta["max_first_deposit_index"] == meta["n_first_deposits"]


# ---------------------------------------------------------------------------
# The derivation everything else rests on
# ---------------------------------------------------------------------------


@lru_cache(maxsize=None)
def _folded() -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    """``(weight_wei, credit_wei, points)`` per contributor, folded from logs."""
    weight: dict[str, int] = defaultdict(int)
    credit: dict[str, int] = defaultdict(int)
    for d in research("deposits.json.gz"):
        addr = d["contributor"].lower()
        weight[addr] += d["weight_added_wei"]
        credit[addr] += d["credited_delta_wei"]
    points = {a: math.isqrt(w) * 1000 // 10**9 for a, w in weight.items()}
    return dict(weight), dict(credit), points


@lru_cache(maxsize=None)
def _first_hour() -> dict[str, int]:
    """The hour each contributor **joined** in, by lowercase address.

    Off the first deposit in ``(block, log_index)`` order, not off the smallest
    ``hour``: they agree here, but the ordering is the definition and the
    minimum is a coincidence of a game nobody deposited into out of order.
    """
    out: dict[str, int] = {}
    for d in sorted(
        research("deposits.json.gz"), key=lambda d: (d["block"], d["log_index"])
    ):
        out.setdefault(d["contributor"].lower(), d["hour"])
    return out


@lru_cache(maxsize=None)
def _first_bps() -> dict[str, int]:
    """The early multiplier each contributor joined at, in bps."""
    out: dict[str, int] = {}
    for d in sorted(
        research("deposits.json.gz"), key=lambda d: (d["block"], d["log_index"])
    ):
        out.setdefault(d["contributor"].lower(), d["early_bps"])
    return out


def test_the_points_curve_reproduces_the_whole_population_wei_exactly() -> None:
    """``isqrt(weight_wei) * 1000 // 10**9``, over 22 319 rows, to the digit.

    This is the pin that makes every derived number in the worst-case fixtures
    provable.  Four independent totals match ``population.json`` exactly —
    weight, credit, contributor count and points — so the fold, the curve and
    the floor are all right, and a fixture built on them is measured data
    rather than a plausible-looking construction.

    ``//`` and ``isqrt``, never ``/`` and ``math.sqrt``: the multiply comes
    before the divide and the divisor is the int ``10**9``.  A float ``sqrt`` of
    1.36e21 loses the low digits and the totals stop matching within one run.
    """
    weight, credit, points = _folded()
    pop = research("population.json")
    assert len(weight) == pop["n_contributors"] == 15_576
    assert sum(weight.values()) == pop["total_weight_wei"]
    assert sum(credit.values()) == pop["total_credit_wei"]
    assert sum(points.values()) == pop["total_points"] == 26_585_740
    assert max(points.values()) == pop["points"]["max"] == 36_924
    assert min(points.values()) == pop["points"]["min"] == 225


def test_every_audited_operators_points_are_the_fold_not_a_quoted_number() -> None:
    """`cluster_economics.json`'s per-cluster points, re-derived from the logs.

    Sixteen independent equalities.  If the research file and the raw sweep
    ever disagree, the OPERATORS panel is quoting one and the CLEANED LIST is
    computing the other, and the two panels contradict each other on screen.
    """
    _, _, points = _folded()
    total = sum(points.values())
    for e in research("cluster_economics.json"):
        members = _membership()[e["cluster"]]
        assert len(members) == e["wallets"], e["cluster"]
        got = sum(points[a] for a in members)
        assert got == e["points"], e["cluster"]
        assert round(100 * got / total, 2) == round(e["share_pct"], 2), e["cluster"]


def test_the_linked_and_clean_halves_of_the_list_add_up() -> None:
    """6 303 linked wallets hold 11 498 903 points; the other 9 273 hold the
    rest.  ``clean_points`` is a subtraction, not a second fold, and this is
    the arithmetic WP3's adapter has to reproduce."""
    _, _, points = _folded()
    linked: set[str] = set().union(*_membership().values())
    total = sum(points.values())
    flagged = sum(points[a] for a in linked)
    assert len(linked) == 6303
    assert flagged == 11_498_903
    assert total - flagged == 15_086_837
    assert len(points) - len(linked) == 9273
    assert round(100 * flagged / total, 2) == 43.25


# ---------------------------------------------------------------------------
# Fixture hygiene
# ---------------------------------------------------------------------------


def test_the_sybil_fixtures_all_live_in_one_directory() -> None:
    """One directory per work package (the captures rule).  A slice loose in
    ``tests/fixtures/curator/`` is a file with no owner, and it is how one work
    package's payload lands in another's glob."""
    assert SYBIL.parent == CURATOR_FIXTURES
    assert SYBIL.is_dir()
    names = {p.name for p in slices()}
    assert names == {
        "labeled_subset.json",
        "operator_row_worst.json",
        "segment_rows_worst.json",
        "clean_list_rows_worst.json",
        # WP3.7's agreement seam: labeled_subset joined 1:1 into the
        # adapter's input shape (its derivation is pinned in
        # test_curator_clusters.py::test_the_agreement_fixture_is_still_the_labeled_subset).
        "adapter_agrees.json",
    }
    # Only JSON and the manifest live here.
    assert {p.name for p in SYBIL.iterdir() if p.is_file()} == names | {"README.md"}


def test_the_reader_returns_a_sorted_list() -> None:
    """An unsorted ``iterdir()`` makes a failure message depend on the
    filesystem's mood, and makes a diff unreadable when a later WP adds a
    slice."""
    paths = slices()
    assert paths == sorted(paths)
    assert all(p.is_file() for p in paths)


def test_no_sybil_fixture_carries_an_api_key() -> None:
    """The keyless rule, asserted over the bytes rather than over intent."""
    for path in sorted(SYBIL.rglob("*")) + sorted(SYBILKIT_FIXTURES.rglob("*")):
        if not path.is_file() or path.suffix == ".gz":
            continue
        text = path.read_text("utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"


def test_the_synthetic_slices_are_marked_and_the_measured_one_is_not() -> None:
    """The ledger: ``rg "SYNTHETIC —"`` must find every shaped payload.

    The three ``*_worst.json`` files carry the marker because no live analysis
    sweep has ever produced a row in this schema — WP3 has not been written.
    ``labeled_subset.json`` deliberately does not: every byte of it is measured,
    joined across five research files rather than invented.
    """
    for name in WORST_CASE:
        assert load(name)["synthetic"] == SYNTHETIC_MARKER, name
    assert "synthetic" not in labeled_subset()


# ---------------------------------------------------------------------------
# The worst-case rows WP4/WP5 measure against
# ---------------------------------------------------------------------------


#: Which ``CURATOR_ROW_KEYS`` entry each worst-case slice is a payload for.
#: Spelled out rather than derived from the filename: the operator slice is
#: ``operator_row_worst.json`` (singular, because ``worst`` is one row) while
#: its contract key is ``operator_rows``, and a string transform that papered
#: over that would be one rename from silently matching the wrong shape.
WORST_CASE_SHAPES = {
    "operator_row_worst.json": "operator_rows",
    "segment_rows_worst.json": "segment_rows",
    "clean_list_rows_worst.json": "clean_list_rows",
}


def test_every_worst_case_row_matches_its_frozen_row_shape() -> None:
    """The fixtures and ``CURATOR_ROW_KEYS`` are the same contract.

    Exact key sets, not ``<=``: a row missing a column would let a widget be
    written without a cell for it, and a row carrying an extra one would let a
    widget be written *around* a key the manager will never send.

    Checked over :func:`row_payloads` — **every** row-shaped payload in the
    envelope, not just ``rows``.  ``worst`` and ``degraded_row`` live outside
    that list, and ``degraded_row`` is the one row in the whole set written by
    hand rather than generated, so it is the likeliest to have the wrong shape
    and was the least likely to be checked.
    """
    assert set(WORST_CASE_SHAPES) == set(WORST_CASE)
    for name, key in WORST_CASE_SHAPES.items():
        shape = CURATOR_ROW_KEYS[key]
        assert tuple(worst_case_envelope(name)["row_keys"]) == shape, name
        for where, row in row_payloads(name):
            assert set(row) == set(shape), (name, where, sorted(row))


def test_the_envelope_accessor_reaches_the_payloads_rows_does_not() -> None:
    """The guard on the guard.

    ``worst_case_rows()`` was once the only accessor, and the two payloads it
    cannot see are exactly the two that matter most: ``worst`` (the row the
    brief names and WP4 sizes against) and ``degraded_row`` (which carries the
    widest string in the entire fixture set, 56 columns).  Both escaped the
    shape check and the pattern-language scan while they were committed.

    This test fails if a later slice adds a row-shaped payload outside ``rows``
    and nobody teaches the accessor about it.
    """
    assert len(row_payloads("operator_row_worst.json")) == 16 + 1  # rows + worst
    assert len(row_payloads("segment_rows_worst.json")) == 12 + 1  # + degraded_row
    assert len(row_payloads("clean_list_rows_worst.json")) == 21   # rows only

    for name in WORST_CASE:
        envelope = worst_case_envelope(name)
        extra = set(envelope) - set(PROVENANCE_FIELDS) - {"rows"}
        covered = {where for where, _ in row_payloads(name) if not where.startswith("rows[")}
        # `totals` is a dict of scalars about the list, not a row -- it has no
        # CURATOR_ROW_KEYS entry to check against, and `rendered_strings`
        # covers it instead.
        assert extra - covered <= {"totals"}, (name, sorted(extra - covered))


def test_the_worst_case_operator_row_is_the_one_the_research_measured() -> None:
    """The row WP4 and WP5 pin their widths against, checked against the
    dataset rather than against itself: 1 995 wallets, 6.81%, 44.6×, high
    confidence, and a deliberately over-provisioned four-reason list (plan §6
    risk 6, "WP0 should over-provision it")."""
    worst = load("operator_row_worst.json")["worst"]
    top = _by_shape(research("cluster_economics.json"), "0.45")
    assert worst["size"] == top["wallets"] == 1995
    assert worst["points"] == top["points"]
    assert worst["points_share_pct"] == round(top["share_pct"], 2)
    assert worst["sqrt_subsidy_x"] == round(top["sybil_multiplier"], 1)
    assert worst["conf"] == "high"
    assert worst["reasons"] == [
        "identical 0.45Ξ send ×1,995",
        "consecutive join indices · ≤2-block spacing",
        "uniform 0.1 gwei priority fee · one gas limit",
        "shared funder chain",
    ]
    # One reason from each of four of the five families.
    #
    # `worst`'s own longest phrase is 45 characters ("uniform 0.1 gwei priority
    # fee · one gas limit") -- but that is NOT the number a column is sized
    # against.  The envelope's longest is 53, on an index-run operator in
    # `rows`.  Sizing to 45 would be the `dev`/`ops` defect CLAUDE.md records,
    # baked into the freeze: a cell simultaneously padded for one row and
    # cutting another mid-word.  The number WP4 uses is pinned in
    # `test_the_widest_strings_the_analysis_panels_must_fit`, over the whole
    # envelope; these two are about this row only and say so.
    assert len(worst["reasons"]) == 4
    assert max(len(r) for r in worst["reasons"]) == 45
    assert sum(len(r) for r in worst["reasons"]) == 134
    assert max(len(r) for r in worst["reasons"]) < _ENVELOPE_MAXIMA[
        "operator_row_worst.json"
    ]["reason"]


def test_the_worst_row_is_the_row_and_not_a_second_opinion_about_it() -> None:
    """`worst` and its entry in `rows` are the **same object**, by designation.

    They were not, at first: the generated row for the 0.45 operator named the
    same-amount window (254-block span) while `worst` named the consecutive
    index run (≤2-block spacing).  Both are real evidence about that operator --
    the research's biggest run is 180 consecutive indices in 7 blocks, all
    0.45 ETH -- but two different lists for one cluster is precisely how WP4
    sizes against one and WP3 produces the other, with both suites green.

    So `worst` IS the row, `worst_cluster` names which one, and the panel
    payload has one answer per operator.
    """
    payload = worst_case_envelope("operator_row_worst.json")
    assert payload["worst_cluster"] == "amt_0.45_h3"
    assert payload["worst"] in payload["rows"]
    top = _by_shape(research("cluster_economics.json"), "0.45")
    matching = [r for r in payload["rows"] if r["points"] == top["points"]]
    assert matching == [payload["worst"]]


#: The widest string each analysis panel has to fit, measured over the WHOLE
#: envelope — ``rows`` ∪ ``worst`` ∪ ``degraded_row`` ∪ ``totals``.
#:
#: These are the numbers WP4 sizes columns from.  They are pinned here, in the
#: file that owns the fixtures, rather than measured inside a widget: CLAUDE.md
#: records the ``dev``/``ops`` defect twice over — a cell sized to a vocabulary
#: someone remembered is simultaneously padded and cutting a value mid-word,
#: and both suites stay green while it happens.
_ENVELOPE_MAXIMA = {
    "operator_row_worst.json": {
        # "consecutive join indices 14,001–14,100 · 1-block span"
        "reason": 53,
        "reasons_per_row": 4,
        "reasons_joined": 150,
    },
    "segment_rows_worst.json": {
        # "per-hour band · joined in hour 20"
        "label": 33,
        # "share unavailable — the analysis sweep has not published", which
        # lives in `degraded_row` and is the widest string in the whole set.
        "detail": 56,
    },
    "clean_list_rows_worst.json": {
        "name": 12,       # NAME_COLS, exactly `surfsurf.eth`
        "address": 42,    # 0x + 40 hex
    },
}


def test_the_widest_strings_the_analysis_panels_must_fit() -> None:
    """Measured over the envelope, not over ``rows``.

    Every one of these was wrong when it was measured on ``rows`` or on
    ``worst`` alone.  The reason column's true maximum is **53**, not the 45 of
    the row the brief names; the detail column's is **56**, and it is in
    ``degraded_row``, which ``worst_case_rows()`` cannot even see.  A layout
    calibrated to the smaller numbers clips on the payload it was built for.
    """
    ops = [row for _, row in row_payloads("operator_row_worst.json")]
    assert max(len(r) for row in ops for r in row["reasons"]) == 53
    assert max(len(row["reasons"]) for row in ops) == 4
    assert max(sum(len(r) for r in row["reasons"]) for row in ops) == 150

    segs = [row for _, row in row_payloads("segment_rows_worst.json")]
    assert max(len(row["label"]) for row in segs) == 33
    assert max(len(row["detail"]) for row in segs) == 56
    # The widest detail is the degraded row's, i.e. outside `rows`.
    assert max(len(row["detail"]) for row in worst_case_rows(
        "segment_rows_worst.json")) == 44

    clean = [row for _, row in row_payloads("clean_list_rows_worst.json")]
    assert max(len(row["name"] or "") for row in clean) == 12
    assert max(len(row["address"]) for row in clean) == 42

    # Restated against the constant the hand-off block quotes, so the two
    # cannot drift.
    m = _ENVELOPE_MAXIMA
    assert m["operator_row_worst.json"]["reason"] == 53
    assert m["segment_rows_worst.json"]["detail"] == 56
    assert m["clean_list_rows_worst.json"]["name"] == 12


def test_the_operator_panel_holds_every_audited_operator() -> None:
    """Sixteen rows, sorted widest-share first (PRD §5.1), each one's numbers
    equal to the dataset's."""
    rows = worst_case_rows("operator_row_worst.json")
    econ = {e["points"]: e for e in research("cluster_economics.json")}
    # Keyed by points, so two operators scoring identically would silently
    # collapse into one and this test would check fifteen rows against
    # fourteen sources without saying so.
    assert len(econ) == 16
    assert len(rows) == 16
    shares = [r["points_share_pct"] for r in rows]
    assert shares == sorted(shares, reverse=True)
    for row in rows:
        source = econ[row["points"]]
        assert row["size"] == source["wallets"]
        assert row["points_share_pct"] == round(source["share_pct"], 2)
        assert row["sqrt_subsidy_x"] == round(source["sybil_multiplier"], 1)
        assert row["conf"] in ("high", "low")
        assert row["reasons"] and all(isinstance(r, str) for r in row["reasons"])


def test_no_worst_case_row_uses_an_accusatory_word() -> None:
    """PRD §2/§8: pattern-language on every surface, and the fixture is a
    surface — WP4 renders these strings verbatim.  Pinned on the payload as
    well as on the schema, because a reason string is copy in a JSON file and
    nothing else would catch it.

    Scanned over :func:`rendered_strings`, which is every string a widget could
    reach: ``rows``, ``worst``, ``degraded_row`` **and** ``totals``.  Scanning
    ``rows`` alone left ``worst``'s four reason phrases — the ones the layout is
    built around — unchecked.

    The provenance fields are excluded deliberately, not by oversight:
    ``synthetic`` and ``note`` both name ``docs/curator_sybil_data/``, so a scan
    of the raw envelope would fail on the word "sybil" in a directory path that
    never reaches a screen.  The exclusion list is pinned below so it cannot
    quietly grow to cover a field that *is* rendered.
    """
    banned = ("sybil", "cheat", "fraud", "attack", "abuse", "wash", "farm", "bot")
    assert PROVENANCE_FIELDS == ("synthetic", "note", "row_keys", "worst_cluster")
    for name in WORST_CASE:
        strings = rendered_strings(name)
        assert strings, name
        for text in strings:
            lowered = text.lower()
            for word in banned:
                assert word not in lowered, (name, word, text)
    # ...and the exclusion really is load-bearing: the raw envelope DOES carry
    # the word, in the source path, which is why the scan is scoped rather than
    # simply run over `json.dumps(envelope)`.
    assert "sybil" in json.dumps(worst_case_envelope(WORST_CASE[0])).lower()


def test_the_segment_rows_are_the_segments_adam_asked_for() -> None:
    """PRD §5.2: whale **operators** by combined credit rather than by single
    send, the index-1000 early cohort, per-multiplier bands, per-hour bands.

    The single-send row is the point of the whole panel: an 800 ETH+ list is
    **2 wallets and 0.25% of points**, while the operator groups are 6 303
    wallets and 43.25% — sorting by one send finds the wrong whales.

    The aggregate's label is ``linked groups`` (review finding #12 / ruling
    D4).  **The numbers are the same 6 303 and 43.25** — the band was always
    measuring every linked cluster, and renaming rather than filtering is
    what keeps that true.
    """
    rows = worst_case_rows("segment_rows_worst.json")
    by_label = {r["label"]: r for r in rows}
    whales = research("whales_segments.json")

    assert "largest operators" not in by_label
    assert by_label["linked groups"]["contributors"] == 6303
    assert by_label["linked groups"]["points_share_pct"] == 43.25

    single = by_label["single-send whales ≥ 800Ξ"]
    assert single["contributors"] == whales["whales_800plus_credit"]["count"] == 2
    assert single["points_share_pct"] == 0.25

    early = by_label["early cohort · join index 1–1000"]
    assert early["contributors"] == whales["index_1_1000"]["count"] == 1000
    assert early["points_share_pct"] == round(whales["index_1_1000"]["points_share_pct"], 2)

    late = by_label["last grace hours · joined 22–23"]
    assert late["contributors"] == whales["joined_hour_22_23"]["count"] == 742
    assert late["points_share_pct"] == 2.39

    assert len([r for r in rows if r["label"].startswith("joined at ")]) == 4
    assert len([r for r in rows if r["label"].startswith("per-hour band")]) == 4


def test_every_segment_share_is_derived_and_none_is_quoted() -> None:
    """The file's ``note`` claims every share in ``rows`` is derived from the
    logs.  This is the test that makes the claim true rather than decorative.

    Three of the twelve shares used to be lifted straight out of
    ``whales_segments.json`` — the whale, early-cohort and last-grace rows.
    They *agreed* with the fold, which is exactly why nobody noticed: a quoted
    number that happens to be right is indistinguishable from a derived one
    until the day the research file is regenerated and the fixture is not.

    So every one of them is recomputed here from ``deposits.json.gz`` +
    ``first_deposits.json.gz``, and the research file is then asserted to
    agree — the agreement is the *conclusion*, not the input.
    """
    _, credit, points = _folded()
    total = sum(points.values())
    first_index = {
        f["contributor"].lower(): f["index"]
        for f in research("first_deposits.json.gz")
    }
    by_label = {r["label"]: r for r in worst_case_rows("segment_rows_worst.json")}

    def share(addresses) -> float:
        return round(100 * sum(points[a] for a in addresses) / total, 2)

    whales = [a for a in credit if credit[a] >= 800 * 10**18]
    early = [a for a, i in first_index.items() if 1 <= i <= 1000]
    late = [a for a, h in _first_hour().items() if h in (22, 23)]

    assert by_label["single-send whales ≥ 800Ξ"]["contributors"] == len(whales) == 2
    assert by_label["single-send whales ≥ 800Ξ"]["points_share_pct"] == share(whales)
    assert by_label["early cohort · join index 1–1000"]["contributors"] == len(early)
    assert by_label["early cohort · join index 1–1000"]["points_share_pct"] == share(early)
    assert by_label["last grace hours · joined 22–23"]["contributors"] == len(late) == 742
    assert by_label["last grace hours · joined 22–23"]["points_share_pct"] == share(late)

    # ...and only now, the research file agrees with all three.
    w = research("whales_segments.json")
    assert round(w["whales_800plus_credit"]["points_share_pct"], 2) == share(whales)
    assert round(w["index_1_1000"]["points_share_pct"], 2) == share(early)
    assert round(w["joined_hour_22_23"]["points_share_pct"], 2) == share(late)
    assert w["whales_800plus_credit"]["sum_points"] == sum(points[a] for a in whales)
    assert w["index_1_1000"]["points"] == sum(points[a] for a in early)


def test_the_multiplier_and_hour_bands_are_derived_from_the_fold() -> None:
    """Each contributor is attributed to the multiplier and the hour of their
    **first** deposit, and the shares are recomputed from the same wei-exact
    fold as everything else.  The bands partition the population: every
    contributor is in exactly one, so the four shares sum to 100."""
    _, credit, points = _folded()
    total = sum(points.values())
    rows = worst_case_rows("segment_rows_worst.json")

    bands = [r for r in rows if r["label"].startswith("joined at ")]
    assert sum(r["contributors"] for r in bands) == 15_576
    assert round(sum(r["points_share_pct"] for r in bands), 1) == 100.0
    # Each band's own share, recomputed -- not just the sum, which a set of
    # four wrong numbers can still hit.
    edges = {"≥ 1.9×": (19_000, 20_001), "1.5–1.9×": (15_000, 19_000),
             "1.06–1.5×": (10_600, 15_000), "≤ 1.06×": (0, 10_600)}
    for row in bands:
        lo, hi = edges[row["label"].removeprefix("joined at ")]
        members = [a for a, b in _first_bps().items() if lo <= b < hi]
        assert row["contributors"] == len(members), row["label"]
        assert row["points_share_pct"] == round(
            100 * sum(points[a] for a in members) / total, 2
        ), row["label"]
        assert row["detail"] == (
            f"{sum(credit[a] for a in members) / 10**18:,.1f}Ξ credited"
        ), row["label"]

    hours = [r for r in rows if r["label"].startswith("per-hour band")]
    joins = research("population.json")["per_hour_joins"]
    assert len(hours) == 4
    for row in hours:
        hour = row["label"].rsplit(" ", 1)[-1]
        assert row["contributors"] == joins[hour], row["label"]
        # The share too, not only the count: a per-hour band's points come
        # from the same fold as everything else, and it was the one group of
        # four whose shares nothing checked.
        members = [a for a, h in _first_hour().items() if h == int(hour)]
        assert row["points_share_pct"] == round(
            100 * sum(points[a] for a in members) / total, 2
        ), row["label"]
    # Widest first, so the panel leads with the hour that mattered.
    assert [r["contributors"] for r in hours] == sorted(
        (r["contributors"] for r in hours), reverse=True
    )


def test_the_unavailable_segment_row_is_a_none_not_a_zero() -> None:
    """The FARM-row lesson, given a payload.  A band whose share could not be
    computed carries ``None``; a widget that rendered it as ``0.0%`` would
    report "this hour scored nothing" for a read that simply failed."""
    row = load("segment_rows_worst.json")["degraded_row"]
    assert set(row) == set(CURATOR_ROW_KEYS["segment_rows"])
    assert row["points_share_pct"] is None
    assert row["contributors"] == research("population.json")["per_hour_joins"]["9"]


def test_the_clean_list_is_the_survivors_of_the_de_sybilled_fold() -> None:
    """Ranked by points, contiguous from 1, and none of them in any audited
    operator — which is what "clean" has to mean for the number beside a
    reader's raw rank to be worth printing."""
    payload = load("clean_list_rows_worst.json")
    rows = payload["rows"]
    _, credit, points = _folded()
    linked: set[str] = set().union(*_membership().values())

    real = rows[:-1]  # the last row is the name-width probe
    assert [r["clean_rank"] for r in real] == list(range(1, len(real) + 1))
    assert [r["points"] for r in real] == sorted(
        (r["points"] for r in real), reverse=True
    )
    for row in real:
        assert row["address"] not in linked
        assert row["points"] == points[row["address"]]
        assert row["credit_eth"] == round(credit[row["address"]] / 10**18, 4)
        assert row["name"] is None  # no reverse ENS resolved; never invented

    totals = payload["totals"]
    assert totals["total_points"] == sum(points.values())
    assert totals["clean_points"] == totals["total_points"] - totals["flagged_points"]
    assert totals["clean_contributors"] == 9273
    assert totals["flagged_points_share_pct"] == 43.25


def test_the_name_width_probe_is_synthetic_and_exactly_name_cols_wide() -> None:
    """CLAUDE.md: curator caps a rendered name at ``NAME_COLS`` = 12, exactly
    ``surfsurf.eth``, because 15 moved the full layout past the app-wide 143.

    The probe carries that string on a ``0xff…ff`` address rather than on a
    real wallet: attributing an ENS name to an address whose reverse record we
    have never resolved would be a fabricated fact sitting in a fixture, and
    fixtures are where facts go to be trusted.
    """
    probe = load("clean_list_rows_worst.json")["rows"][-1]
    assert probe["name"] == "surfsurf.eth"
    assert len(probe["name"]) == 12
    assert probe["address"] == "0x" + "ff" * 20
    _, _, points = _folded()
    assert probe["address"] not in points


# ---------------------------------------------------------------------------
# The labeled subset, and its mirror in the other distribution
# ---------------------------------------------------------------------------


def test_the_labeled_subset_is_the_sixteen_operators_and_the_sixty_controls() -> None:
    subset = labeled_subset()
    assert subset["meta"]["n_clusters"] == 16
    assert subset["meta"]["n_members"] == 160
    assert subset["meta"]["n_controls"] == 60
    assert len(subset["clusters"]) == 16
    assert len(subset["members"]) == 160
    assert len(subset["controls"]) == 60
    assert subset["meta"]["sweep_utc"] == research("sweep_meta.json")["sweep_utc"]

    labels = Counter(m["cluster"] for m in subset["members"])
    assert set(labels) == {e["cluster"] for e in research("cluster_economics.json")}
    assert set(labels.values()) == {10}, "ten sampled members per operator"
    assert all(c["cluster"] is None and c["is_member"] is False
               for c in subset["controls"])
    assert all(m["is_member"] is True for m in subset["members"])


def test_the_labeled_subset_is_self_contained_enough_to_run_detect() -> None:
    """PRD §3.5's benchmark gate has to run **offline**, so every input a
    ``Dataset`` needs is in this one file: deposit rows (amount, block, hour,
    tx hash, log index), the 1-based join index, the tier-B fingerprint and the
    tier-C funder.  A gate that had to reach for a second file would be a gate
    that skips the day the second file moves.
    """
    subset = labeled_subset()
    everyone = subset["members"] + subset["controls"]
    assert len(everyone) == 220

    for row in everyone:
        assert row["address"] == row["address"].lower()
        assert row["first_index"] >= 1              # 1-based, like the event
        assert row["deposits"], row["address"]
        for d in row["deposits"]:
            assert set(d) == {
                "hour", "amount_wei", "credited_delta_wei", "weight_added_wei",
                "new_weight_wei", "tx_count", "early_bps", "block_number",
                "tx_hash", "log_index",
            }
            assert isinstance(d["amount_wei"], int) and d["amount_wei"] > 0
            # The contract's own identity, re-asserted per row.
            assert d["weight_added_wei"] == (
                d["credited_delta_wei"] * d["early_bps"] // 10_000
            )

    assert sum(1 for r in everyone if r["tx"]) == 220, "every sampled tx present"
    for row in everyone:
        assert set(row["tx"]) == {
            "tx_hash", "nonce", "max_priority_fee_wei", "max_fee_wei",
            "gas_limit", "tx_type",
        }


def test_the_labeled_subset_reproduces_the_funding_signal() -> None:
    """The same 10/10 vs 0/47 as the raw datasets, computed off the fixture's
    own precomputed flags — so the benchmark gate and the research agree, and
    an error in the join that built the fixture cannot hide behind the pin that
    reads the research directly.
    """
    subset = labeled_subset()
    farm = [
        m for m in subset["members"]
        if m["cluster"] == "amt_0.45_h3" and (m["funding"] or {}).get("funder")
    ]
    assert len(farm) == 10
    assert all(m["funding"]["funder_in_cluster"] is True for m in farm)

    controls = [c for c in subset["controls"] if (c["funding"] or {}).get("funder")]
    assert len(controls) == 47
    assert not [c for c in controls if c["funding"]["funder_in_cluster"]]


def test_an_unresolved_funder_is_null_and_never_false() -> None:
    """``funder_in_cluster`` is a **tri-state**.  ``None`` means the bounded
    lookup did not resolve a funder — 43 of the 220 sampled addresses — and
    collapsing that to ``False`` would turn "we could not look" into "we looked
    and it was clean", which is the confident-negative the whole build is
    written to avoid."""
    subset = labeled_subset()
    everyone = subset["members"] + subset["controls"]
    unresolved = [
        r for r in everyone if r["funding"] and r["funding"]["funder"] is None
    ]
    assert len(unresolved) == 43, "the bounded sweep must have missed exactly these"
    assert all(r["funding"]["funder_in_cluster"] is None for r in unresolved)
    resolved = [r for r in everyone if r["funding"] and r["funding"]["funder"]]
    assert len(resolved) == 177  # 130 members + 47 controls
    assert len(resolved) + len(unresolved) == 220  # every sampled address, once
    assert all(isinstance(r["funding"]["funder_in_cluster"], bool) for r in resolved)


def test_the_two_readers_keep_the_same_names_for_the_shared_fixtures() -> None:
    """``load`` / ``slices`` / ``labeled_subset`` mean the same thing on both
    sides, and this is the only side that can import both modules to say so.

    The maxpane reader has three accessors the other does not —
    ``worst_case_envelope``, ``worst_case_rows``, ``row_payloads`` — and that
    asymmetry is deliberate rather than drift: they read **presentation**
    payloads (``credit_eth``, ``points_share_pct``, ENS names,
    pattern-language copy) that size the columns of a terminal UI.
    ``sybilkit`` has no UI, is wei-native throughout, and must not learn what a
    column is.  Pinned so the asymmetry stays exactly that size.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_sybilkit_fixtures_probe",
        _REPO_ROOT / "sybilkit" / "tests" / "sybilkit_fixtures.py",
    )
    theirs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(theirs)

    from tests import curator_sybil_fixtures as ours

    def api(module) -> set[str]:
        """Public functions the module itself defines — not what it imports."""
        return {
            name
            for name, obj in vars(module).items()
            if not name.startswith("_")
            and inspect.isfunction(obj)
            and obj.__module__ == module.__name__
        }

    shared = {"load", "slices", "labeled_subset"}
    assert shared <= api(theirs)
    assert shared <= api(ours)

    only_ours = api(ours) - api(theirs)
    assert only_ours == {
        "worst_case_envelope",
        "worst_case_rows",
        "row_payloads",
        "rendered_strings",
    }, sorted(only_ours)
    assert api(theirs) - api(ours) == set(), sorted(api(theirs) - api(ours))


def test_both_distributions_gate_on_the_same_bytes() -> None:
    """PRD §8: the labeled subset is committed to **both** repos.  Two copies
    that were allowed to drift would be two convenient subsets, and neither
    gate would mean anything."""
    ours = (SYBIL / "labeled_subset.json").read_bytes()
    theirs = (SYBILKIT_FIXTURES / "labeled_subset.json").read_bytes()
    assert ours == theirs


def test_sybilkit_carries_the_full_population_and_it_is_the_research_sweep() -> None:
    """WP2's segment tests assert population statistics, so the library needs
    the whole distribution rather than the sample — a precision floor measured
    on a convenient subset is a floor that passes for the wrong reason.

    Committed **gzipped** and byte-identical to the research archives; there is
    no uncompressed copy in either tree, and none is written to run this.
    """
    for name in ("deposits.json.gz", "first_deposits.json.gz"):
        assert (SYBILKIT_FIXTURES / name).read_bytes() == (DATA / name).read_bytes()
    assert not list(SYBILKIT_FIXTURES.glob("deposits.json"))
    assert not list(SYBILKIT_FIXTURES.glob("first_deposits.json"))

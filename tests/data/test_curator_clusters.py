"""WP3 — ``data/curator_clusters.py``: the one seam between maxpane and sybilkit.

The adapter is pure (WP3.1), drives ``sybilkit.sources`` only through injected
transports (WP3.3), and is the **translation boundary**: library vocabulary in,
on-screen pattern language out.  Nothing in this file opens a socket and
nothing sleeps.

The farm doubles below are shared with ``test_curator_manager``'s analysis
tests (imported, never re-typed — the ``test_curator_degradation`` precedent):
six wallets, one byte-identical **odd** amount, deliberately *non*-consecutive
join indices and spread blocks, so tier A alone yields exactly one
amount-family component and **no cluster** (one family never convicts).  The
second family is chosen per test: ``funding`` for the "high" band, ``gas`` for
the "low" one.
"""

from __future__ import annotations

import json

import pytest

from maxpane_dashboard.data.curator_models import (
    CURATOR_ANALYSIS_KEYS,
    CURATOR_ROW_KEYS,
    DepositEvent,
)
from tests.curator_sybil_fixtures import labeled_subset, worst_case_envelope

from maxpane_dashboard.data import curator_clusters

RATE = 1000
MINIMUM = 5 * 10**16

#: One byte-identical **odd** amount (``% 10**16 != 0``), far from the minimum:
#: odd amounts group globally, so the six members form one amount component
#: whatever hour they joined in.
FARM_AMOUNT_WEI = 1_234_500_000_000_000_000
FARM_EARLY_BPS = 15_000

FARM_MEMBERS = tuple("0x" + f"{0xA0 + i:02x}" * 20 for i in range(1, 7))
CONTROLS = tuple("0x" + f"{0xC0 + i:02x}" * 20 for i in range(1, 4))
#: A shared first funder that is not a contributor and not a CEX hot wallet.
FUNDER = "0x" + "fe" * 20
STRANGER = "0x" + "dd" * 20

_CONTROL_AMOUNTS = (
    2_511_100_000_000_000_000,
    3_722_200_000_000_000_000,
    5_933_300_000_000_000_000,
)


def _event(addr: str, amount_wei: int, block: int, log_index: int) -> DepositEvent:
    weight = amount_wei * FARM_EARLY_BPS // 10_000
    return DepositEvent(
        contributor=addr,
        hour=1,
        amount_wei=amount_wei,
        credited_delta_wei=amount_wei,
        weight_added_wei=weight,
        new_weight_wei=weight,
        tx_count=1,
        hour_total_wei=amount_wei,
        early_bps=FARM_EARLY_BPS,
        block_number=block,
        tx_hash="0x" + "ab" * 31 + f"{log_index:02x}",
        log_index=log_index,
        ts=1_786_920_000.0 + log_index,
    )


def farm_events() -> list[DepositEvent]:
    """Six members (one identical odd amount) and three controls."""
    events = [
        _event(addr, FARM_AMOUNT_WEI, 100 + 10 * i, i)
        for i, addr in enumerate(FARM_MEMBERS)
    ]
    events += [
        _event(addr, _CONTROL_AMOUNTS[i], 300 + 10 * i, 40 + i)
        for i, addr in enumerate(CONTROLS)
    ]
    return events


def farm_first_deposits() -> list[dict]:
    """Deliberately non-consecutive indices: no sequence family by accident."""
    rows = [
        {"contributor": addr, "index": 10 * (i + 1), "ts": None}
        for i, addr in enumerate(FARM_MEMBERS)
    ]
    rows += [
        {"contributor": addr, "index": 70 + 10 * i, "ts": None}
        for i, addr in enumerate(CONTROLS)
    ]
    return rows


def farm_funding() -> dict[str, dict]:
    """Every member funded by one shared non-infra funder — the second family."""
    return {
        addr: {"address": addr, "funder": FUNDER, "hops": 1}
        for addr in FARM_MEMBERS
    }


def farm_txs() -> dict[str, dict]:
    """A collapsed fee fingerprint on every member — the gas second family."""
    return {
        event.tx_hash: {
            "tx_hash": event.tx_hash,
            "nonce": 0,
            "max_priority_fee_wei": 100_000_000,
            "max_fee_wei": 200_000_000,
            "gas_limit": 91_600,
            "tx_type": 2,
        }
        for event in farm_events()
        if event.contributor in FARM_MEMBERS
    }


def farm_analysis(wallet: str | None = None, *, second_family: str = "funding"):
    """One linked six-member group, via the chosen corroborating family."""
    kwargs = {"funding": farm_funding()} if second_family == "funding" else {
        "txs": farm_txs()
    }
    return curator_clusters.build_analysis(
        farm_events(),
        farm_first_deposits(),
        points_per_eth=RATE,
        min_deposit_wei=MINIMUM,
        wallet=wallet,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# WP3.1 — the pure adapter core
# ---------------------------------------------------------------------------


def test_tier_a_alone_finds_no_cluster_and_that_zero_is_representable():
    """One family never convicts: the amount component exists, the cluster does
    not, and 'analyzed, nothing linked' is a real answer — never a blank."""
    result = curator_clusters.build_analysis(
        farm_events(),
        farm_first_deposits(),
        points_per_eth=RATE,
        min_deposit_wei=MINIMUM,
    )
    assert result.operators_count == 0
    assert result.operator_rows == []
    assert result.segment_rows, "the population bands exist without operators"
    assert result.clean_contributors == len(FARM_MEMBERS) + len(CONTROLS)
    assert result.points_total > 0


def test_the_second_family_links_the_farm_and_the_rows_take_the_frozen_shape():
    result = farm_analysis()
    assert result.operators_count == 1
    row = result.operator_rows[0]
    assert set(row) == set(CURATOR_ROW_KEYS["operator_rows"])
    assert row["size"] == len(FARM_MEMBERS)
    assert isinstance(row["reasons"], list) and row["reasons"]
    for seg_row in result.segment_rows:
        assert set(seg_row) == set(CURATOR_ROW_KEYS["segment_rows"])
    for clean_row in result.clean_list_rows:
        assert set(clean_row) == set(CURATOR_ROW_KEYS["clean_list_rows"])
        assert clean_row["name"] is None      # the manager's ENS merge fills it

    control = next(
        row for row in result.clean_list_rows if row["address"] == CONTROLS[0]
    )
    assert control["weight_eth"] == pytest.approx(
        _CONTROL_AMOUNTS[0] * FARM_EARLY_BPS / 10_000 / 10**18
    )
    assert control["tx_count"] == 1
    assert control["first_hour"] == 1
    assert control["first_index"] == 70


def test_the_flagged_set_matches_the_library_on_the_committed_fixture():
    """The PRD §8 seam: the adapter and the library agree, byte for byte, over
    the labeled subset both distributions gate on."""
    import sybilkit

    subset = labeled_subset()
    rows = subset["members"] + subset["controls"]
    deposits = [
        {**dep, "contributor": row["address"]}
        for row in rows
        for dep in row["deposits"]
    ]
    firsts = [
        {"contributor": row["address"], "index": row["first_index"]}
        for row in rows
    ]
    txs = {row["tx"]["tx_hash"]: row["tx"] for row in rows if row.get("tx")}
    funding = {
        row["address"]: {
            "address": row["address"],
            "funder": row["funding"]["funder"],
            "hops": row["funding"]["hops"],
        }
        for row in rows
        if row.get("funding")
    }

    result = curator_clusters.build_analysis(
        deposits, firsts, txs=txs, funding=funding,
        points_per_eth=RATE, min_deposit_wei=MINIMUM,
    )
    ds = sybilkit.Dataset.from_events(deposits, firsts, txs=txs, funding=funding)
    res = sybilkit.detect(
        ds,
        curator_clusters.build_preset(RATE, MINIMUM).detect_config(),
    )
    assert res.flagged, "a vacuous agreement proves nothing"
    assert result.flagged == res.flagged
    assert result.operators_count == len(res.clusters)
    assert result.points_total == res.total_points
    assert result.clean_points == res.clean_points


def test_the_adapter_divides_wei_to_eth_exactly_once():
    """The flat dict is the presentation boundary; the manager's own division
    count is pinned at zero, so the adapter's is pinned at ONE site."""
    import inspect

    result = farm_analysis()
    top = result.clean_list_rows[0]
    weights = {e.contributor: e.new_weight_wei for e in farm_events()}
    assert top["credit_eth"] == pytest.approx(
        next(
            e.credited_delta_wei
            for e in farm_events()
            if e.contributor == top["address"]
        )
        / 10**18
    )
    assert weights, "guard: the fixture still holds events"
    src = inspect.getsource(curator_clusters)
    assert src.count("/ _ETH") == 1
    assert "/ 10**18" not in src


def test_points_total_and_clean_points_describe_one_snapshot():
    """R14: the pair comes from ONE DetectResult, never two sweeps."""
    result = farm_analysis()
    assert result.points_total == result.result.total_points
    assert result.clean_points == result.result.clean_points
    payload = curator_clusters.slot_payload(result)
    assert payload["points_total"] == result.result.total_points
    assert payload["clean_points"] == result.result.clean_points


def test_points_share_pct_is_a_percentage_multiplied_once():
    result = farm_analysis()
    row = result.operator_rows[0]
    cluster = result.result.clusters[0]
    assert row["points_share_pct"] == pytest.approx(cluster.points_share * 100)
    assert 0.0 <= row["points_share_pct"] <= 100.0
    share = result.flagged_points_share_pct
    assert share == pytest.approx(
        result.result.flagged_points / result.result.total_points * 100
    )


def test_every_emitted_string_is_pattern_language():
    """The adapter is the translation boundary: no library vocabulary reaches
    a rendered string, whichever code path produced it."""
    result = farm_analysis(wallet=FARM_MEMBERS[0])
    strings: list[str] = []
    for row in result.operator_rows:
        strings += list(row["reasons"])
    for row in result.segment_rows:
        strings += [row["label"], row["detail"]]
    keys = curator_clusters.analysis_keys(result)
    strings += list(keys["you_linked_reasons"] or [])
    assert strings
    for text in strings:
        low = text.lower()
        for word in curator_clusters.FORBIDDEN_WORDS:
            assert word not in low, (word, text)


def test_a_raw_library_reason_never_passes_the_boundary():
    """The mandated bite's designated victim: a reason spelled in the library's
    own vocabulary is replaced with the family's pattern phrase, not shipped."""
    hostile = "dense sybil funder chain"
    out = curator_clusters.pattern_language(hostile, "funding")
    assert out == curator_clusters._REASON_PHRASES["funding"]
    assert "sybil" not in out
    # ...and the clean case passes through untouched.
    assert (
        curator_clusters.pattern_language("shared funder chain", "funding")
        == "shared funder chain"
    )
    # A non-string and an unknown family still answer with a phrase.
    fallback = curator_clusters.pattern_language(None, "nonsense")
    assert isinstance(fallback, str) and fallback


def test_a_hostile_persisted_payload_is_re_guarded_on_the_way_out():
    """A hand-edited cache file is third-party input too: reasons read back
    from the slot payload pass the same boundary before they reach a key."""
    payload = curator_clusters.slot_payload(farm_analysis())
    payload["groups"][0]["reasons"] = ["sybil cluster", "wash trading ring"]
    linkage = curator_clusters.you_linkage(FARM_MEMBERS[0], payload)
    assert linkage["you_linked_state"] == "linked"
    for text in linkage["you_linked_reasons"]:
        low = text.lower()
        for word in curator_clusters.FORBIDDEN_WORDS:
            assert word not in low, (word, text)


def test_the_adapter_forbidden_words_cover_the_librarys_label_words():
    """Boundary parity, derived so it cannot silently drift.

    The library never emits a forbidden word (its own ``test_curator`` scans
    every produced string) and the adapter re-filters everything on the way
    out regardless -- so this is defense-in-depth for a **hand-edited** cache,
    the one input neither of those guards sees.  For that boundary to be
    complete the adapter must screen at least every word the library screens.
    The expectation is read off the library's own ``FORBIDDEN_LABEL_WORDS``
    rather than retyped, so a word added on either side reddens this until the
    two lists agree again (the omitted ``"farmer"`` is exactly how it slipped
    the first time)."""
    from sybilkit.curator import FORBIDDEN_LABEL_WORDS

    adapter = {word.lower() for word in curator_clusters.FORBIDDEN_WORDS}
    library = {word.lower() for word in FORBIDDEN_LABEL_WORDS}
    missing = library - adapter
    assert not missing, f"adapter omits library-screened word(s): {sorted(missing)}"


def test_link_conf_bands_come_from_evidence_structure_not_the_raw_number():
    """Noisy-OR puts every cluster at >= 0.77, so a numeric band boundary is
    meaningless: the funding family (or a third family) is the 'high' claim,
    exactly two families is 'low'."""
    high = farm_analysis(second_family="funding")
    low = farm_analysis(second_family="gas")
    assert high.operator_rows[0]["conf"] == "high"
    assert low.operator_rows[0]["conf"] == "low"
    member = FARM_MEMBERS[0]
    assert curator_clusters.grade_of(member, high) == "high"
    assert curator_clusters.grade_of(member, low) == "low"
    assert curator_clusters.grade_of(CONTROLS[0], high) == "clean"
    assert curator_clusters.grade_of(STRANGER, high) is None


def test_analysis_keys_is_exactly_the_frozen_twelve():
    keys = curator_clusters.analysis_keys(farm_analysis(wallet=FARM_MEMBERS[0]))
    assert set(keys) == set(CURATOR_ANALYSIS_KEYS)
    # The sweep's own freshness marker is the CACHE's to stamp, never the pure
    # adapter's: no clock in here.
    assert keys["analysis_as_of_hhmm"] is None


def test_merge_leaderboard_grade_fills_link_conf_in_place_and_leaves_flagged():
    rows = [
        {"rank": 1, "address": FARM_MEMBERS[0], "flagged": True, "name": None},
        {"rank": 2, "address": CONTROLS[0], "flagged": False, "name": None},
        {"rank": 3, "address": STRANGER, "flagged": False, "name": None},
    ]
    curator_clusters.merge_leaderboard_grade(rows, farm_analysis())
    assert rows[0]["link_conf"] == "high"
    assert rows[1]["link_conf"] == "clean"
    assert rows[2]["link_conf"] is None
    assert rows[0]["flagged"] is True                 # Tier A's bool, untouched
    assert rows[1]["flagged"] is False


def test_with_no_analysis_the_merge_seeds_link_conf_none_on_every_row():
    """R9: build_signals emits rows WITHOUT link_conf, and None is the honest
    'the sweep has not run' — never an empty cell, which reads clean."""
    rows = [{"rank": 1, "address": FARM_MEMBERS[0], "flagged": True}]
    curator_clusters.merge_leaderboard_grade(rows, None)
    assert "link_conf" in rows[0] and rows[0]["link_conf"] is None
    # ...and a None rows list (dead logs) is a no-op, not a crash.
    curator_clusters.merge_leaderboard_grade(None, None)


def test_the_clean_list_rows_are_capped_and_rank_survivors_densely():
    result = farm_analysis()
    rows = result.clean_list_rows
    assert curator_clusters.CLEAN_LIST_LIMIT == 1_000
    assert len(rows) <= curator_clusters.CLEAN_LIST_LIMIT
    assert [row["clean_rank"] for row in rows] == list(range(1, len(rows) + 1))
    linked = set(FARM_MEMBERS)
    assert not linked & {row["address"] for row in rows}


def test_the_segment_rows_lead_with_the_operators_and_end_with_the_hours():
    """The widget renders the first MAX_ROWS only (WP4 concern 5), so the
    aggregate and the cohorts must not be buried under twenty hour bands."""
    result = farm_analysis()
    labels = [row["label"] for row in result.segment_rows]
    # `linked groups`, not `largest operators` (review finding #12 / ruling
    # D4): the aggregate is every linked cluster however small, so the name
    # of the credit-line slice on it claimed a fact about whales while
    # measuring one about linked groups.  `kind` is still "operators", which
    # is what this ordering keys on, so nothing below moved.
    assert labels[0] == "linked groups"
    hour_positions = [
        i for i, label in enumerate(labels) if label.startswith("per-hour band")
    ]
    other_positions = [
        i
        for i, label in enumerate(labels)
        if not label.startswith("per-hour band")
    ]
    assert hour_positions and other_positions
    assert min(hour_positions) > max(other_positions)


def test_slot_payload_is_json_safe_revisable_rows_only():
    result = farm_analysis()
    payload = curator_clusters.slot_payload(result)
    text = json.dumps(payload)                        # raises on a non-primitive
    assert "is_sybil" not in text and "verdict" not in text
    assert isinstance(payload["groups"], list)
    group = payload["groups"][0]
    assert set(FARM_MEMBERS) == set(group["members"])
    assert group["conf"] in ("high", "low")
    assert isinstance(payload["clean_ranks"], dict)
    assert payload["clean_ranks"][CONTROLS[0]] >= 1
    # No boolean rides any group or row: the grade is a revisable word.
    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                assert not isinstance(value, bool) or key in (), (key, value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)
    walk(payload["groups"])


#: A JSON-safe provenance block exactly as the manager will assemble it: an
#: opaque id/hash pair, the detector's own version, the rule set it ran and
#: that rule set's hash, the block the snapshot was taken at, a status-count
#: fold, a caller-stamped fetch time, and an archived-version marker.  No
#: field here is a verdict -- it is what was read, not what was decided.
PUBLISHED_BLOCK = {
    "version_id": "v42",
    "content_hash": "deadbeef" * 8,
    "detector_version": "2026.08.1",
    "rule_set": "curator-v3",
    "rules_sha256": "abc123" * 10,
    "snapshot_block": 21_000_000,
    "status_counts": {"clean": 40, "review": 5, "flagged": 3},
    "fetched_at": 1_786_968_000.0,
    "archived_version": None,
}


def test_the_published_block_carries_the_version_and_its_hash():
    """``published=`` rides beside ``enrichment=`` -- an id, a hash, counts.
    Not something ``AnalysisResult`` computes: the caller (the manager)
    assembles it and hands it in whole, exactly like ``enrichment``."""
    payload = curator_clusters.slot_payload(
        farm_analysis(), published=PUBLISHED_BLOCK
    )
    round_tripped = json.loads(json.dumps(payload))       # raises on a non-primitive
    assert round_tripped["published"] == PUBLISHED_BLOCK
    assert round_tripped["published"]["version_id"] == "v42"
    assert round_tripped["published"]["content_hash"] == PUBLISHED_BLOCK["content_hash"]
    assert round_tripped["published"]["status_counts"] == {
        "clean": 40, "review": 5, "flagged": 3,
    }


def test_a_payload_with_no_published_block_still_loads():
    """A payload written by an older build carries ``enrichment`` and no
    ``published`` key at all -- an absence, never a null -- and it must still
    load: ignored, not rejected.  ``you_linkage``/``grade_of`` are the
    existing readers of a persisted (rather than live) payload, and neither
    of them may need ``published`` to answer."""
    result = farm_analysis(wallet=FARM_MEMBERS[0])
    old_style_enrichment = {
        "txs": {}, "funding": {}, "pending": [], "reasons": {}, "page_bound": 20,
    }
    payload = json.loads(json.dumps(
        curator_clusters.slot_payload(result, enrichment=old_style_enrichment)
    ))
    assert "published" not in payload
    assert payload["enrichment"] == old_style_enrichment

    assert curator_clusters.you_linkage(
        FARM_MEMBERS[0], payload
    ) == curator_clusters.you_linkage(FARM_MEMBERS[0], result)
    assert curator_clusters.grade_of(FARM_MEMBERS[0], payload) in ("high", "low")


def test_the_curve_numbers_are_wei_exact_through_the_adapter():
    """Every point fold is the library's, at the caller's measured rate."""
    from sybilkit.curve import curve_points

    result = farm_analysis()
    weights = {e.contributor: e.new_weight_wei for e in farm_events()}
    expected_total = sum(curve_points(w, RATE) for w in weights.values())
    assert result.points_total == expected_total
    top = result.clean_list_rows[0]
    assert top["points"] == curve_points(weights[top["address"]], RATE)


# ---------------------------------------------------------------------------
# WP3.6 — the reader's linkage, pure
# ---------------------------------------------------------------------------


def test_a_wallet_in_a_cluster_is_linked_with_the_groups_own_evidence():
    result = farm_analysis(wallet=FARM_MEMBERS[2])
    keys = curator_clusters.analysis_keys(result)
    assert keys["you_linked_state"] == "linked"
    assert keys["you_linked_group_size"] == len(FARM_MEMBERS)
    assert keys["you_linked_reasons"]
    assert keys["you_clean_rank"] is None             # removed from the list


def test_a_wallet_analyzed_and_not_linked_is_clean_with_a_dense_rank():
    result = farm_analysis(wallet=CONTROLS[0])
    keys = curator_clusters.analysis_keys(result)
    assert keys["you_linked_state"] == "clean"
    assert keys["you_linked_reasons"] == []           # the representable negative
    assert keys["you_linked_group_size"] is None
    assert isinstance(keys["you_clean_rank"], int)


def test_a_stranger_is_unknown_never_a_confident_clean():
    result = farm_analysis(wallet=STRANGER)
    keys = curator_clusters.analysis_keys(result)
    assert keys["you_linked_state"] is None
    assert keys["you_linked_reasons"] is None
    assert keys["you_linked_group_size"] is None
    assert keys["you_clean_rank"] is None


def test_no_wallet_means_all_four_linkage_keys_are_none():
    keys = curator_clusters.analysis_keys(farm_analysis())
    for key in (
        "you_linked_state",
        "you_linked_reasons",
        "you_linked_group_size",
        "you_clean_rank",
    ):
        assert keys[key] is None, key


def test_you_linkage_answers_identically_from_the_result_and_the_payload():
    """set_wallet recomputes from the persisted last-good, so the payload path
    must agree with the live-object path for every state."""
    result = farm_analysis()
    payload = curator_clusters.slot_payload(result)
    for wallet in (FARM_MEMBERS[0], CONTROLS[0], STRANGER):
        assert curator_clusters.you_linkage(
            wallet, result
        ) == curator_clusters.you_linkage(wallet, payload), wallet


def test_the_preset_refuses_to_run_without_the_live_rate_and_minimum():
    """R10/R13: a remembered constant is the defect the preset exists to
    prevent, so a missing live read raises rather than guessing 1000."""
    with pytest.raises((TypeError, ValueError)):
        curator_clusters.build_analysis(farm_events(), farm_first_deposits())
    with pytest.raises((TypeError, ValueError)):
        curator_clusters.build_analysis(
            farm_events(), farm_first_deposits(), points_per_eth=RATE
        )


def test_the_sqrt_subsidy_survives_and_the_representable_none_does_too():
    result = farm_analysis()
    row = result.operator_rows[0]
    seg = result.segments.operators[0]
    assert row["sqrt_subsidy_x"] == seg.subsidy_x
    assert row["sqrt_subsidy_x"] is None or row["sqrt_subsidy_x"] > 1.0


# ---------------------------------------------------------------------------
# WP3.7 — the integration fixture: the adapter agrees with the library
# ---------------------------------------------------------------------------

from tests.curator_sybil_fixtures import load as load_sybil_fixture


def _agreement_inputs():
    doc = load_sybil_fixture("adapter_agrees.json")
    return doc, doc["deposits"], doc["first_deposits"], doc["txs"], doc["funding"]


def test_the_adapter_agrees_with_the_library_on_the_committed_fixture():
    """PRD §8's mandated seam: over one committed byte source, the adapter's
    flagged set is IDENTICAL to a bare sybilkit.detect run — not similar, not
    a superset, identical."""
    import sybilkit

    doc, deposits, firsts, txs, funding = _agreement_inputs()
    result = curator_clusters.build_analysis(
        deposits,
        firsts,
        txs=txs,
        funding=funding,
        points_per_eth=doc["points_per_eth"],
        min_deposit_wei=doc["min_deposit_wei"],
    )
    ds = sybilkit.Dataset.from_events(deposits, firsts, txs=txs, funding=funding)
    res = sybilkit.detect(
        ds,
        curator_clusters.build_preset(
            doc["points_per_eth"], doc["min_deposit_wei"]
        ).detect_config(),
    )
    assert res.flagged, "a vacuous agreement proves nothing"
    assert result.flagged == res.flagged
    assert result.operators_count == len(res.clusters) > 0
    assert result.points_total == res.total_points
    assert result.clean_points == res.clean_points
    assert result.clean_contributors == len(res.analyzed) - len(res.flagged)


def test_the_operator_rows_match_the_worst_case_fixture_shape():
    """WP4's width sweep was measured against operator_row_worst.json before
    this adapter existed; the rows it produces must be that SHAPE.  Shape
    only: the fixture's conf grades are calibration, never truth (ruling 6)."""
    frozen = worst_case_envelope("operator_row_worst.json")["row_keys"]
    doc, deposits, firsts, txs, funding = _agreement_inputs()
    result = curator_clusters.build_analysis(
        deposits,
        firsts,
        txs=txs,
        funding=funding,
        points_per_eth=doc["points_per_eth"],
        min_deposit_wei=doc["min_deposit_wei"],
    )
    assert result.operator_rows, "the fixture must produce operators"
    for row in result.operator_rows:
        assert set(row) == set(frozen)
        assert set(row) == set(CURATOR_ROW_KEYS["operator_rows"])
        assert isinstance(row["reasons"], list) and row["reasons"]
        assert row["conf"] in ("high", "low")


def test_the_agreement_fixture_is_still_the_labeled_subset():
    """The fixture is a 1:1 join of labeled_subset.json.  Pinning the
    derivation is what stops the two byte sources drifting into two different
    populations under one test name."""
    doc, deposits, firsts, txs, funding = _agreement_inputs()
    subset = labeled_subset()
    rows = subset["members"] + subset["controls"]
    assert {r["contributor"] for r in firsts} == {r["address"] for r in rows}
    assert len(deposits) == sum(len(r["deposits"]) for r in rows)
    assert set(txs) == {r["tx"]["tx_hash"] for r in rows if r.get("tx")}
    assert set(funding) == {r["address"] for r in rows if r.get("funding")}
    assert doc["points_per_eth"] == 1000
    assert doc["min_deposit_wei"] == 5 * 10**16


# ---------------------------------------------------------------------------
# WP3.8 — keyless, no-verdict, single-import guardrails
# ---------------------------------------------------------------------------

import ast
import pathlib

_REPO = pathlib.Path(__file__).resolve().parents[2]


def _imported_module_names(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_no_curator_module_opens_a_socket_for_analysis():
    """Structural, not promised: the adapter and the manager can only reach
    the network through a session somebody INJECTED.  Neither imports httpx,
    neither constructs a client, and the sources' own suite pins that the
    package has exactly one construction site — so a test that forgets to
    inject gets the tier-A-only sweep, never a socket."""
    import inspect

    from maxpane_dashboard.data import curator_manager

    for module in (curator_clusters, curator_manager):
        imported = _imported_module_names(pathlib.Path(module.__file__))
        assert not any(
            name == "httpx" or name.startswith("httpx.") for name in imported
        ), module.__name__
        src = inspect.getsource(module)
        assert "AsyncClient" not in src, module.__name__
        assert "open_client" not in src, module.__name__

    # ...and no curator data test builds a bare httpx client either: every
    # AsyncClient a test constructs must carry a transport.
    for test_file in sorted((_REPO / "tests" / "data").glob("test_curator_*.py")):
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", getattr(node.func, "id", ""))
            if name != "AsyncClient":
                continue
            kwargs = {kw.arg for kw in node.keywords}
            assert "transport" in kwargs, (
                f"{test_file.name} builds an AsyncClient with no transport"
            )


def test_the_analysis_slot_persists_no_boolean_verdict(tmp_path):
    """PRD §2: revisable rows only.  No is_sybil/verdict key reaches the
    file, and no boolean rides ANYWHERE in it — the grade is a word the next
    sweep may revise, never a stored judgement.

    The check used to gate the boolean half of that on a ``"flag" in key``
    substring, which never looks at a ``review_members`` entry (its keys are
    addresses).  Broadened to flag any boolean at all, anywhere in the tree
    — verified by mutation: reverting to the old ``"flag" in key`` gate lets
    a hand-planted boolean under ``review_members`` sail through green.

    The ``enrichment`` half is an old-shaped literal, not a live sweep (T11
    removed ``fetch_enrichment`` -- the sweep's own network half): a payload
    written before T11 still carries exactly this shape, per-address funding
    cursor included -- the deepest nesting in the file and the one whose
    entries carry a ``funder`` and a walk position.  ``groups[0]`` is given a
    non-empty ``review_members`` and the payload is given a ``published``
    block, so the walk actually visits every channel rather than merely
    being handed an input that happens not to contain them.
    """
    from maxpane_dashboard.data.curator_cache import CuratorCache

    addr = FARM_MEMBERS[0]
    legacy_enrichment = {
        "txs": {},
        "funding": {addr: {"address": addr, "funder": FUNDER, "hops": 1}},
        "pending": [],
        "reasons": {},
        "page_bound": 20,
        "cursors": {
            addr: {
                "params": {"page": 21, "filter": "to"},
                "funder": None,
                "block": None,
                "stage": "transactions",
            },
        },
    }

    result = farm_analysis()
    # `build_analysis` never fills `review_members` (only the published-fold
    # builder does) -- planted directly so this walk has a real, non-empty
    # instance of the channel to visit, not an absent key.
    result.groups[0]["review_members"] = {addr: ["amount", "funding"]}
    assert result.groups[0]["review_members"], "guard: the scan must see a review entry"

    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=lambda: 1_786_968_000.0)
    payload = curator_clusters.slot_payload(result, published=PUBLISHED_BLOCK)
    payload["enrichment"] = legacy_enrichment
    cache.store_analysis(payload, ts=1_786_968_000.0)
    cache.save()
    on_disk = json.loads(pathlib.Path(cache.path).read_text(encoding="utf-8"))
    stored = on_disk["last_good"]["clusters"]["payload"]
    assert stored["groups"][0]["review_members"], "guard: it survived to disk"
    assert stored["published"] == PUBLISHED_BLOCK, "guard: it survived to disk"
    assert stored["enrichment"]["cursors"][addr]["params"]["page"] == 21, (
        "guard: the legacy cursor shape survived too"
    )

    offences: list[str] = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                where = f"{path}.{key}"
                if key in ("is_sybil", "sybil", "verdict"):
                    offences.append(where)
                if isinstance(value, bool):
                    offences.append(f"{where} (boolean)")
                walk(value, where)
        elif isinstance(node, list):
            for i, item in enumerate(node):
                walk(item, f"{path}[{i}]")

    walk(on_disk)
    assert offences == []


def test_curator_signals_never_imports_sybilkit():
    """Tier A stays exactly as shipped: the frozen analytics module never
    learns the library exists (its forbidden-word source scan included)."""
    signals = _REPO / "maxpane_dashboard" / "analytics" / "curator_signals.py"
    for name in _imported_module_names(signals):
        assert not name.startswith("sybilkit"), name


def test_only_curator_clusters_imports_sybilkit():
    """The single-seam rule, repo-wide: exactly one maxpane module may import
    the library, and it is the adapter."""
    importers: list[str] = []
    for path in sorted((_REPO / "maxpane_dashboard").rglob("*.py")):
        for name in _imported_module_names(path):
            if name == "sybilkit" or name.startswith("sybilkit."):
                importers.append(str(path.relative_to(_REPO)))
                break
    assert importers == ["maxpane_dashboard/data/curator_clusters.py"]


# ---------------------------------------------------------------------------
# Fix round 1 — M3: an unknown grade band is unknown
# ---------------------------------------------------------------------------


def test_an_unknown_grade_band_is_unknown_never_low():
    """A corrupted/unknown `conf` in a persisted group is bad data, and a
    confidence word derived from bad data is a claim: it renders `?` (None),
    while the membership FACT (linked, size, reasons) is untouched."""
    payload = curator_clusters.slot_payload(farm_analysis())
    payload["groups"][0]["conf"] = "banana"
    assert curator_clusters.grade_of(FARM_MEMBERS[0], payload) is None

    rows = [{"address": FARM_MEMBERS[0], "flagged": True}]
    curator_clusters.merge_leaderboard_grade(rows, payload)
    assert rows[0]["link_conf"] is None

    linkage = curator_clusters.you_linkage(FARM_MEMBERS[0], payload)
    assert linkage["you_linked_state"] == "linked"
    assert linkage["you_linked_group_size"] == len(FARM_MEMBERS)


# ---------------------------------------------------------------------------
# Task 5 — the review band, data layer
# ---------------------------------------------------------------------------
#
# T4 populates `groups[].review_members` (address -> its OWN evidence
# families, for that group's `status == "review"` wallets).  These tests hang
# it off a plain `build_analysis` group by mutation, exactly like the "Fix
# round 1" section above mutates `conf` — review and non-review member are
# both FARM_MEMBERS of the one linked group, so "grades review" and "still
# grades the group's own band" are checked on siblings inside the SAME group.


def test_a_review_member_grades_review_and_not_its_groups_band():
    payload = curator_clusters.slot_payload(farm_analysis())
    reviewer = FARM_MEMBERS[0]
    payload["groups"][0]["review_members"] = {reviewer: ["amount"]}
    assert payload["groups"][0]["conf"] == "high"
    assert curator_clusters.grade_of(reviewer, payload) == "review"


def test_a_flagged_member_of_the_same_group_still_grades_the_groups_band():
    payload = curator_clusters.slot_payload(farm_analysis())
    reviewer, sibling = FARM_MEMBERS[0], FARM_MEMBERS[1]
    payload["groups"][0]["review_members"] = {reviewer: ["amount"]}
    assert curator_clusters.grade_of(sibling, payload) == "high"


def test_a_clean_address_still_grades_clean_and_a_stranger_still_grades_none():
    payload = curator_clusters.slot_payload(farm_analysis())
    payload["groups"][0]["review_members"] = {FARM_MEMBERS[0]: ["amount"]}
    assert curator_clusters.grade_of(CONTROLS[0], payload) == "clean"
    assert curator_clusters.grade_of(STRANGER, payload) is None


# ---------------------------------------------------------------------------
# Fix round 2 (review finding, Critical) — `_group_of` was half-normalised
# ---------------------------------------------------------------------------
#
# `bands_by_address` lowercases every stored member before keying its map;
# `_group_of` lowercased only the caller's query and compared it raw against
# the stored `members` list — a mixed-case stored member (a hand-edited
# cache, exactly this module's threat model) made the two functions
# disagree, which the agreement test below exists to catch.  Fixed by
# lowercasing both sides in `_group_of`, per `sybilkit/report.py`'s own
# documented convention ("every membership test here is lowercased on both
# sides"), not by un-lowercasing `bands_by_address`.


def test_a_mixed_case_stored_member_still_agrees_and_still_grades_the_groups_band():
    """Both halves matter: agreeing on `None` would also be "agreement", so
    this asserts the SAME non-None band from both functions, not just that
    they match each other."""
    payload = curator_clusters.slot_payload(farm_analysis())
    payload["groups"][0]["members"][0] = FARM_MEMBERS[0].upper()
    assert curator_clusters.grade_of(FARM_MEMBERS[0], payload) == "high"
    assert curator_clusters.bands_by_address(payload).get(FARM_MEMBERS[0]) == "high"


def test_bands_by_address_agrees_with_grade_of_on_every_address():
    """The two must never diverge: one is the bulk form of the other.
    Covers both bands `_grade_families`/`published_band` can produce — the
    default fixture's second family ("funding") always yields "high", so a
    "gas" second-family build is added to reach "low" too (review finding,
    Important: a mutation that dropped "low" from the bulk path ONLY left
    the whole suite green until this widened)."""
    for second_family, band in (("funding", "high"), ("gas", "low")):
        payload = curator_clusters.slot_payload(
            farm_analysis(second_family=second_family)
        )
        payload["groups"][0]["review_members"] = {FARM_MEMBERS[0]: ["amount"]}
        bands = curator_clusters.bands_by_address(payload)
        for address in (*FARM_MEMBERS, *CONTROLS, STRANGER):
            assert bands.get(address) == curator_clusters.grade_of(
                address, payload
            ), (second_family, address)
        assert bands[FARM_MEMBERS[0]] == "review"
        assert bands[FARM_MEMBERS[1]] == band
        assert bands[CONTROLS[0]] == "clean"
        assert STRANGER not in bands


def test_you_linked_state_is_review_with_the_wallets_own_families_as_reasons():
    """The group's OWN reasons (its "funding"-second-family evidence) describe
    evidence this reviewed wallet does not itself carry, so they must not
    leak into `you_linked_reasons` — only the wallet's own families do."""
    result = farm_analysis()
    reviewer = FARM_MEMBERS[0]
    result.groups[0]["review_members"] = {reviewer: ["amount"]}
    keys = curator_clusters.you_linkage(reviewer, result)
    assert keys["you_linked_state"] == "review"
    assert keys["you_linked_reasons"] == [curator_clusters.pattern_language(None, "amount")]
    assert curator_clusters.pattern_language(None, "funding") not in keys["you_linked_reasons"]


def test_a_review_wallet_keeps_its_groups_size():
    result = farm_analysis()
    reviewer = FARM_MEMBERS[0]
    result.groups[0]["review_members"] = {reviewer: ["amount"]}
    keys = curator_clusters.you_linkage(reviewer, result)
    assert keys["you_linked_group_size"] == len(FARM_MEMBERS)


def test_an_unreadable_review_members_mapping_costs_the_band_not_the_row():
    """A malformed `review_members` (not a mapping) must not raise, and must
    not take the group's own band or the membership FACT down with it: the
    band falls back to the group's `conf`, and `you_linkage`'s linked state,
    size and reasons are untouched."""
    payload = curator_clusters.slot_payload(farm_analysis())
    payload["groups"][0]["review_members"] = ["not", "a", "mapping"]
    member = FARM_MEMBERS[0]

    assert curator_clusters.grade_of(member, payload) == "high"
    assert curator_clusters.bands_by_address(payload)[member] == "high"

    linkage = curator_clusters.you_linkage(member, payload)
    assert linkage["you_linked_state"] == "linked"
    assert linkage["you_linked_group_size"] == len(FARM_MEMBERS)
    assert linkage["you_linked_reasons"]


def test_review_families_are_refiltered_against_the_allowlist_on_the_persisted_read_path():
    """THE CARRY-FORWARD: T4's `FILTER_FAMILIES` allowlist protects the WRITE
    site only.  A hand-edited cache file is third-party input too (this
    module's own docstring says so), so a forbidden word smuggled into a
    persisted `review_members` family list must be dropped reading it back
    out — not merely softened into a generic phrase by `pattern_language`,
    which would still emit one reason per bogus entry.  Two entries in, one
    real reason out proves the entry was DROPPED, not just re-worded."""
    payload = curator_clusters.slot_payload(farm_analysis())
    reviewer = FARM_MEMBERS[0]
    payload["groups"][0]["review_members"] = {
        reviewer: ["amount", "sybil-cluster"]
    }
    keys = curator_clusters.you_linkage(reviewer, payload)
    assert keys["you_linked_reasons"] == [curator_clusters.pattern_language(None, "amount")]


def test_merge_leaderboard_grade_reports_a_review_wallet_too():
    """The leaderboard merge is the O(population) form of `grade_of`; the
    review band must survive going through `bands_by_address` on that path,
    not just the single-address one."""
    payload = curator_clusters.slot_payload(farm_analysis())
    reviewer = FARM_MEMBERS[0]
    payload["groups"][0]["review_members"] = {reviewer: ["amount"]}
    rows = [{"rank": 1, "address": reviewer, "flagged": True, "name": None}]
    curator_clusters.merge_leaderboard_grade(rows, payload)
    assert rows[0]["link_conf"] == "review"


def test_merge_leaderboard_grade_reports_the_low_band_too():
    """Review finding, Important: the default fixture's second family
    ("funding") always yields "high", so the merge path also needs a "gas"
    second-family build to prove `bands_by_address` carries "low" through
    `merge_leaderboard_grade`, not just "high"/"review"/"clean"."""
    payload = curator_clusters.slot_payload(farm_analysis(second_family="gas"))
    rows = [{"rank": 1, "address": FARM_MEMBERS[1], "flagged": True, "name": None}]
    curator_clusters.merge_leaderboard_grade(rows, payload)
    assert rows[0]["link_conf"] == "low"


def test_a_non_list_review_family_value_degrades_to_empty_reasons():
    """Review finding, Minor: `review_members`'s outer mapping can be
    well-formed while one wallet's OWN value is not a list (`None`, a bare
    string) — a narrower corruption than the whole mapping being unreadable.
    The code already guards this with `isinstance(families, list)`; this
    pins that it degrades to an empty reasons list rather than raising or
    (for the string case) iterating characters as if they were families."""
    for bad_families in (None, "amount"):
        payload = curator_clusters.slot_payload(farm_analysis())
        reviewer = FARM_MEMBERS[0]
        payload["groups"][0]["review_members"] = {reviewer: bad_families}
        keys = curator_clusters.you_linkage(reviewer, payload)
        assert keys["you_linked_state"] == "review", bad_families
        assert keys["you_linked_reasons"] == [], bad_families

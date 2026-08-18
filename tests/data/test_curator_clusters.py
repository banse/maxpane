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
import math

import pytest

from maxpane_dashboard.data.curator_models import (
    CURATOR_ANALYSIS_KEYS,
    CURATOR_ROW_KEYS,
    DepositEvent,
)
from tests.curator_sybil_fixtures import labeled_subset

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
    assert len(rows) <= curator_clusters.CLEAN_LIST_LIMIT
    assert [row["clean_rank"] for row in rows] == list(range(1, len(rows) + 1))
    linked = set(FARM_MEMBERS)
    assert not linked & {row["address"] for row in rows}


def test_the_segment_rows_lead_with_the_operators_and_end_with_the_hours():
    """The widget renders the first MAX_ROWS only (WP4 concern 5), so the
    aggregate and the cohorts must not be buried under twenty hour bands."""
    result = farm_analysis()
    labels = [row["label"] for row in result.segment_rows]
    assert labels[0] == "largest operators"
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

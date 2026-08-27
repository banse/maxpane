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
# WP3.3 — candidates and the bounded, resumable enrichment fetch
# ---------------------------------------------------------------------------
#
# Every fetch drives ``sybilkit.sources`` through an injected
# ``httpx.MockTransport``; no test in this section (or any other) opens a
# socket, and the no-session case is proven with a bomb rather than promised.

import asyncio

import httpx


async def no_sleep(_seconds: float) -> None:
    """Injected pacing: the suite proves the calls, never spends the seconds."""


class AnalysisRoutes:
    """One async MockTransport handler for both sources wire shapes.

    POST is the JSON-RPC fingerprint batch (answered per ``id``, the
    re-alignment contract); GET is Blockscout's per-address transaction page.
    Shared with ``test_curator_manager``'s sweep tests — imported, never
    re-typed.
    """

    def __init__(
        self,
        *,
        funder: str = FUNDER,
        blocking: bool = False,
        tx_result: str = "full",
        pages_forever: tuple[str, ...] = (),
        unreadable: tuple[str, ...] = (),
    ) -> None:
        self.funder = funder
        self.blocking = blocking
        self.tx_result = tx_result
        self.pages_forever = {a.lower() for a in pages_forever}
        self.unreadable = {a.lower() for a in unreadable}
        self.release = asyncio.Event()
        self.started = asyncio.Event()
        self.posts: list = []
        self.gets: list[str] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        self.started.set()
        if self.blocking:
            await self.release.wait()
        if request.method == "POST":
            body = json.loads(request.content.decode())
            self.posts.append(body)
            out = []
            for entry in body:
                tx_hash = entry["params"][0]
                result = (
                    None
                    if self.tx_result == "null"
                    else {
                        "hash": tx_hash,
                        "nonce": "0x0",
                        "maxPriorityFeePerGas": "0x5f5e100",
                        "maxFeePerGas": "0xbebc200",
                        "gas": "0x165e0",
                        "type": "0x2",
                    }
                )
                out.append({"jsonrpc": "2.0", "id": entry["id"], "result": result})
            return httpx.Response(200, json=out)
        addr = request.url.path.rstrip("/").split("/")[-2].lower()
        self.gets.append(addr)
        if addr in self.unreadable:
            return httpx.Response(503, text="down")
        if addr in self.pages_forever:
            return httpx.Response(
                200,
                json={"items": [], "next_page_params": {"page": len(self.gets)}},
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "from": {"hash": self.funder},
                        "to": {"hash": addr},
                        "block_number": 90,
                    }
                ],
                "next_page_params": None,
            },
        )

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def test_fetch_enrichment_without_a_session_never_touches_the_sources(monkeypatch):
    """No transport and no client means NO fetch — structurally, via a bomb.
    This is what keeps every FakeClient-driven manager test socket-free."""

    async def bomb(*_args, **_kwargs):
        raise AssertionError("a source was driven with no injected session")

    monkeypatch.setattr(
        curator_clusters._tx_sources, "fetch_tx_fingerprints", bomb
    )
    monkeypatch.setattr(curator_clusters._blockscout, "fetch_funding", bomb)

    state = {
        "txs": {"0xabc": {"tx_hash": "0xabc", "nonce": 0}},
        "funding": {},
        "pending": [FARM_MEMBERS[0]],
        "reasons": {FARM_MEMBERS[0]: "budget"},
        "page_bound": 20,
    }
    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=["0xdef"], funding_wanted=[FARM_MEMBERS[1]], state=state
        )
    )
    assert sweep.fetched is False
    assert sweep.tx_ok is None and sweep.funding_ok is None
    assert sweep.txs == state["txs"]                  # carried, untouched
    assert list(sweep.funding_pending) == state["pending"]


def test_fetch_enrichment_accumulates_and_never_rereads_known():
    routes = AnalysisRoutes()
    hashes = [e.tx_hash for e in farm_events()[:3]]
    addrs = list(FARM_MEMBERS[:3])

    first = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=hashes,
            funding_wanted=addrs,
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert first.fetched is True
    assert first.tx_ok is True and first.funding_ok is True
    assert set(first.txs) == set(hashes)
    assert set(first.funding) == set(addrs)
    assert first.funding[addrs[0]]["funder"] == FUNDER

    gets, posts = len(routes.gets), len(routes.posts)
    second = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=hashes,
            funding_wanted=addrs,
            state=first.state(),
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert len(routes.gets) == gets, "a known address was re-read"
    assert len(routes.posts) == posts, "a known fingerprint was re-fetched"
    assert second.funding == first.funding
    # Nothing was attempted, and 'not attempted' is not 'failed'.
    assert second.tx_ok is None and second.funding_ok is None


def test_the_funding_budget_defers_and_the_cursor_resumes():
    routes = AnalysisRoutes()
    addrs = list(FARM_MEMBERS)

    first = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=addrs,
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
            funding_budget=2,
        )
    )
    assert len(first.funding) == 2
    assert set(first.funding_pending) == set(addrs[2:])
    assert set(first.funding_reasons.values()) == {"budget"}

    second = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=addrs,
            state=first.state(),
            transport=routes.transport,
            sleep=no_sleep,
            funding_budget=2,
        )
    )
    # The deferred addresses go first: coverage extends, nothing is re-read.
    assert set(second.funding) == set(addrs[:4])
    assert set(second.funding_pending) == set(addrs[4:])


def test_a_pages_pending_raises_the_bound_and_unreadable_does_not():
    """WP2's cursor vocabulary, acted on: 'pages' means the bound is what needs
    raising; 'unreadable' means retry as-is and spend no more pages on a
    failing endpoint."""
    stuck, flaky, fine = FARM_MEMBERS[0], FARM_MEMBERS[1], FARM_MEMBERS[2]
    routes = AnalysisRoutes(pages_forever=(stuck,), unreadable=(flaky,))

    first = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[stuck, flaky, fine],
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert first.funding_reasons[stuck] == "pages"
    assert first.funding_reasons[flaky] == "unreadable"
    assert fine in first.funding
    start_bound = first.page_bound

    second = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[],
            state=first.state(),
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert second.page_bound == min(
        start_bound * 2, curator_clusters.MAX_FUNDING_PAGES
    )
    assert second.page_bound > start_bound
    assert curator_clusters.MAX_FUNDING_PAGES >= second.page_bound


def test_a_source_outage_keeps_the_carried_state():
    """None from a fetcher is 'could not read', never 'there is nothing': the
    accumulated map and the cursor survive, and the pass reports itself."""

    async def dead(_request):
        raise httpx.ConnectError("network unreachable")

    state = {
        "txs": {},
        "funding": {FARM_MEMBERS[0]: {"address": FARM_MEMBERS[0], "funder": FUNDER, "hops": 1}},
        "pending": [FARM_MEMBERS[1]],
        "reasons": {FARM_MEMBERS[1]: "unreadable"},
        "page_bound": 20,
    }
    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[FARM_MEMBERS[2]],
            state=state,
            transport=httpx.MockTransport(dead),
            sleep=no_sleep,
        )
    )
    assert sweep.funding_ok is False
    assert sweep.funding == state["funding"]          # last-good, untouched
    assert list(sweep.funding_pending) == state["pending"]


def test_a_zero_funding_budget_skips_the_call_entirely():
    """WP2's warning verbatim: fetch_funding(budget=0) still opens a session,
    so the skip switch is not calling it at all."""
    routes = AnalysisRoutes()
    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=list(FARM_MEMBERS),
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
            funding_budget=0,
        )
    )
    assert routes.gets == [] and routes.posts == []
    assert sweep.funding_ok is None                   # skipped, not failed
    assert sweep.funding == {}


def test_a_tx_sweep_that_resolved_nothing_is_a_healthy_pass_not_an_outage():
    """Fix round 2's rule: test `is not None`, never truthiness — a node
    answering `result: null` is the documented ask-again case."""
    routes = AnalysisRoutes(tx_result="null")
    hashes = [e.tx_hash for e in farm_events()[:2]]
    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=hashes,
            funding_wanted=[],
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert sweep.tx_ok is True                        # reached, healthy
    assert sweep.txs == {}                            # nothing resolved yet
    # ...and the hashes stay wanted: a later pass asks again.
    routes.tx_result = "full"
    again = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=hashes,
            funding_wanted=[],
            state=sweep.state(),
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert set(again.txs) == set(hashes)


# ---------------------------------------------------------------------------
# WP7.2 — the per-address funding page cursor (review finding #14b, ruling D6)
# ---------------------------------------------------------------------------
#
# A page-bounded address used to re-walk its history **from page 1 every
# sweep, forever**, and pendings head the budget, so it crowded out addresses
# nobody had looked at yet.  ``FundingSweep.page_cursors`` is the library's
# half; this is the adapter's: the cursor rides inside the existing
# ``enrichment`` dict of the slot payload, so ``SLOT_CLUSTERS``'s own shape
# does not change and ``curator_cache`` needs no version bump.

#: A slot payload's ``enrichment`` dict exactly as the build **before** the
#: cursor wrote it: five keys, no ``"cursors"``.  Frozen as a literal rather
#: than regenerated from today's code, because the whole point of the
#: compatibility gate is that these are bytes this build can no longer
#: produce — a payload regenerated by the current adapter would carry the new
#: key and the gate would test nothing.
PRE_CURSOR_ENRICHMENT = {
    "txs": {},
    "funding": {},
    "pending": [FARM_MEMBERS[0]],
    "reasons": {FARM_MEMBERS[0]: "pages"},
    "page_bound": 20,
}


class PagedFundingRoutes:
    """Blockscout with a long history: empty pages, then the funder on the last.

    Every GET records the page number it asked for, which is what makes
    "resumed" and "re-walked from the top" different observations rather than
    the same green.  The ``filter=to`` assertion rides along because a cursor
    that drops it asks for the address's whole history instead of its incoming
    half (finding #14a).
    """

    def __init__(self, address: str, *, pages: int = 25, funder: str = FUNDER):
        self.address = address.lower()
        self.pages = pages
        self.funder = funder
        self.requested: list[int] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "GET", "this route serves the funding walk only"
        assert request.url.params.get("filter") == "to"
        raw = request.url.params.get("page")
        number = 1 if raw is None else int(raw)
        self.requested.append(number)
        if number >= self.pages:
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "from": {"hash": self.funder},
                            "to": {"hash": self.address},
                            "block_number": 90,
                        }
                    ],
                    "next_page_params": None,
                },
            )
        return httpx.Response(
            200,
            json={"items": [], "next_page_params": {"page": number + 1}},
        )

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def test_a_slot_payload_written_before_the_cursor_still_loads():
    """The compatibility gate, and the reason the read is ``prior.get``.

    A cache file persisted by yesterday's build has no ``"cursors"`` key.  It
    must load, resume the walk from page 1 — the pre-cursor behaviour, which
    is correct, merely slow — and raise nothing.  Anything else turns a
    library improvement into a startup crash for every existing user.
    """
    addr = FARM_MEMBERS[0]
    routes = PagedFundingRoutes(addr, pages=3)
    payload = json.loads(
        json.dumps(
            curator_clusters.slot_payload(
                farm_analysis(), enrichment=PRE_CURSOR_ENRICHMENT
            )
        )
    )
    carried = payload["enrichment"]
    assert "cursors" not in carried            # guard: really the old shape

    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[],
            state=carried,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert routes.requested[0] == 1            # resumed from the top, as before
    assert sweep.funding[addr]["funder"] == FUNDER
    assert sweep.funding_cursors == {}         # resolved: nothing to resume
    assert sweep.state()["cursors"] == {}


def test_the_funding_cursor_survives_a_round_trip_through_the_slot_payload():
    """The cursor is only worth anything if it survives the *file*.

    It rides inside the existing ``enrichment`` dict, so this is a real
    ``slot_payload`` through ``json.dumps``/``loads`` and back into
    ``fetch_enrichment`` — not an in-process hand-off.
    """
    addr = FARM_MEMBERS[0]
    routes = PagedFundingRoutes(addr, pages=99)   # never finishes in one bound
    first = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[addr],
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert first.funding_reasons[addr] == "pages"
    assert first.funding_cursors[addr]["params"]["page"] == 21
    assert first.funding_cursors[addr]["params"]["filter"] == "to"
    assert first.funding_cursors[addr]["stage"] == "transactions"

    payload = json.loads(
        json.dumps(
            curator_clusters.slot_payload(
                farm_analysis(), enrichment=first.state()
            )
        )
    )
    carried = payload["enrichment"]
    assert carried["cursors"][addr]["params"]["page"] == 21

    walked = len(routes.requested)
    second = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[],
            state=carried,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    resumed = routes.requested[walked:]
    assert resumed and resumed[0] == 21         # off the file, not from page 1
    assert 1 not in resumed
    assert second.funding_cursors[addr]["params"]["page"] > 21


def test_a_page_bounded_address_makes_progress_across_two_sweeps():
    """The defect this whole mechanism exists to end, end to end.

    25 pages of history against a 20-page bound: sweep one reaches the wall,
    sweep two starts where it stopped and **finishes**.  Without the cursor
    the second sweep re-reads pages 1–20 and the address is pending forever,
    while heading the budget — so it crowds out addresses nobody has looked
    at yet.
    """
    addr = FARM_MEMBERS[0]
    routes = PagedFundingRoutes(addr, pages=25)
    first = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[addr],
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert first.funding == {}                       # NOT a resolved None row
    assert first.funding_pending == (addr,)
    assert first.funding_reasons[addr] == "pages"
    assert routes.requested == list(range(1, 21))

    second = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[],
            state=first.state(),
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert routes.requested[20:] == list(range(21, 26))
    assert second.funding[addr]["funder"] == FUNDER
    assert second.funding_pending == ()
    assert second.funding_cursors == {}              # finished: nothing to keep


# ---------------------------------------------------------------------------
# WP7.3 — the sweep states the detached sweep now has to read
# ---------------------------------------------------------------------------
#
# Two of the library's degraded paths changed shape in the review-fix round,
# and the adapter's reading of them is the thing a user actually feels:
#
# * finding #10 — a malformed batch used to throw away every fingerprint the
#   earlier batches had already read and return ``None``.  It now returns a
#   PARTIAL ``TxSweep``, which is a healthy pass, not an outage.
# * finding #5a — a ``{"items": null}`` page from a 200 used to finish the
#   walk and write a resolved ``funder=None`` row.  It now leaves the address
#   PENDING.
#
# The adapter's contract is unchanged — ``is None`` is the outage, everything
# else is a pass — but "unchanged" is a claim until something asserts it.


class PartialTxRoutes:
    """A fingerprint pool that answers the first batch and refuses the second.

    The refusal wears OUR OWN bug's shape (``invalid argument`` — one of
    ``MALFORMED_REQUEST_PATTERNS``), which short-circuits the pool rather than
    rotating: it fails identically everywhere.  What it must NOT do any more
    is discard the batch that already came back.
    """

    def __init__(self) -> None:
        self.batches = 0
        self.asked: list[list[str]] = []

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.method == "POST", "this route serves the batch pool only"
        body = json.loads(request.content.decode())
        self.batches += 1
        self.asked.append([entry["params"][0] for entry in body])
        if self.batches == 2:
            return httpx.Response(
                200,
                json=[
                    {
                        "jsonrpc": "2.0",
                        "id": entry["id"],
                        "error": {
                            "code": -32602,
                            "message": "invalid argument 0: hex string of odd length",
                        },
                    }
                    for entry in body
                ],
            )
        return httpx.Response(
            200,
            json=[
                {
                    "jsonrpc": "2.0",
                    "id": entry["id"],
                    "result": {
                        "hash": entry["params"][0],
                        "nonce": "0x0",
                        "maxPriorityFeePerGas": "0x5f5e100",
                        "maxFeePerGas": "0xbebc200",
                        "gas": "0x165e0",
                        "type": "0x2",
                    },
                }
                for entry in body
            ],
        )

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)


def test_a_partial_tx_sweep_is_a_healthy_pass_that_leaves_the_rest_wanted():
    """`is None` is the outage; a sweep with pendings is coverage, not failure.

    Sixty hashes is two batches.  The first comes back, the second is our own
    bug — and the pass must keep the forty it read while leaving the twenty it
    did not **wanted**, never recorded as "these transactions have no
    fingerprint".  A `tx_ok=False` here would fold a healthy pass into the
    degraded group and hide forty real reads behind it.
    """
    hashes = [f"0x{i:064x}" for i in range(1, 61)]
    routes = PartialTxRoutes()

    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=hashes,
            funding_wanted=[],
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    )
    assert routes.batches == 2                   # short-circuited, not rotated
    assert sweep.tx_ok is True                   # partial is NOT an outage
    assert set(sweep.txs) == set(hashes[:40])
    assert set(sweep.txs).isdisjoint(hashes[40:])

    healthy = AnalysisRoutes()
    again = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=hashes,
            funding_wanted=[],
            state=sweep.state(),
            transport=healthy.transport,
            sleep=no_sleep,
        )
    )
    asked = {entry["params"][0] for post in healthy.posts for entry in post}
    assert asked == set(hashes[40:]), "a known fingerprint was re-fetched"
    assert set(again.txs) == set(hashes)


def test_an_outage_still_keeps_the_last_good_rather_than_publishing_an_empty_analysis():
    """Both sources dead, and every carried field survives — cursor included.

    The rule this pins is the repo's oldest: a failed read is `None`, never
    an empty map.  An empty `funding` here would be persisted, and the next
    pass reads it back as `known` — so one dead minute would erase coverage
    that took many sweeps to accumulate.
    """

    async def dead(_request):
        raise httpx.ConnectError("network unreachable")

    known_hash = "0x" + "1" * 64
    carried = {
        "txs": {known_hash: {"tx_hash": known_hash, "nonce": 0}},
        "funding": {
            FARM_MEMBERS[0]: {
                "address": FARM_MEMBERS[0], "funder": FUNDER, "hops": 1
            }
        },
        "pending": [FARM_MEMBERS[1]],
        "reasons": {FARM_MEMBERS[1]: "pages"},
        "page_bound": 20,
        "cursors": {
            FARM_MEMBERS[1]: {
                "params": {"page": 21, "filter": "to"},
                "funder": None,
                "block": None,
                "stage": "transactions",
            }
        },
    }
    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=["0x" + "2" * 64],
            funding_wanted=[FARM_MEMBERS[2]],
            state=carried,
            transport=httpx.MockTransport(dead),
            sleep=no_sleep,
        )
    )
    assert sweep.fetched is True
    assert sweep.tx_ok is False and sweep.funding_ok is False
    assert sweep.txs == carried["txs"]
    assert sweep.funding == carried["funding"]
    assert list(sweep.funding_pending) == carried["pending"]
    assert sweep.funding_reasons == carried["reasons"]
    assert sweep.funding_cursors == carried["cursors"]
    assert sweep.state()["cursors"] == carried["cursors"]


def test_a_null_items_funding_page_leaves_the_address_pending_not_resolved():
    """Finding #5a's consequence, asserted where it would be persisted.

    `{"items": null}` off a 200 is an unread page, not a finished walk.  A
    resolved `funder=None` row for it would be handed back as `known` by the
    very next pass, so the address would never be looked at again and one bad
    minute would be frozen as "this wallet has no funder", forever — in a
    file that outlives the process.

    Two addresses on purpose: one that answers, so the pass is a pass rather
    than the total outage a single unreachable address would rightly be.
    """
    good, broken = FARM_MEMBERS[0], FARM_MEMBERS[1]

    async def handler(request: httpx.Request) -> httpx.Response:
        addr = request.url.path.rstrip("/").split("/")[-2].lower()
        if addr == broken:
            return httpx.Response(
                200, json={"items": None, "next_page_params": None}
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "from": {"hash": FUNDER},
                        "to": {"hash": addr},
                        "block_number": 90,
                    }
                ],
                "next_page_params": None,
            },
        )

    sweep = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[good, broken],
            state=None,
            transport=httpx.MockTransport(handler),
            sleep=no_sleep,
        )
    )
    assert sweep.funding_ok is True                  # one address answered
    assert sweep.funding[good]["funder"] == FUNDER
    assert broken not in sweep.funding               # NOT a funder=None row
    assert broken in sweep.funding_pending
    assert sweep.funding_reasons[broken] == "unreadable"
    # ...and the persisted state says the same thing, which is what the next
    # pass reads: the address is wanted, not answered.
    assert broken not in sweep.state()["funding"]
    assert broken in sweep.state()["pending"]


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

    The enrichment half is a **real** sweep's ``state()`` rather than a
    hand-typed stub, so the scan runs over the per-address funding cursor
    too: that is the newest thing in the file and the one whose entries carry
    a ``funder`` and a walk position.  ``groups[0]`` is given a non-empty
    ``review_members`` and the payload is given a ``published`` block, so
    the walk actually visits both new channels rather than merely being
    handed an input that happens not to contain them.
    """
    from maxpane_dashboard.data.curator_cache import CuratorCache

    routes = PagedFundingRoutes(FARM_MEMBERS[0], pages=99)
    enrichment = asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[],
            funding_wanted=[FARM_MEMBERS[0]],
            state=None,
            transport=routes.transport,
            sleep=no_sleep,
        )
    ).state()
    assert enrichment["cursors"], "guard: the scan must see a cursor"

    result = farm_analysis()
    # `build_analysis` never fills `review_members` (only the published-fold
    # builder does) -- planted directly so this walk has a real, non-empty
    # instance of the channel to visit, not an absent key.
    result.groups[0]["review_members"] = {FARM_MEMBERS[0]: ["amount", "funding"]}
    assert result.groups[0]["review_members"], "guard: the scan must see a review entry"

    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=lambda: 1_786_968_000.0)
    cache.store_analysis(
        curator_clusters.slot_payload(
            result, enrichment=enrichment, published=PUBLISHED_BLOCK
        ),
        ts=1_786_968_000.0,
    )
    cache.save()
    on_disk = json.loads(pathlib.Path(cache.path).read_text(encoding="utf-8"))
    stored = on_disk["last_good"]["clusters"]["payload"]
    assert stored["groups"][0]["review_members"], "guard: it survived to disk"
    assert stored["published"] == PUBLISHED_BLOCK, "guard: it survived to disk"

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
# Fix round 2 — M4: a hand-edited cache file is third-party input too
# ---------------------------------------------------------------------------
#
# ``fetch_enrichment`` reads six sub-payloads out of the persisted slot, four
# of them maps.  Every one was read ``(prior.get(key) or {}).items()``, which
# is a *type assumption* about bytes this module's own docstring calls
# third-party input: hand-edit ``"txs": []`` into the cache file and a list has
# no ``.items()``.  The manager's detached-sweep catch contains the
# AttributeError to a failed analysis tier with backoff — but a backoff does
# not repair a file, so the analysis panels stay dark on every sweep until
# somebody deletes ``~/.maxpane/curator_cache.json`` by hand.
#
# The entry-level half is the same doctrine one level down and was equally
# untested: ``cursors`` is the only map whose entries are re-wrapped with
# ``dict(value)``, which raises on a value that is not a mapping.

#: The four persisted maps, and the sweep attribute each one becomes.
_ENRICHMENT_MAPS = {
    "txs": "txs",
    "funding": "funding",
    "reasons": "funding_reasons",
    "cursors": "funding_cursors",
}


def _healthy_enrichment() -> dict:
    """A carried state with all four maps non-empty, JSON round-tripped.

    Round-tripped because the shapes this guards against arrive **through the
    file**: the point is bytes, not in-process objects.
    """
    tx_hash = "0x" + "1" * 64
    return json.loads(
        json.dumps(
            {
                "txs": {tx_hash: {"tx_hash": tx_hash, "nonce": 0}},
                "funding": {
                    FARM_MEMBERS[0]: {
                        "address": FARM_MEMBERS[0],
                        "funder": FUNDER,
                        "hops": 1,
                    }
                },
                "pending": [FARM_MEMBERS[1]],
                "reasons": {FARM_MEMBERS[1]: "pages"},
                "page_bound": 20,
                "cursors": {
                    FARM_MEMBERS[1]: {
                        "params": {"page": 21, "filter": "to"},
                        "funder": None,
                        "block": None,
                        "stage": "transactions",
                    }
                },
            }
        )
    )


def _carried(state) -> curator_clusters.EnrichmentSweep:
    """One sweep with neither client nor transport: carried state, no I/O.

    ``fetched=False`` is asserted by every caller below, which is what makes
    "this path opened no socket" an observation rather than a claim.
    """
    return asyncio.run(
        curator_clusters.fetch_enrichment(
            tx_wanted=[], funding_wanted=[], state=state
        )
    )


def test_every_persisted_enrichment_map_survives_a_hand_edited_cache_file():
    """The whole class, walked: each of the four maps hand-edited into a JSON
    list in turn, and each time the sweep must load, drop *that* map and keep
    the other three.

    One at a time rather than all four at once, because the failure mode being
    pinned is a map taking its siblings down with it: the read is a single
    expression per key and an exception in any one of them aborts the load of
    all of them.
    """
    sound = _carried(_healthy_enrichment())
    for key, attr in _ENRICHMENT_MAPS.items():
        assert getattr(sound, attr), f"guard: {key} is empty when the file is sound"

    for torn_key, torn_attr in _ENRICHMENT_MAPS.items():
        state = _healthy_enrichment()
        state[torn_key] = ["hand-edited into a JSON list"]
        sweep = _carried(state)

        assert sweep.fetched is False, torn_key
        # The unreadable map is dropped -- an empty map is the honest reading
        # of "these bytes are not a map", and it is re-derived next sweep.
        assert getattr(sweep, torn_attr) == {}, torn_key
        assert sweep.state()[torn_key] == {}, torn_key
        # ...and it takes nothing else with it.
        for other_key, other_attr in _ENRICHMENT_MAPS.items():
            if other_key == torn_key:
                continue
            assert getattr(sweep, other_attr) == getattr(sound, other_attr), (
                f"a torn {torn_key} lost {other_key} too"
            )
        assert sweep.funding_pending == sound.funding_pending, torn_key


def test_a_hand_edited_pending_list_is_dropped_not_iterated():
    """The fifth read, and the same class one shape over.

    ``pending`` is the one carried sequence, and it was read
    ``(prior.get("pending") or ())`` — which iterates *whatever is there*.  An
    int raises `TypeError` in the detached sweep exactly like the four maps
    did; a bare string is worse than a crash, because iterating it yields one
    single-character "address" per character and pendings **head the funding
    budget**, so five characters would crowd out five real wallets on every
    sweep, forever, and nothing would ever say so.
    """
    for torn in (5, "0x" + "ab" * 20):
        state = _healthy_enrichment()
        state["pending"] = torn
        sweep = _carried(state)

        assert sweep.fetched is False
        assert sweep.funding_pending == (), torn
        assert sweep.state()["pending"] == [], torn
        # ...and, as with the maps, it takes nothing else down with it.
        for key, attr in _ENRICHMENT_MAPS.items():
            assert getattr(sweep, attr), f"a torn pending lost {key}"


def test_a_cursor_entry_that_is_not_a_mapping_is_dropped_not_cast():
    """The entry-level guard on ``cursors``, which no test could see.

    ``cursors`` is the only carried map whose entries are re-wrapped with
    ``dict(entry)``, so a hand-edited entry that is a JSON list raises inside
    the *detached* sweep — where the traceback is a failed analysis tier and
    nothing else.  The sound sibling entry in the same map must survive, which
    is what makes this a dropped row rather than a dropped file.
    """
    good, bad = FARM_MEMBERS[1], FARM_MEMBERS[2]
    state = _healthy_enrichment()
    state["cursors"][bad] = ["page", 21]

    sweep = _carried(state)

    assert sweep.fetched is False
    assert bad not in sweep.funding_cursors
    assert sweep.funding_cursors[good]["params"]["page"] == 21
    assert bad not in sweep.state()["cursors"]


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

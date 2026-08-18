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


def test_candidates_are_the_component_members_plus_a_bounded_margin():
    """R3: the funding sweep is candidates-only, never full-population — the
    members of every tier-A component >= min_size, in chain order, plus a
    small deterministic control margin."""
    preset = curator_clusters.build_preset(RATE, MINIMUM)
    addrs, hashes = curator_clusters.candidate_targets(
        farm_events(), farm_first_deposits(), preset
    )
    assert addrs[: len(FARM_MEMBERS)] == list(FARM_MEMBERS)   # chain order
    assert set(addrs[len(FARM_MEMBERS):]) <= set(CONTROLS)    # the margin
    assert len(addrs) <= len(FARM_MEMBERS) + curator_clusters.CONTROL_MARGIN
    member_first_txs = {
        e.tx_hash for e in farm_events() if e.contributor in FARM_MEMBERS
    }
    assert set(hashes) == member_first_txs


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
    file, and no boolean rides any 'flag'-shaped key — the grade is a word
    the next sweep may revise, never a stored judgement."""
    from maxpane_dashboard.data.curator_cache import CuratorCache

    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=lambda: 1_786_968_000.0)
    cache.store_analysis(
        curator_clusters.slot_payload(
            farm_analysis(), enrichment={"txs": {}, "funding": {}, "pending": []}
        ),
        ts=1_786_968_000.0,
    )
    cache.save()
    on_disk = json.loads(pathlib.Path(cache.path).read_text(encoding="utf-8"))

    offences: list[str] = []

    def walk(node, path="$"):
        if isinstance(node, dict):
            for key, value in node.items():
                where = f"{path}.{key}"
                if key in ("is_sybil", "sybil", "verdict"):
                    offences.append(where)
                if "flag" in key and isinstance(value, bool):
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

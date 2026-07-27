"""Tests for the FWA Pool B log client.

**Zero network access, proven rather than promised.** Every ``FWALogClient`` in
this module is constructed with an injected ``httpx.AsyncClient`` whose
transport is either :class:`_RaisingTransport` (any request at all is a test
failure) or :class:`_ScriptedTransport` (only pre-registered Pool B URLs answer;
anything else raises). There is no code path here that can reach the internet.

Every fixture under ``tests/fixtures/fwa/`` is a live capture with its raw
JSON-RPC body preserved at ``response.result``, so the decoders are exercised
against bytes that actually came off mainnet.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import httpx
import pytest

from maxpane_dashboard.data.fwa_logs import (
    DRPC_BLOCK_PAGE,
    DRPC_GATEWAY,
    FWA_CORE_ADDRESS,
    LOG_ENDPOINTS,
    OUTCOME_LABELS,
    REASON_UNAVAILABLE,
    SETTLEMENT_EVENTS,
    TENDERLY_GATEWAY,
    FWALogClient,
    build_draw_events,
    collection_registry,
    config_history,
    config_params,
    crown_history,
    crown_summary,
    decode_log,
    decode_logs,
    dedupe_logs,
    dedupe_top_listing_set,
    load_config_keys,
    load_topics,
    price_history,
    settlement_mix,
    topic0,
)
from maxpane_dashboard.data.fwa_models import FWA_ROW_KEYS, FWA_SETTLEMENT_OUTCOMES

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "fwa"
MODULE_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "maxpane_dashboard"
    / "data"
    / "fwa_logs.py"
).read_text(encoding="utf-8")


def load_fixture(name: str) -> dict:
    with (FIXTURES / f"{name}.json").open(encoding="utf-8") as fh:
        return json.load(fh)


def raw_logs(name: str) -> list[dict]:
    """The untouched JSON-RPC log array at ``response.result``."""
    return load_fixture(name)["response"]["result"]


# ---------------------------------------------------------------------------
# Transports — the zero-network guarantee
# ---------------------------------------------------------------------------


class _RaisingTransport(httpx.AsyncBaseTransport):
    """Fails the test on any outbound request."""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"network access attempted: {request.url}")


class _ScriptedTransport(httpx.AsyncBaseTransport):
    """Answers registered Pool B URLs from a handler; refuses everything else."""

    def __init__(self, handlers: dict[str, Callable[[dict], httpx.Response]]):
        self._handlers = handlers
        self.requests: list[tuple[str, dict]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        payload = json.loads(request.content.decode())
        self.requests.append((url, payload))
        handler = self._handlers.get(url)
        if handler is None:
            raise AssertionError(f"unregistered endpoint contacted: {url}")
        response = handler(payload)
        response.request = request
        return response

    def calls_to(self, url: str) -> list[dict]:
        return [payload for (u, payload) in self.requests if u == url]


def offline_client(**kwargs: Any) -> FWALogClient:
    """A client wired to a transport that raises if anything touches it."""
    return FWALogClient(
        http_client=httpx.AsyncClient(transport=_RaisingTransport()), **kwargs
    )


def scripted_client(
    handlers: dict[str, Callable[[dict], httpx.Response]], **kwargs: Any
) -> tuple[FWALogClient, _ScriptedTransport]:
    transport = _ScriptedTransport(handlers)
    client = FWALogClient(
        http_client=httpx.AsyncClient(transport=transport), **kwargs
    )
    return client, transport


def ok(result: Any, request_id: int = 1) -> httpx.Response:
    return httpx.Response(
        200, json={"jsonrpc": "2.0", "id": request_id, "result": result}
    )


def rpc_error(entry: str, status: int | None = None) -> httpx.Response:
    """A verbatim recorded failure body from ``rpc_errors.json``."""
    err = load_fixture("rpc_errors")["errors"][entry]
    return httpx.Response(
        status if status is not None else err["http_status"],
        content=err["raw_body"].encode(),
        headers={"Content-Type": "application/json"},
    )


def span(payload: dict) -> tuple[int, int]:
    params = payload["params"][0]
    return int(params["fromBlock"], 16), int(params["toBlock"], 16)


# ===========================================================================
# 1. Decoders — one per event, against the live-captured fixtures
# ===========================================================================


def test_decode_acquisition_requested_matches_fixture():
    fixture = load_fixture("logs_acquisition_requested")
    decoded = decode_logs(fixture["response"]["result"])
    expected = fixture["expected_decoded"]

    assert len(decoded) == expected["log_count"] == 157

    first_expected = expected["first"]
    first = min(decoded, key=lambda e: (e["block_number"], e["log_index"]))
    assert first["event"] == "AcquisitionRequested"
    assert first["block_number"] == first_expected["blockNumber"]
    assert first["log_index"] == first_expected["logIndex"]
    assert first["request_id"] == first_expected["requestId"]
    assert first["purchaser"] == first_expected["requester"]
    # The two non-indexed data words: this is the whole price history.
    assert first["acquisition_fee_wei"] == first_expected["acquisitionFee"]
    assert first["total_weight"] == first_expected["totalWeight"]

    last_expected = expected["last"]
    last = max(decoded, key=lambda e: (e["block_number"], e["log_index"]))
    assert last["block_number"] == last_expected["blockNumber"]
    assert last["acquisition_fee_wei"] == last_expected["acquisitionFee"]
    assert last["total_weight"] == last_expected["totalWeight"]


def test_decode_every_recorded_acquisition_event():
    """All 157, not just the endpoints — a word-offset slip shows up mid-list."""
    fixture = load_fixture("logs_acquisition_requested")
    decoded = {
        (e["block_number"], e["log_index"]): e
        for e in decode_logs(fixture["response"]["result"])
    }
    for expected in fixture["expected_decoded"]["events"]:
        entry = decoded[(expected["blockNumber"], expected["logIndex"])]
        assert entry["request_id"] == expected["requestId"]
        assert entry["purchaser"] == expected["requester"]
        assert entry["acquisition_fee_wei"] == expected["acquisitionFee"]
        assert entry["total_weight"] == expected["totalWeight"]


def test_decode_nft_kept():
    logs = load_fixture("logs_settlements")["events"]["NFTKept"]["response"]["result"]
    decoded = decode_logs(logs)
    assert len(decoded) == 21
    entry = decoded[0]
    assert entry["event"] == "NFTKept"
    assert entry["outcome"] == "kept"
    # topics: listingId, purchaser, depositor -> exactly one data word.
    assert entry["listing_id"] == 0xD977
    assert entry["purchaser"] == "0xdf90937e07c60108b505fe3c542ab782e0a19ae5"
    assert entry["depositor"] == "0x732db9da8806ff6c988bd1ff808cceb11fecda44"
    assert entry["backing_wei"] == 0x2B42EABF6E1000
    assert entry["block_number"] == 0x186D0FB
    assert entry["ts"] == 0x6A652D5F


def test_decode_depositor_bid_accepted_two_data_words():
    logs = load_fixture("logs_settlements")["events"]["DepositorBidAccepted"][
        "response"
    ]["result"]
    decoded = decode_logs(logs)
    assert len(decoded) == 27
    entry = decoded[0]
    assert entry["event"] == "DepositorBidAccepted"
    assert entry["outcome"] == "bid_eth"
    assert entry["listing_id"] == 0xD6AE
    assert entry["payout_wei"] == 0x00E8866DA08CA000
    assert entry["retained_wei"] == 0x2908A9EF27E000
    # payout is 85% of backing at the live rate: a PAYOUT rate, not a discount.
    assert entry["payout_wei"] > entry["retained_wei"]


def test_decode_depositor_bid_accepted_as_tokens_three_data_words():
    logs = load_fixture("logs_settlements")["events"]["DepositorBidAcceptedAsTokens"][
        "response"
    ]["result"]
    decoded = decode_logs(logs)
    assert len(decoded) == 54
    entry = decoded[0]
    assert entry["event"] == "DepositorBidAcceptedAsTokens"
    assert entry["outcome"] == "bid_fwa"
    assert entry["listing_id"] == 0xD667
    assert entry["eth_payout_wei"] == 0x011028FA7ED32400
    assert entry["retained_wei"] == 0x30073B438EAC00
    # The third word is a $FWA amount, orders of magnitude larger than the wei
    # legs. Reading it as the payout would put an absurd number on screen.
    assert entry["token_out"] == 0xF40AFC643CDD393601
    assert entry["token_out"] > entry["eth_payout_wei"]


def test_decode_nft_relisted_two_indexed_ids():
    logs = load_fixture("logs_settlements")["events"]["NFTRelisted"]["response"][
        "result"
    ]
    decoded = decode_logs(logs)
    assert len(decoded) == 10
    entry = decoded[0]
    assert entry["event"] == "NFTRelisted"
    assert entry["outcome"] == "relist"
    # Both ids are indexed uint256 topics -- not addresses.
    assert entry["listing_id"] == 0xD740
    assert entry["new_listing_id"] == 0xDD42
    assert entry["to_depositor_wei"] == 0x00C171FC8C052000


def test_decode_unsettled_finalized_is_empty_all_time():
    event = load_fixture("logs_settlements")["events"]["UnsettledFinalized"]
    logs = event["response"]["result"]
    # Captured over FULL history, and genuinely empty.
    assert logs == []
    assert event["all_time_count"] == 0
    assert event["window_blocks"] == 65923
    assert decode_logs(logs) == []


def test_decode_top_listing_set():
    logs = raw_logs("logs_top_listing_set")
    decoded = decode_logs(logs)
    assert len(decoded) == 33
    first = decoded[0]
    assert first["event"] == "TopListingSet"
    assert first["listing_id"] == 1
    assert first["holder"] == "0xfc3c962fad2c1cc77f1a0d46e7b8a2de79a21774"
    assert first["is_vacate"] is False
    vacate = decoded[1]
    assert vacate["listing_id"] == 0
    assert vacate["holder"] == "0x" + "0" * 40
    assert vacate["is_vacate"] is True


def test_decode_top_listing_settled():
    logs = raw_logs("logs_top_listing_settled")
    decoded = decode_logs(logs)
    assert len(decoded) == 12
    entry = decoded[0]
    assert entry["event"] == "TopListingSettled"
    assert entry["listing_id"] == 0x1B
    assert entry["holder"] == "0xfc3c962fad2c1cc77f1a0d46e7b8a2de79a21774"
    assert entry["amount_wei"] == 0x06863F94D7DEE457


def test_decode_config_set():
    fixture = load_fixture("logs_config_set")
    decoded = decode_logs(fixture["response"]["result"])
    assert len(decoded) == fixture["_meta"]["log_count"] == 27
    by_id = {(e["block_number"], e["tx_hash"], e["key"]): e for e in decoded}
    for expected in fixture["expected_decoded"]["all_events"]:
        entry = by_id[
            (expected["blockNumber"], expected["txHash"].lower(), expected["key"])
        ]
        assert entry["name"] == expected["key_name"]
        assert entry["value"] == expected["value"]


def test_decode_collection_whitelist_set():
    fixture = load_fixture("logs_collection_whitelist_set")
    decoded = decode_logs(fixture["response"]["result"])
    assert len(decoded) == 51
    expected = fixture["expected_decoded"]["events"]
    for entry, exp in zip(decoded, expected):
        assert entry["event"] == "CollectionWhitelistSet"
        assert entry["collection"] == exp["collection"]
        assert entry["allowed"] is exp["whitelisted"]
        assert entry["block_number"] == exp["blockNumber"]


def test_decode_backing_updated_three_data_words():
    fixture = load_fixture("logs_backing_updated")
    decoded = decode_logs(fixture["response"]["result"])
    assert len(decoded) == fixture["_meta"]["log_count"] == 70
    entry = decoded[0]
    assert entry["event"] == "BackingUpdated"
    assert entry["listing_id"] == 0x1C9
    assert entry["depositor"] == "0x08e6adfcfbfb13666433ba03711b39c00bd2baf4"
    assert entry["old_backing_wei"] == 0x2AA1EFB94E0000
    assert entry["new_backing_wei"] == 0x2386F26FC10000
    assert entry["new_weight"] == 0x056BC75E2D63100000


def test_unknown_topic_and_malformed_log_decode_to_none():
    assert decode_log({"topics": []}) is None
    assert decode_log({"topics": ["0x" + "ff" * 32]}) is None
    # Right topic0, truncated topic list: dropped, not crashed.
    assert decode_log({"topics": [topic0("NFTKept")]}) is None


def test_topic0_hashes_come_from_the_vendored_table():
    """Never hardcoded in this module — sourced from ``abis/fwa/topics.json``."""
    topics = load_topics()
    assert len(topics) == 42
    for name in (
        "AcquisitionRequested",
        "NFTKept",
        "DepositorBidAccepted",
        "DepositorBidAcceptedAsTokens",
        "NFTRelisted",
        "UnsettledFinalized",
        "TopListingSet",
        "TopListingSettled",
        "ConfigSet",
        "CollectionWhitelistSet",
        "BackingUpdated",
        "NFTAllocated",
        "TopListingFunded",
    ):
        assert topic0(name) == topics[name]["topic0"]
    # And each fixture's recorded topic0 agrees with the table.
    for fixture_name, event in (
        ("logs_acquisition_requested", "AcquisitionRequested"),
        ("logs_top_listing_set", "TopListingSet"),
        ("logs_top_listing_settled", "TopListingSettled"),
        ("logs_config_set", "ConfigSet"),
        ("logs_collection_whitelist_set", "CollectionWhitelistSet"),
        ("logs_backing_updated", "BackingUpdated"),
    ):
        assert load_fixture(fixture_name)["_meta"]["topic0"] == topic0(event)


def test_collection_whitelist_set_is_emitted_by_fwa_core():
    """Findings §13.1 — core, not FWAWhitelist. The allowlist derives from core."""
    meta = load_fixture("logs_collection_whitelist_set")["_meta"]
    assert meta["contract"].lower() == FWA_CORE_ADDRESS.lower()
    assert load_topics()["CollectionWhitelistSet"]["contract"] == "fwa_core"
    for log in raw_logs("logs_collection_whitelist_set"):
        assert log["address"].lower() == FWA_CORE_ADDRESS.lower()


# ===========================================================================
# 2. Crown dedupe — the signature deliverable
# ===========================================================================


def test_top_listing_set_dedupes_vacate_pair():
    """33 logs, 16 vacate+set pairs, 17 actual reigns.

    A naive reader counts 33 crown changes. The vacate log carries
    ``listingId == 0`` and ``depositor == address(0)`` and is emitted in the
    *same transaction* as the set that follows it.
    """
    fixture = load_fixture("logs_top_listing_set")
    analysis = fixture["dedupe_analysis"]
    decoded = decode_logs(fixture["response"]["result"])

    assert len(decoded) == analysis["total_logs"] == 33
    assert sum(1 for e in decoded if e["is_vacate"]) == analysis["vacate_logs"] == 16

    reigns = dedupe_top_listing_set(decoded)
    assert len(reigns) == analysis["set_logs"] == 17
    assert all(not e["is_vacate"] for e in reigns)

    # The decoded sequence must match the fixture's recorded ordering exactly.
    recorded = analysis["sequence"]
    assert [(e["block_number"], e["log_index"]) for e in dedupe_logs(decoded)] == [
        (s["blockNumber"], s["logIndex"]) for s in recorded
    ]
    assert [(e["listing_id"], e["holder"]) for e in reigns] == [
        (s["listingId"], s["holder"]) for s in recorded if not s["is_vacate"]
    ]

    # Each recorded pair really is one transaction emitting vacate then set.
    for pair in analysis["pairs"]:
        assert pair["vacate"]["txHash"] == pair["set"]["txHash"]
        assert pair["vacate"]["logIndex"] + 1 == pair["set"]["logIndex"]
    assert len(analysis["pairs"]) == analysis["vacate_then_set_pairs_in_same_tx"] == 16


def test_dedupe_survives_overlapping_pages():
    """Backfill pages and the tail overlap by design; identity dedupe absorbs it."""
    decoded = decode_logs(raw_logs("logs_top_listing_set"))
    doubled = decoded + [dict(e) for e in decoded]  # every log delivered twice
    assert len(dedupe_logs(doubled)) == 33
    assert len(dedupe_top_listing_set(doubled)) == 17


def test_dedupe_is_order_independent():
    """The vacate must never win just because it arrived last."""
    decoded = decode_logs(raw_logs("logs_top_listing_set"))
    shuffled = list(reversed(decoded))
    assert dedupe_top_listing_set(shuffled) == dedupe_top_listing_set(decoded)
    # And the newest reign is a real holder, not the zero address.
    assert dedupe_top_listing_set(shuffled)[-1]["holder"] == (
        "0xb873bdcba0e9e40503a562abfeb4cce80cc33119"
    )


def test_crown_history_counts():
    """33 raw set logs, 12 payouts, 91.096 ETH — and 17 reigns after dedupe."""
    sets = decode_logs(raw_logs("logs_top_listing_set"))
    settled = decode_logs(raw_logs("logs_top_listing_settled"))

    summary = crown_summary(sets, settled)
    assert summary["raw_set_logs"] == 33
    assert summary["vacate_logs"] == 16
    assert summary["sets_total"] == 17  # what crown_sets_total carries
    assert summary["payouts_total"] == 12
    assert summary["paid_wei"] == 91095949696468281862
    assert summary["paid_eth"] == pytest.approx(91.096, abs=5e-4)
    assert summary["largest_payout_eth"] == pytest.approx(38.400795, abs=1e-6)


def test_crown_history_is_a_per_holder_aggregation():
    """WP-1's contract: one row per wallet, not one per event."""
    sets = decode_logs(raw_logs("logs_top_listing_set"))
    settled = decode_logs(raw_logs("logs_top_listing_settled"))
    rows = crown_history(sets, settled)

    assert all(set(row) == set(FWA_ROW_KEYS["crown_history"]) for row in rows)
    assert [row["rank"] for row in rows] == list(range(1, len(rows) + 1))

    holders = {row["holder"] for row in rows}
    assert len(holders) == len(rows)  # no wallet appears twice
    # 17 reigns spread over 10 wallets, not 17 rows.
    assert sum(row["reigns"] for row in rows) == 17
    assert len(rows) == 10

    # One wallet currently holds four crowns.
    max_reigns = max(row["reigns"] for row in rows)
    assert max_reigns == 4
    top = [row for row in rows if row["reigns"] == 4]
    assert len(top) == 1
    assert top[0]["holder"] == "0x60ceef10f9dd4a5d7874f22f461048ea96f475f6"

    assert sum(row["payout_eth"] for row in rows) == pytest.approx(91.096, abs=5e-4)
    assert all(row["last_block"] is not None for row in rows)


def test_crown_history_without_payouts_does_not_crash():
    sets = decode_logs(raw_logs("logs_top_listing_set"))
    rows = crown_history(sets)
    assert sum(row["reigns"] for row in rows) == 17
    assert all(row["payout_eth"] == 0.0 for row in rows)


# ===========================================================================
# 3. Settlement mix
# ===========================================================================


def test_settlement_mix_shares_match_recorded_counts():
    recorded = load_fixture("logs_settlements")["settlement_mix_all_time"]
    rows = settlement_mix(recorded["counts"])

    assert [row.outcome for row in rows] == list(FWA_SETTLEMENT_OUTCOMES)
    assert sum(row.count for row in rows) == recorded["total"] == 51522

    by_outcome = {row.outcome: row for row in rows}
    assert by_outcome["bid_fwa"].count == 38083
    assert by_outcome["bid_eth"].count == 7133
    assert by_outcome["relist"].count == 3934
    assert by_outcome["kept"].count == 2372
    assert by_outcome["forced"].count == 0

    assert by_outcome["bid_fwa"].share_pct == pytest.approx(73.92, abs=5e-3)
    assert by_outcome["bid_eth"].share_pct == pytest.approx(13.84, abs=5e-3)
    assert by_outcome["relist"].share_pct == pytest.approx(7.64, abs=5e-3)
    assert by_outcome["kept"].share_pct == pytest.approx(4.60, abs=5e-3)
    assert by_outcome["forced"].share_pct == 0.0

    # Bit-exact against the fixture's own 3-dp figures.
    for event, outcome in SETTLEMENT_EVENTS.items():
        assert round(by_outcome[outcome].share_pct, 3) == recorded["shares_pct"][event]

    # Unrounded, so the five rows sum to exactly 100.
    assert sum(row.share_pct for row in rows) == pytest.approx(100.0)


def test_settlement_mix_keeps_the_zero_row_and_survives_an_empty_total():
    empty = settlement_mix({})
    assert len(empty) == 5
    assert [row.count for row in empty] == [0] * 5
    assert [row.share_pct for row in empty] == [0.0] * 5
    # The never-fired outcome keeps its row rather than disappearing.
    assert empty[-1].outcome == "forced"
    assert all(row.label == OUTCOME_LABELS[row.outcome] for row in empty)


def test_settlement_mix_accepts_event_names_or_outcome_keys():
    by_event = settlement_mix({"NFTKept": 3, "DepositorBidAccepted": 1})
    by_key = settlement_mix({"kept": 3, "bid_eth": 1})
    assert [r.model_dump() for r in by_event] == [r.model_dump() for r in by_key]


# ===========================================================================
# 4. ConfigSet — the launch-write filter and the settable flag
# ===========================================================================


def test_config_history_filters_the_launch_write():
    """Findings §13.11: 27 logs, 21 of them one launch write, 6 real changes."""
    fixture = load_fixture("logs_config_set")
    expected = fixture["expected_decoded"]
    decoded = decode_logs(fixture["response"]["result"])
    assert len(decoded) == 27

    changes = config_history(decoded)
    assert len(changes) == expected["post_launch_change_count"] == 6
    assert all(not row["is_launch_write"] for row in changes)
    assert all(
        row["block_number"] != expected["launch_write_block"] for row in changes
    )
    assert [(row["key"], row["value"], row["block_number"]) for row in changes] == [
        (c["key"], c["value"], c["blockNumber"])
        for c in expected["post_launch_changes"]
    ]

    everything = config_history(decoded, include_launch=True)
    assert len(everything) == 27
    launch = [row for row in everything if row["is_launch_write"]]
    assert len(launch) == expected["launch_write_count"] == 21
    assert len({row["tx_hash"] for row in launch}) == 1


def test_config_history_resolves_key_15_to_crown_tithe():
    decoded = decode_logs(raw_logs("logs_config_set"))
    changes = config_history(decoded)
    key15 = [row for row in changes if row["key"] == 15]
    assert len(key15) == 1
    assert key15[0]["name"] == "TOP_LISTING_SHARE_BPS"
    assert key15[0]["value"] == 100  # docs say 500; the owner moved it mid-flight
    assert key15[0]["block_number"] == 25592190
    assert key15[0]["settable"] is True


def test_constructor_only_keys_are_marked_unsettable():
    """Findings §13.3 — keys 1 / 24 / 63 are rejected by the setters.

    The flag comes from ``config_keys.json``, never from the §8 prose table, so
    the parameter-drift widget cannot imply the owner can still move them.
    """
    keys = load_config_keys()
    for key in (1, 24, 63):
        assert keys[key]["settable"] is False
        assert keys[key]["dispatcher"] == "constructor"

    launch = config_history(
        decode_logs(raw_logs("logs_config_set")), include_launch=True
    )
    constructor_only = {row["key"]: row for row in launch if row["settable"] is False}
    assert set(constructor_only) == {1, 24, 63}
    assert constructor_only[1]["name"] == "CALLBACK_GAS_LIMIT"
    assert constructor_only[24]["name"] == "VRF_KEY_HASH"
    assert constructor_only[63]["name"] == "VRF_SERVICE"
    # And none of them is a post-launch "change" the widget would flag.
    assert not [row for row in config_history(launch) if row["key"] in (1, 24, 63)]


def test_partial_scan_cannot_mistake_a_change_for_the_launch_write():
    """A backfill that never reached the deploy block must filter nothing."""
    decoded = decode_logs(raw_logs("logs_config_set"))
    post_launch_only = [e for e in decoded if e["block_number"] > 25546793]
    assert len(post_launch_only) == 6
    assert len(config_history(post_launch_only)) == 6


def test_config_params_drift_is_measured_against_the_last_configset():
    decoded = decode_logs(raw_logs("logs_config_set"))
    # No live read -> no drift claimed. "Unknown" must not render as "changed".
    assert all(not p.is_drift for p in config_params(decoded))

    params = {p.key: p for p in config_params(decoded, {15: 250})}
    assert params[15].is_drift is True
    assert params[15].value == 250
    assert params[15].block_number == 25592190
    # Key 41 was set three times; the latest write wins.
    assert params[41].value == 1
    assert params[41].block_number == 25592194
    assert params[41].is_drift is False


# ===========================================================================
# 5. Collection registry
# ===========================================================================


def test_collection_registry_has_51():
    """Rule 7 — the live allowlist, never the docs' 16."""
    fixture = load_fixture("logs_collection_whitelist_set")
    decoded = decode_logs(fixture["response"]["result"])
    registry = collection_registry(decoded)

    assert len(registry) == fixture["expected_decoded"]["collection_count"] == 51
    assert all(row["allowed"] for row in registry.values())
    assert all(addr == addr.lower() for addr in registry)
    assert "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d" in registry  # BAYC


def test_collection_registry_last_write_wins_on_a_delisting():
    decoded = decode_logs(raw_logs("logs_collection_whitelist_set"))
    target = decoded[0]["collection"]
    delist = dict(decoded[0])
    delist.update(block_number=decoded[0]["block_number"] + 1, allowed=False,
                  log_index=0, tx_hash="0xdead")
    registry = collection_registry(decoded + [delist])
    # De-listed collections stay visible as allowed=False rather than vanishing.
    assert len(registry) == 51
    assert registry[target]["allowed"] is False


# ===========================================================================
# 6. Price history — findings §13.12
# ===========================================================================


def test_price_history_reconstructed_from_acquisition_requested():
    """The first event in block N carries the state at the END of block N-1."""
    fixture = load_fixture("logs_acquisition_requested")
    cross = fixture["cross_check_against_state"]
    decoded = decode_logs(fixture["response"]["result"])
    history = price_history(decoded)

    assert history == sorted(history, key=lambda p: p["block_number"])
    assert len({p["block_number"] for p in history}) == len(history)

    sample = next(
        p for p in history if p["block_number"] == cross["event"]["blockNumber"]
    )
    # The sample is the FIRST log in the block, not an arbitrary one.
    assert sample["log_index"] == cross["event"]["logIndex"]
    assert sample["acquisition_fee_wei"] == cross["event"]["acquisitionFee"]
    assert sample["total_weight"] == cross["event"]["totalWeight"]

    # ...and it is pinned to N-1, matching the recorded state bit-for-bit.
    prev = cross["state_at_previous_block"]
    assert sample["state_block"] == prev["block_number"]
    assert sample["state_block"] == sample["block_number"] - 1
    assert sample["acquisition_fee_wei"] == prev["acquisitionFee"]
    assert sample["total_weight"] == prev["totalWeight"]
    assert cross["acquisitionFee_matches_exactly"] is True
    assert cross["totalWeight_matches_exactly"] is True


def test_price_history_never_pins_to_the_end_of_its_own_block():
    """The deliberate counter-example: a 0.017% error that looks like rounding."""
    fixture = load_fixture("logs_acquisition_requested")
    counter = fixture["cross_check_against_state"][
        "counter_example_end_of_block_25612701"
    ]
    decoded = decode_logs(fixture["response"]["result"])

    in_block = sorted(
        (e for e in decoded if e["block_number"] == 25612701),
        key=lambda e: e["log_index"],
    )
    last = in_block[-1]
    assert last["acquisition_fee_wei"] == counter["last_event_acquisitionFee"]

    same_block_state = counter["state_acquisitionFee_at_25612701"]
    delta = same_block_state - last["acquisition_fee_wei"]
    assert delta == counter["delta_wei"] == 23673702503423
    assert abs(delta) / same_block_state == pytest.approx(0.00017, abs=2e-5)

    # price_history keeps the FIRST event of the block and labels it N-1, so the
    # 0.017% comparison is one nobody downstream is invited to make.
    sample = next(p for p in price_history(decoded) if p["block_number"] == 25612701)
    assert sample["state_block"] == 25612700
    assert sample["log_index"] == in_block[0]["log_index"]
    assert sample["events_in_block"] == len(in_block) > 1


# ===========================================================================
# 7. Draw events / activity feed
# ===========================================================================


def _allocation(block: int, log_index: int, listing_id: int, ts: int) -> dict:
    return {
        "event": "NFTAllocated",
        "block_number": block,
        "log_index": log_index,
        "tx_hash": f"0x{block:064x}",
        "ts": ts,
        "listing_id": listing_id,
        "request_id": f"0x{listing_id:064x}",
        "purchaser": "0x" + "aa" * 20,
        "depositor": "0x" + "bb" * 20,
        "value_wei": 10**17,
        "random_word": 7,
    }


def test_draw_events_pair_allocation_with_the_settlement_actually_made():
    settlements = decode_logs(
        load_fixture("logs_settlements")["events"]["DepositorBidAcceptedAsTokens"][
            "response"
        ]["result"]
    )
    settled = settlements[0]
    alloc = _allocation(
        settled["block_number"] - 5, 3, settled["listing_id"], 1_700_000_000
    )
    unsettled = _allocation(settled["block_number"] - 4, 4, 999_999, 1_700_000_100)

    rows = build_draw_events(
        [alloc, unsettled],
        settlements,
        listing_index={
            settled["listing_id"]: {
                "collection": "0xBC4CA0EDa7647A8aB7C2061c2E118A18a936f13D",
                "token_id": 42,
                "collection_name": "BAYC",
            }
        },
    )

    assert [r.block_number for r in rows] == [
        unsettled["block_number"],
        alloc["block_number"],
    ]  # newest first

    pending, matched = rows
    assert pending.outcome == ""
    assert pending.outcome_label == "Awaiting settlement"
    assert pending.amount_wei == 0
    assert pending.collection == "0x" + "0" * 40  # unresolved, never invented
    assert pending.collection_name is None

    assert matched.outcome == "bid_fwa"
    assert matched.outcome_label == OUTCOME_LABELS["bid_fwa"]
    assert matched.amount_wei == settled["eth_payout_wei"]
    assert matched.collection == "0xbc4ca0eda7647a8ab7c2061c2e118a18a936f13d"
    assert matched.collection_name == "BAYC"
    assert matched.token_id == 42

    assert set(FWA_ROW_KEYS["draw_events"]) - {"amount_eth"} <= set(
        matched.model_dump()
    )


def test_draw_events_ignore_settlements_that_predate_the_allocation():
    """A relisted listing settles more than once; a draw owns only its own."""
    settlements = decode_logs(
        load_fixture("logs_settlements")["events"]["NFTKept"]["response"]["result"]
    )
    settled = settlements[0]
    stale = dict(settled)
    stale.update(block_number=settled["block_number"] - 100, log_index=0,
                 tx_hash="0xstale", backing_wei=1)
    alloc = _allocation(settled["block_number"] - 1, 0, settled["listing_id"], 1)

    rows = build_draw_events([alloc], [stale, settled])
    assert len(rows) == 1
    assert rows[0].outcome == "kept"
    assert rows[0].amount_wei == settled["backing_wei"]


def test_draw_events_respect_limit():
    allocs = [_allocation(1000 + i, 0, i, 1_700_000_000 + i) for i in range(30)]
    rows = build_draw_events(allocs, [], limit=5)
    assert len(rows) == 5
    assert [r.block_number for r in rows] == [1029, 1028, 1027, 1026, 1025]


# ===========================================================================
# 8. Endpoint behaviour: pagination, capability, failover, degradation
# ===========================================================================

FULL_HISTORY = (25546793, 25612716)


def test_no_publicnode_in_endpoint_list():
    """Pool B only — enforced as a whitelist, not documented as a convention."""
    assert LOG_ENDPOINTS == (TENDERLY_GATEWAY, DRPC_GATEWAY)
    assert TENDERLY_GATEWAY == "https://gateway.tenderly.co/public/mainnet"
    assert DRPC_GATEWAY == "https://eth.drpc.org"

    lowered = MODULE_SOURCE.lower()
    for banned in ("publicnode", "1rpc.io", "llamarpc", "rpc.ankr.com", "cloudflare-eth"):
        assert banned not in lowered, f"{banned} must not appear in fwa_logs.py"

    # And the constructor refuses anything outside the whitelist. Findings
    # §13.10: the batching endpoint serves a ~128-block window fine, so a short
    # capability probe would wrongly green-light it and then fail the backfill.
    with pytest.raises(ValueError):
        FWALogClient(endpoints=["https://ethereum-rpc." + "publicnode" + ".com"])
    with pytest.raises(ValueError):
        FWALogClient(endpoints=["https://cloudflare-eth.com"])


def test_module_issues_no_capability_probe_at_startup():
    """Constructing a client must not touch the network at all."""
    client = offline_client()  # transport raises on any request
    assert client.status() == {
        "available": False,
        "reason": REASON_UNAVAILABLE,
        "as_of_ts": None,
        "last_seen_block": 0,
    }


async def test_tenderly_single_request_no_cap():
    from_block, to_block = FULL_HISTORY
    logs = raw_logs("logs_top_listing_set")
    client, transport = scripted_client(
        {TENDERLY_GATEWAY: lambda payload: ok(logs)}
    )

    result = await client.backfill(from_block, to_block, ["TopListingSet"])

    calls = transport.calls_to(TENDERLY_GATEWAY)
    assert len(calls) == 1  # 65,924 blocks in one shot -- no block-range cap
    assert span(calls[0]) == (from_block, to_block)
    assert calls[0]["params"][0]["address"] == FWA_CORE_ADDRESS
    assert calls[0]["params"][0]["topics"] == [[topic0("TopListingSet")]]
    assert result["available"] is True
    assert client.crown_summary()["sets_total"] == 17
    await client.close()


async def test_drpc_paginates_at_10000_blocks():
    from_block, to_block = FULL_HISTORY
    logs = raw_logs("logs_config_set")

    def drpc(payload: dict) -> httpx.Response:
        lo, hi = span(payload)
        assert hi - lo + 1 <= DRPC_BLOCK_PAGE, "exceeded the free-plan 10k cap"
        return ok([log for log in logs if lo <= int(log["blockNumber"], 16) <= hi])

    client, transport = scripted_client(
        {DRPC_GATEWAY: drpc}, endpoints=[DRPC_GATEWAY]
    )
    await client.backfill(from_block, to_block, ["ConfigSet"])

    calls = transport.calls_to(DRPC_GATEWAY)
    total = to_block - from_block + 1
    assert len(calls) == -(-total // DRPC_BLOCK_PAGE) == 7  # §8's "~7 requests"
    # Contiguous, non-overlapping pages that cover the range exactly.
    spans = [span(c) for c in calls]
    assert spans[0][0] == from_block and spans[-1][1] == to_block
    assert all(b[0] == a[1] + 1 for a, b in zip(spans, spans[1:]))
    # And nothing was lost in the paging.
    assert len(client.entries("ConfigSet")) == 27
    assert len(client.config_history()) == 6
    await client.close()


async def test_range_error_string_triggers_pagination():
    """The verbatim drpc range-cap body must shrink the window, not kill it."""
    from_block, to_block = FULL_HISTORY
    logs = raw_logs("logs_config_set")
    seen: list[tuple[int, int]] = []

    def tenderly(payload: dict) -> httpx.Response:
        lo, hi = span(payload)
        seen.append((lo, hi))
        if hi - lo + 1 > DRPC_BLOCK_PAGE:
            return rpc_error("drpc_block_range_cap")
        return ok([log for log in logs if lo <= int(log["blockNumber"], 16) <= hi])

    client, transport = scripted_client({TENDERLY_GATEWAY: tenderly})
    result = await client.backfill(from_block, to_block, ["ConfigSet"])

    assert result["available"] is True
    assert seen[0] == (from_block, to_block)  # tried wide first
    assert any(hi - lo + 1 <= DRPC_BLOCK_PAGE for lo, hi in seen)  # then shrank
    assert len(client.entries("ConfigSet")) == 27
    await client.close()


async def test_result_cap_uses_the_range_the_error_suggests():
    """Tenderly's 50k-result cap arrives inside an HTTP 200 and names a range."""
    from_block, to_block = FULL_HISTORY
    suggested_hi = 0x186C47D  # from the recorded error's `data` field
    seen: list[tuple[int, int]] = []

    def tenderly(payload: dict) -> httpx.Response:
        lo, hi = span(payload)
        seen.append((lo, hi))
        if lo == from_block and hi == to_block:
            resp = rpc_error("tenderly_result_count_cap")
            assert resp.status_code == 200, "the cap hides inside a 200"
            return resp
        return ok([])

    client, transport = scripted_client({TENDERLY_GATEWAY: tenderly})
    result = await client.backfill(from_block, to_block, ["AcquisitionRequested"])

    assert result["available"] is True
    assert seen[0] == (from_block, to_block)
    assert seen[1] == (from_block, suggested_hi)  # parsed, not halved blindly
    assert seen[-1][1] == to_block  # and the remainder still got scanned
    await client.close()


async def test_failover_from_tenderly_to_drpc():
    logs = raw_logs("logs_top_listing_settled")
    client, transport = scripted_client(
        {
            TENDERLY_GATEWAY: lambda payload: rpc_error("onerpc_rate_limit_429"),
            DRPC_GATEWAY: lambda payload: ok(logs),
        }
    )
    result = await client.backfill(25546793, 25556793, ["TopListingSettled"])
    assert result["available"] is True
    assert transport.calls_to(DRPC_GATEWAY)
    assert client.crown_summary()["payouts_total"] == 12
    await client.close()


async def test_archive_refusal_fails_over_instead_of_retrying():
    """An archive gate is not a transient error — move on to the next endpoint."""
    logs = raw_logs("logs_backing_updated")
    client, transport = scripted_client(
        {
            TENDERLY_GATEWAY: lambda payload: rpc_error("publicnode_archive_refusal"),
            DRPC_GATEWAY: lambda payload: ok(logs),
        }
    )
    result = await client.backfill(25546793, 25556793, ["BackingUpdated"])
    assert result["available"] is True
    assert len(transport.calls_to(TENDERLY_GATEWAY)) == 1  # no pointless retries
    assert len(client.backing_updates()) == 70
    await client.close()


async def test_both_endpoints_down_returns_unavailable_not_raise():
    """Pool B is the one genuine SPOF. It must degrade, never crash."""
    client, transport = scripted_client(
        {
            TENDERLY_GATEWAY: lambda payload: rpc_error("llamarpc_dead", status=521),
            DRPC_GATEWAY: lambda payload: rpc_error("onerpc_rate_limit_429"),
        }
    )

    result = await client.backfill(*FULL_HISTORY, ["TopListingSet"])

    assert result["available"] is False
    assert result["reason"] == REASON_UNAVAILABLE == "logs endpoint unavailable"
    assert transport.calls_to(TENDERLY_GATEWAY) and transport.calls_to(DRPC_GATEWAY)

    # Every derived product still answers, with empty-but-valid shapes.
    snapshot = client.snapshot()
    assert snapshot["available"] is False
    assert snapshot["reason"] == REASON_UNAVAILABLE
    assert snapshot["as_of_ts"] is None
    assert snapshot["draw_events"] == []
    assert snapshot["crown_history"] == []
    assert snapshot["crown_sets_total"] == 0
    assert len(snapshot["settlement_mix"]) == 5  # the table still renders
    assert client.config_history() == []
    assert client.collection_registry() == {}
    assert client.price_history() == []
    assert await client.head_block() == 0
    await client.close()


async def test_degraded_after_a_good_scan_keeps_last_good_with_an_as_of_marker():
    """A stale number is fine. A stale number presented as live is not."""
    logs = raw_logs("logs_top_listing_set")
    state = {"up": True}

    def tenderly(payload: dict) -> httpx.Response:
        if state["up"]:
            return ok(logs)
        return rpc_error("onerpc_rate_limit_429")

    client, transport = scripted_client(
        {TENDERLY_GATEWAY: tenderly, DRPC_GATEWAY: tenderly}
    )

    await client.backfill(*FULL_HISTORY, ["TopListingSet"])
    good = client.snapshot()
    assert good["available"] is True and good["as_of_ts"] is not None

    state["up"] = False
    result = await client.tail(FULL_HISTORY[1], head=FULL_HISTORY[1] + 100)

    assert result["available"] is False
    assert result["reason"] == REASON_UNAVAILABLE
    degraded = client.snapshot()
    assert degraded["available"] is False
    # Last-good aggregates survive, stamped with when they were captured.
    assert degraded["as_of_ts"] == good["as_of_ts"]
    assert degraded["crown_sets_total"] == 17
    assert degraded["crown_history"] == good["crown_history"]
    await client.close()


async def test_tail_resumes_from_last_seen_block():
    logs = raw_logs("logs_top_listing_set")
    client, transport = scripted_client({TENDERLY_GATEWAY: lambda p: ok(logs)})

    await client.backfill(*FULL_HISTORY, ["TopListingSet"])
    assert client.last_seen_block == FULL_HISTORY[1]

    await client.tail(head=FULL_HISTORY[1] + 500, events=["TopListingSet"])

    calls = transport.calls_to(TENDERLY_GATEWAY)
    assert len(calls) == 2
    # Resumes AT last_seen_block, not after it: a log landing later in the
    # boundary block would otherwise be lost forever.
    assert span(calls[1]) == (FULL_HISTORY[1], FULL_HISTORY[1] + 500)
    assert client.last_seen_block == FULL_HISTORY[1] + 500
    # Re-delivering the same 33 logs must not inflate the reign count.
    assert client.crown_summary()["sets_total"] == 17
    await client.close()


async def test_tail_uses_head_block_when_not_given_one():
    logs = raw_logs("logs_config_set")

    def tenderly(payload: dict) -> httpx.Response:
        if payload["method"] == "eth_blockNumber":
            return ok(hex(25612716))
        return ok(logs)

    client, transport = scripted_client({TENDERLY_GATEWAY: tenderly})
    await client.tail(25546793, events=["ConfigSet"])
    methods = [p["method"] for p in transport.calls_to(TENDERLY_GATEWAY)]
    assert methods == ["eth_blockNumber", "eth_getLogs"]
    assert client.last_seen_block == 25612716
    await client.close()


async def test_backfill_uses_one_or_filter_for_all_event_types():
    client, transport = scripted_client({TENDERLY_GATEWAY: lambda p: ok([])})
    await client.backfill(*FULL_HISTORY)
    calls = transport.calls_to(TENDERLY_GATEWAY)
    assert len(calls) == 1  # one pass, not one per event type
    filters = calls[0]["params"][0]["topics"]
    assert len(filters) == 1 and isinstance(filters[0], list)
    assert len(filters[0]) == 14
    assert topic0("AcquisitionRequested") in filters[0]
    assert topic0("CollectionWhitelistSet") in filters[0]
    await client.close()


async def test_full_backfill_populates_every_derived_product():
    """One mixed OR-filter response, all six products, all from Pool B."""
    mixed = (
        raw_logs("logs_top_listing_set")
        + raw_logs("logs_top_listing_settled")
        + raw_logs("logs_config_set")
        + raw_logs("logs_collection_whitelist_set")
        + raw_logs("logs_backing_updated")
        + raw_logs("logs_acquisition_requested")
    )
    for event in load_fixture("logs_settlements")["events"].values():
        mixed += event["response"]["result"]

    client, _ = scripted_client({TENDERLY_GATEWAY: lambda p: ok(mixed)})
    await client.backfill(*FULL_HISTORY)
    snapshot = client.snapshot()

    assert snapshot["available"] is True
    assert snapshot["crown_sets_total"] == 17
    assert snapshot["crown_payouts_total"] == 12
    assert snapshot["crown_paid_eth"] == pytest.approx(91.096, abs=5e-4)
    assert len(snapshot["config_history"]) == 6
    assert len(snapshot["allowed_collections"]) == 51
    assert len(snapshot["settlement_mix"]) == 5
    assert len(snapshot["price_history"]) > 0
    assert len(snapshot["backing_updates"]) == 70
    # Settlement counts are the ones in this scan's window, not fabricated.
    counts = snapshot["event_counts"]
    assert counts["NFTKept"] == 21
    assert counts["DepositorBidAcceptedAsTokens"] == 54
    assert counts["UnsettledFinalized"] == 0
    await client.close()


async def test_backing_updates_provide_the_sweep_invalidation_signal():
    logs = raw_logs("logs_backing_updated")
    client, _ = scripted_client({TENDERLY_GATEWAY: lambda p: ok(logs)})
    await client.backfill(*FULL_HISTORY, ["BackingUpdated"])

    everything = client.backing_updates()
    assert len(everything) == 70
    cutoff = everything[35]["block_number"]
    recent = client.backing_updates(since=cutoff)
    assert 0 < len(recent) < 70
    assert all(e["block_number"] >= cutoff for e in recent)
    assert client.backing_invalidated_since(cutoff) == {
        e["listing_id"] for e in recent
    }
    await client.close()


# ===========================================================================
# 9. Persistence handoff (WP-9's cache owns the file; this owns the shape)
# ===========================================================================


async def test_export_import_round_trip_restores_aggregates_but_not_availability():
    logs = raw_logs("logs_top_listing_set") + raw_logs("logs_top_listing_settled")
    client, _ = scripted_client({TENDERLY_GATEWAY: lambda p: ok(logs)})
    await client.backfill(*FULL_HISTORY, ["TopListingSet", "TopListingSettled"])
    state = json.loads(json.dumps(client.export_state()))  # must be serializable
    await client.close()

    restored = offline_client()  # nothing may touch the network
    assert restored.import_state(state) is True
    assert restored.crown_summary()["sets_total"] == 17
    assert restored.crown_summary()["payouts_total"] == 12
    assert restored.last_seen_block == FULL_HISTORY[1]
    assert restored.as_of_ts == state["as_of_ts"]
    # Cached rows are last-good data, not proof the endpoint is up.
    assert restored.available is False
    assert restored.unavailable_reason == REASON_UNAVAILABLE


async def test_snapshot_is_json_serializable_with_a_documented_unit_boundary():
    """The exact handoff WP-12 hands to ``FWACache.set_log_aggregates``."""
    mixed = raw_logs("logs_top_listing_set") + raw_logs("logs_top_listing_settled")
    for event in load_fixture("logs_settlements")["events"].values():
        mixed += event["response"]["result"]

    client, _ = scripted_client({TENDERLY_GATEWAY: lambda p: ok(mixed)})
    await client.backfill(*FULL_HISTORY)
    snapshot = client.snapshot()

    json.dumps(snapshot)  # must survive the cache round trip unmodified

    # draw_events stay wei-native: the manager owns the one wei -> ETH step.
    for row in snapshot["draw_events"]:
        assert "amount_wei" in row and "amount_eth" not in row
        assert isinstance(row["amount_wei"], int)
    # crown_history has no model behind it, so it IS the presentation payload.
    for row in snapshot["crown_history"]:
        assert set(row) == set(FWA_ROW_KEYS["crown_history"])
        assert isinstance(row["payout_eth"], float)
    # ...and the exact integer total is still reachable.
    assert client.crown_summary()["paid_wei"] == 91095949696468281862

    for row in snapshot["settlement_mix"]:
        assert set(row) == set(FWA_ROW_KEYS["settlement_mix"])
    await client.close()


def test_import_state_rejects_garbage_without_raising():
    client = offline_client()
    assert client.import_state(None) is False
    assert client.import_state({}) is False
    assert client.import_state({"events": "nope"}) is False
    assert client.available is False

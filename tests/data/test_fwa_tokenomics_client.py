"""Offline transport tests for FWA NETWORK state and token logs."""

from __future__ import annotations

import json
from typing import Any, Callable

import httpx
import pytest
from pydantic import ValidationError

import maxpane_dashboard.data.fwa_tokenomics_client as module
from maxpane_dashboard.data.evm_abi import (
    encode_address,
    encode_uint,
    strip0x,
)
from maxpane_dashboard.data.fwa_client import MULTICALL3
from maxpane_dashboard.data.fwa_ecosystem_addresses import OfficialDeployment
from maxpane_dashboard.data.fwa_logs import TENDERLY_GATEWAY
from maxpane_dashboard.data.fwa_tokenomics_client import (
    BOUGHT_TOPIC,
    BUYBACK_ROUTED_TOPIC,
    BURN_RECIPIENT_TOPICS,
    DEPENDENCIES,
    STATE_CALLS,
    TOKEN_TRANSFER_TOPIC,
    BuybackEvent,
    FWATokenomicsClient,
    FWATokenomicsLogClient,
    TokenomicsState,
    runtime_codehash,
)
from maxpane_dashboard.data.keccak import keccak256_hex
from tests.fwa_ecosystem_fixtures import (
    DenyNetworkTransport,
    FixedClock,
    load_fwa_ecosystem_fixture,
)


STATE = load_fwa_ecosystem_fixture("core/state_snapshot.json")
LOGS = load_fwa_ecosystem_fixture("core/flow_logs.json")


class RecordingTransport(httpx.MockTransport):
    def __init__(self, handler: Callable[[dict[str, Any]], httpx.Response]) -> None:
        self.payloads: list[dict[str, Any]] = []

        def dispatch(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            self.payloads.append(payload)
            return handler(payload)

        super().__init__(dispatch)


def _ok(payload: dict[str, Any], result: Any) -> httpx.Response:
    return httpx.Response(
        200,
        json={"jsonrpc": "2.0", "id": payload.get("id"), "result": result},
    )


def _decode_aggregate(data: str) -> list[tuple[str, str]]:
    raw = strip0x(data)
    assert raw[:8] == "82ad56cb"
    body = raw[8:]
    array_offset = int(body[:64], 16) * 2
    count = int(body[array_offset : array_offset + 64], 16)
    base = array_offset + 64
    calls: list[tuple[str, str]] = []
    for index in range(count):
        offset = int(body[base + index * 64 : base + (index + 1) * 64], 16) * 2
        start = base + offset
        target = "0x" + body[start + 24 : start + 64]
        calldata_offset = int(body[start + 128 : start + 192], 16) * 2
        calldata_start = start + calldata_offset
        length = int(body[calldata_start : calldata_start + 64], 16)
        calldata = "0x" + body[
            calldata_start + 64 : calldata_start + 64 + length * 2
        ]
        calls.append((target.lower(), calldata.lower()))
    return calls


def _aggregate_result(results: list[tuple[bool, str]]) -> str:
    tuples: list[str] = []
    for success, data in results:
        raw = strip0x(data)
        padded = raw + "0" * ((64 - len(raw) % 64) % 64)
        tuples.append(
            encode_uint(1 if success else 0)
            + encode_uint(64)
            + encode_uint(len(raw) // 2)
            + padded
        )
    offsets: list[int] = []
    cursor = len(tuples) * 32
    for encoded in tuples:
        offsets.append(cursor)
        cursor += len(encoded) // 2
    return (
        "0x"
        + encode_uint(32)
        + encode_uint(len(tuples))
        + "".join(encode_uint(offset) for offset in offsets)
        + "".join(tuples)
    )


def _state_client(
    transport: httpx.MockTransport,
    *,
    clock: FixedClock | None = None,
) -> FWATokenomicsClient:
    return FWATokenomicsClient(
        primary_rpc="https://state.invalid",
        fallback_rpcs=["https://state-fallback.invalid"],
        http_client=httpx.AsyncClient(transport=transport),
        inter_call_delay=0.0,
        backoff_seconds=(0.0,),
        clock=clock or FixedClock(STATE["observed_at"]),
    )


def _state_handler(
    *,
    changes: dict[str, int] | None = None,
    failed: set[str] | None = None,
    short: set[str] | None = None,
) -> tuple[RecordingTransport, list[dict[str, Any]]]:
    values = {**STATE["state"], **(changes or {})}
    failed = failed or set()
    short = short or set()
    quote_calls: list[dict[str, Any]] = []
    by_call = {
        (spec.address.lower(), spec.calldata.lower()): spec.key for spec in STATE_CALLS
    }

    def handler(payload: dict[str, Any]) -> httpx.Response:
        method = payload["method"]
        if method == "eth_blockNumber":
            return _ok(payload, hex(STATE["block_number"]))
        if method == "eth_gasPrice":
            return _ok(payload, hex(STATE["gas_price_wei"]))
        assert method == "eth_call"
        call, block_tag = payload["params"]
        assert block_tag == hex(STATE["block_number"])
        if call["to"].lower() == MULTICALL3:
            encoded: list[tuple[bool, str]] = []
            for inner in _decode_aggregate(call["data"]):
                key = by_call[inner]
                if key in failed:
                    encoded.append((False, "0x"))
                elif key in short:
                    encoded.append((True, "0x01"))
                else:
                    encoded.append((True, "0x" + encode_uint(values[key])))
            return _ok(payload, _aggregate_result(encoded))
        assert call["to"].lower() == module.FWA_CORE
        assert call["data"] == module.SELECTORS["quoteAcquisitionPrice()"]
        quote_calls.append(call)
        quote = STATE["quote"]
        return _ok(
            payload,
            "0x"
            + encode_uint(quote["fee_wei"])
            + encode_uint(quote["vrf_wei"])
            + encode_uint(quote["total_wei"]),
        )

    return RecordingTransport(handler), quote_calls


def _quantity(value: int) -> str:
    return hex(value)


def _topic_address(address: str) -> str:
    return "0x" + strip0x(address).rjust(64, "0")


def _words(*values: int) -> str:
    return "0x" + "".join(encode_uint(value) for value in values)


def _raw_flow_logs() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    buy = LOGS["buyback"]
    bought = {
        "address": module.FWA_TOKEN,
        "blockNumber": _quantity(buy["block_number"]),
        "blockTimestamp": _quantity(buy["block_timestamp"]),
        "transactionHash": buy["tx_hash"],
        "logIndex": _quantity(buy["bought_log_index"]),
        "topics": [BOUGHT_TOPIC, _topic_address(buy["caller"])],
        "data": _words(
            buy["eth_spent_wei"],
            buy["amount_bought_wei"],
            buy["caller_reward_wei"],
        ),
    }
    routed = {
        "address": module.FWA_TOKEN,
        "blockNumber": _quantity(buy["block_number"]),
        "blockTimestamp": _quantity(buy["block_timestamp"]),
        "transactionHash": buy["tx_hash"],
        "logIndex": _quantity(buy["routed_log_index"]),
        "topics": [BUYBACK_ROUTED_TOPIC],
        "data": _words(
            buy["to_depositors_wei"],
            buy["to_purchasers_wei"],
            buy["burned_wei"],
        ),
    }
    burns: list[dict[str, Any]] = []
    for row in LOGS["burns"]:
        burns.append(
            {
                "address": module.FWA_TOKEN,
                "blockNumber": _quantity(row["block_number"]),
                "blockTimestamp": _quantity(row["block_timestamp"]),
                "transactionHash": row["tx_hash"],
                "logIndex": _quantity(row["log_index"]),
                "topics": [
                    TOKEN_TRANSFER_TOPIC,
                    _topic_address("0x" + "12" * 20),
                    _topic_address(row["recipient"]),
                ],
                "data": _words(row["amount_wei"]),
            }
        )
    return [bought, routed, dict(bought)], burns + [dict(burns[0])]


def test_topic_preimages_and_selectors_match_vendored_metadata() -> None:
    assert BOUGHT_TOPIC == keccak256_hex(
        b"Bought(address,uint256,uint256,uint256)"
    )
    assert BUYBACK_ROUTED_TOPIC == keccak256_hex(
        b"BuybackRouted(uint256,uint256,uint256)"
    )
    assert TOKEN_TRANSFER_TOPIC == keccak256_hex(
        b"Transfer(address,address,uint256)"
    )
    assert STATE["state"]["route_purchaser_bps"] == 4000
    # All immutable selectors used here are also present in the vendored table.
    with open("maxpane_dashboard/abis/fwa/selectors.json", encoding="utf-8") as handle:
        vendored = json.load(handle)
    assert vendored["routeDepositorBps()"] == module.SEL_ROUTE_DEPOSITOR_BPS
    assert vendored["routePurchaserBps()"] == module.SEL_ROUTE_PURCHASER_BPS
    assert vendored["routeBurnBps()"] == module.SEL_ROUTE_BURN_BPS
    assert vendored["CALLER_REWARD_BPS()"] == module.SEL_CALLER_REWARD_BPS


def test_strict_wei_models_reject_floats() -> None:
    data = {
        "observed_at": STATE["observed_at"],
        "state_block": STATE["block_number"],
        "chain_head": STATE["block_number"],
        "total_supply_wei": 1.0,
    }
    with pytest.raises(ValidationError):
        TokenomicsState(**data)
    buy = LOGS["buyback"]
    with pytest.raises(ValidationError):
        BuybackEvent(
            block_number=buy["block_number"],
            block_timestamp=buy["block_timestamp"],
            observed_at=LOGS["observed_at"],
            tx_hash=buy["tx_hash"],
            bought_log_index=10,
            routed_log_index=11,
            caller=buy["caller"],
            eth_spent_wei=1.0,
            amount_bought_wei=1,
            caller_reward_wei=1,
            to_depositors_wei=1,
            to_purchasers_wei=1,
            burned_wei=1,
        )


async def test_state_batch_and_quote_are_pinned_with_required_gas_context() -> None:
    transport, quote_calls = _state_handler(changes=STATE["mutation"])
    client = _state_client(transport)
    result = await client.fetch_state(
        block_number=STATE["block_number"],
        gas_price_wei=STATE["gas_price_wei"],
    )

    assert result.state_block == STATE["block_number"]
    assert result.settlement_payout_bps == 8750
    assert result.crown_share_bps == 75
    assert result.route_purchaser_bps == 4000
    assert result.route_depositor_bps == 3000
    assert result.route_burn_bps == 3000
    assert result.quote_total_wei == STATE["quote"]["total_wei"]
    assert result.failed_fields == ()
    assert quote_calls == [
        {
            "to": module.FWA_CORE,
            "data": module.SELECTORS["quoteAcquisitionPrice()"],
            "gas": "0x200000",
            "gasPrice": hex(STATE["gas_price_wei"]),
        }
    ]
    assert all(
        payload["params"][1] == hex(STATE["block_number"])
        for payload in transport.payloads
        if payload["method"] == "eth_call"
    )
    await client.close()


async def test_failed_subcalls_are_none_while_measured_zero_stays_zero() -> None:
    transport, _ = _state_handler(
        failed={"refund_credit_total_wei"},
        short={"crown_share_bps"},
    )
    client = _state_client(transport)
    result = await client.fetch_state(
        block_number=STATE["block_number"],
        gas_price_wei=STATE["gas_price_wei"],
    )
    assert result.refund_credit_total_wei is None
    assert result.crown_share_bps is None
    assert result.accrued_owner_fees_wei == 0
    assert "refund_credit_total_wei" in result.failed_fields
    assert "crown_share_bps" in result.failed_fields
    await client.close()


async def test_failed_head_returns_a_complete_none_snapshot_without_quote() -> None:
    def handler(payload: dict[str, Any]) -> httpx.Response:
        return httpx.Response(200, json={"error": {"code": -32000, "message": "down"}})

    transport = RecordingTransport(handler)
    client = _state_client(transport)
    result = await client.fetch_state()
    assert result.state_block is None
    assert result.active_listings is None
    assert result.quote_total_wei is None
    assert {payload["method"] for payload in transport.payloads} == {"eth_blockNumber"}
    await client.close()


async def test_integrity_reads_code_and_dependencies_at_the_same_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    code = "0x6001600055"
    deployment = OfficialDeployment(
        role="core",
        address=module.FWA_CORE,
        deployment_block=1,
        runtime_codehash=runtime_codehash(code),
        abi_resource="abis/fwa/fwa_core.json",
    )
    monkeypatch.setattr(module, "OFFICIAL_DEPLOYMENTS", (deployment,))
    wrong = "0x" + "99" * 20

    def handler(payload: dict[str, Any]) -> httpx.Response:
        if payload["method"] == "eth_getCode":
            assert payload["params"][1] == hex(STATE["block_number"])
            return _ok(payload, code)
        call, block_tag = payload["params"]
        assert block_tag == hex(STATE["block_number"])
        results: list[tuple[bool, str]] = []
        by_call = {
            (spec.address.lower(), spec.selector.lower()): spec for spec in DEPENDENCIES
        }
        for inner in _decode_aggregate(call["data"]):
            spec = by_call[inner]
            if spec.key == "rewards.fwa":
                results.append((True, "0x01"))
                continue
            actual = wrong if spec.key == "core.rewards" else spec.expected
            results.append((True, "0x" + encode_address(actual)))
        return _ok(payload, _aggregate_result(results))

    transport = RecordingTransport(handler)
    client = _state_client(transport)
    result = await client.fetch_official_integrity(STATE["block_number"])
    assert result.codehash_matches == {"core": True}
    assert result.dependency_matches["core.rewards"] is False
    assert result.dependency_matches["core.vrfService"] is True
    assert result.dependency_matches["rewards.fwa"] is None
    assert result.status_for("core") == "mismatch"
    assert result.status_for("rewards") == "unknown"
    await client.close()


def test_runtime_codehash_distinguishes_bad_hex_from_empty_code() -> None:
    assert runtime_codehash("not hex") is None
    assert runtime_codehash("0x0") is None
    assert runtime_codehash("0x") == keccak256_hex(b"")


async def test_log_client_decodes_pairs_burns_and_overlap_dedupes() -> None:
    buyback_logs, burn_logs = _raw_flow_logs()

    def handler(payload: dict[str, Any]) -> httpx.Response:
        params = payload["params"][0]
        assert params["address"] == module.FWA_TOKEN
        topics = params["topics"]
        result = buyback_logs if isinstance(topics[0], list) else burn_logs
        return _ok(payload, result)

    transport = RecordingTransport(handler)
    client = FWATokenomicsLogClient(
        endpoints=[TENDERLY_GATEWAY],
        http_client=httpx.AsyncClient(transport=transport),
        clock=FixedClock(LOGS["observed_at"]),
        min_call_interval=0.0,
    )
    result = await client.fetch_flow_logs(
        LOGS["from_block"], LOGS["to_block"], history_complete=True
    )
    assert result.buybacks_available and result.burns_available
    assert len(result.buybacks) == 1
    assert len(result.burns) == 3
    event = result.buybacks[0]
    assert event.eth_spent_wei == LOGS["buyback"]["eth_spent_wei"]
    assert event.to_purchasers_wei == LOGS["buyback"]["to_purchasers_wei"]
    assert len(transport.payloads) == 2
    assert transport.payloads[0]["params"][0]["topics"] == [
        [BOUGHT_TOPIC, BUYBACK_ROUTED_TOPIC]
    ]
    assert transport.payloads[1]["params"][0]["topics"] == [
        TOKEN_TRANSFER_TOPIC,
        None,
        list(BURN_RECIPIENT_TOPICS),
    ]
    await client.close()


async def test_log_groups_degrade_independently() -> None:
    _buyback_logs, burn_logs = _raw_flow_logs()

    def handler(payload: dict[str, Any]) -> httpx.Response:
        topics = payload["params"][0]["topics"]
        if isinstance(topics[0], list):
            return httpx.Response(
                200,
                json={
                    "jsonrpc": "2.0",
                    "id": payload["id"],
                    "error": {"code": -32603, "message": "unavailable"},
                },
            )
        return _ok(payload, burn_logs)

    client = FWATokenomicsLogClient(
        endpoints=[TENDERLY_GATEWAY],
        http_client=httpx.AsyncClient(transport=RecordingTransport(handler)),
        clock=FixedClock(LOGS["observed_at"]),
        min_call_interval=0.0,
    )
    result = await client.fetch_flow_logs(1, 2, history_complete=False)
    assert result.buybacks_available is False
    assert result.buybacks == ()
    assert result.burns_available is True
    assert len(result.burns) == 3
    assert result.unavailable_reason == "buyback logs unavailable"
    await client.close()


def test_log_pool_rejects_the_state_batching_endpoint() -> None:
    with pytest.raises(ValueError, match="not a Pool B"):
        FWATokenomicsLogClient(
            endpoints=["https://ethereum-rpc.publicnode.com"],
            http_client=httpx.AsyncClient(transport=DenyNetworkTransport()),
        )

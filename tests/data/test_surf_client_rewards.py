"""F-S5: ``SurfClient.fetch_seat_rewards`` -- a seat's IMD rewards, keyless.

Zero network: every request goes through an ``httpx.MockTransport`` serving the
committed capture for seat 420 (``tests/fixtures/surf/client/seat420_*``,
2026-10-02). A reward is IMD reaching the owner from a known payer: today a
``disperseToken`` transaction **sent by** ``DEV_WALLET`` (surfsurf.eth) through
Disperse. Anything the read cannot establish fails the whole read (``None``):
an understated or unverified total must never look like a real one.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from maxpane_dashboard.data import surf_addresses as A
from maxpane_dashboard.data.surf_client import SEAT_REWARD_PAGE_BOUND, SurfClient
from maxpane_dashboard.data.surf_models import SeatRewards

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "surf" / "client"
PAGE = json.loads((FIX / "seat420_imd_transfers_page1.json").read_text())
CHAIN = json.loads((FIX / "seat420_reward_chain_reads.json").read_text())
OWNER = "0xe5b1275fb926613d983da33fbfe1f331b7f64f2a"
PAIRED_TS = 1789882465.536          # 2026-09-20T05:34:25.536Z, /seats pairedAt
#: The three disperse payments, 09-23 / 09-25 / 09-28 (13.8662 IMD).
REWARD_RAW = 7692307692307692307 + 3052147239263803680 + 3121794871794871794
STRANGER = "0x" + "ab" * 20


def _handler(page_items=None, senders=None, decimals=None, balance=None, pages=None,
             seen: list | None = None):
    """Blockscout GET pages + RPC batches, each overridable per test."""
    items = PAGE["items"] if page_items is None else page_items
    senders = CHAIN["tx_senders"] if senders is None else senders
    decimals = CHAIN["imd_decimals_result"] if decimals is None else decimals
    balance = CHAIN["idmd_balance_of_owner_result"] if balance is None else balance

    def handle(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(str(request.url))
        if request.method == "GET":
            assert "/token-transfers" in request.url.path, request.url
            assert request.url.params.get("token") == A.IMD_TOKEN
            assert request.url.params.get("filter") == "to"
            if pages is not None:
                return httpx.Response(200, json=pages(request))
            return httpx.Response(200, json={"items": items, "next_page_params": None})
        body = json.loads(request.content)
        out = []
        for call in body if isinstance(body, list) else [body]:
            method, params = call["method"], call["params"]
            if method == "eth_getTransactionByHash":
                sender = senders.get(params[0].lower())
                result: Any = None if sender is None else {"hash": params[0], "from": sender}
            elif method == "eth_call" and params[0]["data"] == "0x313ce567":
                assert params[0]["to"].lower() == A.IMD_TOKEN.lower()
                result = decimals
            elif method == "eth_call" and params[0]["data"].startswith("0x70a08231"):
                assert params[0]["to"].lower() == A.IDMD_NFT.lower()
                assert params[0]["data"].endswith(OWNER[2:])
                result = balance
            else:
                raise AssertionError(f"unexpected RPC {method} {params}")
            if isinstance(result, Exception):
                out.append({"jsonrpc": "2.0", "id": call["id"], "error": {"code": -32000, "message": "boom"}})
            else:
                out.append({"jsonrpc": "2.0", "id": call["id"], "result": result})
        return httpx.Response(200, json=out if isinstance(body, list) else out[0])

    return handle


def _client(handler) -> SurfClient:
    return SurfClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
                      inter_call_delay=0.0, backoff_seconds=(0.0, 0.0))


async def _read(since_ts: float = PAIRED_TS, **kw) -> SeatRewards | None:
    return await _client(_handler(**kw)).fetch_seat_rewards(OWNER, since_ts)


async def test_the_420_capture_sums_the_three_disperse_payments():
    got = await _read()
    assert got == SeatRewards(raw_total=REWARD_RAW, decimals=18, seats_held=1, transfers=3)
    assert round(got.raw_total / 10 ** got.decimals, 4) == 13.8662


async def test_transfers_from_a_non_payer_never_count_even_inside_the_window():
    """hisdudeness.eth's 25 + 50 IMD (08-21) predate pairedAt; with the window
    opened to include them they still are not rewards: the sender is no payer."""
    got = await _read(since_ts=0.0)
    assert got is not None and got.raw_total == REWARD_RAW and got.transfers == 3


async def test_a_stranger_using_the_public_disperse_contract_is_not_a_payer():
    senders = dict(CHAIN["tx_senders"])
    newest = PAGE["items"][0]["transaction_hash"].lower()
    senders[newest] = STRANGER
    got = await _read(senders=senders)
    assert got is not None and got.transfers == 2
    assert got.raw_total == REWARD_RAW - int(PAGE["items"][0]["total"]["value"])


async def test_an_unreadable_disperse_sender_fails_the_read():
    senders = dict(CHAIN["tx_senders"])
    senders.pop(PAGE["items"][1]["transaction_hash"].lower())
    assert await _read(senders=senders) is None


async def test_the_since_window_drops_older_payments():
    # 2026-09-24: only the 09-25 and 09-28 payments are at or after it.
    got = await _read(since_ts=1790208000.0)
    assert got is not None and got.transfers == 2
    assert got.raw_total == 3052147239263803680 + 3121794871794871794


async def test_paging_stops_at_the_first_row_older_than_since():
    """Page 1 ends with a row before pairedAt, so page 2 is never asked for."""
    seen: list[str] = []

    def pages(request):
        assert "block_number" not in request.url.params, "asked for a page past the window"
        return {"items": PAGE["items"], "next_page_params": {"block_number": 1, "index": 0}}

    got = await _read(pages=pages, seen=seen)
    assert got is not None and got.raw_total == REWARD_RAW
    assert sum("/token-transfers" in u for u in seen) == 1


async def test_hitting_the_page_bound_with_a_cursor_left_fails_the_read():
    newest = PAGE["items"][:1]

    def pages(_request):
        return {"items": newest, "next_page_params": {"block_number": 9, "index": 0}}

    seen: list[str] = []
    assert await _read(pages=pages, seen=seen) is None
    assert sum("/token-transfers" in u for u in seen) == SEAT_REWARD_PAGE_BOUND


async def test_a_malformed_row_fails_the_read_rather_than_dropping_it():
    items = copy.deepcopy(PAGE["items"])
    items[1]["total"]["value"] = "not-a-number"
    assert await _read(page_items=items) is None


@pytest.mark.parametrize("balance", ["0x" + "0" * 64, RuntimeError("boom")])
async def test_no_seat_held_or_an_unreadable_balance_fails_the_read(balance):
    assert await _read(balance=balance) is None


async def test_an_unreadable_decimals_fails_the_read():
    assert await _read(decimals=RuntimeError("boom")) is None


async def test_nothing_received_is_a_real_zero_with_no_sender_lookups():
    seen: list[str] = []
    got = await _read(page_items=[], seen=seen)
    assert got == SeatRewards(raw_total=0, decimals=18, seats_held=1, transfers=0)
    assert len(seen) == 2, "one transfers page and one state batch, no sender lookup"


async def test_a_row_of_another_token_fails_the_read():
    """Review I2: ``token=IMD`` is Blockscout's promise; a row it breaks is not IMD."""
    items = copy.deepcopy(PAGE["items"])
    items[0]["token"]["address_hash"] = "0x" + "11" * 20
    assert await _read(page_items=items) is None
    items[0].pop("token")
    assert await _read(page_items=items) is None


async def test_a_direct_payer_counts_without_a_sender_lookup(monkeypatch):
    payer = STRANGER
    monkeypatch.setattr(A, "REWARD_DIRECT_PAYERS", (payer,))
    items = copy.deepcopy(PAGE["items"])
    items[0]["from"]["hash"] = payer
    senders = dict(CHAIN["tx_senders"])
    senders.pop(items[0]["transaction_hash"].lower())      # never asked for
    got = await _read(page_items=items, senders=senders)
    assert got is not None and got.transfers == 3 and got.raw_total == REWARD_RAW


async def test_disperse_listed_as_direct_still_takes_the_sender_check(monkeypatch):
    monkeypatch.setattr(A, "REWARD_DIRECT_PAYERS", (A.DISPERSE,))
    senders = dict(CHAIN["tx_senders"])
    senders[PAGE["items"][0]["transaction_hash"].lower()] = STRANGER
    got = await _read(senders=senders)
    assert got is not None and got.transfers == 2


async def test_a_total_outage_is_none():
    def offline(request):
        raise httpx.ConnectError("offline", request=request)

    assert await _client(offline).fetch_seat_rewards(OWNER, PAIRED_TS) is None


@pytest.mark.parametrize("owner", ["", "0x123", "not an address", None])
async def test_a_bad_owner_issues_no_request(owner):
    def no_network(request):
        raise AssertionError(f"network: {request.url}")

    assert await _client(no_network).fetch_seat_rewards(owner, PAIRED_TS) is None


def test_the_payer_rule_is_data():
    """One constant per role: a new payer is a one-line change."""
    assert A.REWARD_DISPERSERS == (A.DEV_WALLET,)
    assert A.REWARD_DISPERSE_CONTRACTS == (A.DISPERSE,)
    assert A.REWARD_DIRECT_PAYERS == ()
    assert A.DISPERSE == "0xd15fE25eD0Dba12fE05e7029C88b10C25e8880E3"

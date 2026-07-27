"""Tests for OCMClient: uint reads, failure sentinels, and log classification.

Zero network: every test drives the client through a monkeypatched ``_rpc``.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data import ocm_client as oc
from maxpane_dashboard.data.ocm_client import OCMClient, _decode_uint256, _pad_address

_NFT = oc._NFT_ADDRESS.lower()
_OCMD = oc._OCMD_ADDRESS.lower()
_FAUCET = oc._FAUCET_ADDRESS.lower()


def _uint(value: int) -> str:
    return "0x" + f"{value:064x}"


def _topic_addr(addr: str) -> str:
    return "0x" + _pad_address(addr)


class _FakeChain:
    """Canned RPC responses keyed by method and calldata."""

    def __init__(
        self,
        *,
        total_supply: int = 4000,
        mint_cost: int = 10 * 10**18,
        ocmd_supply: int = 5000 * 10**18,
        staked: int = 1500,
        burned: int = 12,
        faucet_closed: int = 0,
        block: int = 21_000_000,
        block_ts: int = 1_700_000_000,
        logs: list | None = None,
        raise_on: tuple[str, ...] = (),
        empty_on: tuple[str, ...] = (),
    ) -> None:
        self.total_supply = total_supply
        self.mint_cost = mint_cost
        self.ocmd_supply = ocmd_supply
        self.staked = staked
        self.burned = burned
        self.faucet_closed = faucet_closed
        self.block = block
        self.block_ts = block_ts
        self.logs = logs if logs is not None else []
        self.raise_on = raise_on
        self.empty_on = empty_on
        self.calls: list[str] = []

    def _label(self, to: str, data: str) -> str:
        sel = data[:10]
        if to == _FAUCET:
            return "faucet"
        if to == _OCMD and sel == oc._SEL_TOTAL_SUPPLY:
            return "ocmd_supply"
        if to == _NFT and sel == oc._SEL_TOTAL_SUPPLY:
            return "total_supply"
        if to == _NFT and sel == oc._SEL_CURRENT_MINTING_COST:
            return "mint_cost"
        if to == _NFT and sel == oc._SEL_BALANCE_OF:
            who = data[10:].lower()
            if who == _pad_address(oc._OCMD_ADDRESS):
                return "staked"
            if who == _pad_address(oc._BURN_ADDRESS):
                return "burned"
        return "unknown"

    async def __call__(self, method: str, params: list):
        if method == "eth_blockNumber":
            self.calls.append("blockNumber")
            if "blockNumber" in self.raise_on:
                raise RuntimeError("rpc down")
            return hex(self.block)
        if method == "eth_getBlockByNumber":
            self.calls.append("getBlock")
            if "getBlock" in self.raise_on:
                raise RuntimeError("rpc down")
            return {"timestamp": hex(self.block_ts)}
        if method == "eth_getLogs":
            self.calls.append("getLogs")
            if "getLogs" in self.raise_on:
                raise RuntimeError("rpc down")
            return self.logs
        if method == "eth_call":
            to = params[0]["to"].lower()
            label = self._label(to, params[0]["data"])
            self.calls.append(label)
            if label in self.raise_on:
                raise RuntimeError("rpc down")
            if label in self.empty_on:
                return "0x"
            return _uint(
                {
                    "total_supply": self.total_supply,
                    "mint_cost": self.mint_cost,
                    "ocmd_supply": self.ocmd_supply,
                    "staked": self.staked,
                    "burned": self.burned,
                    "faucet": self.faucet_closed,
                }.get(label, 0)
            )
        raise AssertionError(f"unexpected method {method}")


def _client(chain: _FakeChain, monkeypatch) -> OCMClient:
    client = OCMClient()
    monkeypatch.setattr(client, "_rpc", chain)
    return client


# ---------------------------------------------------------------------------
# Decoding
# ---------------------------------------------------------------------------


def test_decode_uint256():
    assert _decode_uint256(_uint(0)) == 0
    assert _decode_uint256(_uint(4000)) == 4000
    assert _decode_uint256("") == 0
    assert _decode_uint256("0x") == 0
    # Extra words (a tuple return) decode to the first word only.
    assert _decode_uint256(_uint(7) + f"{99:064x}") == 7


def test_pad_address():
    padded = _pad_address("0xdeaDDeADDEaDdeaDdEAddEADDEAdDeadDEADDEaD")
    assert len(padded) == 64
    assert padded.endswith("deaddeaddeaddeaddeaddeaddeaddeaddeaddead")


# ---------------------------------------------------------------------------
# _read_uint: None means "unknown", never 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_uint_returns_value(monkeypatch):
    chain = _FakeChain()
    client = _client(chain, monkeypatch)
    assert await client._read_uint(oc._NFT_ADDRESS, oc._SEL_TOTAL_SUPPLY, "ts") == 4000
    await client.close()


@pytest.mark.asyncio
async def test_read_uint_returns_none_on_rpc_failure(monkeypatch):
    chain = _FakeChain(raise_on=("total_supply",))
    client = _client(chain, monkeypatch)
    assert await client._read_uint(oc._NFT_ADDRESS, oc._SEL_TOTAL_SUPPLY, "ts") is None
    await client.close()


@pytest.mark.asyncio
async def test_read_uint_returns_none_on_empty_returndata(monkeypatch):
    """A revert or a wrong selector answers 0x -- that is not a zero value."""
    chain = _FakeChain(empty_on=("total_supply",))
    client = _client(chain, monkeypatch)
    assert await client._read_uint(oc._NFT_ADDRESS, oc._SEL_TOTAL_SUPPLY, "ts") is None
    await client.close()


@pytest.mark.asyncio
async def test_read_uint_distinguishes_a_genuine_zero(monkeypatch):
    chain = _FakeChain(burned=0)
    client = _client(chain, monkeypatch)
    value = await client._read_uint(
        oc._NFT_ADDRESS,
        f"{oc._SEL_BALANCE_OF}{_pad_address(oc._BURN_ADDRESS)}",
        "burned",
    )
    assert value == 0 and value is not None
    await client.close()


# ---------------------------------------------------------------------------
# fetch_snapshot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_snapshot_happy_path(monkeypatch):
    chain = _FakeChain(total_supply=4000, burned=12, staked=1500)
    client = _client(chain, monkeypatch)

    snap = await client.fetch_snapshot()

    assert snap.read_failures == 0
    assert snap.collection.total_supply == 4000
    assert snap.collection.burned_count == 12  # balanceOf(0xdead)
    assert snap.collection.net_supply == 3988
    assert snap.collection.remaining == 6000
    assert snap.staking.total_staked == 1500
    assert snap.staking.ocmd_total_supply == 5000.0
    assert snap.staking.daily_emission == 1500.0
    assert snap.faucet_open is True
    await client.close()


@pytest.mark.asyncio
async def test_fetch_snapshot_flags_failed_core_reads(monkeypatch):
    chain = _FakeChain(raise_on=("total_supply", "burned"))
    client = _client(chain, monkeypatch)

    snap = await client.fetch_snapshot()

    assert snap.read_failures == 2
    assert snap.collection.total_supply == 0
    assert snap.collection.burned_count == 0
    await client.close()


@pytest.mark.asyncio
async def test_fetch_snapshot_total_outage_flags_every_core_read(monkeypatch):
    chain = _FakeChain(
        raise_on=(
            "total_supply",
            "mint_cost",
            "ocmd_supply",
            "staked",
            "burned",
            "faucet",
            "blockNumber",
        )
    )
    client = _client(chain, monkeypatch)

    snap = await client.fetch_snapshot()

    assert snap.read_failures == 4  # supply, ocmd supply, staked, burned
    assert snap.recent_events == []
    await client.close()


@pytest.mark.asyncio
async def test_fetch_snapshot_tolerates_non_core_read_failures(monkeypatch):
    """A dud mint-cost/faucet selector must not condemn the whole snapshot."""
    chain = _FakeChain(empty_on=("mint_cost", "faucet"))
    client = _client(chain, monkeypatch)

    snap = await client.fetch_snapshot()

    assert snap.read_failures == 0
    assert snap.collection.current_minting_cost == 0
    assert snap.faucet_open is True
    await client.close()


@pytest.mark.asyncio
async def test_fetch_snapshot_faucet_closed(monkeypatch):
    chain = _FakeChain(faucet_closed=1)
    client = _client(chain, monkeypatch)
    snap = await client.fetch_snapshot()
    assert snap.faucet_open is False
    await client.close()


# ---------------------------------------------------------------------------
# Activity scanning
# ---------------------------------------------------------------------------


def _log(from_addr_topic: str, to_addr_topic: str, token_id: int, block: int, tx: str):
    return {
        "topics": [
            oc._TRANSFER_TOPIC,
            from_addr_topic,
            to_addr_topic,
            "0x" + f"{token_id:064x}",
        ],
        "transactionHash": tx,
        "blockNumber": hex(block),
    }


_HOLDER = _topic_addr("0x" + "11" * 20)
_ZERO = oc._ZERO_ADDR_TOPIC
_BURN = oc._BURN_ADDR_TOPIC
_STAKE = oc._OCMD_ADDR_TOPIC


@pytest.mark.asyncio
async def test_scan_classifies_events(monkeypatch):
    block = 21_000_000
    chain = _FakeChain(
        block=block,
        logs=[
            _log(_ZERO, _HOLDER, 4001, block - 10, "0xmint"),
            _log(_HOLDER, _BURN, 4002, block - 9, "0xburn"),
            _log(_HOLDER, _STAKE, 4003, block - 8, "0xstake"),
            _log(_HOLDER, _STAKE, 4004, block - 8, "0xstake"),
            _log(_STAKE, _HOLDER, 4005, block - 7, "0xunstake"),
            _log(_HOLDER, _topic_addr("0x" + "22" * 20), 4006, block - 6, "0xxfer"),
        ],
    )
    client = _client(chain, monkeypatch)

    events = await client._scan_recent_activity(block)

    kinds = {e.event_type for e in events}
    assert kinds == {"mint", "burn", "stake", "unstake"}
    # Plain transfers are not activity.
    assert all(e.token_id != 4006 for e in events)
    # Stakes in one tx are grouped with a count.
    stake = next(e for e in events if e.event_type == "stake")
    assert stake.count == 2 and stake.token_id is None
    # Newest first.
    assert [e.block_number for e in events] == sorted(
        [e.block_number for e in events], reverse=True
    )
    await client.close()


@pytest.mark.asyncio
async def test_scan_treats_transfer_to_zero_address_as_burn(monkeypatch):
    block = 21_000_000
    chain = _FakeChain(
        block=block, logs=[_log(_HOLDER, _ZERO, 4007, block - 3, "0xburn2")]
    )
    client = _client(chain, monkeypatch)
    events = await client._scan_recent_activity(block)
    assert [e.event_type for e in events] == ["burn"]
    await client.close()


@pytest.mark.asyncio
async def test_scan_skips_malformed_logs(monkeypatch):
    block = 21_000_000
    good = _log(_ZERO, _HOLDER, 4001, block - 1, "0xmint")
    short = {"topics": [oc._TRANSFER_TOPIC, _ZERO, _HOLDER], "blockNumber": "0x1"}
    junk = {"topics": [oc._TRANSFER_TOPIC, _ZERO, _HOLDER, "0xnothex"],
            "blockNumber": "0x1"}
    chain = _FakeChain(block=block, logs=[good, short, junk])
    client = _client(chain, monkeypatch)

    events = await client._scan_recent_activity(block)

    assert len(events) == 1
    assert events[0].event_type == "mint"
    await client.close()


@pytest.mark.asyncio
async def test_scan_returns_empty_on_log_failure(monkeypatch):
    chain = _FakeChain(raise_on=("getLogs",))
    client = _client(chain, monkeypatch)
    assert await client._scan_recent_activity(21_000_000) == []
    await client.close()


@pytest.mark.asyncio
async def test_scan_estimates_timestamps_from_block_distance(monkeypatch):
    block = 21_000_000
    chain = _FakeChain(
        block=block,
        block_ts=1_700_000_000,
        logs=[_log(_ZERO, _HOLDER, 4001, block - 10, "0xmint")],
    )
    client = _client(chain, monkeypatch)
    events = await client._scan_recent_activity(block)
    assert events[0].timestamp == 1_700_000_000 - 10 * 12
    await client.close()

"""Tests for :class:`TTTManager` — scan windows, cycle wiring, degradation.

**Zero network.** The manager is built via ``__new__`` so ``__init__`` never
touches ``~/.maxpane`` or constructs a real client; a :class:`FakeClient`
stands in for every RPC/HTTP source and asserts on the ranges it was asked
for.

The centrepiece is CRIT-1: ``_scan_events`` used ``min(last + 1, current -
5000)`` where it meant ``max(...)``, pinning every 30s poll to the full
5,000-block (~16.7h) window and re-applying every event in it.
"""

from __future__ import annotations

import time
from typing import Any

import pytest

from maxpane_dashboard.data import ttt_manager as ttt_manager_mod
from maxpane_dashboard.data.ttt_cache import TTTCache
from maxpane_dashboard.data.ttt_client import (
    _DEFAULT_LOG_LOOKBACK_BLOCKS,
    _FACTORY_DEPLOY_BLOCK,
    _INCREMENTAL_LOG_LOOKBACK,
)
from maxpane_dashboard.data.ttt_manager import _REORG_MARGIN_BLOCKS, TTTManager

WEI = 10**18
TOKEN_A = "0x" + "aa" * 20
TOKEN_B = "0x" + "bb" * 20
ACTOR = "0x" + "c0" * 20
HEAD = 25_600_000        # realistic: above _FACTORY_DEPLOY_BLOCK
NOW = 1_800_000_000.0


class FakeClient:
    """Records every scan range; serves a fixed event set by block number."""

    def __init__(
        self,
        *,
        launches: list[dict] | None = None,
        deposits: list[dict] | None = None,
        buys: list[dict] | None = None,
        block_number: int = HEAD,
        factory: dict | None = None,
    ) -> None:
        self.launches = list(launches or [])
        self.deposits = list(deposits or [])
        self.buys = list(buys or [])
        self.block_number = block_number
        self.factory = factory or {
            "max_supply": 10_000,
            "total_minted": 10_000,
            "burn_count": 1_234,
            "active_shares": 8_766,
            "acc_eth_per_share": 10**27,
        }
        self.ranges: dict[str, list[tuple[int, int]]] = {
            "Launched": [], "Deposited": [], "Bought": []
        }
        self.metadata_requests: list[list[str]] = []
        self.reservoir_requests: list[list[str]] = []
        self.floor_calls = 0
        self.closed = False

    async def fetch_block_number(self) -> int:
        return self.block_number

    async def fetch_factory_state(self) -> dict:
        return dict(self.factory)

    def _window(self, name: str, events: list[dict], fb: int, tb: int) -> list[dict]:
        self.ranges[name].append((fb, tb))
        return [e for e in events if fb <= e["block_number"] <= tb]

    async def fetch_launched_events(self, fb: int, tb: int) -> list[dict]:
        return self._window("Launched", self.launches, fb, tb)

    async def fetch_deposit_events(self, fb: int, tb: int) -> list[dict]:
        return self._window("Deposited", self.deposits, fb, tb)

    async def fetch_buyback_events(
        self, addresses: list[str], fb: int, tb: int
    ) -> list[dict]:
        return self._window("Bought", self.buys, fb, tb)

    async def fetch_token_metadata(self, addrs: list[str]) -> dict:
        self.metadata_requests.append(list(addrs))
        return {a.lower(): ("SYM", 18) for a in addrs}

    async def fetch_token_reservoirs(self, addrs: list[str]) -> dict:
        self.reservoir_requests.append(list(addrs))
        return {a.lower(): 2 * WEI for a in addrs}

    async def fetch_site_market_data(self) -> dict:
        return {}

    async def fetch_market_data(self, addrs: list[str]) -> dict:
        return {}

    async def close(self) -> None:
        self.closed = True


class FakePrice:
    def __init__(self, usd: float = 3800.0) -> None:
        self.usd = usd
        self.closed = False

    async def get_eth_usd(self) -> float:
        return self.usd

    async def close(self) -> None:
        self.closed = True


def make_manager(client: FakeClient | None = None, **kw: Any) -> TTTManager:
    """Build a manager with no disk and no network."""
    mgr = TTTManager.__new__(TTTManager)
    mgr.client = client or FakeClient()
    mgr.price_client = FakePrice()
    mgr.cache = TTTCache()
    mgr._poll_interval = 30
    mgr._cycle_count = 0
    mgr._error_count = 0
    mgr._last_floor_eth = None
    mgr._last_floor_usd = None
    mgr._last_sales_24h = None
    for k, v in kw.items():
        setattr(mgr, k, v)
    return mgr


def deposit_event(block: int, *, token: str = TOKEN_A, holder: int = WEI, **kw) -> dict:
    ev = {
        "token": token,
        "sender": ACTOR,
        "total": 3 * holder,
        "holder_share": holder,
        "block_number": block,
        "log_index": 4,
        "tx_hash": "0x" + f"{block:064x}",
    }
    ev.update(kw)
    return ev


def launch_event(block: int, *, token_id: int = 42, token: str = TOKEN_A) -> dict:
    return {
        "token_id": token_id,
        "erc20_address": token,
        "launcher": ACTOR,
        "block_number": block,
        "log_index": 1,
        "tx_hash": "0x" + f"{block ^ 0xF:064x}",
    }


def buy_event(block: int, *, token: str = TOKEN_A) -> dict:
    return {
        "token": token,
        "caller": ACTOR,
        "eth_spent": WEI // 2,
        "caller_reward": WEI // 100,
        "block_number": block,
        "log_index": 2,
        "tx_hash": "0x" + f"{block ^ 0xFF:064x}",
    }


# ===========================================================================
# 1. CRIT-1 — the scan window
# ===========================================================================


async def test_first_run_starts_at_the_factory_deploy_block():
    """Discovery must not use a rolling window.

    All 121 Launched events sit ~410k-496k blocks behind head, so the old
    150k rolling lookback found none of them, advanced the watermark past
    them, and left every token-derived panel permanently empty.
    """
    client = FakeClient()
    mgr = make_manager(client)
    await mgr._scan_events(HEAD, NOW)
    assert client.ranges["Deposited"] == [(_FACTORY_DEPLOY_BLOCK, HEAD)]


async def test_first_run_covers_the_whole_known_launch_history():
    client = FakeClient()
    mgr = make_manager(client)
    await mgr._scan_events(HEAD, NOW)
    from_block, to_block = client.ranges["Launched"][0]
    # The live launch window, measured 2026-07-28.
    assert from_block <= 25_130_773 and to_block >= 25_216_572


async def test_the_default_lookback_only_bites_if_the_factory_were_older():
    """The rolling lookback is a floor of last resort, not the usual path."""
    client = FakeClient()
    mgr = make_manager(client)
    far_future = _FACTORY_DEPLOY_BLOCK + _DEFAULT_LOG_LOOKBACK_BLOCKS + 500_000
    await mgr._scan_events(far_future, NOW)
    assert client.ranges["Deposited"] == [
        (far_future - _DEFAULT_LOG_LOOKBACK_BLOCKS, far_future)
    ]


async def test_steady_state_scans_forward_from_the_watermark_not_5000_back():
    """The CRIT-1 regression, stated as the window itself.

    With the shipped ``min()`` this asserted range was
    ``(HEAD + 2 - 5000, HEAD + 2)`` — a 5,000-block rescan on every poll.
    """
    client = FakeClient()
    mgr = make_manager(client)
    mgr.cache.last_seen_block["Deposited"] = HEAD

    await mgr._scan_events(HEAD + 2, NOW)

    from_block, to_block = client.ranges["Deposited"][-1]
    assert (from_block, to_block) == (HEAD + 1 - _REORG_MARGIN_BLOCKS, HEAD + 2)
    assert to_block - from_block + 1 <= _REORG_MARGIN_BLOCKS + 2
    assert from_block > HEAD - _INCREMENTAL_LOG_LOOKBACK


async def test_the_incremental_lookback_is_a_floor_after_a_long_downtime():
    """Offline for 200k blocks: scan the last 5,000, don't page the whole gap."""
    client = FakeClient()
    mgr = make_manager(client)
    mgr.cache.last_seen_block["Deposited"] = HEAD - 200_000

    await mgr._scan_events(HEAD, NOW)

    assert client.ranges["Deposited"] == [(HEAD - _INCREMENTAL_LOG_LOOKBACK, HEAD)]


async def test_the_scan_window_never_goes_negative_near_genesis():
    client = FakeClient()
    mgr = make_manager(client)
    mgr.cache.last_seen_block["Deposited"] = 3
    await mgr._scan_events(5, NOW)
    assert client.ranges["Deposited"][-1][0] == 0


async def test_the_reorg_margin_re_covers_recent_blocks():
    """The overlap is deliberate — an event that reorged in is still caught."""
    client = FakeClient(deposits=[deposit_event(HEAD - 5)])
    mgr = make_manager(client)
    mgr.cache.last_seen_block["Deposited"] = HEAD  # already scanned past it

    await mgr._scan_events(HEAD + 1, NOW)

    mgr.cache.recompute_rolling_counters(NOW)
    assert mgr.cache.eth_to_holders_24h_wei == WEI


async def test_an_hour_of_polling_does_not_inflate_the_fee_counters():
    """CRIT-1 end to end: 120 cycles over one 1 ETH deposit reads 1 ETH.

    Before the fix this asserted 120 ETH (~120x), and the inflated value was
    persisted, so it survived restarts.
    """
    client = FakeClient(deposits=[deposit_event(HEAD - 100, holder=WEI)])
    mgr = make_manager(client)

    head = HEAD
    for _ in range(120):          # one hour at a 30s poll interval
        await mgr._scan_events(head, NOW)
        head += 2
    mgr.cache.recompute_rolling_counters(NOW)

    assert mgr.cache.eth_to_holders_24h_wei == WEI
    assert mgr.cache.per_token_fees(TOKEN_A, NOW) == (1.0, 1.0)
    assert len(mgr.cache.activity_log) == 1


async def test_an_hour_of_polling_does_not_flood_the_activity_ring():
    """Duplicate rows used to evict real history out of the 200-item buffer."""
    deposits = [deposit_event(HEAD - 500 + i, holder=WEI) for i in range(5)]
    client = FakeClient(deposits=deposits, launches=[launch_event(HEAD - 400)])
    mgr = make_manager(client)

    head = HEAD
    for _ in range(120):
        await mgr._scan_events(head, NOW)
        head += 2
    mgr.cache.recompute_rolling_counters(NOW)

    assert len(mgr.cache.activity_log) == 6      # 5 fees + 1 burn, once each
    assert mgr.cache.launches_24h == 1
    assert mgr.cache.eth_to_holders_24h_wei == 5 * WEI


async def test_repeated_polling_does_not_inflate_launch_counts():
    client = FakeClient(launches=[launch_event(HEAD - 50, token_id=7)])
    mgr = make_manager(client)
    for _ in range(30):
        await mgr._scan_events(HEAD, NOW)
    mgr.cache.recompute_rolling_counters(NOW)
    assert mgr.cache.launches_24h == 1
    assert len(mgr.cache.tokens) == 1


async def test_all_three_topics_advance_their_own_watermark():
    client = FakeClient(
        launches=[launch_event(HEAD - 10)],
        deposits=[deposit_event(HEAD - 10)],
        buys=[buy_event(HEAD - 10)],
    )
    mgr = make_manager(client)
    await mgr._scan_events(HEAD, NOW)      # discovers the token
    await mgr._scan_events(HEAD + 1, NOW)  # now Bought has targets
    assert mgr.cache.last_seen_block == {
        "Launched": HEAD + 1, "Deposited": HEAD + 1, "Bought": HEAD + 1
    }


async def test_bought_is_not_scanned_before_any_token_is_known():
    client = FakeClient(buys=[buy_event(HEAD - 10)])
    mgr = make_manager(client)
    await mgr._scan_events(HEAD, NOW)
    assert client.ranges["Bought"] == []
    assert "Bought" not in mgr.cache.last_seen_block


async def test_bought_scan_is_capped_at_200_token_addresses():
    seen: list[int] = []

    class CountingClient(FakeClient):
        async def fetch_buyback_events(self, addresses, fb, tb):
            seen.append(len(addresses))
            return []

    client = CountingClient()
    mgr = make_manager(client)
    for i in range(250):
        mgr.cache.register_token(
            token_id=i, address="0x" + f"{i:040x}", deployer=ACTOR, launch_block=1
        )
    await mgr._scan_events(HEAD, NOW)
    assert seen == [200]


async def test_a_zero_block_number_skips_scanning_entirely():
    client = FakeClient()
    mgr = make_manager(client)
    await mgr._scan_events(0, NOW)
    assert client.ranges == {"Launched": [], "Deposited": [], "Bought": []}
    assert mgr.cache.last_seen_block == {}


async def test_a_failing_topic_scan_leaves_its_watermark_alone():
    class BrokenDeposits(FakeClient):
        async def fetch_deposit_events(self, fb, tb):
            raise RuntimeError("rpc down")

    client = BrokenDeposits(launches=[launch_event(HEAD - 5)])
    mgr = make_manager(client)
    await mgr._scan_events(HEAD, NOW)
    assert mgr.cache.last_seen_block["Launched"] == HEAD
    assert "Deposited" not in mgr.cache.last_seen_block


# ===========================================================================
# 2. Block-timestamp extrapolation
# ===========================================================================


async def test_block_timestamp_extrapolates_backwards_at_12s_per_block():
    mgr = make_manager()
    assert await mgr._block_timestamp(HEAD - 100, NOW, HEAD) == int(NOW) - 1200
    assert await mgr._block_timestamp(HEAD, NOW, HEAD) == int(NOW)


async def test_block_timestamp_falls_back_to_now_without_a_head():
    mgr = make_manager()
    assert await mgr._block_timestamp(HEAD, NOW, 0) == int(NOW)
    assert await mgr._block_timestamp(0, NOW, HEAD) == int(NOW)


async def test_block_timestamp_is_clamped_at_zero():
    mgr = make_manager()
    assert await mgr._block_timestamp(0, 10.0, 10**9) >= 0


# ===========================================================================
# 3. Metadata / reservoir / market refresh
# ===========================================================================


async def test_metadata_is_fetched_only_for_tokens_missing_a_symbol():
    client = FakeClient()
    mgr = make_manager(client)
    mgr.cache.register_token(
        token_id=1, address=TOKEN_A, deployer=ACTOR, launch_block=1
    )
    mgr.cache.register_token(
        token_id=2, address=TOKEN_B, deployer=ACTOR, launch_block=1, symbol="BBB"
    )
    await mgr._fill_missing_metadata()
    assert client.metadata_requests == [[TOKEN_A.lower()]]
    assert mgr.cache.tokens[TOKEN_A.lower()].symbol == "SYM"

    await mgr._fill_missing_metadata()          # nothing left to fill
    assert len(client.metadata_requests) == 1


async def test_metadata_work_is_capped_at_50_per_cycle():
    client = FakeClient()
    mgr = make_manager(client)
    for i in range(75):
        mgr.cache.register_token(
            token_id=i, address="0x" + f"{i:040x}", deployer=ACTOR, launch_block=1
        )
    await mgr._fill_missing_metadata()
    assert len(client.metadata_requests[0]) == 50


async def test_a_failed_metadata_batch_leaves_symbols_unset():
    class Broken(FakeClient):
        async def fetch_token_metadata(self, addrs):
            raise RuntimeError("boom")

    mgr = make_manager(Broken())
    mgr.cache.register_token(
        token_id=1, address=TOKEN_A, deployer=ACTOR, launch_block=1
    )
    await mgr._fill_missing_metadata()
    assert mgr.cache.tokens[TOKEN_A.lower()].symbol is None


async def test_reservoirs_are_chunked_at_200_addresses():
    client = FakeClient()
    mgr = make_manager(client)
    for i in range(450):
        mgr.cache.register_token(
            token_id=i, address="0x" + f"{i:040x}", deployer=ACTOR, launch_block=1
        )
    await mgr._refresh_reservoirs()
    assert [len(c) for c in client.reservoir_requests] == [200, 200, 50]
    assert all(t.reservoir_wei == 2 * WEI for t in mgr.cache.tokens.values())


async def test_a_failed_reservoir_chunk_does_not_abort_the_others():
    class HalfBroken(FakeClient):
        def __init__(self):
            super().__init__()
            self.n = 0

        async def fetch_token_reservoirs(self, addrs):
            self.n += 1
            if self.n == 1:
                raise RuntimeError("chunk 1 died")
            return {a.lower(): 5 * WEI for a in addrs}

    mgr = make_manager(HalfBroken())
    for i in range(250):
        mgr.cache.register_token(
            token_id=i, address="0x" + f"{i:040x}", deployer=ACTOR, launch_block=1
        )
    await mgr._refresh_reservoirs()
    filled = [t for t in mgr.cache.tokens.values() if t.reservoir_wei == 5 * WEI]
    assert len(filled) == 50


async def test_market_data_prefers_the_site_scrape_over_dexscreener():
    class SiteFirst(FakeClient):
        def __init__(self):
            super().__init__()
            self.dex_called = False

        async def fetch_site_market_data(self):
            return {
                TOKEN_A.lower(): {
                    "price_usd": 0.01, "change_h24": 5.0,
                    "volume_h24": 1000.0, "mcap": 50000.0,
                }
            }

        async def fetch_market_data(self, addrs):
            self.dex_called = True
            return {}

    client = SiteFirst()
    mgr = make_manager(client)
    mgr.cache.register_token(
        token_id=1, address=TOKEN_A, deployer=ACTOR, launch_block=1
    )
    await mgr._refresh_market_data()
    assert client.dex_called is False
    assert mgr.cache.tokens[TOKEN_A.lower()].price_usd == 0.01
    assert mgr.cache.tokens[TOKEN_A.lower()].market_cap_usd == 50000.0


async def test_market_data_falls_back_to_dexscreener_when_the_site_fails():
    class SiteDown(FakeClient):
        async def fetch_site_market_data(self):
            raise RuntimeError("site 503")

        async def fetch_market_data(self, addrs):
            return {TOKEN_A.lower(): {"price_usd": 0.02, "change_h24": None,
                                      "volume_h24": 5.0, "mcap": 7.0}}

    mgr = make_manager(SiteDown())
    mgr.cache.register_token(
        token_id=1, address=TOKEN_A, deployer=ACTOR, launch_block=1
    )
    await mgr._refresh_market_data()
    assert mgr.cache.tokens[TOKEN_A.lower()].price_usd == 0.02


async def test_market_refresh_with_no_tokens_is_a_no_op():
    class Exploding(FakeClient):
        async def fetch_site_market_data(self):
            raise AssertionError("should not be called")

    mgr = make_manager(Exploding())
    await mgr._refresh_market_data()
    await mgr._refresh_reservoirs()


# ===========================================================================
# 4. Full cycle
# ===========================================================================


async def test_fetch_and_compute_returns_the_widget_contract():
    client = FakeClient(
        launches=[launch_event(HEAD - 20)],
        deposits=[deposit_event(HEAD - 20, holder=2 * WEI)],
    )
    mgr = make_manager(client)
    out = await mgr.fetch_and_compute()

    for key in (
        "launches", "max_supply", "unburned", "burned_pct", "launches_24h",
        "holder_pool_eth_total", "holder_pool_eth_24h", "floor_eth", "floor_usd",
        "top_tokens_by_volume", "total_mcap_usd", "total_mcap_eth",
        "burns_history", "floor_history", "volume_history",
        "fresh_launch_signal", "buybacks_ready_signal", "decay_window_signal",
        "concentration_signal", "activity_events", "top_fee_engines",
        "claim_math_scenarios", "eth_usd", "current_block",
        "last_updated_seconds_ago", "error_count", "poll_interval",
        "active_view", "holder_fee_share", "sales_24h",
    ):
        assert key in out, f"missing dashboard key {key}"

    assert out["current_block"] == HEAD
    assert out["eth_usd"] == 3800.0
    assert out["launches_24h"] == 1
    assert out["holder_pool_eth_24h"] == 2.0
    assert out["unburned"] == 8_766
    assert out["burned_pct"] == pytest.approx(12.34)


async def test_repeated_cycles_keep_the_headline_fee_number_stable():
    """The user-visible symptom of CRIT-1: 'ETH to holders 24h' climbing."""
    client = FakeClient(deposits=[deposit_event(HEAD - 30, holder=WEI)])
    mgr = make_manager(client)

    readings = []
    for i in range(10):
        client.block_number = HEAD + i * 2
        out = await mgr.fetch_and_compute()
        readings.append(out["holder_pool_eth_24h"])

    assert readings == [1.0] * 10


async def test_a_factory_outage_degrades_instead_of_raising():
    class NoFactory(FakeClient):
        async def fetch_factory_state(self):
            raise RuntimeError("all endpoints down")

    mgr = make_manager(NoFactory())
    out = await mgr.fetch_and_compute()
    assert out["error_count"] == 1
    assert out["max_supply"] == 10_000
    assert out["launches"] == 0
    assert out["unburned"] == 10_000


async def test_a_price_outage_reports_zero_and_drops_the_eth_mcap():
    class NoPrice(FakePrice):
        async def get_eth_usd(self):
            raise RuntimeError("coingecko down")

    mgr = make_manager(price_client=NoPrice())
    out = await mgr.fetch_and_compute()
    assert out["eth_usd"] == 0.0
    assert out["total_mcap_eth"] is None


async def test_aggregate_market_cap_only_counts_tokens_that_have_one():
    client = FakeClient()
    mgr = make_manager(client)
    for i, mcap in enumerate([1000.0, None, 3000.0]):
        addr = "0x" + f"{i:040x}"
        mgr.cache.register_token(
            token_id=i, address=addr, deployer=ACTOR, launch_block=1, symbol="S"
        )
        mgr.cache.update_token_market(
            addr, price_usd=1.0, change_h24=0.0, volume_h24=1.0, mcap=mcap
        )
    out = await mgr.fetch_and_compute()
    assert out["total_mcap_usd"] == 4000.0
    assert out["total_mcap_token_count"] == 2
    assert out["total_mcap_eth"] == pytest.approx(4000.0 / 3800.0)


async def test_the_leaderboard_is_ranked_by_24h_volume_and_capped_at_ten():
    client = FakeClient()
    mgr = make_manager(client)
    for i in range(12):
        addr = "0x" + f"{i:040x}"
        mgr.cache.register_token(
            token_id=i, address=addr, deployer=ACTOR, launch_block=HEAD - i,
            symbol=f"S{i}",
        )
        mgr.cache.update_token_market(
            addr, price_usd=1.0, change_h24=0.0, volume_h24=float(i), mcap=1.0
        )
    out = await mgr.fetch_and_compute()
    rows = out["top_tokens_by_volume"]
    assert len(rows) == 10
    assert [r["vol_usd_h24"] for r in rows] == [float(i) for i in range(11, 1, -1)]
    assert [r["rank"] for r in rows] == list(range(1, 11))


async def test_the_activity_feed_is_capped_at_25_and_newest_first():
    deposits = [deposit_event(HEAD - 100 + i) for i in range(40)]
    mgr = make_manager(FakeClient(deposits=deposits))
    out = await mgr.fetch_and_compute()
    blocks = [e["block_number"] for e in out["activity_events"]]
    assert len(blocks) == 25
    assert blocks == sorted(blocks, reverse=True)


def test_age_str_buckets():
    from maxpane_dashboard.data.ttt_manager import _age_str

    assert _age_str(HEAD - 10, HEAD) == "10b"
    assert _age_str(HEAD - 299, HEAD) == "299b"     # under the 300-block cutoff
    assert _age_str(HEAD - 300, HEAD) == "1h"       # 300 * 12s == exactly 1h
    assert _age_str(HEAD - 301, HEAD) == "1h"
    assert _age_str(HEAD - 3000, HEAD) == "10h"
    assert _age_str(HEAD - 30_000, HEAD) == "4d"
    assert _age_str(HEAD + 5, HEAD) == "0b"     # future block clamps


# ===========================================================================
# 5. Persistence wiring
# ===========================================================================


async def test_save_cache_and_close_are_wired_to_the_cache_and_clients(
    tmp_path, monkeypatch
):
    path = tmp_path / "ttt_cache.json"
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_FILE", path)

    client = FakeClient(deposits=[deposit_event(HEAD - 10)])
    mgr = make_manager(client)
    await mgr.fetch_and_compute()
    await mgr.close()

    assert path.exists()
    assert client.closed and mgr.price_client.closed

    revived = TTTCache()
    revived.load_from_file(str(path))
    assert revived.last_seen_block["Deposited"] == HEAD


async def test_a_restart_does_not_double_count_the_reorg_margin(
    tmp_path, monkeypatch
):
    """Save, reload, poll again: the overlapping events stay counted once."""
    path = tmp_path / "ttt_cache.json"
    monkeypatch.setattr(ttt_manager_mod, "_CACHE_FILE", path)

    deposits = [deposit_event(HEAD - 3, holder=WEI)]
    first = make_manager(FakeClient(deposits=deposits))
    await first._scan_events(HEAD, NOW)
    first.cache.recompute_rolling_counters(NOW)
    assert first.cache.eth_to_holders_24h_wei == WEI
    first.save_cache()

    second = make_manager(FakeClient(deposits=deposits))
    second.cache.load_from_file(str(path))
    await second._scan_events(HEAD + 1, NOW)   # margin re-covers HEAD-3
    second.cache.recompute_rolling_counters(NOW)
    assert second.cache.eth_to_holders_24h_wei == WEI


async def test_last_updated_seconds_ago_is_non_negative():
    mgr = make_manager()
    out = await mgr.fetch_and_compute()
    assert 0.0 <= out["last_updated_seconds_ago"] < 10.0
    assert out["poll_interval"] == 30


async def test_the_floor_metric_is_reported_unavailable_not_zero():
    """Its source is gone; the keys stay, pinned to None with a reason.

    A fabricated 0.0 would render as a real floor of zero ETH; None plus a
    reason lets a consumer say "unavailable" and say why.
    """
    from maxpane_dashboard.data.ttt_client import FLOOR_UNAVAILABLE_REASON

    mgr = make_manager()
    out = await mgr.fetch_and_compute()
    assert out["floor_eth"] is None
    assert out["floor_usd"] is None
    assert out["sales_24h"] is None
    assert out["floor_unavailable_reason"] == FLOOR_UNAVAILABLE_REASON
    assert "Reservoir" in out["floor_unavailable_reason"]


async def test_no_floor_request_is_ever_issued():
    """The dead host must not be dialled — not even once, not even to fail."""
    class FloorTrap(FakeClient):
        async def fetch_nft_floor(self):
            raise AssertionError("the floor source is gone; do not call it")

    mgr = make_manager(FloorTrap())
    for _ in range(4):
        await mgr.fetch_and_compute()

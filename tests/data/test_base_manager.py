"""Manager-layer tests for ``BaseManager`` (MEDI-13) and its failure
sentinels (MEDI-12).

MEDI-13: ``fetch_and_compute``/``_compute_overview`` build the dict that
every Base terminal widget reads via ``data.get()``.  Per-widget
``try/except`` and ``.get()`` defaults mean a key rename or a
``None``-propagation bug blanks widgets behind a warning log instead of
failing anything, and nothing in the suite exercised that contract -- only
the token-detail path (``tests/data/test_token_detail.py``) was covered.

MEDI-12: ``get_eth_price`` returned ``(0.0, 0.0)`` and
``get_dexscreener_trending`` returned ``[]`` on failure, so a
GeckoTerminal/DexScreener 429 produced a *successful* cycle carrying
zeros.  Those zeros were appended to the overview time-series and
persisted to ``~/.maxpane/base_cache.json``, where they crushed the ETH
sparkline's scale and made ``compute_volume_trend(current, prev=0.0)``
answer "Rising" on the next successful cycle.  The rule the fix follows:
a failed read is ``None``, never ``0`` -- and a ``None`` is never written
to persisted history.

Zero network: the client is replaced with a stub and the on-disk cache is
redirected to ``tmp_path``.
"""

from __future__ import annotations

import time

import pytest

from maxpane_dashboard.data import base_manager as base_manager_module
from maxpane_dashboard.data.base_manager import BaseManager
from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _token(
    symbol: str,
    *,
    price: float = 1.0,
    volume: float = 1_000_000.0,
    change: float | None = 5.0,
    buys: int = 100,
    sells: int = 50,
) -> BaseToken:
    return BaseToken(
        address=f"0x{symbol.lower():0<40}",
        name=f"{symbol} Token",
        symbol=symbol,
        price_usd=price,
        price_change_5m=None,
        price_change_1h=None,
        price_change_24h=change,
        volume_24h=volume,
        market_cap=10_000_000.0,
        fdv=None,
        liquidity=500_000.0,
        pair_address=f"0xpair{symbol.lower():0<35}",
        dex="aerodrome",
        created_at=None,
        buys_24h=buys,
        sells_24h=sells,
    )


class _FakeClient:
    """Canned-data async client mirroring BaseChainClient's surface."""

    def __init__(
        self,
        *,
        tokens: list[BaseToken] | None = None,
        eth: tuple[float | None, float | None] = (3000.0, 2.5),
        gas: float | None = 0.02,
        raise_on_snapshot: bool = False,
    ) -> None:
        self.tokens = tokens if tokens is not None else [
            _token("AAA", volume=2_000_000.0, change=12.0),
            _token("BBB", volume=1_000_000.0, change=-4.0),
            _token("CCC", volume=150_000.0, change=1.0),
        ]
        self.eth = eth
        self.gas = gas
        self.raise_on_snapshot = raise_on_snapshot
        self.closed = False
        self.fetched_at = time.time()

    async def fetch_snapshot(self, *, remote_only: bool = False) -> BaseSnapshot:
        if self.raise_on_snapshot:
            raise RuntimeError("upstream 429")
        return BaseSnapshot(
            trending_tokens=tuple(self.tokens),
            trending_pools=(),
            launches=(),
            fetched_at=self.fetched_at,
        )

    async def get_eth_price(self) -> tuple[float | None, float | None]:
        return self.eth

    async def get_base_gas_price(self) -> float | None:
        return self.gas

    def get_launch_stats(self, launches: list) -> dict:
        return {
            "total_launches_1h": 0,
            "graduated_count": 0,
            "avg_age": 0.0,
            "launch_rate_per_hour": 0.0,
        }

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def make_manager(tmp_path, monkeypatch):
    """Build a BaseManager with an isolated cache file and a fake client."""
    monkeypatch.setattr(base_manager_module, "_CACHE_DIR", tmp_path)
    monkeypatch.setattr(
        base_manager_module, "_CACHE_FILE", tmp_path / "base_cache.json"
    )

    def _build(client: _FakeClient | None = None, *, remote_only: bool = True):
        manager = BaseManager(poll_interval=30, remote_only=remote_only)
        manager.client = client or _FakeClient()
        return manager

    return _build


# ---------------------------------------------------------------------------
# MEDI-13: the widget-facing dict contract
# ---------------------------------------------------------------------------

#: Keys read by the Base terminal widgets on every cycle.
CORE_KEYS = {
    "trending_tokens", "trending_pools", "launches", "launch_stats",
    "graduated_launches", "top_gainers", "top_losers", "volume_leaders",
    "token_signals", "token_statuses", "price_histories",
    "error_count", "last_updated_seconds_ago", "poll_interval",
}

#: Additional keys the overview (remote_only) screen reads.
OVERVIEW_KEYS = {
    "top_gainer_name", "top_gainer_pct", "gainers", "losers",
    "buy_sell_signal", "volume_signal", "whale_signal", "recommendation",
    "whale_trades", "volume_history", "eth_price_history",
    "trade_count_history",
}

#: Keys that exist only when their upstream read succeeded (MEDI-12).
CONDITIONAL_KEYS = {"eth_price", "eth_change_24h", "gas_price", "total_volume"}


@pytest.mark.asyncio
async def test_core_contract_keys_present(make_manager) -> None:
    manager = make_manager(remote_only=False)
    data = await manager.fetch_and_compute()
    assert not CORE_KEYS - set(data.keys())


@pytest.mark.asyncio
async def test_overview_contract_keys_present(make_manager) -> None:
    manager = make_manager()
    data = await manager.fetch_and_compute()
    missing = (CORE_KEYS | OVERVIEW_KEYS | CONDITIONAL_KEYS) - set(data.keys())
    assert not missing, f"missing keys: {missing}"


@pytest.mark.asyncio
async def test_non_overview_mode_omits_overview_keys(make_manager) -> None:
    manager = make_manager(remote_only=False)
    data = await manager.fetch_and_compute()
    assert not (OVERVIEW_KEYS | CONDITIONAL_KEYS) & set(data.keys())


@pytest.mark.asyncio
async def test_values_are_computed_not_just_present(make_manager) -> None:
    manager = make_manager()
    data = await manager.fetch_and_compute()

    assert data["eth_price"] == 3000.0
    assert data["gas_price"] == 0.02
    assert data["total_volume"] == pytest.approx(3_150_000.0)
    assert data["top_gainer_name"] == "AAA Token (AAA)"
    assert [t.symbol for t in data["top_gainers"]][0] == "AAA"
    assert data["poll_interval"] == 30
    assert data["last_updated_seconds_ago"] >= 0
    assert len(data["whale_trades"]) == 3


@pytest.mark.asyncio
async def test_fetch_failure_raises_and_counts(make_manager) -> None:
    manager = make_manager(_FakeClient(raise_on_snapshot=True))
    with pytest.raises(RuntimeError):
        await manager.fetch_and_compute()
    assert manager._error_count == 1

    # A subsequent good cycle reports the accumulated count.
    manager.client = _FakeClient()
    data = await manager.fetch_and_compute()
    assert data["error_count"] == 1


@pytest.mark.asyncio
async def test_close_saves_cache_and_closes_client(make_manager, tmp_path) -> None:
    client = _FakeClient()
    manager = make_manager(client)
    await manager.fetch_and_compute()
    await manager.close()
    assert client.closed
    assert (tmp_path / "base_cache.json").exists()


# ---------------------------------------------------------------------------
# MEDI-12: a failed read is None, never 0 -- and is never persisted
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_eth_failure_records_no_price_point(make_manager) -> None:
    manager = make_manager(_FakeClient(eth=(None, None)))
    data = await manager.fetch_and_compute()

    assert data["eth_price_history"] == [], "a 0.0 ETH sentinel was persisted"
    assert "eth_price" not in data
    assert "eth_change_24h" not in data
    # The rest of the cycle still works -- ETH is not load-bearing.
    assert data["total_volume"] == pytest.approx(3_150_000.0)
    assert len(data["volume_history"]) == 1


@pytest.mark.asyncio
async def test_gas_failure_is_absent_not_zero(make_manager) -> None:
    manager = make_manager(_FakeClient(gas=None))
    data = await manager.fetch_and_compute()
    assert "gas_price" not in data


@pytest.mark.asyncio
async def test_empty_trending_records_no_volume_point(make_manager) -> None:
    manager = make_manager(_FakeClient(tokens=[]))
    data = await manager.fetch_and_compute()

    assert data["volume_history"] == [], "a 0.0 volume sentinel was persisted"
    assert data["trade_count_history"] == []
    assert "total_volume" not in data
    # ETH still read fine, so its point is recorded independently.
    assert len(data["eth_price_history"]) == 1


@pytest.mark.asyncio
async def test_outage_then_recovery_does_not_report_false_rising(
    make_manager,
) -> None:
    """The exact MEDI-12 sequence: a failed cycle then a good one.

    With the sentinel persisted, ``compute_volume_trend(current, 0.0)``
    answered "Rising" no matter what the real volume did.
    """
    client = _FakeClient(tokens=[])
    manager = make_manager(client)

    outage = await manager.fetch_and_compute()
    assert outage["volume_signal"] is None
    assert "unavailable" in outage["recommendation"]

    # Recovery: volume is in fact *lower* than the pre-outage level.
    client.tokens = [_token("AAA", volume=1_000.0)]
    client.fetched_at = time.time()
    recovered = await manager.fetch_and_compute()

    assert recovered["volume_signal"] != "Rising"
    assert recovered["volume_signal"] is None, (
        "there is no earlier real reading to trend against"
    )


@pytest.mark.asyncio
async def test_trend_is_computed_between_two_real_readings(make_manager) -> None:
    client = _FakeClient(tokens=[_token("AAA", volume=1_000_000.0)])
    manager = make_manager(client)
    await manager.fetch_and_compute()

    client.tokens = [_token("AAA", volume=2_000_000.0)]
    client.fetched_at = time.time()
    second = await manager.fetch_and_compute()
    assert second["volume_signal"] == "Rising"

    client.tokens = [_token("AAA", volume=500_000.0)]
    client.fetched_at = time.time()
    third = await manager.fetch_and_compute()
    assert third["volume_signal"] == "Falling"


@pytest.mark.asyncio
async def test_a_month_old_persisted_point_is_not_trended_against(
    make_manager,
) -> None:
    """Restart case: 41-day gaps were observed in the real cache."""
    client = _FakeClient(tokens=[_token("AAA", volume=1_000_000.0)])
    manager = make_manager(client)
    manager.cache.volume_history.append(
        (time.time() - 41 * 86_400, 5_000_000.0)
    )

    data = await manager.fetch_and_compute()
    assert data["volume_signal"] is None, (
        "trended against a point from a previous month"
    )


@pytest.mark.asyncio
async def test_a_skipped_cycle_still_trends(make_manager) -> None:
    """The age guard tolerates a missed poll or two; it is not a 1-cycle rule."""
    client = _FakeClient(tokens=[_token("AAA", volume=1_000_000.0)])
    manager = make_manager(client)
    manager.cache.volume_history.append((time.time() - 45.0, 500_000.0))

    data = await manager.fetch_and_compute()
    assert data["volume_signal"] == "Rising"


@pytest.mark.asyncio
async def test_no_zero_ever_reaches_the_persisted_file(
    make_manager, tmp_path
) -> None:
    """End to end: the corruption is what outlives the outage."""
    import json

    client = _FakeClient(tokens=[], eth=(None, None), gas=None)
    manager = make_manager(client)
    await manager.fetch_and_compute()
    await manager.close()

    saved = json.loads((tmp_path / "base_cache.json").read_text())
    assert saved["overview_volume"] == []
    assert saved["overview_eth_price"] == []
    assert saved["overview_trade_count"] == []

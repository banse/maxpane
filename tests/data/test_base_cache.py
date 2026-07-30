"""Tests for ``BaseTokenCache`` growth bounds (LOW-6).

``_price_histories`` used to be an uncapped dict: every never-seen token
address from an uncapped upstream trending response allocated a 120-point
deque, the whole dict was persisted to ``~/.maxpane/base_cache.json``, and
it was reloaded uncapped on every MaxPane startup for *every* dashboard
(``BaseManager`` is constructed unconditionally).  One hostile or broken
GeckoTerminal response with hundreds of thousands of pool entries created
that many deques in a single poll cycle, and an already-bloated file
re-bloated the process on the next launch.

These tests pin the three bounds: per-update truncation, an LRU cap on
tracked addresses, and the same cap applied on load.
"""

from __future__ import annotations

import json
import time

import pytest

from maxpane_dashboard.data.base_cache import BaseTokenCache
from maxpane_dashboard.data.base_models import BaseSnapshot, BaseToken

NOW = time.time()


def _token(index: int, price: float = 1.0) -> BaseToken:
    """A minimal BaseToken with a deterministic, unique address."""
    return BaseToken(
        address=f"0x{index:040x}",
        name=f"Token{index}",
        symbol=f"T{index}",
        price_usd=price,
        price_change_5m=None,
        price_change_1h=None,
        price_change_24h=None,
        volume_24h=0.0,
        market_cap=0.0,
        fdv=None,
        liquidity=0.0,
        pair_address=None,
        dex=None,
        created_at=None,
    )


def _snapshot(count: int, *, fetched_at: float = NOW, start: int = 0) -> BaseSnapshot:
    return BaseSnapshot(
        trending_tokens=tuple(_token(i) for i in range(start, start + count)),
        trending_pools=(),
        launches=(),
        fetched_at=fetched_at,
    )


class TestUpdateTruncation:
    def test_oversized_snapshot_is_truncated(self, caplog) -> None:
        """One hostile response cannot allocate a deque per entry."""
        cache = BaseTokenCache(max_history=10, max_tokens=500, max_tokens_per_update=50)
        with caplog.at_level("WARNING"):
            cache.update(_snapshot(5000))

        assert cache.history_size == 50
        assert "truncating" in caplog.text

    def test_normal_snapshot_is_untouched(self) -> None:
        cache = BaseTokenCache(max_history=10, max_tokens=500, max_tokens_per_update=50)
        cache.update(_snapshot(30))
        assert cache.history_size == 30
        assert len(cache.get_price_history(_token(0).address)) == 1


class TestTrackedAddressCap:
    def test_cap_holds_across_cycles(self) -> None:
        """Churning trending lists never grow the tracked set past the cap."""
        cache = BaseTokenCache(max_history=10, max_tokens=100, max_tokens_per_update=50)
        for cycle in range(20):
            cache.update(
                _snapshot(50, fetched_at=NOW + cycle, start=cycle * 50)
            )
        assert cache.history_size == 100

    def test_eviction_is_least_recently_updated(self) -> None:
        cache = BaseTokenCache(max_history=10, max_tokens=3, max_tokens_per_update=10)
        cache.update(_snapshot(3))  # tokens 0, 1, 2

        # Re-touch token 0 so token 1 becomes the least recently updated.
        cache.record_token(_token(0), timestamp=NOW + 1)
        cache.record_token(_token(99), timestamp=NOW + 2)

        assert cache.history_size == 3
        assert cache.get_price_history(_token(0).address) != []
        assert cache.get_price_history(_token(99).address) != []
        assert cache.get_price_history(_token(1).address) == []

    def test_record_token_respects_cap(self) -> None:
        cache = BaseTokenCache(max_history=10, max_tokens=5, max_tokens_per_update=50)
        for i in range(500):
            cache.record_token(_token(i), timestamp=NOW + i)
        assert cache.history_size == 5

    def test_repeated_updates_keep_history_per_token(self) -> None:
        """Capping addresses must not cost per-token history depth."""
        cache = BaseTokenCache(max_history=10, max_tokens=100, max_tokens_per_update=50)
        for cycle in range(5):
            cache.update(_snapshot(3, fetched_at=NOW + cycle))
        assert len(cache.get_price_history(_token(0).address)) == 5


class TestLoadCap:
    def _write(self, path, histories: dict) -> str:
        path.write_text(json.dumps({"saved_at": NOW, "histories": histories}))
        return str(path)

    def test_bloated_file_is_capped_on_load(self, tmp_path, caplog) -> None:
        """An already-bloated cache file must not re-bloat the process."""
        histories = {
            f"0x{i:040x}": [[NOW - 1000 + i, 1.0]] for i in range(2000)
        }
        path = self._write(tmp_path / "base_cache.json", histories)

        cache = BaseTokenCache(max_history=10, max_tokens=100)
        with caplog.at_level("WARNING"):
            cache.load_from_file(path)

        assert cache.history_size == 100
        assert "least-recently-updated" in caplog.text

    def test_load_keeps_the_newest_histories(self, tmp_path) -> None:
        histories = {f"0x{i:040x}": [[NOW - 1000 + i, 1.0]] for i in range(10)}
        path = self._write(tmp_path / "base_cache.json", histories)

        cache = BaseTokenCache(max_history=10, max_tokens=3)
        cache.load_from_file(path)

        assert cache.history_size == 3
        # Entries 7, 8, 9 carry the newest timestamps.
        for i in (7, 8, 9):
            assert cache.get_price_history(f"0x{i:040x}") != []
        for i in (0, 5, 6):
            assert cache.get_price_history(f"0x{i:040x}") == []

    def test_load_then_save_writes_a_bounded_file(self, tmp_path) -> None:
        histories = {f"0x{i:040x}": [[NOW - 1000 + i, 1.0]] for i in range(2000)}
        src = self._write(tmp_path / "base_cache.json", histories)

        cache = BaseTokenCache(max_history=10, max_tokens=100)
        cache.load_from_file(src)
        out = str(tmp_path / "out.json")
        cache.save_to_file(out)

        with open(out) as fh:
            payload = json.load(fh)
        assert len(payload["histories"]) == 100

    def test_load_survives_unrankable_entries(self, tmp_path) -> None:
        """Corrupt histories sort oldest and are dropped, never raise."""
        histories = {
            "0xdead": "not a list",
            "0xbeef": [],
            "0xcafe": ["not a point"],
            "0xf00d": [[None, 1.0]],
            "0xgood": [[NOW - 5, 1.0]],
        }
        path = self._write(tmp_path / "base_cache.json", histories)

        cache = BaseTokenCache(max_history=10, max_tokens=2)
        cache.load_from_file(path)  # must not raise

        assert cache.history_size <= 2
        assert cache.get_price_history("0xgood") == [(pytest.approx(NOW - 5), 1.0)]

    def test_load_after_update_still_respects_cap(self, tmp_path) -> None:
        histories = {f"0x{i:040x}": [[NOW - 1000 + i, 1.0]] for i in range(200)}
        path = self._write(tmp_path / "base_cache.json", histories)

        cache = BaseTokenCache(max_history=10, max_tokens=50, max_tokens_per_update=50)
        cache.load_from_file(path)
        cache.update(_snapshot(50, fetched_at=NOW, start=10_000))

        assert cache.history_size == 50

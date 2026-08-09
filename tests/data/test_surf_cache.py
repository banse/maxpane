"""Tests for the SURF tiered cache and its persistence layer (WP4).

Everything runs offline against a fake clock and ``tmp_path``: no network, no
sleeping, no dependence on wall-clock time.
"""

from __future__ import annotations

import json
import math

import pytest

from maxpane_dashboard.data.surf_cache import (
    DEFAULT_CACHE_PATH,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_SLOW,
    TIERS,
    TIER_TTL_SECONDS,
    SurfCache,
)


class FakeClock:
    """Monotonic-by-hand clock so TTL tests never sleep."""

    def __init__(self, t: float = 1_786_190_400.0) -> None:   # 2026-08-08T12:00:00Z
        self.t = float(t)

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += float(seconds)
        return self.t


def _cache(tmp_path, clock=None) -> SurfCache:
    return SurfCache(path=str(tmp_path / "surf_cache.json"), clock=clock or FakeClock())


# ---------------------------------------------------------------------------
# Refresh tiers (PRD §5)
# ---------------------------------------------------------------------------


def test_tier_ttls_match_the_prd(tmp_path):
    """fast is due every refresh; medium 90 s; slow 420 s."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    assert TIERS == (TIER_FAST, TIER_MEDIUM, TIER_SLOW)
    assert TIER_TTL_SECONDS[TIER_FAST] == 0.0
    assert 60.0 <= TIER_TTL_SECONDS[TIER_MEDIUM] <= 120.0
    assert 300.0 <= TIER_TTL_SECONDS[TIER_SLOW] <= 600.0

    # Nothing fetched yet: everything is due.
    assert set(c.tiers_due()) == set(TIERS)

    for tier in TIERS:
        c.mark_fetched(tier)
    # fast has a zero TTL by design — the announce nonce is the whole edge.
    assert c.tiers_due() == (TIER_FAST,)

    clock.advance(TIER_TTL_SECONDS[TIER_MEDIUM])
    assert TIER_MEDIUM in c.tiers_due()
    assert TIER_SLOW not in c.tiers_due()

    clock.advance(TIER_TTL_SECONDS[TIER_SLOW])
    assert set(c.tiers_due()) == set(TIERS)


def test_failed_tier_backs_off_instead_of_hammering(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    c.mark_failed(TIER_MEDIUM)
    assert TIER_MEDIUM not in c.tiers_due()      # spaced, not immediate
    assert c.seconds_until_due(TIER_MEDIUM) > 0.0

    clock.advance(60.0)
    assert TIER_MEDIUM in c.tiers_due()
    # A failure never counts as a fetch.
    assert c.last_fetch_ts(TIER_MEDIUM) is None


def test_explicit_now_overrides_the_injected_clock(tmp_path):
    """Every time-taking method accepts ``now=`` (CLAUDE.md: inject the clock)."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.mark_fetched(TIER_SLOW, now=1_000.0)
    assert c.is_fresh(TIER_SLOW, now=1_100.0) is True
    assert c.is_fresh(TIER_SLOW, now=1_000.0 + TIER_TTL_SECONDS[TIER_SLOW]) is False


def test_unknown_tier_raises(tmp_path):
    c = _cache(tmp_path)
    with pytest.raises(ValueError):
        c.mark_fetched("hourly")


def test_default_cache_path_is_the_maxpane_convention():
    assert DEFAULT_CACHE_PATH.endswith("/.maxpane/surf_cache.json")


from maxpane_dashboard.data.surf_cache import (   # noqa: E402  (appended import)
    SLOTS,
    SLOT_CHAIN,
    SLOT_MARKET,
    LastGood,
)


# ---------------------------------------------------------------------------
# Last-good slots
# ---------------------------------------------------------------------------


def test_last_good_survives_a_failed_fetch_and_carries_its_timestamp(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    c.store_last_good(SLOT_MARKET, {"imd_price_usd": 0.7074})
    clock.advance(300.0)
    c.mark_failed(TIER_MEDIUM)

    entry = c.get_last_good(SLOT_MARKET)
    assert entry.payload == {"imd_price_usd": 0.7074}
    assert entry.age_seconds(clock.t) == 300.0
    assert c.as_of_ts(SLOT_MARKET) == clock.t - 300.0
    assert c.age_of(SLOT_MARKET) == 300.0
    assert len(entry.as_of_hhmm()) == 5 and ":" in entry.as_of_hhmm()


def test_a_last_good_never_exists_without_a_timestamp(tmp_path):
    """A stale value presented as live is worse than an honest gap."""
    c = _cache(tmp_path)
    entry = c.store_last_good(SLOT_CHAIN, {"imd_supply": 2376731.868679})
    assert entry.ts > 0.0
    with pytest.raises(Exception):
        entry.ts = 1.0                       # type: ignore[misc]
    assert entry.age_seconds(entry.ts - 5.0) == 0.0     # never negative


def test_unknown_slot_and_empty_slots_are_honest(tmp_path):
    c = _cache(tmp_path)
    assert c.get_last_good(SLOT_CHAIN) is None
    assert c.as_of_ts(SLOT_CHAIN) is None
    assert c.age_of(SLOT_CHAIN) is None
    assert c.newest_as_of() is None
    with pytest.raises(ValueError):
        c.store_last_good("weather", {})


def test_newest_as_of_is_the_freshest_successful_read(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.store_last_good(SLOT_CHAIN, {})
    clock.advance(120.0)
    c.store_last_good(SLOT_MARKET, {})
    assert c.newest_as_of() == clock.t
    assert len(SLOTS) == 6


def test_store_last_good_rejects_none_and_keeps_the_original_entry(tmp_path):
    """None means no successful read happened; it must never overwrite a good one."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    c.store_last_good(SLOT_MARKET, {"price": 9.99})
    original_ts = clock.t
    clock.advance(60.0)

    with pytest.raises(ValueError):
        c.store_last_good(SLOT_MARKET, None)

    entry = c.get_last_good(SLOT_MARKET)
    assert entry.payload == {"price": 9.99}
    assert entry.ts == original_ts


def test_store_last_good_accepts_a_genuine_empty_payload(tmp_path):
    """[]/0/""/{} are real successful readings, not outages -- do not over-guard."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    c.store_last_good(SLOT_MARKET, {"price": 9.99})
    clock.advance(60.0)

    entry = c.store_last_good(SLOT_MARKET, [])
    assert entry.payload == []
    assert entry.ts == clock.t
    assert c.get_last_good(SLOT_MARKET).payload == []


from maxpane_dashboard.data.surf_cache import (   # noqa: E402
    SERIES_IMD_PRICE_USD,
    SERIES_IMD_SUPPLY,
    SERIES_NAMES,
    SERIES_PARITY_PCT,
)

# Live values captured 2026-08-08 (tests/fixtures/surf/captures/).
IMD_SUPPLY = 2_376_731.868679          # imd_token.json total_supply / 1e18
IMD_PRICE_USD = 0.7074                 # dexscreener_imd.json priceUsd
FP_PRICE_USD = 0.7274                  # dexscreener_fp.json, deepest pair
PARITY_PCT = -2.7495188342040167       # (imd - fp) / fp * 100


def test_series_bucket_by_hour_and_overwrite_within_the_hour(tmp_path):
    c = _cache(tmp_path)
    base = 1_786_190_400.0               # exactly on an hour boundary

    c.sample_series(base, imd_supply=IMD_SUPPLY, imd_price_usd=IMD_PRICE_USD)
    c.sample_series(base + 1800.0, imd_supply=IMD_SUPPLY - 15_745.0)
    assert c.get_series(SERIES_IMD_SUPPLY) == [[base, IMD_SUPPLY - 15_745.0]]

    c.sample_series(base + 3600.0, imd_supply=IMD_SUPPLY - 15_745.0)
    assert len(c.get_series(SERIES_IMD_SUPPLY)) == 2
    assert c.get_series(SERIES_IMD_PRICE_USD) == [[base, IMD_PRICE_USD]]


def test_none_never_punches_a_zero_into_a_series(tmp_path):
    """A dead RPC must not write a 2.37M -> 0 supply step into the sparkline."""
    c = _cache(tmp_path)
    base = 1_786_190_400.0
    c.sample_series(base, imd_supply=IMD_SUPPLY, imd_price_usd=IMD_PRICE_USD)
    c.sample_series(base + 3600.0, imd_supply=None, imd_price_usd=None, parity_pct=None)

    assert c.get_series(SERIES_IMD_SUPPLY) == [[base, IMD_SUPPLY]]
    assert c.get_series(SERIES_IMD_PRICE_USD) == [[base, IMD_PRICE_USD]]
    assert c.get_series(SERIES_PARITY_PCT) == []


def test_parity_series_accepts_a_negative_spread(tmp_path):
    c = _cache(tmp_path)
    c.sample_series(1_786_190_400.0, parity_pct=PARITY_PCT)
    assert c.get_series(SERIES_PARITY_PCT) == [[1_786_190_400.0, PARITY_PCT]]


def test_non_finite_and_unparsable_samples_are_dropped(tmp_path):
    c = _cache(tmp_path)
    c.sample_series(1_786_190_400.0, imd_supply=float("nan"))
    c.sample_series(1_786_190_400.0, imd_price_usd=float("inf"))
    c.sample_series(1_786_190_400.0, parity_pct="cheap")     # type: ignore[arg-type]
    assert all(c.get_series(name) == [] for name in SERIES_NAMES)


def test_series_are_bounded_at_seven_days(tmp_path):
    c = _cache(tmp_path)
    base = 1_700_000_000.0
    for hour in range(200):
        c.sample_series(base + hour * 3600.0, imd_price_usd=0.7 + hour)
    series = c.get_series(SERIES_IMD_PRICE_USD)
    assert len(series) == 168
    assert series[-1][1] == 0.7 + 199

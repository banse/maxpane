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

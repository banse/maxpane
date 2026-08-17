"""WP5 — the curator cache: tiers, persistence, series, latch, folds, clusters.

Nothing here sleeps and nothing here opens a socket: the clock is injected and
every expiry is driven by advancing it.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.data import curator_cache
from maxpane_dashboard.data.curator_cache import (
    SLOTS,
    SLOT_BLOCKSCOUT,
    SLOT_CONFIG,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    TIERS,
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    TIER_TTL_SECONDS,
    CuratorCache,
)

#: 2026-08-17 00:00:00 UTC, comfortably after the captured launch.
NOW = 1_786_968_000.0


class Clock:
    """An injected clock a test advances by hand.  Nothing sleeps."""

    def __init__(self, start: float = NOW) -> None:
        self.now = float(start)

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += float(seconds)
        return self.now


@pytest.fixture()
def clock() -> Clock:
    return Clock()


@pytest.fixture()
def cache(tmp_path, clock) -> CuratorCache:
    return CuratorCache(path=str(tmp_path / "curator_cache.json"), clock=clock)


# ---------------------------------------------------------------------------
# WP5.1 — tiers, slots, clock
# ---------------------------------------------------------------------------


def test_the_four_tiers_and_their_ttls_are_the_prd_tiers():
    assert TIERS == (TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_ONCE)
    assert TIER_TTL_SECONDS[TIER_FAST] == 15.0
    assert TIER_TTL_SECONDS[TIER_MEDIUM] == 60.0
    assert TIER_TTL_SECONDS[TIER_SLOW] == 420.0
    assert TIER_TTL_SECONDS[TIER_ONCE] == float("inf")
    assert set(TIER_FAILURE_BACKOFF_SECONDS) == set(TIERS)


def test_every_tier_is_due_before_it_has_ever_been_fetched(cache):
    assert set(cache.tiers_due()) == set(TIERS)


def test_ttls_drive_tiers_due_off_the_injected_clock(cache, clock):
    for tier in TIERS:
        cache.mark_fetched(tier)
    assert cache.tiers_due() == ()

    clock.advance(15)
    assert cache.tiers_due() == (TIER_FAST,)

    clock.advance(45)          # 60 s in
    assert cache.tiers_due() == (TIER_FAST, TIER_MEDIUM)

    clock.advance(360)         # 420 s in
    assert cache.tiers_due() == (TIER_FAST, TIER_MEDIUM, TIER_SLOW)


def test_the_once_tier_never_comes_due_twice_after_a_success(cache, clock):
    cache.mark_fetched(TIER_ONCE)
    clock.advance(365 * 24 * 3600)
    assert TIER_ONCE not in cache.tiers_due()
    assert cache.is_fresh(TIER_ONCE) is True


def test_a_failed_tier_is_not_marked_fetched_and_returns_after_its_backoff(cache, clock):
    """A failure spaces the retry; it never restarts the TTL.

    The distinction matters for ``once``, whose successful TTL is infinite: a
    failure that went through ``mark_fetched`` would make the immutables
    permanently unreadable for the life of the process.
    """
    cache.mark_failed(TIER_MEDIUM)
    assert cache.last_fetch_ts(TIER_MEDIUM) is None
    assert TIER_MEDIUM not in cache.tiers_due()

    clock.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_MEDIUM] - 1)
    assert TIER_MEDIUM not in cache.tiers_due()
    clock.advance(2)
    assert TIER_MEDIUM in cache.tiers_due()


def test_a_failed_once_tier_comes_due_again(cache, clock):
    cache.mark_failed(TIER_ONCE)
    assert cache.is_fresh(TIER_ONCE) is True
    clock.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_ONCE] + 1)
    assert TIER_ONCE in cache.tiers_due()


def test_an_explicit_retry_after_overrides_the_backoff(cache, clock):
    cache.mark_failed(TIER_FAST, retry_after=300)
    clock.advance(299)
    assert TIER_FAST not in cache.tiers_due()
    clock.advance(2)
    assert TIER_FAST in cache.tiers_due()


def test_an_unknown_tier_raises_naming_the_valid_set(cache):
    for call in (
        lambda: cache.is_fresh("hourly"),
        lambda: cache.mark_fetched("hourly"),
        lambda: cache.mark_failed("hourly"),
        lambda: cache.seconds_until_due("hourly"),
        lambda: cache.last_fetch_ts("hourly"),
    ):
        with pytest.raises(ValueError) as excinfo:
            call()
        assert "hourly" in str(excinfo.value)
        assert TIER_MEDIUM in str(excinfo.value)


def test_an_unknown_slot_raises_naming_the_valid_set(cache):
    for call in (
        lambda: cache.store_last_good("market", {"a": 1}),
        lambda: cache.get_last_good("market"),
        lambda: cache.as_of_ts("market"),
        lambda: cache.age_of("market"),
    ):
        with pytest.raises(ValueError) as excinfo:
            call()
        assert "market" in str(excinfo.value)
        assert SLOT_STATE in str(excinfo.value)


def test_the_five_slots_are_the_five_independently_failing_sources():
    assert SLOTS == (SLOT_STATE, SLOT_LOGS, SLOT_WALLET, SLOT_CONFIG, SLOT_BLOCKSCOUT)


def test_storing_none_as_a_last_good_payload_is_refused(cache):
    """``None`` means *no read happened*.  Storing it would overwrite a good
    payload and its provenance with an outage nothing downstream can see."""
    cache.store_last_good(SLOT_STATE, {"settled": False}, ts=NOW)
    with pytest.raises(ValueError):
        cache.store_last_good(SLOT_STATE, None, ts=NOW + 15)
    assert cache.get_last_good(SLOT_STATE).payload == {"settled": False}
    assert cache.as_of_ts(SLOT_STATE) == NOW


def test_a_falsy_but_real_payload_is_stored(cache):
    """``[]`` / ``0`` are answers, not absences — the whole point of the rule."""
    cache.store_last_good(SLOT_LOGS, [], ts=NOW)
    assert cache.get_last_good(SLOT_LOGS).payload == []


def test_age_and_newest_as_of_read_the_injected_clock(cache, clock):
    cache.store_last_good(SLOT_STATE, {"a": 1}, ts=NOW - 30)
    cache.store_last_good(SLOT_LOGS, {"b": 2}, ts=NOW - 5)
    assert cache.age_of(SLOT_STATE) == 30
    assert cache.newest_as_of() == NOW - 5
    clock.advance(10)
    assert cache.age_of(SLOT_STATE) == 40
    assert cache.age_of(SLOT_WALLET) is None
    assert cache.as_of_ts(SLOT_CONFIG) is None


def test_the_cache_never_calls_time_time_internally():
    """Every stamp comes from the injected clock or an explicit ``now=``."""
    src = curator_cache.__dict__["__doc__"] or ""
    assert "time.time" not in src
    body = open(curator_cache.__file__, encoding="utf-8").read()
    # ``time.time`` may appear exactly once: as the *default* of the injected
    # ``clock`` parameter.  Anywhere else is a clock a test cannot control.
    assert body.count("time.time") == 1
    assert "clock: Callable[[], float] = time.time" in body

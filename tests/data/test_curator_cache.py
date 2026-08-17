"""WP5 — the curator cache: tiers, persistence, series, latch, folds, clusters.

Nothing here sleeps and nothing here opens a socket: the clock is injected and
every expiry is driven by advancing it.
"""

from __future__ import annotations

import inspect
import json
import os
import pathlib

import pytest

from maxpane_dashboard.data import curator_cache
from maxpane_dashboard.data.series_points import CLOCK_SKEW_TOLERANCE_SECONDS
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


# ---------------------------------------------------------------------------
# WP5.2 — persistence, schema version, coerce_points
# ---------------------------------------------------------------------------


def _write(tmp_path, payload) -> str:
    target = tmp_path / "curator_cache.json"
    target.write_text(json.dumps(payload), encoding="utf-8")
    return str(target)


def _file(tmp_path, **sections) -> dict:
    base = {"version": 1, "saved_at": NOW, "last_good": {}, "series": {}}
    base.update(sections)
    return base


def test_a_single_null_in_a_series_does_not_abort_the_load(tmp_path, clock):
    """The bug that once broke startup for EVERY dashboard, not just the one
    owning the file.  A corrupt point is dropped and counted, never fatal."""
    path = _write(
        tmp_path,
        _file(
            tmp_path,
            series={"volume_series": [[1, 2], [3, None], "junk", [5, 6]]},
        ),
    )
    cache = CuratorCache(path=path, clock=clock)
    cache.load(now=NOW)
    assert cache.get_series("volume_series") == [[1.0, 2.0], [5.0, 6.0]]


def test_every_persisted_series_goes_through_coerce_points():
    src = inspect.getsource(curator_cache)
    assert "coerce_points" in src
    assert "float(pt[1])" not in src        # the hand-rolled version that broke


def test_a_future_dated_point_is_dropped_and_a_slightly_fast_clock_is_not(tmp_path, clock):
    """``CLOCK_SKEW_TOLERANCE_SECONDS``: a machine whose clock runs a minute
    fast must not throw away the samples it just wrote itself."""
    slightly_fast = NOW + 60
    far_future = NOW + 10 * CLOCK_SKEW_TOLERANCE_SECONDS
    path = _write(
        tmp_path,
        _file(
            tmp_path,
            series={"volume_series": [[NOW - 3600, 1.0], [slightly_fast, 2.0], [far_future, 3.0]]},
        ),
    )
    cache = CuratorCache(path=path, clock=clock)
    cache.load(now=NOW)
    kept = [ts for ts, _v in cache.get_series("volume_series")]
    assert kept == [NOW - 3600, slightly_fast]


def test_an_unknown_schema_version_loads_nothing_rather_than_guessing(tmp_path, clock):
    for version in (None, 0, 2, "1", True):
        payload = _file(tmp_path, series={"volume_series": [[NOW - 60, 7.0]]})
        payload["version"] = version
        path = _write(tmp_path, payload)
        cache = CuratorCache(path=path, clock=clock)
        cache.load(now=NOW)
        assert cache.get_series("volume_series") == [], f"schema {version!r} was trusted"


def test_save_is_atomic(tmp_path, clock, monkeypatch):
    """temp + rename, so a kill mid-write leaves the previous file intact."""
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_last_good(SLOT_STATE, {"settled": False}, ts=NOW)
    cache.save()
    good = pathlib.Path(path).read_text(encoding="utf-8")

    real_replace = os.replace

    def _die(src, dst):
        raise OSError("killed mid-write")

    monkeypatch.setattr(curator_cache.os, "replace", _die)
    cache.store_last_good(SLOT_STATE, {"settled": True}, ts=NOW + 15)
    cache.save()                       # must not raise
    monkeypatch.setattr(curator_cache.os, "replace", real_replace)

    assert pathlib.Path(path).read_text(encoding="utf-8") == good
    assert not (tmp_path / "curator_cache.json.tmp").exists()


def test_a_missing_or_unreadable_cache_file_is_silently_an_empty_cache(tmp_path, clock):
    missing = CuratorCache(path=str(tmp_path / "nope.json"), clock=clock)
    missing.load(now=NOW)
    assert missing.get_series("volume_series") == []
    assert missing.newest_as_of() is None

    broken_path = tmp_path / "broken.json"
    broken_path.write_text("{not json at all", encoding="utf-8")
    broken = CuratorCache(path=str(broken_path), clock=clock)
    broken.load(now=NOW)
    assert broken.get_series("volume_series") == []

    listy = tmp_path / "listy.json"
    listy.write_text("[1, 2, 3]", encoding="utf-8")
    other = CuratorCache(path=str(listy), clock=clock)
    other.load(now=NOW)
    assert other.get_series("volume_series") == []


def test_a_last_good_slot_with_no_usable_stamp_is_dropped_not_defaulted(tmp_path, clock):
    payload = _file(
        tmp_path,
        last_good={
            SLOT_STATE: {"payload": {"a": 1}},                       # no ts
            SLOT_LOGS: {"payload": {"b": 2}, "ts": "yesterday"},      # unusable ts
            SLOT_CONFIG: {"payload": {"c": 3}, "ts": NOW + 86400},    # future
            SLOT_WALLET: {"payload": {"d": 4}, "ts": NOW - 30},       # good
            "market": {"payload": {"e": 5}, "ts": NOW - 30},          # unknown slot
        },
    )
    cache = CuratorCache(path=_write(tmp_path, payload), clock=clock)
    cache.load(now=NOW)
    assert cache.get_last_good(SLOT_STATE) is None
    assert cache.get_last_good(SLOT_LOGS) is None
    assert cache.get_last_good(SLOT_CONFIG) is None
    assert cache.get_last_good(SLOT_WALLET).payload == {"d": 4}
    assert set(cache.last_good) == {SLOT_WALLET}


def test_a_round_trip_preserves_the_last_good_slots_and_the_series(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_last_good(SLOT_STATE, {"settled": False, "hour": 4}, ts=NOW - 10)
    cache._series["volume_series"] = {NOW - 7200: 851.89, NOW - 3600: 9987.26}
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert restored.get_last_good(SLOT_STATE).payload == {"settled": False, "hour": 4}
    assert restored.as_of_ts(SLOT_STATE) == NOW - 10
    assert restored.get_series("volume_series") == [
        [NOW - 7200, 851.89],
        [NOW - 3600, 9987.26],
    ]

"""WP5 — the curator cache: tiers, persistence, series, latch, folds, clusters.

Nothing here sleeps and nothing here opens a socket: the clock is injected and
every expiry is driven by advancing it.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import os
import pathlib

import pytest

from maxpane_dashboard.analytics.curator_signals import bucket_start_ts, hourly_buckets
from maxpane_dashboard.data import curator_cache
from maxpane_dashboard.data.curator_models import ContributorRow, DepositEvent
from maxpane_dashboard.data.series_points import CLOCK_SKEW_TOLERANCE_SECONDS
from maxpane_dashboard.data.curator_cache import (
    SLOTS,
    SLOT_BLOCKSCOUT,
    SLOT_CLUSTERS,
    SLOT_CONFIG,
    SLOT_LOGS,
    SLOT_STATE,
    SLOT_WALLET,
    TIERS,
    TIER_ANALYSIS,
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_FAST,
    TIER_MEDIUM,
    TIER_ONCE,
    TIER_SLOW,
    TIER_TTL_SECONDS,
    MAX_SERIES_POINTS,
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


def test_the_five_tiers_and_their_ttls_are_the_prd_tiers():
    """Grown 4 -> 5 in WP3.2: the detached B+C sweep rides its own long tier."""
    assert TIERS == (TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_ONCE, TIER_ANALYSIS)
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


def test_the_six_slots_are_the_six_independently_failing_sources():
    """Grown 5 -> 6 in WP3.2: the analysis last-good is its own slot, because
    the detached sweep fails independently of every fetch tier."""
    assert SLOTS == (
        SLOT_STATE,
        SLOT_LOGS,
        SLOT_WALLET,
        SLOT_CONFIG,
        SLOT_BLOCKSCOUT,
        SLOT_CLUSTERS,
    )


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


# ---------------------------------------------------------------------------
# WP5.3 — the series, fed from folded logs only (H2)
# ---------------------------------------------------------------------------

LAUNCH_TIME = 1_786_910_327          # 2026-08-16 19:58:47 UTC, the real launch
HOUR = 3600
THRESHOLD_WEI = 5 * 10**18


def _deposit(hour: int, amount_wei: int, *, index: int, block: int = 25_770_000):
    """One decoded ``Deposited`` event, wei-native like the chain's."""
    return DepositEvent(
        contributor="0x" + f"{index:040x}",
        hour=hour,
        amount_wei=amount_wei,
        credited_delta_wei=amount_wei,
        weight_added_wei=amount_wei,
        new_weight_wei=amount_wei,
        tx_count=1,
        hour_total_wei=amount_wei,
        early_bps=19_491,
        block_number=block + index,
        tx_hash="0x" + f"{index:064x}",
        log_index=index,
        ts=float(LAUNCH_TIME + hour * HOUR + 10),
    )


def _deposits_hour_0_and_1():
    """Hour 0 takes 851.89 ETH, hour 1 takes 730 — the shape of the capture."""
    return [
        _deposit(0, 851_890_000_000_000_000_000, index=1),
        _deposit(1, 730_000_000_000_000_000_000, index=2),
    ]


def _buckets_from(deposits, *, first_judged_hour=24):
    """Fold to ``(bucket_start_ts, volume_wei)`` pairs — the writer's input.

    The hour comes off ``Deposited``'s indexed second topic and its wall clock
    is ``launchTime + hour × hourDuration``, so no timestamp read participates.
    """
    buckets = hourly_buckets(
        deposits,
        launch_time=LAUNCH_TIME,
        hour_duration=HOUR,
        first_judged_hour=first_judged_hour,
        hourly_threshold_wei=THRESHOLD_WEI,
    )
    return [
        [bucket_start_ts(b.hour, LAUNCH_TIME, HOUR), b.volume_wei] for b in buckets
    ]


def test_the_series_writer_takes_folded_buckets_not_a_state_reading():
    """H2, structural.  The live hour-total view legitimately drops to 0 at
    every hour boundary while the last-active-hour view still names the
    previous bucket.  A state-poll sparkline reads that as a crash -- and the
    zero gets PERSISTED, so the corruption outlives the boundary that produced
    it."""
    params = set(inspect.signature(CuratorCache.record_hour_buckets).parameters)
    assert params == {"self", "buckets", "now"}
    src = inspect.getsource(curator_cache)
    for banned in ("current_hour_total", "currentHourTotal"):
        assert banned not in src


def test_the_boundary_fixture_writes_no_zero(cache):
    """The behavioural half.  Replay: hour 1 with 730 ETH, then the boundary
    tick where the live hour total is 0 and the last active hour still says
    hour 1.  The series must still read [.., 730] -- the boundary is invisible
    to it, because no state reading can reach the writer.

    # SYNTHETIC — re-point at tests/fixtures/curator/captures/live/<bundle>
    # (WP1.3 capture A).  The synthetic is captures/results.json with two words
    # changed; the real pair is the same two words changed by the chain.
    """
    cache.record_hour_buckets(_buckets_from(_deposits_hour_0_and_1()))
    cache.record_hour_buckets(_buckets_from(_deposits_hour_0_and_1()))  # boundary tick
    series = cache.get_series("volume_series")
    assert [v for _ts, v in series] == [851.89, 730.0]
    assert 0.0 not in [v for _ts, v in series[:-1]]


def test_a_genuinely_silent_hour_does_write_a_zero(cache):
    """The mirror image, and the reason the rule is 'from logs only' rather
    than 'never write a zero'.  A judged hour that took in nothing IS a zero,
    and it is the most important point on the chart."""
    deposits = [
        _deposit(0, 851_890_000_000_000_000_000, index=1),
        _deposit(2, 12_000_000_000_000_000_000, index=2),      # hour 1 is silent
    ]
    cache.record_hour_buckets(_buckets_from(deposits))
    values = [v for _ts, v in cache.get_series("volume_series")]
    assert values == [851.89, 0.0, 12.0]


def test_re_recording_the_same_fold_is_idempotent(cache):
    """Every cycle re-records the whole folded history; the series must not
    grow a duplicate hour or fall out of ascending order."""
    for _ in range(5):
        cache.record_hour_buckets(_buckets_from(_deposits_hour_0_and_1()))
    series = cache.get_series("volume_series")
    stamps = [ts for ts, _v in series]
    assert stamps == sorted(stamps) == [LAUNCH_TIME, LAUNCH_TIME + HOUR]


def test_a_later_fold_revises_an_hour_it_had_already_written(cache):
    """A sweep that recovers a missed range corrects the bucket in place."""
    cache.record_hour_buckets([[LAUNCH_TIME, 10 * 10**18]])
    cache.record_hour_buckets([[LAUNCH_TIME, 42 * 10**18]])
    assert cache.get_series("volume_series") == [[LAUNCH_TIME, 42.0]]


def test_junk_buckets_are_dropped_rather_than_coerced(cache):
    cache.record_hour_buckets(
        [
            [LAUNCH_TIME, 10**18],
            [None, 10**18],            # no stamp
            [LAUNCH_TIME + HOUR, None],  # a failed read is not a zero
            [LAUNCH_TIME + 2 * HOUR, -5],
            "junk",
            [LAUNCH_TIME + 3 * HOUR],
        ]
    )
    assert cache.get_series("volume_series") == [[LAUNCH_TIME, 1.0]]


def test_the_contributor_series_takes_a_folded_total_and_refuses_none(cache):
    assert cache.record_contributor_count(143, ts=LAUNCH_TIME) is True
    assert cache.record_contributor_count(None, ts=LAUNCH_TIME + HOUR) is False
    assert cache.record_contributor_count(5, ts=None) is False
    assert cache.record_contributor_count(145, ts=LAUNCH_TIME + HOUR) is True
    assert cache.get_series("contributors_series") == [
        [LAUNCH_TIME, 143.0],
        [LAUNCH_TIME + HOUR, 145.0],
    ]


def test_the_series_are_capped_and_drop_the_oldest(cache):
    cache.record_hour_buckets(
        [[LAUNCH_TIME + i * HOUR, i * 10**18] for i in range(MAX_SERIES_POINTS + 20)]
    )
    series = cache.get_series("volume_series")
    assert len(series) == MAX_SERIES_POINTS
    assert series[0][0] == LAUNCH_TIME + 20 * HOUR


def test_the_series_survive_a_save_load_round_trip(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.record_hour_buckets(_buckets_from(_deposits_hour_0_and_1()))
    cache.record_contributor_count(2, ts=LAUNCH_TIME + HOUR)
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert restored.get_series("volume_series") == [
        [LAUNCH_TIME, 851.89],
        [LAUNCH_TIME + HOUR, 730.0],
    ]
    assert restored.get_series("contributors_series") == [[LAUNCH_TIME + HOUR, 2.0]]


# ---------------------------------------------------------------------------
# WP5.4 — the settlement evidence latch (H1)
# ---------------------------------------------------------------------------


def test_the_first_true_observation_is_persisted_with_its_evidence(cache):
    rec = cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    assert rec.settled is True and rec.block_number == 25_776_000
    assert rec.observed_at == NOW


def test_a_false_observation_never_clears_a_true_one(cache):
    """One-way by construction, and the contract agrees: isSettled() is
    ``_settled || _isShort(currentHour())`` and never returns false again.  A
    later false can only be a bad read, a wrong endpoint, or a fork."""
    cache.observe_settlement(True, block_number=1, now=NOW)
    cache.observe_settlement(False, block_number=2, now=NOW + 15)
    assert cache.settlement_record().settled is True
    assert cache.settlement_record().block_number == 1
    assert cache.settlement_record().observed_at == NOW


def test_a_none_observation_never_clears_a_true_one(cache):
    """The outage case, which is the whole point."""
    cache.observe_settlement(True, block_number=1, now=NOW)
    cache.observe_settlement(None, block_number=None, now=NOW + 15)
    assert cache.settlement_record().settled is True


def test_a_false_reading_never_creates_a_record(cache):
    """``False`` is a real reading — the game is running — but it is live state,
    not evidence.  A ``settled=False`` record would hand the phase machine a
    second source of truth to disagree with."""
    assert cache.observe_settlement(False, block_number=25_770_000, now=NOW) is None
    assert cache.observe_settlement(None, block_number=None, now=NOW) is None
    assert cache.settlement_record() is None


def test_the_latch_survives_a_save_load_round_trip(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    cache.record_settled_event(hour=24, ts=1_787_000_400, contributors=300,
                              volume_wei=9 * 10**21)
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW + 3600)
    rec = restored.settlement_record()
    assert rec.settled is True
    assert rec.block_number == 25_776_000
    assert rec.observed_at == NOW
    assert rec.settled_hour == 24
    assert rec.total_volume_wei == 9 * 10**21


def test_a_persisted_record_is_re_validated_not_trusted(tmp_path, clock):
    """The surf hook_status lesson: never trust the boolean a file happened to
    contain.  A record missing block_number or observed_at, or carrying a
    non-bool, is discarded rather than believed."""
    for junk in (
        {"settled": True},
        {"settled": "yes", "block_number": 1, "observed_at": NOW},
        {"settled": True, "block_number": "x", "observed_at": NOW},
        {"settled": True, "block_number": 1},
        {"settled": True, "block_number": 1, "observed_at": None},
        {"settled": False, "block_number": 1, "observed_at": NOW},
        {"settled": 1, "block_number": 1, "observed_at": NOW},
        "settled!",
    ):
        path = _write(tmp_path, _file(tmp_path, settlement=junk))
        cache = CuratorCache(path=path, clock=clock)
        cache.load(now=NOW)
        assert cache.settlement_record() is None, junk


def test_the_settled_event_fills_the_obituary_without_creating_the_latch(cache):
    """A Settled log with no prior view observation must NOT set the latch:
    the event is evidence about the past, the view is evidence about now.  (In
    practice they agree -- but a log-only latch is the exact hazard the PRD
    names, one level down.)"""
    cache.record_settled_event(hour=24, ts=1_787_000_400, contributors=300,
                               volume_wei=9 * 10**21)
    assert cache.settlement_record() is None
    cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    rec = cache.settlement_record()
    assert rec.settled_hour == 24 and rec.total_contributors == 300


def test_the_obituary_stays_none_rather_than_zero_when_the_log_never_fires(cache):
    """PRD §11: settled from the view with the Settled log absent -> the
    obituary fields are None, not 0."""
    cache.observe_settlement(True, block_number=25_776_000, now=NOW)
    rec = cache.settlement_record()
    assert rec.settled_hour is None
    assert rec.settled_at_ts is None
    assert rec.total_contributors is None
    assert rec.total_volume_wei is None


def test_an_observation_with_an_unreadable_height_still_latches(cache):
    """The phase truth outranks its label: losing the block number loses the
    evidence's precision, not the verdict."""
    rec = cache.observe_settlement(True, block_number=None, now=NOW)
    assert rec.settled is True and rec.block_number is None


# ---------------------------------------------------------------------------
# WP5.5 — the folded contributor table, the raw history and the watermark
# ---------------------------------------------------------------------------


def _row(address: str, *, weight=10**18, credit=10**18, tx_count=1,
         first_hour=0, first_index=1, points=1000) -> ContributorRow:
    return ContributorRow(
        address=address,
        weight_wei=weight,
        credit_wei=credit,
        tx_count=tx_count,
        first_hour=first_hour,
        first_index=first_index,
        points=points,
    )


def test_a_never_swept_cache_has_no_watermark(cache):
    """``None`` means backfill from the creation block — never 'start from
    now', which would leave the whole game unfolded behind an empty
    leaderboard and no error anywhere."""
    assert cache.last_seen_block() is None


def test_the_watermark_advances_only_on_a_successful_sweep(cache):
    cache.store_fold([_row("0xaa")], last_block=25_770_500)
    assert cache.last_seen_block() == 25_770_500

    # A sweep that could not read its head stores nothing new about blocks.
    cache.store_fold([_row("0xaa")], last_block=None)
    assert cache.last_seen_block() == 25_770_500

    # And a lagging replica cannot re-open an already-folded range.
    cache.store_fold([_row("0xaa")], last_block=25_770_100)
    assert cache.last_seen_block() == 25_770_500


def test_the_fold_round_trips_and_a_row_with_a_missing_field_is_dropped(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_fold([_row("0xaa"), _row("0xbb", points=None)], last_block=25_770_500)
    cache.save()

    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    raw["fold"].append({"address": "0xcc"})                 # no weight/credit/tx
    raw["fold"].append({"weight_wei": 1, "credit_wei": 1, "tx_count": 1})
    raw["fold"].append("junk")
    pathlib.Path(path).write_text(json.dumps(raw), encoding="utf-8")

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    rows = restored.fold_rows()
    assert [r.address for r in rows] == ["0xaa", "0xbb"]
    assert rows[1].points is None                            # a real None survives
    assert restored.last_seen_block() == 25_770_500


def test_events_are_de_duplicated_on_tx_hash_and_log_index(cache):
    first = _deposits_hour_0_and_1()
    assert cache.store_events(first) == 2
    assert cache.store_events(first) == 0                    # a replayed window
    assert len(cache.events()) == 2


def test_events_stay_ordered_oldest_first_however_they_arrive(cache):
    late = _deposit(3, 10**18, index=9, block=25_780_000)
    early = _deposit(0, 10**18, index=1, block=25_770_000)
    cache.store_events([late])
    cache.store_events([early])
    assert [e.block_number for e in cache.events()] == [
        early.block_number,
        late.block_number,
    ]


def test_the_event_cap_drops_the_oldest_and_counts_the_drop(cache):
    over = curator_cache.MAX_PERSISTED_EVENTS + 5
    cache.store_events([_deposit(0, 10**18, index=i, block=25_770_000) for i in range(over)])
    kept = cache.events()
    assert len(kept) == curator_cache.MAX_PERSISTED_EVENTS
    assert cache.dropped_events == 5
    assert kept[0].log_index == 5                            # the oldest went


def test_the_drop_count_survives_a_relaunch(tmp_path, clock, monkeypatch):
    """``dropped_events`` is persisted, because a *relaunch* is where the
    manager's cross-check reads it.

    ``seen = len(events()) + dropped_events`` is what stops the history cap
    from declaring the fold permanently short against a contract counter that
    never forgets.  As a per-process counter that arithmetic was right inside
    one process and wrong across the file: the reloaded cache reported 0
    dropped, so every launch after the cap first trips would schedule a full
    re-sweep from the creation block, re-drop the same overflow and publish a
    ``degraded`` that could not clear.
    """
    monkeypatch.setattr(curator_cache, "MAX_PERSISTED_EVENTS", 25)
    path = str(tmp_path / "curator_cache.json")

    first = CuratorCache(path=path, clock=clock)
    first.store_events([_deposit(0, 10**18, index=i) for i in range(30)])
    assert (len(first.events()), first.dropped_events) == (25, 5)
    first.save()

    second = CuratorCache(path=path, clock=clock)
    second.load()
    assert len(second.events()) == 25
    assert second.dropped_events == 5, (
        "the drop count did not survive the file; the fold now reads as 25 "
        "seen against a contract counter of 30 and re-sweeps from the "
        "creation block on every launch"
    )
    # The same total the cross-check computes, on both sides of the restart.
    assert len(second.events()) + second.dropped_events == 30

    # Loading is a restore, not an accumulation.
    second.load()
    assert second.dropped_events == 5


@pytest.mark.parametrize("bad", [None, True, -3, "5", 2.0])
def test_a_bad_drop_count_in_the_file_leaves_the_counter_at_zero(tmp_path, clock, bad):
    """One malformed value costs its own field, never the load."""
    path = pathlib.Path(tmp_path / "curator_cache.json")
    seed = CuratorCache(path=str(path), clock=clock)
    seed.store_events(_deposits_hour_0_and_1())
    seed.save()
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["dropped_events"] = bad
    path.write_text(json.dumps(raw), encoding="utf-8")

    cache = CuratorCache(path=str(path), clock=clock)
    cache.load()
    assert cache.dropped_events == 0
    assert len(cache.events()) == 2  # the rest of the file still loaded


def test_the_raw_history_round_trips_and_a_broken_row_is_dropped(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_events(_deposits_hour_0_and_1())
    cache.save()

    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    broken = dict(raw["events"][0])
    broken.pop("amount_wei")
    broken["tx_hash"] = "0x" + "9" * 64
    raw["events"].append(broken)
    raw["events"].append({"contributor": "0xaa"})
    pathlib.Path(path).write_text(json.dumps(raw), encoding="utf-8")

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    events = restored.events()
    assert len(events) == 2
    assert events[0].amount_wei == 851_890_000_000_000_000_000
    assert events[0].ts is not None


def test_an_event_whose_stamp_never_arrived_stays_none_through_a_round_trip(tmp_path, clock):
    """A missing stamp renders '--:--'.  A 0 would render 1970-01-01."""
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_events([dataclasses.replace(_deposit(0, 10**18, index=7), ts=None)])
    cache.save()
    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert restored.events()[0].ts is None


def test_first_deposits_and_hour_saved_merge_and_round_trip(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_first_deposits([
        {"contributor": "0xAA", "index": 2, "ts": LAUNCH_TIME + 10},
        {"contributor": "0xbb", "index": 1, "ts": None},
        {"contributor": "0xcc"},                     # no index — dropped
        "junk",
    ])
    cache.store_first_deposits([{"contributor": "0xaa", "index": 2, "ts": LAUNCH_TIME + 11}])
    cache.store_hour_saved([{"hour": 30, "wallet": "0xdd", "ts": LAUNCH_TIME + 3600}])
    cache.store_rescued_total(0)
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert [r["index"] for r in restored.first_deposits()] == [1, 2]
    assert restored.first_deposits()[1]["ts"] == LAUNCH_TIME + 11   # merged, not doubled
    assert restored.hour_saved() == [{"hour": 30, "wallet": "0xdd", "ts": float(LAUNCH_TIME + 3600)}]
    assert restored.rescued_total_wei() == 0                        # 0 is REAL


def test_an_unread_rescued_total_stays_none(cache):
    assert cache.rescued_total_wei() is None
    cache.store_rescued_total(None)
    assert cache.rescued_total_wei() is None


# ---------------------------------------------------------------------------
# WP5.6 — cluster (fan-out pattern) state
# ---------------------------------------------------------------------------


def _cluster(first_block: int, last_block: int, *, share=12.5) -> dict:
    return {
        "size": 9,
        "amount_eth": 60.0,
        "first_block": first_block,
        "last_block": last_block,
        "points": 8_100,
        "points_share_pct": share,
    }


def test_clusters_persist_and_reload(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_events(_deposits_hour_0_and_1())
    inside = cache.events()[0].block_number
    cache.store_clusters([_cluster(inside, inside + 4)])
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    rows = restored.clusters()
    assert len(rows) == 1
    assert rows[0]["size"] == 9 and rows[0]["points"] == 8_100
    assert rows[0]["first_block"] == inside


def test_a_cluster_outside_the_retained_history_is_dropped_not_rendered(tmp_path, clock):
    """The rows that evidenced it are gone; a flag nothing can be traced back
    to is a pattern claim with no witness."""
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_events(_deposits_hour_0_and_1())
    oldest = cache.events()[0].block_number
    cache.store_clusters([_cluster(oldest - 5_000, oldest - 4_990), _cluster(oldest, oldest + 2)])
    cache.save()

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert [row["first_block"] for row in restored.clusters()] == [oldest]


def test_a_cluster_reloaded_with_no_retained_history_at_all_is_dropped(tmp_path, clock):
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_clusters([_cluster(25_770_000, 25_770_010)])
    cache.save()
    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert restored.clusters() == []


def test_the_flagged_points_share_is_recomputed_on_load_never_restored(tmp_path, clock):
    """It is a ratio against a total that changes every hour; a restored one
    would be a stale percentage rendered beside live absolutes."""
    path = str(tmp_path / "curator_cache.json")
    cache = CuratorCache(path=path, clock=clock)
    cache.store_events(_deposits_hour_0_and_1())
    inside = cache.events()[0].block_number
    cache.store_clusters([_cluster(inside, inside + 1, share=41.7)])
    cache.save()

    on_disk = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    assert "points_share_pct" not in on_disk["clusters"][0]

    restored = CuratorCache(path=path, clock=clock)
    restored.load(now=NOW)
    assert restored.clusters()[0]["points_share_pct"] is None


def test_junk_cluster_rows_are_dropped_rather_than_rendered(cache):
    cache.store_clusters(["junk", {"size": 3}, _cluster(1, 2), None])
    assert len(cache.clusters()) == 1


# ---------------------------------------------------------------------------
# expire() / drop_last_good() — the runtime wallet switch (the `w` key)
# ---------------------------------------------------------------------------


def test_expire_makes_a_fresh_tier_due_without_touching_its_provenance(cache, clock):
    """The point of the method: refetch now, but keep `as of` honest.

    `mark_failed` also makes a tier come due *eventually*, and using it here
    would be wrong in both directions — it spaces the retry by the backoff, and
    it says the last attempt failed when it succeeded.
    """
    cache.mark_fetched(TIER_FAST)
    assert cache.is_fresh(TIER_FAST) is True
    fetched_at = cache.last_fetch_ts(TIER_FAST)

    cache.expire(TIER_FAST)

    assert cache.is_due(TIER_FAST) is True
    assert cache.seconds_until_due(TIER_FAST) == 0.0
    assert TIER_FAST in cache.tiers_due()
    # Provenance survives: expiring is not a fetch and not a failure.
    assert cache.last_fetch_ts(TIER_FAST) == fetched_at


def test_expire_leaves_every_other_tier_alone(cache):
    for tier in TIERS:
        cache.mark_fetched(tier)
    cache.expire(TIER_FAST)
    assert cache.tiers_due() == (TIER_FAST,)


def test_expire_is_idempotent_and_refuses_an_unknown_tier(cache):
    cache.expire(TIER_FAST)
    cache.expire(TIER_FAST)          # never fetched, expired twice: still fine
    assert cache.is_due(TIER_FAST) is True
    with pytest.raises(ValueError, match="unknown curator refresh tier"):
        cache.expire("wallet")       # a slot name, not a tier


def test_drop_last_good_forgets_the_payload_and_its_stamp(cache, clock):
    cache.store_last_good(SLOT_WALLET, {"address": "0x" + "ab" * 20})
    assert cache.get_last_good(SLOT_WALLET) is not None

    cache.drop_last_good(SLOT_WALLET)

    assert cache.get_last_good(SLOT_WALLET) is None
    assert cache.as_of_ts(SLOT_WALLET) is None
    assert cache.age_of(SLOT_WALLET) is None


def test_drop_last_good_leaves_the_other_slots_and_the_newest_stamp(cache, clock):
    cache.store_last_good(SLOT_STATE, {"hour": 14})
    clock.advance(60)
    cache.store_last_good(SLOT_WALLET, {"address": "0x" + "cd" * 20})
    newest_before = cache.newest_as_of()

    cache.drop_last_good(SLOT_WALLET)

    assert cache.get_last_good(SLOT_STATE) is not None
    # The dropped slot was the freshest, so the screen's `as of` must fall back
    # to the state read rather than keeping a stamp with nothing behind it.
    assert cache.newest_as_of() < newest_before


def test_drop_last_good_is_idempotent_and_refuses_an_unknown_slot(cache):
    cache.drop_last_good(SLOT_WALLET)
    cache.drop_last_good(SLOT_WALLET)
    with pytest.raises(ValueError, match="unknown curator slot"):
        cache.drop_last_good(TIER_FAST)   # a tier name, not a slot


# ---------------------------------------------------------------------------
# WP3.2 — the analysis tier and the clusters slot
# ---------------------------------------------------------------------------


def test_the_analysis_tier_is_long_ttl_with_a_shorter_backoff():
    """PRD §4 sizes the detached B+C sweep at ~30-60 min.  Its failure backoff
    must be shorter than its TTL, or a failed sweep would retry no sooner than
    a successful one and the backoff would be decorative."""
    assert TIER_ANALYSIS in TIERS
    assert 1_800.0 <= TIER_TTL_SECONDS[TIER_ANALYSIS] <= 3_600.0
    assert (
        TIER_FAILURE_BACKOFF_SECONDS[TIER_ANALYSIS]
        < TIER_TTL_SECONDS[TIER_ANALYSIS]
    )
    # ...and the four shipped tiers did not move with the growth.
    assert TIER_TTL_SECONDS[TIER_FAST] == 15.0
    assert TIER_TTL_SECONDS[TIER_MEDIUM] == 60.0
    assert TIER_TTL_SECONDS[TIER_SLOW] == 420.0
    assert TIER_TTL_SECONDS[TIER_ONCE] == float("inf")


def test_the_analysis_slot_refuses_none_and_round_trips(tmp_path, clock):
    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=clock)
    assert cache.analysis_last_good() is None
    assert cache.analysis_as_of_hhmm() is None
    with pytest.raises(ValueError):
        cache.store_last_good(SLOT_CLUSTERS, None, ts=NOW)

    payload = {"operators_count": 2, "groups": [{"size": 6, "conf": "high"}]}
    cache.store_analysis(payload, ts=NOW)
    assert cache.analysis_last_good().payload == payload
    cache.save()

    restored = CuratorCache(path=cache.path, clock=clock)
    restored.load(now=NOW)
    entry = restored.analysis_last_good()
    assert entry is not None
    assert entry.payload == payload
    assert entry.ts == NOW


def test_an_older_file_without_the_slot_still_loads_its_other_sections(
    tmp_path, clock
):
    """The additive-schema rule (the ens/dropped_events precedent), and the
    WP3.2 bite's designated victim: bumping _SCHEMA_VERSION makes this version-1
    file load NOTHING, so the state slot below comes back empty and this test
    reddens."""
    assert curator_cache._SCHEMA_VERSION == 1
    path = tmp_path / "old.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "saved_at": NOW,
                "last_good": {
                    "state": {"payload": {"settled": False}, "ts": NOW - 60}
                },
            }
        )
    )
    cache = CuratorCache(path=str(path), clock=clock)
    cache.load(now=NOW)
    assert cache.get_last_good(SLOT_STATE).payload == {"settled": False}
    # The older file simply lacks the slot; absence is 'analysis never ran'.
    assert cache.analysis_last_good() is None


def test_analysis_as_of_hhmm_is_the_slots_own_stamp_not_the_fast_tiers(
    tmp_path, clock
):
    """The sweep is detached and long-TTL: one marker for both tiers would
    present an hours-old analysis as live."""
    import time as _time

    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=clock)
    analysis_ts = NOW - 2 * 3600                      # an hours-old sweep
    cache.store_analysis({"operators_count": 0}, ts=analysis_ts)
    cache.store_last_good(SLOT_STATE, {"settled": False}, ts=NOW)

    expected = _time.strftime("%H:%M", _time.localtime(analysis_ts))
    assert cache.analysis_as_of_hhmm() == expected
    assert cache.analysis_as_of_hhmm() != _time.strftime(
        "%H:%M", _time.localtime(cache.newest_as_of())
    )


def test_an_analysis_publish_never_moves_the_global_freshness_marker(
    tmp_path, clock
):
    """`as_of_hhmm` claims a source ANSWERED.  The sweep re-analyzes data that
    was already fetched, so a publish during a total outage must not make the
    title bar's marker jump forward."""
    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=clock)
    cache.store_last_good(SLOT_STATE, {"settled": False}, ts=NOW)
    before = cache.newest_as_of()

    cache.store_analysis({"operators_count": 0}, ts=NOW + 1_800)
    assert cache.newest_as_of() == before


def test_the_analysis_slot_is_a_last_good_not_a_history(tmp_path, clock):
    """No verdict enters a SERIES: the slot is revisable, the series writers
    are untouched, and the persisted series section stays exactly the two
    sparkline payloads."""
    cache = CuratorCache(path=str(tmp_path / "c.json"), clock=clock)
    cache.store_analysis(
        {
            "operators_count": 1,
            "groups": [
                {"size": 6, "conf": "high", "members": ["0x" + "a1" * 20]}
            ],
        },
        ts=NOW,
    )
    cache.save()
    on_disk = json.loads(pathlib.Path(cache.path).read_text())
    assert set(on_disk["series"]) <= set(curator_cache.SERIES_NAMES)
    assert "clusters" not in on_disk["series"]
    with pytest.raises(ValueError, match="unknown curator series"):
        cache.get_series("clusters")
    # ...and a second publish REPLACES the first: revisable, never appended.
    cache.store_analysis({"operators_count": 0, "groups": []}, ts=NOW + 60)
    assert cache.analysis_last_good().payload["operators_count"] == 0

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
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_FAST,
    TIER_LAUNCHPAD,
    TIER_MEDIUM,
    TIER_SLOW,
    TIERS,
    TIER_TTL_SECONDS,
    SurfCache,
)

# Task 8 fix round 1: the launchpad cursor's round trip is only a meaningful
# proof if the cursor comes from the real ``fetch_launchpad`` sweep rather
# than a hand-typed literal here -- a literal would keep passing after the
# real cursor's shape moved, which is exactly the failure mode this test
# exists to catch. Imported rather than copied, on the same precedent as
# ``tests/data/test_fwa_refresh_budget.py`` importing ``test_fwa_client``'s
# harness: a cursor built by a different double than the one the client's
# own unit tests trust is a cursor whose shape this test cannot vouch for.
from maxpane_dashboard.data import surf_client
from tests.data.test_surf_client import (
    RecordingTransport,
    _client_on,
    _launchpad_fixture_handler,
    _load_launchpad,
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
    """fast is due every refresh; medium 90 s; slow 420 s; launchpad 600 s."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    assert TIERS == (TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_LAUNCHPAD)
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
    assert TIER_LAUNCHPAD not in c.tiers_due()

    clock.advance(TIER_TTL_SECONDS[TIER_SLOW])
    assert TIER_SLOW in c.tiers_due()
    assert TIER_LAUNCHPAD not in c.tiers_due()

    clock.advance(TIER_TTL_SECONDS[TIER_LAUNCHPAD])
    assert set(c.tiers_due()) == set(TIERS)


def test_launchpad_tier_is_slow_and_backs_off_shorter(tmp_path):
    """The analysis-tier shape: a long TTL, a shorter failure backoff.

    Deliberately slower than the title bar's clock -- the panel carries its
    own `as of HH:MM` and says so (the curator `TIER_ANALYSIS` precedent).
    """
    assert TIER_LAUNCHPAD in TIERS
    assert TIER_TTL_SECONDS[TIER_LAUNCHPAD] == 600.0
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_LAUNCHPAD] == 180.0
    assert TIER_FAILURE_BACKOFF_SECONDS[TIER_LAUNCHPAD] < TIER_TTL_SECONDS[TIER_LAUNCHPAD]


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
    SLOT_LAUNCHPAD,
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
    assert len(SLOTS) == 7


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


def test_forward_ordered_sampling_is_unchanged(tmp_path):
    """Baseline: normal ascending-time polling still just appends/overwrites."""
    c = _cache(tmp_path)
    base = 1_786_190_400.0
    c.sample_series(base, imd_supply=100.0)
    c.sample_series(base + 1800.0, imd_supply=150.0)          # same hour: last-wins
    c.sample_series(base + 3600.0, imd_supply=200.0)
    c.sample_series(base + 7200.0, imd_supply=300.0)
    assert c.get_series(SERIES_IMD_SUPPLY) == [
        [base, 150.0],
        [base + 3600.0, 200.0],
        [base + 7200.0, 300.0],
    ]


def test_out_of_order_sample_does_not_break_ascending_order(tmp_path):
    """A backward clock step (NTP correction) must not reverse the series."""
    c = _cache(tmp_path)
    hour = 1_786_190_400.0
    c.sample_series(hour + 3600.0, imd_supply=200.0)
    c.sample_series(hour, imd_supply=100.0)                   # arrives late, older bucket

    series = c.get_series(SERIES_IMD_SUPPLY)
    assert series == [[hour, 100.0], [hour + 3600.0, 200.0]]
    timestamps = [pt[0] for pt in series]
    assert timestamps == sorted(timestamps)


def test_interleaved_repeat_of_an_earlier_hour_does_not_duplicate_it(tmp_path):
    """A repeat of an already-recorded hour, arriving after a newer one, must
    merge in place -- never create two non-adjacent entries for one hour."""
    c = _cache(tmp_path)
    hour = 1_786_190_400.0
    c.sample_series(hour, imd_supply=1.0)
    c.sample_series(hour - 3600.0, imd_supply=2.0)            # older, unseen hour
    c.sample_series(hour, imd_supply=3.0)                     # repeat of the first hour

    series = c.get_series(SERIES_IMD_SUPPLY)
    timestamps = [pt[0] for pt in series]
    assert timestamps == sorted(timestamps)
    assert len(timestamps) == len(set(timestamps)), "an hour must never appear twice"
    assert series == [[hour - 3600.0, 2.0], [hour, 3.0]]


# ---------------------------------------------------------------------------
# Signal baselines (PRD §3)
# ---------------------------------------------------------------------------


from maxpane_dashboard.data.surf_cache import (   # noqa: E402
    BASELINE_DETAIL_CAP,
    BASELINE_FIRED_KEY,
)


def _baselines() -> dict:
    """The shape build_signals returns, using live values from the captures."""
    return {
        "announce_nonce": 14,             # eth_getTransactionCount(ANNOUNCE)
        "dev_nonce": 2350,
        "ops_nonce": 29,
        "lp_liquidity": 1234567890123456789,
        "gate_open": False,               # gate closed since 2026-05-14
        # WP2's spelling (BASELINE_SCALARS), not a paraphrase: the cache is
        # schema-agnostic, so a wrong key here round-trips green and only shows
        # up as a detector that never fires. Task WP4.11 has the same rule.
        "identities_written": 1,          # 1/2000 written
        "imd_supply": IMD_SUPPLY,
        "channel_tx_count": 21,           # posts AND replies, against nonce 14
        "hook_live": False,               # v4 hook not deployed
        "bridge_last_block": 25_707_780,
        # WP2's shape, verbatim: {signal: {"ts": float, "detail": str}}. The
        # details are the real ones build_signals renders — the nonce-13 post
        # and the 2026-07-31 burn.
        BASELINE_FIRED_KEY: {
            "post": {"ts": 1_786_076_831.0, "detail": '#13 "as always 0 promises."'},
            "burn": {"ts": 1_785_903_575.0, "detail": "31,064 IMD → BurnExecutor"},
        },
    }


def test_baselines_round_trip_in_memory(tmp_path):
    c = _cache(tmp_path)
    assert c.get_baselines() == {}
    c.set_baselines(_baselines())
    assert c.get_baselines() == _baselines()


def test_get_baselines_hands_out_a_copy_not_the_live_dict(tmp_path):
    """A caller mutating what it got must not silently advance a baseline.

    The FIRED store is two levels deep, so a one-level ``dict(...)`` is not a
    copy: the per-signal ``{"ts", "detail"}`` dicts would still be shared, and a
    caller editing a detail would rewrite what the next restart renders.
    """
    c = _cache(tmp_path)
    c.set_baselines(_baselines())
    got = c.get_baselines()
    got["announce_nonce"] = 99
    got[BASELINE_FIRED_KEY]["post"]["ts"] = 0.0
    got[BASELINE_FIRED_KEY]["post"]["detail"] = "tampered"
    assert c.get_baselines()["announce_nonce"] == 14
    assert c.get_baselines()[BASELINE_FIRED_KEY]["post"] == {
        "ts": 1_786_076_831.0,
        "detail": '#13 "as always 0 promises."',
    }


def test_unusable_baseline_values_are_dropped_not_coerced(tmp_path):
    c = _cache(tmp_path)
    c.set_baselines(
        {
            "announce_nonce": 14,
            "imd_supply": float("nan"),
            "junk": object(),
            "nested": {"too": {"deep": 1}},
            BASELINE_FIRED_KEY: {
                "post": {"ts": "yesterday", "detail": "x"},   # unparsable stamp
                "lp": {"ts": float("inf"), "detail": "x"},
                "burn": {"ts": -1.0, "detail": "x"},          # non-positive
                "gate": 1_786_076_831.0,                      # the OLD flat shape
            },
        }
    )
    got = c.get_baselines()
    assert got["announce_nonce"] == 14
    assert "imd_supply" not in got          # NaN is not a supply
    assert "junk" not in got
    assert "nested" not in got
    assert got[BASELINE_FIRED_KEY] == {}    # every fired entry was unusable


def test_a_fired_detail_is_coerced_to_text_and_bounded(tmp_path):
    """``detail`` is what a restart re-renders, so it must survive as text.

    It is third-party-influenced (a post body reaches it through WP2), so it is
    stored as a plain string and bounded — but bounded generously: WP2's
    ``DETAIL_LIMIT`` (48) caps the *message body*, and the rendered line adds a
    label and quotes around it. A tight cap here would silently rewrite the
    line the user sees after a restart.
    """
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.set_baselines(
        {
            BASELINE_FIRED_KEY: {
                "post": {"ts": clock.t - 60.0, "detail": "x" * (BASELINE_DETAIL_CAP + 50)},
                "lp": {"ts": clock.t - 60.0, "detail": None},
                "gate": {"ts": clock.t - 60.0, "detail": 42},
            }
        }
    )
    fired = c.get_baselines()[BASELINE_FIRED_KEY]
    assert len(fired["post"]["detail"]) == BASELINE_DETAIL_CAP
    assert fired["lp"]["detail"] == ""       # a missing detail is empty, not dropped
    assert fired["gate"]["detail"] == "42"   # coerced, never a stray int on disk


def test_a_future_dated_fired_stamp_is_dropped(tmp_path):
    """Clock-skew corruption must not pin a detector at FIRED forever."""
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    c.set_baselines(
        {
            BASELINE_FIRED_KEY: {
                "post": {"ts": clock.t + 86_400.0, "detail": "from the future"},
                "lp": {"ts": clock.t - 60.0, "detail": "LP +33 ETH"},
            }
        }
    )
    assert c.get_baselines()[BASELINE_FIRED_KEY] == {
        "lp": {"ts": clock.t - 60.0, "detail": "LP +33 ETH"}
    }


def test_set_baselines_replaces_wholesale(tmp_path):
    """build_signals returns the complete advanced set; merging would resurrect."""
    c = _cache(tmp_path)
    c.set_baselines(_baselines())
    c.set_baselines({"announce_nonce": 15})
    assert c.get_baselines() == {"announce_nonce": 15}


def test_non_mapping_baselines_are_ignored(tmp_path):
    c = _cache(tmp_path)
    c.set_baselines(_baselines())
    c.set_baselines(None)                   # type: ignore[arg-type]
    assert c.get_baselines() == {}


# ---------------------------------------------------------------------------
# Observed-burn accumulator (WP4.5) -- successful reads only
# ---------------------------------------------------------------------------


def test_observed_burn_total_is_none_before_any_read_then_zero(tmp_path):
    """The three states the widget branches on, pinned at the source.

    ``None`` and ``0.0`` are different claims and the difference is the whole
    point: ``None`` is "we have never successfully read totalSupply", ``0.0``
    is "we have, and nothing has moved *since*".  Neither is "no IMD has ever
    been burned" -- ~58,849 IMD were burned before any install existed (PRD
    §1) and this accumulator structurally cannot see them.  WP3.2's SurfHero
    renders ``0.0`` as words for exactly that reason.
    """
    c = _cache(tmp_path)
    assert c.observed_burn_total() is None
    assert c.record_supply(IMD_SUPPLY) is None          # first read: no conclusion
    assert c.observed_burn_total() == 0.0               # observed nothing, honestly
    # A *delta* still needs a second successful read; one read concludes nothing.
    assert c.record_supply(IMD_SUPPLY) == 0.0
    assert c.observed_burn_total() == 0.0


def test_a_real_burn_is_accumulated(tmp_path):
    """The 2026-08-05 event: 15,745 IMD, announced to the minute."""
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    delta = c.record_supply(IMD_SUPPLY - 15_745.0)
    assert delta == pytest.approx(15_745.0)
    assert c.observed_burn_total() == pytest.approx(15_745.0)

    # A later burn adds; the total is cumulative, never a replacement.
    c.record_supply(IMD_SUPPLY - 15_745.0 - 31_064.0)
    assert c.observed_burn_total() == pytest.approx(46_809.0)


def test_a_failed_supply_read_can_never_produce_a_burn(tmp_path):
    """The regression this whole module exists for: None is not 0 (PRD §6.1)."""
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    assert c.record_supply(None) is None                # outage
    assert c.observed_burn_total() == 0.0               # no 2.37M "burn"
    assert c.last_supply == IMD_SUPPLY                  # baseline untouched

    # Recovery compares against the pre-outage baseline, not against None.
    assert c.record_supply(IMD_SUPPLY) == 0.0
    assert c.observed_burn_total() == 0.0


def test_a_supply_increase_is_a_bridge_in_not_a_negative_burn(tmp_path):
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    assert c.record_supply(IMD_SUPPLY + 1_000.0) == 0.0
    assert c.observed_burn_total() == 0.0
    assert c.last_supply == IMD_SUPPLY + 1_000.0


def test_a_non_finite_supply_is_not_a_reading(tmp_path):
    c = _cache(tmp_path)
    c.record_supply(IMD_SUPPLY)
    assert c.record_supply(float("nan")) is None
    assert c.last_supply == IMD_SUPPLY


def test_out_of_order_block_does_not_fabricate_a_burn(tmp_path):
    """Fix round 1: a stale RPC replica must not manufacture a burn.

    True burn is 150 (1000 -> 850). A stale replica then answers with an
    OLDER block reporting 900 -- read naively that looks like a bridge-in
    increase and would re-baseline the accumulator upward; a later in-order
    re-poll of 850 would then look like a SECOND decrease (total 200, not
    150). The block number is what tells the accumulator to ignore it: it
    advances monotonically on-chain even when replies do not arrive in that
    order over a load-balanced RPC pool.
    """
    c = _cache(tmp_path)
    assert c.record_supply(1000.0, block_number=100) is None       # baseline
    assert c.record_supply(850.0, block_number=200) == pytest.approx(150.0)
    # Stale replica: block 150 was already superseded by block 200.
    assert c.record_supply(900.0, block_number=150) is None
    assert c.last_supply == 850.0                                   # untouched
    # In-order re-poll of the same true value: no further decrease.
    assert c.record_supply(850.0, block_number=300) == 0.0
    assert c.observed_burn_total() == pytest.approx(150.0)          # not 200


def test_a_genuine_bridge_in_still_re_baselines_at_an_advancing_block(tmp_path):
    """An increase at a strictly later block is a real bridge-in, not noise."""
    c = _cache(tmp_path)
    c.record_supply(1000.0, block_number=100)
    assert c.record_supply(1200.0, block_number=200) == 0.0   # bridge-in, re-baselines
    assert c.last_supply == 1200.0
    delta = c.record_supply(1100.0, block_number=300)         # decrease from the NEW high
    assert delta == pytest.approx(100.0)
    assert c.observed_burn_total() == pytest.approx(100.0)


def test_a_repeated_block_is_ignored(tmp_path):
    c = _cache(tmp_path)
    c.record_supply(1000.0, block_number=100)
    assert c.record_supply(850.0, block_number=200) == pytest.approx(150.0)
    assert c.record_supply(900.0, block_number=200) is None    # same block, ignored
    assert c.last_supply == 850.0
    assert c.observed_burn_total() == pytest.approx(150.0)


def test_omitting_block_number_falls_back_to_value_only_behaviour(tmp_path):
    """A caller with no block number yet must not lose the old behaviour."""
    c = _cache(tmp_path)
    c.record_supply(1000.0)
    assert c.record_supply(850.0) == pytest.approx(150.0)
    assert c.observed_burn_total() == pytest.approx(150.0)


def test_a_numeric_string_is_not_a_reading(tmp_path):
    """The contract is ``float | None``, not "anything float() tolerates"."""
    c = _cache(tmp_path)
    c.record_supply(1000.0)
    assert c.record_supply("1000") is None
    assert c.last_supply == 1000.0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

HOSTILE = [
    [1_786_100_000.0, 0.71],       # good
    [1_786_103_600.0, None],       # the reported crash: a null in the file
    "not a point",
    # A **non-numeric** string, matching `tests/data/test_cache_corruption.py`'s
    # own hostile fixture. `"0.72"` would be the wrong choice and it is the one
    # this fixture used to carry: `coerce_point` does `float(pt[1])` inside a
    # `except (TypeError, ValueError)`, so `float("0.72")` *succeeds* and the
    # point survives — three points back, not two, and the assertion below fails
    # for a reason that looks like a validator bug. It is not one. Do **not**
    # "fix" `data/series_points.py` to reject numeric strings: it is a leaf
    # shared by all eight dashboards, no surf work package owns it, and
    # tightening it is a repo-wide change to report to the plan owner.
    [1_786_107_200.0, "banana"],   # a string that is not a number
    [1_786_110_800.0, float("nan")],
    [0, 0.73],                     # non-positive timestamp
    [1_786_114_400.0, 0.74],       # good
]
GOOD = [[1_786_100_000.0, 0.71], [1_786_114_400.0, 0.74]]


def test_round_trip_restores_everything_that_matters(tmp_path):
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)

    c.store_last_good(SLOT_MARKET, {"imd_price_usd": IMD_PRICE_USD})
    c.sample_series(clock.t, imd_supply=IMD_SUPPLY, imd_price_usd=IMD_PRICE_USD,
                    parity_pct=PARITY_PCT)
    c.set_baselines(_baselines())
    c.record_supply(IMD_SUPPLY)
    c.record_supply(IMD_SUPPLY - 15_745.0)
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()

    assert restored.get_last_good(SLOT_MARKET).payload == {"imd_price_usd": IMD_PRICE_USD}
    assert restored.get_last_good(SLOT_MARKET).ts == clock.t
    assert restored.get_series(SERIES_IMD_SUPPLY) == c.get_series(SERIES_IMD_SUPPLY)
    assert restored.get_series(SERIES_PARITY_PCT) == [[_bucket(clock.t), PARITY_PCT]]
    assert restored.get_baselines() == _baselines()
    assert restored.observed_burn_total() == pytest.approx(15_745.0)
    assert restored.last_supply == pytest.approx(IMD_SUPPLY - 15_745.0)


def _bucket(ts: float) -> float:
    return float(int(ts // 3600) * 3600)


def test_a_restart_neither_resurrects_nor_loses_a_fired_stamp(tmp_path):
    """PRD §3: the FIRED display must survive a restart with its real age.

    Both halves of the entry have to survive: the ``ts`` is what dates the row
    (``age_s``, and whether ``FIRED_TTL_S`` has passed) and the ``detail`` is
    what the relaxed ``last: …`` clause quotes. Losing either turns a persisted
    FIRED into a blank one.
    """
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    fired_at = clock.t - 7_200.0             # fired two hours ago

    c = SurfCache(path=path, clock=clock)
    c.set_baselines(
        {
            "announce_nonce": 14,
            BASELINE_FIRED_KEY: {"post": {"ts": fired_at, "detail": '#14 "soon"'}},
        }
    )
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert restored.get_baselines()[BASELINE_FIRED_KEY]["post"] == {
        "ts": fired_at,
        "detail": '#14 "soon"',
    }
    # And the *nonce* baseline came back too, so the signal cannot re-fire on
    # the same post.
    assert restored.get_baselines()["announce_nonce"] == 14


def test_every_tier_is_due_again_after_a_restart(tmp_path):
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    for tier in TIERS:
        c.mark_fetched(tier)
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert set(restored.tiers_due()) == set(TIERS)


def test_launchpad_slot_round_trips_through_the_cache_file(tmp_path):
    """The detached launchpad sweep's last-good payload survives a restart.

    Task 6 hangs a slow, detached launchpad sweep off ``TIER_LAUNCHPAD`` /
    ``SLOT_LAUNCHPAD``; this only proves the slot exists and round-trips --
    the sweep itself is out of scope here.
    """
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)

    assert SLOT_LAUNCHPAD in SLOTS
    c.store_last_good(SLOT_LAUNCHPAD, {"coin_count": 146})
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert restored.get_last_good(SLOT_LAUNCHPAD).payload == {"coin_count": 146}


async def test_the_launchpad_cursors_real_shape_round_trips_through_the_cache_file(
    tmp_path,
) -> None:
    """The test above proves the SLOT round-trips at all, with a one-key toy
    payload. It does not prove the **cursor** survives, because the cursor is
    the one field in that slot with real internal structure -- six keys, three
    of them nested dicts, one a list -- and nothing about
    ``test_launchpad_slot_round_trips_through_the_cache_file``'s
    ``{"coin_count": 146}`` exercises any of that.

    Task 8's own round-trip test (``test_surf_manager.py``) already proves
    the *manager* reads the cursor back out of the slot and hands it to
    ``fetch_launchpad`` on the next sweep -- but it reads that slot out of
    ``SurfCache``'s in-memory dict, never through an actual ``save()``/
    ``load()``. This is the other half: the cursor a *real*
    ``SurfClient.fetch_launchpad()`` sweep produces, written to an actual
    cache file and read back, asserted equal.

    The cursor comes from a real sweep against the committed launchpad
    fixtures (the same double ``test_fetch_launchpad_ranks_and_decodes_the_
    real_fixture`` in ``test_surf_client.py`` uses) rather than a hand-typed
    dict here: a hand-typed literal would keep this test green even after
    ``_launchpad_logs`` changed what it puts in the cursor, which is the one
    kind of drift a round-trip test is supposed to catch.

    ``traders`` (a ``sorted()`` list, never the raw ``set`` -- see
    ``_launchpad_logs``'s own comment) is deliberately not sanity-checked as
    a list *before* the save/load round trip below: ``SurfCache._jsonable``
    already coerces a bare ``set`` into a list on the way to disk, so a
    regression there does not crash ``save()`` (which is documented "never
    raises" and means it) and does not drop the slot either -- both milder
    than they sound. What it *does* break is exactly what the final
    assertion below checks: a Python ``set`` is never ``==`` to the ``list``
    it round-trips into, so a dropped ``sorted()`` still fails this test,
    just via a value mismatch after ``save()``/``load()`` rather than a
    crash during either.
    """
    reads = _load_launchpad("launchpad_reads.json")
    logs_data = _load_launchpad("launchpad_logs.json")
    launches = [surf_client._decode_launched_log(r) for r in logs_data["launched"]]
    assert all(launch is not None for launch in launches)
    prices = {launch["pool_id"]: 5_000_000_000_000 + i for i, launch in enumerate(launches)}

    handler = _launchpad_fixture_handler(reads, logs_data, prices)
    transport = RecordingTransport(handler)
    async with _client_on(transport, now_fn=lambda: 2_000_000_000.0) as client:
        state = await client.fetch_launchpad()

    cursor = state.cursor
    assert cursor is not None
    # Ruling R13: all six keys, never the three-key shape an earlier draft of
    # this plan described -- and this assertion is itself read off the real
    # sweep's own output, not typed here, so it moves with the client rather
    # than silently going stale against it.
    assert set(cursor) == {
        "last_block", "launches", "swaps_all", "traders",
        "burn_by_coin", "burned_total_wei",
    }
    # A rich shape, not a degenerate all-empty default -- the two fields the
    # `traders` mutation below does not touch, so they stay a meaningful
    # sanity check under it rather than being what actually catches it.
    assert isinstance(cursor["launches"], dict) and cursor["launches"]
    assert all(isinstance(rec, dict) for rec in cursor["launches"].values())
    assert isinstance(cursor["swaps_all"], dict) and cursor["swaps_all"]

    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    c.store_last_good(SLOT_LAUNCHPAD, {"cursor": cursor})
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert restored.get_last_good(SLOT_LAUNCHPAD).payload["cursor"] == cursor


def test_a_null_poisoned_series_costs_only_that_point(tmp_path, caplog):
    """One null used to abort startup for *every* dashboard."""
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "series": {
                    SERIES_IMD_PRICE_USD: HOSTILE,
                    SERIES_PARITY_PCT: [[1_786_100_000.0, -2.7495188342040167]],
                },
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    with caplog.at_level("WARNING"):
        c.load()                                     # must not raise

    assert c.get_series(SERIES_IMD_PRICE_USD) == GOOD
    assert c.get_series(SERIES_PARITY_PCT) == [[1_786_100_000.0, -2.7495188342040167]]
    assert "Skipped" in caplog.text


def test_a_negative_parity_point_survives_but_a_negative_price_does_not(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "series": {
                    SERIES_PARITY_PCT: [[1_786_100_000.0, -2.75]],
                    SERIES_IMD_PRICE_USD: [[1_786_100_000.0, -0.71]],
                },
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_series(SERIES_PARITY_PCT) == [[1_786_100_000.0, -2.75]]
    assert c.get_series(SERIES_IMD_PRICE_USD) == []


def test_corrupt_missing_and_hostile_files_load_empty_not_raise(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json at all")
    SurfCache(path=str(bad), clock=FakeClock()).load()          # no raise

    SurfCache(path=str(tmp_path / "nope.json"), clock=FakeClock()).load()

    listy = tmp_path / "list.json"
    listy.write_text("[1, 2, 3]")
    c = SurfCache(path=str(listy), clock=FakeClock())
    c.load()
    assert c.get_baselines() == {}
    assert c.get_last_good(SLOT_CHAIN) is None


def test_one_bad_section_never_costs_the_others(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "last_good": "not a mapping",
                "baselines": {"announce_nonce": 14},
                "series": {SERIES_IMD_SUPPLY: [[1_786_100_000.0, IMD_SUPPLY]]},
                "burned_cum": "lots",
                "last_supply": IMD_SUPPLY,
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    # No `fired` key: `_sanitise_baselines` emits one only when the input had
    # one, and this file's `baselines` section does not. Seeding it
    # unconditionally would be the wrong repair — `test_set_baselines_replaces_wholesale`
    # asserts `{"announce_nonce": 15}` exactly, and a manufactured empty `fired`
    # would also claim a store the file never held.
    assert c.get_baselines() == {"announce_nonce": 14}
    assert c.get_series(SERIES_IMD_SUPPLY) == [[1_786_100_000.0, IMD_SUPPLY]]
    assert c.burned_cum == 0.0
    assert c.last_supply == pytest.approx(IMD_SUPPLY)


def test_save_creates_its_directory_is_atomic_and_never_raises(tmp_path):
    nested = tmp_path / "deep" / "surf_cache.json"
    c = SurfCache(path=str(nested), clock=FakeClock())
    c.set_baselines({"announce_nonce": 14})
    c.save()
    assert nested.exists()
    assert not (tmp_path / "deep" / "surf_cache.json.tmp").exists()
    json.loads(nested.read_text())

    SurfCache(path="/proc/definitely/not/writable.json", clock=FakeClock()).save()


def test_a_non_finite_value_is_nulled_on_the_way_to_disk_never_fabricated(tmp_path):
    path = tmp_path / "surf_cache.json"
    c = SurfCache(path=str(path), clock=FakeClock())
    c.store_last_good(SLOT_CHAIN, {"imd_supply": float("inf"), "block": 25_707_780})
    c.save()
    payload = json.loads(path.read_text())
    assert payload["last_good"][SLOT_CHAIN]["payload"] == {
        "imd_supply": None,
        "block": 25_707_780,
    }


def test_a_stale_replica_after_restart_does_not_double_count_a_burn(tmp_path):
    """Fix round 1 review repro: the block watermark must survive a restart.

    True burn across the whole sequence is 150 (1000 -> 900 -> 850). Without
    a persisted watermark, a post-restart stale replica of the
    already-superseded block-100 reading looks "in order" (no watermark to
    reject it against), gets read as a bridge-in back up to 1000, and the
    next genuine 850 reading then looks like a SECOND 150 burn -- 250 total,
    not 150.
    """
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    assert c.record_supply(1000.0, block_number=100) is None            # baseline
    assert c.record_supply(900.0, block_number=101) == pytest.approx(100.0)
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    # The stale replica: block 100 was already superseded by block 101
    # before the restart.
    assert restored.record_supply(1000.0, block_number=100) is None
    assert restored.last_supply == pytest.approx(900.0)                 # untouched
    assert restored.record_supply(850.0, block_number=200) == pytest.approx(50.0)
    assert restored.observed_burn_total() == pytest.approx(150.0)       # not 250


def test_a_missing_watermark_does_not_silently_unguard_a_restored_supply(tmp_path):
    """A legacy/corrupt ``last_supply_block`` must not revert to no guard at all.

    ``last_supply`` came back but its watermark did not, so the cache cannot
    verify what block that value belongs to. The first block-numbered
    reading after that -- however it compares to the restored value -- must
    re-establish the watermark rather than be scored as a delta against a
    value whose provenance it cannot trust; only the *next* one after that is
    a real, guarded comparison.
    """
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps({"version": 1, "last_supply": 900.0})   # no last_supply_block key
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.last_supply == pytest.approx(900.0)

    # This would look like a 100-unit burn if compared naively -- it must not be.
    assert c.record_supply(800.0, block_number=50) is None
    assert c.last_supply == pytest.approx(800.0)
    assert c.observed_burn_total() == pytest.approx(0.0)
    # The watermark is now established at block 50, so ordering is guarded again.
    assert c.record_supply(700.0, block_number=40) is None              # stale, ignored
    assert c.last_supply == pytest.approx(800.0)
    assert c.record_supply(700.0, block_number=60) == pytest.approx(100.0)
    assert c.observed_burn_total() == pytest.approx(100.0)


def test_a_last_good_slot_stamped_a_year_ahead_does_not_read_as_live(tmp_path):
    """A skewed or hand-edited clock must not make a dead source look live.

    Series points and FIRED entries already reject a far-future ``ts``
    (``test_a_null_poisoned_series_costs_only_that_point`` and
    ``test_a_future_dated_fired_stamp_is_dropped``); a last-good slot must
    get the same treatment, or ``age_of`` clamps to ``0.0`` and the slot
    renders as freshly-arrived forever.
    """
    clock = FakeClock()
    path = tmp_path / "surf_cache.json"
    future_ts = clock.t + 365 * 24 * 3600            # a year ahead
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "last_good": {
                    SLOT_MARKET: {"payload": {"imd_price_usd": IMD_PRICE_USD}, "ts": future_ts},
                },
            }
        )
    )
    c = SurfCache(path=str(path), clock=clock)
    c.load()
    assert c.get_last_good(SLOT_MARKET) is None
    assert c.age_of(SLOT_MARKET) is None


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------


def test_the_cache_imports_no_client_no_analytics_no_network():
    from pathlib import Path as _Path

    import maxpane_dashboard.data.surf_cache as mod

    src = _Path(mod.__file__).read_text()
    project_imports = [
        line.strip()
        for line in src.splitlines()
        if line.strip().startswith(("import maxpane", "from maxpane"))
    ]
    assert project_imports == [
        "from maxpane_dashboard.data.series_points import (",
    ]
    for banned in ("requests", "httpx", "aiohttp", "urllib", "socket",
                   "surf_client", "surf_signals", "surf_manager", "textual"):
        assert f"import {banned}" not in src
    # It must not know the FIRED window: relaxing a FIRED is build_signals' call.
    assert "FIRED_TTL_S" not in src

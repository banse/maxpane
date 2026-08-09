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

"""Tests for the SURF tiered cache and its persistence layer (WP4).

Everything runs offline against a fake clock and ``tmp_path``: no network, no
sleeping, no dependence on wall-clock time.
"""

from __future__ import annotations

import json
import math
import os

import pytest

from maxpane_dashboard.data.surf_cache import (
    DEFAULT_CACHE_PATH,
    TIER_FAILURE_BACKOFF_SECONDS,
    TIER_FAST,
    TIER_LAUNCHPAD,
    TIER_POOL4,
    TIER_POOL4_STAKERS,
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
    _client_serving_the_real_burns,
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
    """fast is due every refresh; medium 90 s; slow 420 s; launchpad/pool4 600 s.

    ``TIER_POOL4`` joined the tuple with WP7 (the surf ``p`` body), and
    ``TIER_POOL4_STAKERS`` with WP0 of the ``4`` market body. The literal
    below is hand-typed rather than derived on purpose — deriving it from
    ``TIERS`` would compare a constant against itself — so a new tier reddens
    here first, which is what happened both times.
    """
    clock = FakeClock()
    c = _cache(tmp_path, clock)

    assert TIERS == (
        TIER_FAST, TIER_MEDIUM, TIER_SLOW, TIER_LAUNCHPAD, TIER_POOL4,
        TIER_POOL4_STAKERS, "swarm", "swarm_scores", "swarm_seat",
    )
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
    # The staker fold is the slowest tier of the six, so "everything is due"
    # is not reached here — and saying so is the point: a walk that asserted
    # `set(TIERS)` one advance too early would be green only because the
    # slowest tier had not yet been added to the tuple.
    assert TIER_POOL4_STAKERS not in c.tiers_due()

    clock.advance(TIER_TTL_SECONDS[TIER_POOL4_STAKERS])
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
    # Seven source groups, plus pool4's own slot (WP7), plus the staker
    # fold's (WP0 of the `4` body). The staker slot is deliberately NOT a
    # ninth degraded *group*: `SOURCE_POOL4` ("p4") is the eighth and last
    # name the title row has columns for, so the fold serves last-good behind
    # its own stale marker and folds into `p4` only when it has nothing.
    # Plus the swarm's two tier slots and, since WP4 of the swarm v2 plan, the
    # jobs-seen map both swarm tiers append to (`SLOT_SWARM_JOBS_SEEN`), and
    # the AGENT body's one seat (`SLOT_SWARM_SEAT`, the /seats plan WP2).
    assert len(SLOTS) == 13


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


def test_fired_tx_hash_is_normalised_and_malformed_or_legacy_values_are_safe(tmp_path):
    clock = FakeClock()
    c = _cache(tmp_path, clock)
    target = "0x" + "Ab" * 32
    c.set_baselines(
        {
            BASELINE_FIRED_KEY: {
                "post": {
                    "ts": clock.t - 60.0,
                    "detail": "new post",
                    "tx_hash": target,
                },
                "thread": {
                    "ts": clock.t - 60.0,
                    "detail": "bad target",
                    "tx_hash": "0xshort",
                },
                "burn": {"ts": clock.t - 60.0, "detail": "legacy"},
            }
        }
    )

    fired = c.get_baselines()[BASELINE_FIRED_KEY]
    assert fired["post"]["tx_hash"] == target.lower()
    assert "tx_hash" not in fired["thread"]
    assert fired["burn"] == {"ts": clock.t - 60.0, "detail": "legacy"}


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
    the one field in that slot with real internal structure -- seven keys,
    four of them nested dicts, one a list -- and nothing about
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

    ``burns`` is real here too but comes back **empty** off these fixtures --
    ``_launchpad_fixture_handler`` answers the burnkeeper log sweep empty on
    purpose (see its own docstring), so an empty ``{}`` would round-trip
    trivially and prove nothing about the one field in this cursor whose
    leaves are themselves ``None``-valued (``sender``, ``fee_wei``). A second
    real sweep supplies it: ``_client_serving_the_real_burns`` against the
    committed burnkeeper captures, run with both the sender read and the fee
    read switched off, so every row it returns comes back
    ``sender: None, fee_wei: None`` -- still a real client's real output,
    just the real output of the one sweep that actually exercises this key.
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

    # F8: both sweeps in this test already run on an injected
    # ``httpx.MockTransport`` double (never a real socket) -- but nothing
    # here proved that double was actually *exercised*, only that it was
    # *present*. A future refactor that quietly stopped routing
    # ``fetch_launchpad`` through ``client._client`` (a cache short-circuit,
    # say) would still leave ``cursor`` looking plausible on a laptop that
    # happens to be online, and this test would pass for the wrong reason.
    # `test_curator_published.py::test_every_request_goes_through_the_
    # injected_transport` closed exactly that gap for its own module: "a
    # module that ignored transport entirely ... would ALSO return None --
    # passing this test for the wrong reason on exactly the machines it runs
    # on. Asserting the injected transport was actually invoked is the only
    # way to make this environment-independent." Same proof, same reasoning,
    # applied here rather than invented fresh.
    assert transport.requests, "the mocked launchpad transport was never invoked"

    cursor = state.cursor
    assert cursor is not None
    # Ruling R13: all seven keys, never the three-key shape an earlier draft
    # of this plan described. This set is hand-typed, deliberately -- not
    # "read off the real sweep's own output" (an earlier version of this
    # comment claimed exactly that, which was never true of the two lines
    # below it and went stale the moment the cursor grew `burns`). Deriving
    # the expected set from `cursor` itself (`set(cursor) == set(cursor)`)
    # would be tautological and could never go red, which is the one thing a
    # key-set pin exists to be able to do. A hand-typed literal is the right
    # design here for that reason: it is exactly what made this assertion
    # fail the day `burns` joined the cursor as a seventh key, and it is
    # expected to fail again the next time the shape moves.
    assert set(cursor) == {
        "last_block", "launches", "swaps_all", "traders",
        "burn_by_coin", "burned_total_wei", "burns",
    }
    # A rich shape, not a degenerate all-empty default -- the two fields the
    # `traders` mutation below does not touch, so they stay a meaningful
    # sanity check under it rather than being what actually catches it.
    assert isinstance(cursor["launches"], dict) and cursor["launches"]
    assert all(isinstance(rec, dict) for rec in cursor["launches"].values())
    assert isinstance(cursor["swaps_all"], dict) and cursor["swaps_all"]

    # `burns` off THIS fixture is `{}` (see the docstring above), so splice
    # in the real, non-empty, `None`-bearing shape a second real sweep
    # produces before the round trip -- otherwise the newest and most
    # structured key in this cursor would be pinned by its key alone, with
    # nothing checking that its values, or their `None`s, survive at all.
    async with _client_serving_the_real_burns(
        price=False, attribute=False,
    ) as burn_client:
        burn_state = await burn_client.fetch_launchpad(resume=None)
    real_burns = burn_state.cursor["burns"]
    assert real_burns and all(
        rec["sender"] is None and rec["fee_wei"] is None
        for rec in real_burns.values()
    )
    # F8, same reasoning as the assertion on `transport` above: this client
    # is built by `_client_serving_the_real_burns` on its own
    # `RecordingTransport`, never exposed as a local here, so reach it off
    # `burn_client`'s own `_client` (the injected `httpx.AsyncClient`, kept
    # alive after the `async with` block because `OwnedHttpClient.close()` is
    # a no-op for a client it does not own) and prove that double, too, was
    # actually exercised rather than merely present.
    burn_transport = burn_client._client._transport
    assert isinstance(burn_transport, RecordingTransport)
    assert burn_transport.requests, "the mocked burnkeeper transport was never invoked"
    cursor["burns"] = real_burns

    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    c.store_last_good(SLOT_LAUNCHPAD, {"cursor": cursor})
    c.save()

    restored = SurfCache(path=path, clock=clock)
    restored.load()
    restored_cursor = restored.get_last_good(SLOT_LAUNCHPAD).payload["cursor"]
    assert restored_cursor == cursor
    # The blanket equality above already recurses into every nested dict,
    # `burns` included -- but state the coverage explicitly for the field
    # this test exists to prove, rather than trusting an unexamined `==` to
    # have reached five rows deep on its own.
    assert restored_cursor["burns"] == real_burns
    assert all(
        rec["sender"] is None and rec["fee_wei"] is None
        for rec in restored_cursor["burns"].values()
    )


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

    # F7: a fresh cache starts clean (nothing to persist yet), and ``save()``
    # now skips the write entirely while clean -- so without a mutation here
    # this call would return before ever touching the unwritable path,
    # proving nothing. Dirty it first so the write, and the exception it
    # raises, are actually exercised.
    unwritable = SurfCache(path="/proc/definitely/not/writable.json", clock=FakeClock())
    unwritable.set_baselines({"announce_nonce": 14})
    unwritable.save()


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
# F7 -- save() skips the write when nothing has changed
#
# The mechanism is a dirty flag set at the exact point of every mutation
# ``save()`` persists (never inferred from container identity -- ``series``'
# deques and ``_pool4_accumulators`` are mutated *in place*, so an identity
# check on the outer container would miss exactly the mutation it exists to
# catch), cleared only after a successful write. Every test below observes
# the skip structurally: a spy on ``os.replace`` (the call ``save()`` uses to
# commit the atomic temp-then-rename) counts real writes, and the file's
# inode -- which that rename always replaces on a real write -- corroborates
# it independently.
# ---------------------------------------------------------------------------


def _os_replace_spy(monkeypatch) -> list[tuple[str, str]]:
    """Count real ``os.replace`` calls without changing what they do."""
    calls: list[tuple[str, str]] = []
    real_replace = os.replace

    def spy(src, dst):
        calls.append((str(src), str(dst)))
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", spy)
    return calls


def test_a_cycle_with_nothing_changed_performs_no_write(tmp_path, monkeypatch):
    calls = _os_replace_spy(monkeypatch)
    c = _cache(tmp_path)
    c.store_last_good(SLOT_CHAIN, {"block": 1, "announce_nonce": 14})
    c.save()
    assert len(calls) == 1
    path = tmp_path / "surf_cache.json"
    ino = path.stat().st_ino
    written = path.read_bytes()

    # Nothing mutates the cache between these -- this is "a cycle in which
    # nothing changed". Called twice to prove the skip is not a one-shot.
    c.save()
    c.save()

    assert len(calls) == 1, "an unchanged cache must not call os.replace again"
    assert path.stat().st_ino == ino, "no write means no new inode"
    assert path.read_bytes() == written


def test_a_changed_slot_still_writes_and_the_written_shape_is_unaffected(
    tmp_path, monkeypatch
):
    calls = _os_replace_spy(monkeypatch)
    c = _cache(tmp_path)
    c.store_last_good(SLOT_CHAIN, {"block": 1, "announce_nonce": 14})
    c.save()
    assert len(calls) == 1
    path = tmp_path / "surf_cache.json"
    ino = path.stat().st_ino

    c.store_last_good(SLOT_CHAIN, {"block": 2, "announce_nonce": 14})
    c.save()

    assert len(calls) == 2, "a real change must still write"
    assert path.stat().st_ino != ino, (
        "a real write always replaces the file (atomic temp-then-rename)"
    )
    payload = json.loads(path.read_text())
    # The skip mechanism changed nothing about *what* gets written: same
    # top-level shape every other persistence test in this file relies on.
    assert set(payload) == {
        "version", "saved_at", "last_good", "series", "baselines",
        "burned_cum", "last_supply", "last_supply_block", "pool4_accumulators",
    }
    assert payload["last_good"][SLOT_CHAIN]["payload"] == {
        "block": 2, "announce_nonce": 14,
    }


def test_an_in_place_series_update_within_the_same_hour_still_dirties_the_cache(
    tmp_path, monkeypatch
):
    """The identity trap, worked: ``_bucket_into`` mutates the deque in place
    (``deq[-1] = ...``) rather than replacing ``self.series[name]``, so an
    identity check on the series dict -- or on the deque object -- would
    never see this change. The flag must still catch it.
    """
    calls = _os_replace_spy(monkeypatch)
    c = _cache(tmp_path)
    base = 1_786_190_400.0  # on an hour boundary
    c.sample_series(base, imd_supply=100.0)
    c.save()
    assert len(calls) == 1
    path = tmp_path / "surf_cache.json"
    ino = path.stat().st_ino
    deq_before = c.series[SERIES_IMD_SUPPLY]

    # Same hour, a different value: the `deq[-1] = (bucket, val)` branch,
    # mutating the SAME deque object rather than replacing it.
    c.sample_series(base + 60.0, imd_supply=105.0)
    assert c.series[SERIES_IMD_SUPPLY] is deq_before, (
        "this must exercise the in-place mutation path, or the test below "
        "proves nothing"
    )
    c.save()

    assert len(calls) == 2, "an in-place series mutation must still trigger a write"
    assert path.stat().st_ino != ino
    payload = json.loads(path.read_text())
    assert payload["series"][SERIES_IMD_SUPPLY] == [[base, 105.0]]


def test_replacing_one_pool4_accumulator_entry_still_dirties_the_cache(
    tmp_path, monkeypatch
):
    """Same trap, one layer out: ``set_pool4_accumulator`` replaces one key
    of ``self._pool4_accumulators`` (``dict.__setitem__``) -- the outer dict
    object is never swapped, only mutated in place.
    """
    calls = _os_replace_spy(monkeypatch)
    c = _cache(tmp_path)
    c.set_pool4_accumulator(
        "SEPOLIA", {"genesis_block": 100, "cursor_block": 100, "sums": {}}
    )
    c.save()
    assert len(calls) == 1
    path = tmp_path / "surf_cache.json"
    ino = path.stat().st_ino
    outer_before = c._pool4_accumulators

    c.set_pool4_accumulator(
        "SEPOLIA", {"genesis_block": 100, "cursor_block": 150, "sums": {"a": 3}}
    )
    assert c._pool4_accumulators is outer_before, (
        "this must exercise the in-place mutation path"
    )
    c.save()

    assert len(calls) == 2
    assert path.stat().st_ino != ino


def test_a_skipped_write_still_recovers_exactly_the_same_state_after_a_restart(
    tmp_path, monkeypatch
):
    calls = _os_replace_spy(monkeypatch)
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    c.store_last_good(SLOT_CHAIN, {"block": 1, "announce_nonce": 14})
    c.set_baselines({"announce_nonce": 14})
    c.sample_series(clock.t, imd_supply=100.0)
    assert c.record_supply(1000.0, block_number=10) is None
    c.save()
    assert len(calls) == 1

    # A quiet cycle: nothing mutates the cache before this save, so it must
    # be skipped -- and a restart afterwards must still recover everything
    # the first, real write put on disk.
    c.save()
    assert len(calls) == 1

    restored = SurfCache(path=path, clock=FakeClock())
    restored.load()
    assert restored.get_last_good(SLOT_CHAIN).payload == c.get_last_good(SLOT_CHAIN).payload
    assert restored.get_last_good(SLOT_CHAIN).ts == c.get_last_good(SLOT_CHAIN).ts
    assert restored.get_baselines() == c.get_baselines()
    assert restored.get_series(SERIES_IMD_SUPPLY) == c.get_series(SERIES_IMD_SUPPLY)
    assert restored.last_supply == c.last_supply
    assert restored.burned_cum == c.burned_cum


from maxpane_dashboard.data.surf_cache import (   # noqa: E402  (appended import)
    SERIES_POOL4_RESERVE_SEPOLIA,
)


# ---------------------------------------------------------------------------
# Fix round 2 -- ``load()`` dirties the cache exactly when it had to repair
# something, so a damaged file self-heals on the next save() and a clean
# round trip still skips the write.
# ---------------------------------------------------------------------------


def test_a_damaged_load_dirties_the_cache_so_the_next_save_repairs_it(
    tmp_path, monkeypatch
):
    """Several sanitised fields at once: a dropped last-good slot (bad ts), a
    dropped series point, a non-numeric ``burned_cum``, and a structurally
    bogus pool4 accumulator. None of this should raise, and -- the point of
    this test -- the reload must not look "clean": it diverged from what the
    file held, so it must be dirty, and a save() right after load(), with no
    other mutation in between, must actually rewrite the file rather than
    skip it (the pre-dirty-flag self-healing).
    """
    calls = _os_replace_spy(monkeypatch)
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "last_good": {
                    # A future-dated ts: LastGood.from_dict raises, dropping
                    # the whole slot.
                    SLOT_MARKET: {
                        "payload": {"imd_price_usd": IMD_PRICE_USD},
                        "ts": 9_999_999_999.0,
                    },
                },
                "series": {SERIES_IMD_SUPPLY: [[1_786_100_000.0, "banana"]]},
                "burned_cum": "not-a-number",
                "pool4_accumulators": {
                    SERIES_POOL4_RESERVE_SEPOLIA: {"genesis_block": "nope"},
                },
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()

    # The damage really was dropped/coerced, not silently kept:
    assert c.get_last_good(SLOT_MARKET) is None
    assert c.get_series(SERIES_IMD_SUPPLY) == []
    assert c.burned_cum == 0.0

    assert c._dirty is True, "a load that had to repair something must dirty the cache"

    c.save()
    assert len(calls) == 1, "a damaged load must self-heal on the very next save"
    on_disk = json.loads(path.read_text())
    assert on_disk["burned_cum"] == 0.0, "the corrupt bytes must not survive the repair"


def test_a_clean_load_does_not_dirty_the_cache(tmp_path, monkeypatch):
    """The mirror image: a fully well-formed cache file, freshly loaded, must
    not be marked dirty -- there was nothing to repair, so the very next
    save() (nothing else mutating in between) must still be skipped.
    """
    clock = FakeClock()
    path = str(tmp_path / "surf_cache.json")
    c = SurfCache(path=path, clock=clock)
    c.store_last_good(SLOT_MARKET, {"imd_price_usd": IMD_PRICE_USD})
    c.sample_series(clock.t, imd_supply=IMD_SUPPLY)
    c.set_baselines(_baselines())
    c.record_supply(IMD_SUPPLY)
    c.set_pool4_accumulator(
        "SEPOLIA", {"genesis_block": 100, "cursor_block": 150, "sums": {"a": 3}}
    )
    c.save()

    calls = _os_replace_spy(monkeypatch)
    restored = SurfCache(path=path, clock=clock)
    restored.load()
    assert restored._dirty is False, "a clean load must not look dirty"

    restored.save()
    assert calls == [], "a clean load followed by no mutation must not write"


# ---------------------------------------------------------------------------
# Fix round 2, gap 1 -- the ``x or default`` idiom that used to guard four
# outer fields (``last_good``, ``series``, ``burned_cum``,
# ``pool4_accumulators``) could not tell "the field is absent" from "the
# field is present, falsy, and the wrong type": both sides of the ``or``
# land on the same default and no exception is ever raised, so the corrupt
# bytes silently survived every reload. A *truthy* wrong type (a non-empty
# string) already dirtied correctly, because it reached the ``.items()`` /
# ``float()`` call that raises. Only the falsy shapes were the gap.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["", 0, []])
def test_a_falsy_wrong_type_last_good_dirties_the_cache(tmp_path, bad):
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps({"version": 1, "last_good": bad}))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_last_good(SLOT_MARKET) is None
    assert c._dirty is True, f"last_good={bad!r} must dirty the cache"


@pytest.mark.parametrize("bad", ["", 0, []])
def test_a_falsy_wrong_type_series_block_dirties_the_cache(tmp_path, bad):
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps({"version": 1, "series": bad}))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_series(SERIES_IMD_SUPPLY) == []
    assert c._dirty is True, f"series={bad!r} must dirty the cache"


@pytest.mark.parametrize("bad", ["", []])
def test_a_falsy_wrong_type_burned_cum_dirties_the_cache(tmp_path, bad):
    # 0 is deliberately excluded here: it is a genuinely valid burned_cum
    # value, not corruption, and must never dirty (covered below).
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps({"version": 1, "burned_cum": bad}))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.burned_cum == 0.0
    assert c._dirty is True, (
        f"burned_cum={bad!r} is the sharpest case: a string/list where a "
        "number belongs, the same class of corruption as the truthy "
        "'not-a-number' case, and it must dirty exactly like that one."
    )


def test_burned_cum_zero_is_valid_and_never_dirties(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps({"version": 1, "burned_cum": 0}))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.burned_cum == 0.0
    assert c._dirty is False, "0 is a real, valid burned_cum -- not corruption"


@pytest.mark.parametrize("bad", ["", 0, []])
def test_a_falsy_wrong_type_pool4_accumulators_dirties_the_cache(tmp_path, bad):
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps({"version": 1, "pool4_accumulators": bad}))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_pool4_accumulator("SEPOLIA") is None
    assert c._dirty is True, f"pool4_accumulators={bad!r} must dirty the cache"


@pytest.mark.parametrize(
    "field", ["last_good", "series", "burned_cum", "pool4_accumulators"]
)
def test_a_missing_optional_field_stays_clean(tmp_path, field):
    """Absence must still never dirty: dropping any one of the four fields
    entirely (the ordinary shape of an older or minimal cache file) must
    load exactly as clean as a fully populated file.
    """
    payload = {
        "version": 1,
        "last_good": {},
        "series": {},
        "burned_cum": 0.0,
        "pool4_accumulators": {},
    }
    del payload[field]
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps(payload))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c._dirty is False, f"a missing {field!r} is absence, not corruption"


@pytest.mark.parametrize(
    "field", ["last_good", "series", "burned_cum", "pool4_accumulators"]
)
def test_an_explicit_null_field_stays_clean(tmp_path, field):
    """The same absence guarantee when the key is present with an explicit
    JSON ``null`` rather than omitted outright.
    """
    payload = {
        "version": 1,
        "last_good": {},
        "series": {},
        "burned_cum": 0.0,
        "pool4_accumulators": {},
    }
    payload[field] = None
    path = tmp_path / "surf_cache.json"
    path.write_text(json.dumps(payload))
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c._dirty is False, f"an explicit null {field!r} is absence, not corruption"


# ---------------------------------------------------------------------------
# Fix round 2, gap 2 -- a per-series value that is present but not a
# sequence at all is a contract mismatch with ``coerce_points``, which is
# documented to answer ``([], 0)`` for "not a sequence" -- so ``dropped``
# stays 0 and the series is silently replaced with an empty one, identical
# to "this series was never populated". Both truthinesses of the bad shape
# must dirty; only ``None`` (absent-equivalent) must not.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["not-a-list", 5, "", 0])
def test_a_wrong_shape_series_value_dirties_the_cache(tmp_path, bad):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps({"version": 1, "series": {SERIES_IMD_SUPPLY: bad}})
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_series(SERIES_IMD_SUPPLY) == []
    assert c._dirty is True, f"series[{SERIES_IMD_SUPPLY!r}]={bad!r} must dirty"


def test_a_null_series_value_stays_clean(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps({"version": 1, "series": {SERIES_IMD_SUPPLY: None}})
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_series(SERIES_IMD_SUPPLY) == []
    assert c._dirty is False, "an explicit null series value is absence, not corruption"


def test_a_well_formed_series_value_stays_clean(tmp_path):
    path = tmp_path / "surf_cache.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "series": {SERIES_IMD_SUPPLY: [[FakeClock().t - 10, 100.0]]},
            }
        )
    )
    c = SurfCache(path=str(path), clock=FakeClock())
    c.load()
    assert c.get_series(SERIES_IMD_SUPPLY) == [[FakeClock().t - 10, 100.0]]
    assert c._dirty is False, "a well-formed series value must not dirty"


# ---------------------------------------------------------------------------
# Fix round 2 -- the ``store_last_good`` / ``get_last_good`` no-copy
# invariant: nothing under ``maxpane_dashboard/`` may mutate a stored
# payload in place, because ``store_last_good`` keeps the caller's object
# and ``get_last_good().payload`` hands it back live. A structural sweep is
# the cheap guard here: measured against the largest slot (SLOT_SWARM_SCORES,
# ~223 KB), ``copy.deepcopy`` costs under 1 ms -- cheap at the 30 s poll rate
# -- but copying on ``store_last_good`` alone would only protect against the
# caller re-mutating the object it originally passed in. It would do nothing
# about a *consumer* of ``get_last_good().payload`` mutating the object it
# was handed, which is the other half of the reported risk and the one a
# per-call copy cost cannot cheaply close (``get_last_good`` has no bounded
# call rate the way the poll-driven ``store_last_good`` does -- a screen can
# call it every render). A test that proves no such call site exists anywhere
# in the tree covers both directions at zero runtime cost, which a partial,
# non-free copy does not.
# ---------------------------------------------------------------------------


def _payload_mutation_offenders(root, *, exclude: frozenset[str] = frozenset()) -> list[str]:
    """Every line under ``root`` that mutates a ``.payload`` in place.

    Textual, not AST-based, on this repo's own precedent (``test_the_cache_
    imports_no_client_no_analytics_no_network`` above greps for banned import
    strings the same way) -- deliberately coarse, so a match inside a comment
    still counts as an offender worth a human look rather than being silently
    exempted. That over-matching direction is harmless and was already
    documented before fix round 2.

    The *under*-matching direction was not documented, and it is the
    dangerous one: it invites false confidence that "offenders == []" means
    "no in-place mutation exists" when several real shapes slip past both
    patterns clean, confirmed by construction (see
    ``test_the_sweep_has_known_blind_spots`` below):

    * **aliasing** -- ``p = entry.payload; p["k"] = 1`` never spells the
      literal substring ``.payload[``.
    * **getattr** -- ``getattr(entry, "payload")["k"] = 1`` likewise never
      spells ``.payload[``.
    * **nested-container indexing** -- ``entry.payload["a"]["b"] = 1``: the
      assignment follows the *second* ``]``, but ``assign`` only requires
      ``=`` right after the *first* one (its ``[^\\]]*`` stops there), so the
      whole line misses.
    * **a space before the bracket** -- ``entry.payload [0] = 1``: ``assign``
      hard-codes ``.payload\\[`` with nothing between the two.
    * **a ``.get(...).append(...)`` chain** -- ``entry.payload.get("k",
      []).append(x)`` mutates the list ``.payload["k"]`` refers to, but the
      text right after ``.payload.`` is ``get(``, not one of ``call``'s four
      names, so it passes both patterns clean.

    Catching any of these needs an AST walk, not a regex, and that rewrite is
    out of scope here. What belongs here is not pretending the gap is closed.

    ``exclude`` is a set of paths relative to ``root`` (as ``rglob`` would
    join them) to skip entirely -- see the caller below for why.
    """
    import re

    assign = re.compile(r"\.payload\[[^\]]*\]\s*=(?!=)")
    call = re.compile(r"\.payload\.(update|append|pop|setdefault)\s*\(")
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if str(path.relative_to(root)) in exclude:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if assign.search(line) or call.search(line):
                offenders.append(f"{path}:{lineno}: {line.strip()}")
    return offenders


# ``curator_cache.py``/``curator_manager.py`` and ``fwa_cache.py``/
# ``fwa_manager.py`` each define their own ``LastGood``-shaped type with its
# own ``.payload`` attribute, structurally similar to SURF's but unrelated to
# it -- store_last_good/get_last_good's no-copy invariant is a SURF contract,
# not a repo-wide one. Scoping this sweep to exclude the four means this
# surf-named test asserts only what it can actually justify. Left unscoped,
# it would still find zero offenders today, but a *legitimate* future
# mutation inside curator's or FWA's own payload handling would trip this
# test anyway, with a failure message that names ``store_last_good`` and
# ``SurfCache`` -- the wrong file and the wrong invariant, pointing whoever
# hits it at code that never touched surf. Every other module, including any
# future surf file, stays covered: only these four are known today to carry
# an unrelated `.payload`-bearing type this test was never designed to
# police, and excluding by name is precise where excluding by directory
# would risk hiding a real surf regression alongside it.
_NON_SURF_PAYLOAD_OWNERS = frozenset(
    {
        "data/curator_cache.py",
        "data/curator_manager.py",
        "data/fwa_cache.py",
        "data/fwa_manager.py",
    }
)


def test_no_maxpane_code_mutates_a_stored_last_good_payload_in_place():
    import pathlib

    repo = pathlib.Path(__file__).resolve().parents[2]
    offenders = _payload_mutation_offenders(
        repo / "maxpane_dashboard", exclude=_NON_SURF_PAYLOAD_OWNERS
    )
    assert offenders == [], (
        "store_last_good keeps the caller's object without copying and "
        "get_last_good().payload hands it back live -- an in-place mutation "
        "here would change persisted cache state with _dirty left False:\n"
        + "\n".join(offenders)
    )


def test_the_sweep_excludes_only_the_named_non_surf_owners(tmp_path):
    """The exclude mechanism actually removes what it names, nothing more.

    A violation planted in an excluded path must not surface; the identical
    violation planted in a sibling, non-excluded path must.
    """
    excluded = tmp_path / "data" / "curator_cache.py"
    excluded.parent.mkdir(parents=True)
    excluded.write_text('entry.payload["k"] = 1\n')

    kept = tmp_path / "data" / "surf_manager.py"
    kept.write_text('entry.payload["k"] = 1\n')

    all_offenders = _payload_mutation_offenders(tmp_path)
    assert any("curator_cache.py" in o for o in all_offenders)
    assert any("surf_manager.py" in o for o in all_offenders)

    scoped_offenders = _payload_mutation_offenders(
        tmp_path, exclude=frozenset({"data/curator_cache.py"})
    )
    assert not any("curator_cache.py" in o for o in scoped_offenders)
    assert any("surf_manager.py" in o for o in scoped_offenders)


def test_the_sweep_has_known_blind_spots(tmp_path):
    """The five under-matching shapes named in ``_payload_mutation_offenders``'
    docstring, constructed and confirmed to slip through both patterns.

    This is a documentation test, not a demand the sweep catch these --
    closing this needs an AST walk, out of scope for this fix. The point is
    that "offenders == []" must never be read as "no in-place `.payload`
    mutation exists anywhere in this shape space": these five are real and
    invisible to it.
    """
    probe = tmp_path / "probe_blind_spots.py"
    probe.write_text(
        "\n".join(
            [
                "def f(entry):",
                "    p = entry.payload",
                '    p["k"] = 1',  # aliasing
                '    getattr(entry, "payload")["k"] = 1',  # getattr
                '    entry.payload["a"]["b"] = 1',  # nested-container indexing
                "    entry.payload [0] = 1",  # space before the bracket
                '    entry.payload.get("k", []).append(1)',  # .get().append() chain
                "",
            ]
        )
    )
    assert _payload_mutation_offenders(tmp_path) == []


def test_the_payload_mutation_sweep_actually_catches_a_violation(tmp_path):
    """Prove the checker bites: a synthetic module with one offending line in
    each shape the real sweep looks for must all be caught.
    """
    probe = tmp_path / "probe_module.py"
    probe.write_text(
        "\n".join(
            [
                "def f(entry):",
                '    entry.payload["k"] = 1',
                "    entry.payload.update({})",
                "    entry.payload.append(1)",
                "    entry.payload.pop()",
                "    entry.payload.setdefault('k', 1)",
                "    entry.payload['k'] == 1  # a comparison must NOT be flagged",
                "",
            ]
        )
    )
    offenders = _payload_mutation_offenders(tmp_path)
    assert len(offenders) == 5
    assert all("== 1" not in o for o in offenders)


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

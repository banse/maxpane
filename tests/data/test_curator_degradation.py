"""WP5.13 — the degradation matrix, driven end to end through a fake client.

Seven rows, one test each, every one of them a *rendered state* rather than an
internal flag.  The clock is injected and nothing sleeps; no socket is opened.

The doubles and the fixtures are imported from ``test_curator_manager`` rather
than re-typed: two copies of a state fixture is how the two files start
disagreeing about what a healthy round looks like.
"""

from __future__ import annotations

import asyncio

import pytest

from maxpane_dashboard.analytics.curator_signals import LEADERBOARD_LIMIT
from maxpane_dashboard.data import curator_addresses as A
from maxpane_dashboard.data.curator_cache import CuratorCache
from maxpane_dashboard.data.curator_manager import (
    SOURCES,
    SOURCE_LOGS,
    SOURCE_STATE,
    SOURCE_WALLET,
    CuratorManager,
)
from maxpane_dashboard.data.curator_models import CURATOR_KEYS
from tests.data.test_curator_manager import (
    CONFIG,
    NOW,
    WALLET,
    Clock,
    FakeClient,
    _scenario_client,
    _state,
    _sweep,
    _wallet_state,
)

#: Grace ends at launchTime + 86 400 = 2026-08-17 19:58:47 UTC; the earliest
#: settlement is one hour later.  Both are chain facts, not chosen numbers.
GRACE_ENDS = A.LAUNCH_TIME + 86_400
DURING_GRACE = A.LAUNCH_TIME + 4 * 3600
AFTER_GRACE = GRACE_ENDS + 60


def _manager(tmp_path, clock, client, **kwargs) -> CuratorManager:
    return CuratorManager(
        client=client,
        cache=CuratorCache(path=str(tmp_path / "curator_cache.json"), clock=clock),
        clock=clock,
        **kwargs,
    )


def _healthy_client(**overrides) -> FakeClient:
    client = _scenario_client({"state": True, "logs": True, "wallet": True})
    client.answers.update(overrides)
    return client


def _dead_client() -> FakeClient:
    return FakeClient(
        fetch_state=None,
        fetch_balance=None,
        fetch_config=None,
        fetch_logs=lambda *_: None,
        fetch_blockscout_logs=lambda *_: None,
        fetch_wallet=None,
    )


# ---------------------------------------------------------------------------
# Row 1 — the state pool is down (all three endpoints)
# ---------------------------------------------------------------------------


def test_a_dead_state_pool_keeps_every_log_derived_key(tmp_path, clock=None):
    clock = Clock(DURING_GRACE)
    client = _healthy_client()
    manager = _manager(tmp_path, clock, client)
    healthy = asyncio.run(manager.fetch_and_compute())
    assert healthy["degraded"] == []

    client.answers.update(fetch_state=None, fetch_balance=None, fetch_config=None)
    clock.advance(60)
    out = asyncio.run(manager.fetch_and_compute())

    # Dies: the phase truth, the clock, earlyBps, forced ETH.
    assert out["degraded"] == [SOURCE_STATE]
    assert out["settled"] is None
    assert out["hour_seconds_left"] is None
    assert out["early_multiplier_x"] is None
    assert out["forced_eth"] is None

    # Keeps working: everything folded from logs.
    assert 0 < len(out["leaderboard_rows"]) <= LEADERBOARD_LIMIT
    assert out["volume_series"] == healthy["volume_series"]
    assert len(out["activity_rows"]) > 0
    assert out["cluster_rows"] is not None

    # And nothing became a zero on the way.
    for key in ("hour_needed_eth", "current_hour", "hour_fed_eth"):
        assert out[key] is None, key


def test_a_dead_state_pool_cannot_take_the_phase_once_settlement_was_observed(tmp_path):
    """The single most important row of the matrix, in its smallest form."""
    clock = Clock(AFTER_GRACE)
    client = _healthy_client(fetch_state=_state(settled=True, current_hour=24))
    manager = _manager(tmp_path, clock, client)
    assert asyncio.run(manager.fetch_and_compute())["phase"] == "settled"

    client.answers.update(fetch_state=None, fetch_balance=None, fetch_config=None)
    clock.advance(60)
    out = asyncio.run(manager.fetch_and_compute())
    assert out["phase"] == "settled"
    assert out["settled"] is True
    assert SOURCE_STATE in out["degraded"]


# ---------------------------------------------------------------------------
# Row 2 — the logs pool is down (tenderly + drpc)
# ---------------------------------------------------------------------------


def test_a_dead_logs_pool_keeps_the_clock_the_phase_and_you(tmp_path):
    clock = Clock(DURING_GRACE)
    client = _healthy_client()
    manager = _manager(tmp_path, clock, client, wallet=WALLET)
    healthy = asyncio.run(manager.fetch_and_compute())

    client.answers["fetch_logs"] = lambda *_: None
    clock.advance(60)
    out = asyncio.run(manager.fetch_and_compute())

    assert out["degraded"] == [SOURCE_LOGS]
    assert out["phase"] == "grace"
    assert out["hour_seconds_left"] == 3_412
    assert out["early_multiplier_x"] == pytest.approx(1.9491)
    assert out["forced_eth"] == 0.0                      # read, and 0 is healthy
    assert out["you_points"] == 1000

    # The fold is last-good, behind an as-of marker that stopped moving.
    assert out["leaderboard_rows"] == healthy["leaderboard_rows"]
    assert out["volume_series"] == healthy["volume_series"]
    assert out["as_of_hhmm"] is not None


def test_a_logs_pool_that_was_never_reachable_renders_unavailable_not_empty(tmp_path):
    """A None list means 'source dead'; [] would claim nobody has deposited."""
    clock = Clock(DURING_GRACE)
    client = _healthy_client(fetch_logs=lambda *_: None)
    manager = _manager(tmp_path, clock, client)
    out = asyncio.run(manager.fetch_and_compute())

    assert out["degraded"] == [SOURCE_LOGS]
    assert out["leaderboard_rows"] is None
    assert out["activity_rows"] is None
    assert out["closest_call_rows"] is None
    assert out["cluster_rows"] is None
    assert out["volume_series"] == []                     # this install's history
    assert out["survival_streak_hours"] is None           # not a streak of 0
    assert out["clusters_count"] is None                  # not 'no clusters found'
    # The contract's own counters still answer, because they are state reads.
    assert out["contributors_total"] == 143


# ---------------------------------------------------------------------------
# Row 3 — everything is down
# ---------------------------------------------------------------------------


def test_everything_down_returns_the_whole_contract_with_no_zero_anywhere(tmp_path):
    clock = Clock(DURING_GRACE)
    manager = _manager(tmp_path, clock, _dead_client(), wallet=WALLET)
    out = asyncio.run(manager.fetch_and_compute())

    assert set(out) == set(CURATOR_KEYS)
    assert out["degraded"] == sorted(SOURCES) == ["logs", "state", "wallet"]
    for key, value in out.items():
        if key in ("degraded", "volume_series", "contributors_series"):
            continue
        assert value is None, f"{key} = {value!r} — a dead source invented a value"


def test_everything_down_never_crashes_however_many_times_it_runs(tmp_path):
    clock = Clock(DURING_GRACE)
    manager = _manager(tmp_path, clock, _dead_client(), wallet=WALLET)
    for _ in range(10):
        out = asyncio.run(manager.fetch_and_compute())
        assert set(out) == set(CURATOR_KEYS)
        clock.advance(30)


# ---------------------------------------------------------------------------
# Row 4 — the flagship: an outage AFTER settlement was observed
# ---------------------------------------------------------------------------


def test_settlement_survives_a_total_outage(tmp_path):
    """PRD §11.3.  Observe settled once, then kill every endpoint forever."""
    clock = Clock(AFTER_GRACE)
    manager = _manager(
        tmp_path, clock, _healthy_client(fetch_state=_state(settled=True, current_hour=24))
    )
    first = asyncio.run(manager.fetch_and_compute())
    assert first["phase"] == "settled"

    manager.client = _dead_client()
    for tick in range(1, 6):
        clock.advance(60)
        out = asyncio.run(manager.fetch_and_compute())
        assert out["phase"] == "settled", f"phase lost on tick {tick}"
        assert out["settled"] is True
        assert "state" in out["degraded"]
        assert out["as_of_hhmm"] == first["as_of_hhmm"]   # freshness froze
    # ...and the freshness marker is what moved, not the verdict.
    assert out["settled_observed_at"] == first["settled_observed_at"]


def test_the_latch_survives_a_restart_as_well_as_an_outage(tmp_path):
    """The evidence record is persisted, so the archive reads SETTLED on a
    fresh process whose endpoints are all dead."""
    clock = Clock(AFTER_GRACE)
    path = str(tmp_path / "curator_cache.json")
    first = CuratorManager(
        client=_healthy_client(fetch_state=_state(settled=True, current_hour=24)),
        cache=CuratorCache(path=path, clock=clock),
        clock=clock,
    )
    before = asyncio.run(first.fetch_and_compute())
    asyncio.run(first.close())

    clock.advance(3600)
    second = CuratorManager(
        client=_dead_client(), cache=CuratorCache(path=path, clock=clock), clock=clock
    )
    out = asyncio.run(second.fetch_and_compute())
    assert out["phase"] == "settled"
    assert out["settled"] is True
    assert out["settled_observed_at"] == before["settled_observed_at"]


# ---------------------------------------------------------------------------
# Row 5 — the wallet read fails while the chain is healthy
# ---------------------------------------------------------------------------


def test_a_failed_wallet_read_costs_the_you_row_and_nothing_else(tmp_path):
    clock = Clock(DURING_GRACE)
    client = _healthy_client(fetch_wallet=None)
    manager = _manager(tmp_path, clock, client, wallet=WALLET)
    out = asyncio.run(manager.fetch_and_compute())

    assert out["degraded"] == [SOURCE_WALLET]
    for key in ("you_rank", "you_points", "you_credit_eth", "you_marginal_points"):
        assert out[key] is None, key
    assert out["phase"] == "grace"
    assert 0 < len(out["leaderboard_rows"]) <= LEADERBOARD_LIMIT
    assert out["contributors_total"] == 143


def test_no_wallet_configured_is_not_a_degradation(tmp_path):
    clock = Clock(DURING_GRACE)
    client = _healthy_client()
    manager = _manager(tmp_path, clock, client)
    out = asyncio.run(manager.fetch_and_compute())
    assert out["degraded"] == []
    assert out["you_rank"] is None
    assert not any(name == "fetch_wallet" for name, *_ in client.calls)


# ---------------------------------------------------------------------------
# Row 6 — the grace → judged crossing
# ---------------------------------------------------------------------------


def test_the_phase_flips_on_the_injected_clock_alone(tmp_path):
    """Nothing was refetched and nothing on chain changed: the same readings
    produce a different phase because the wall clock crossed
    launchTime + gracePeriod.  The boundary itself belongs to `judged`."""
    clock = Clock(GRACE_ENDS - 1)
    client = _healthy_client(fetch_state=_state(current_hour=24, hour_needed_wei=0))
    manager = _manager(tmp_path, clock, client)

    before = asyncio.run(manager.fetch_and_compute())
    assert before["phase"] == "grace"
    assert before["grace_seconds_left"] == 1

    clock.advance(1)
    at_boundary = asyncio.run(manager.fetch_and_compute())
    assert at_boundary["phase"] == "judged"
    assert at_boundary["grace_seconds_left"] == 0
    assert at_boundary["current_hour"] == before["current_hour"]
    assert at_boundary["contributors_total"] == before["contributors_total"]


# ---------------------------------------------------------------------------
# Row 7 — settled from the view with the Settled log absent
# ---------------------------------------------------------------------------


def test_settled_from_the_view_leaves_the_obituary_none_not_zero(tmp_path):
    """settle() is permissionless and may lag death indefinitely, so the view
    can say SETTLED for hours before any log exists.  The final hour and the
    final totals are then unknown -- which is not the same as zero."""
    clock = Clock(AFTER_GRACE)
    client = _healthy_client(fetch_state=_state(settled=True, current_hour=25))
    manager = _manager(tmp_path, clock, client)
    out = asyncio.run(manager.fetch_and_compute())

    assert out["phase"] == "settled"
    assert out["settled"] is True
    assert out["sig_settled_state"] == "fired"
    assert out["settled_hour"] is None
    assert out["settled_at_ts"] is None
    assert out["settled_observed_at"] == clock.now
    assert out["lived_desc"] is not None


# ---------------------------------------------------------------------------
# WP3.5 — the analysis sweep's health folds into the `logs` story
# ---------------------------------------------------------------------------
#
# No new degraded-group name: the title bar renders the frozen vocabulary
# verbatim.  The rule, pinned here exactly: the analysis is enrichment over
# the logs, so a failed sweep lights `logs` ONLY while there is no analysis
# last-good to serve; with one, the keys ride behind `analysis_as_of_hhmm`
# and nothing lights; and not-yet-run is not a failure at all.

from maxpane_dashboard.data import curator_clusters
from maxpane_dashboard.data.curator_cache import (
    TIER_ANALYSIS,
    TIER_FAILURE_BACKOFF_SECONDS,
)
from tests.data.test_curator_manager import (
    ANALYSIS_CONFIG,
    PublishedRoutes,
    _analysis_manager,
    _store_farm_slot,
)


def _run_sweep(manager, now):
    async def _go():
        task = manager._spawn_analysis({TIER_ANALYSIS}, now, ANALYSIS_CONFIG)
        await asyncio.wait_for(task, timeout=5)

    asyncio.run(_go())


def test_a_not_yet_run_analysis_is_not_a_degradation(tmp_path):
    clock = Clock(DURING_GRACE)
    manager = _analysis_manager(tmp_path, clock)
    out = asyncio.run(manager.fetch_and_compute())
    assert out["degraded"] == []
    assert out["operator_rows"] is None            # not yet run, honestly


def test_a_failed_sweep_with_no_last_good_lights_logs_and_blanks_nothing(tmp_path):
    """The keys' None must read as 'could not analyze', and the only frozen
    group name that story belongs to is `logs` — while the fold and the clock
    keep working untouched.

    The failure is injected at the TRANSPORT (the published version check
    answers 503), not by monkeypatching a function: a dead source is what this
    rule is about, and asserting it structurally is what CLAUDE.md asks for.
    """
    clock = Clock(DURING_GRACE)
    manager = _analysis_manager(
        tmp_path, clock, published=PublishedRoutes(dead=("versions",))
    )

    _run_sweep(manager, clock.now)
    assert manager._analysis_failed is True
    assert manager.cache.analysis_last_good() is None
    # ...and the tier is backed off, not hammered.
    assert TIER_ANALYSIS not in manager.cache.tiers_due(clock.now + 1)
    assert TIER_ANALYSIS in manager.cache.tiers_due(
        clock.now + TIER_FAILURE_BACKOFF_SECONDS[TIER_ANALYSIS] + 1
    )

    out = asyncio.run(manager.fetch_and_compute())
    assert out["degraded"] == [SOURCE_LOGS]
    assert out["operator_rows"] is None
    assert out["operators_count"] is None
    # Nothing blanked: the fold and the clock are other sources' answers.
    assert out["leaderboard_rows"]
    assert out["phase"] == "grace"
    assert out["hour_seconds_left"] is not None


def test_a_failed_sweep_with_a_last_good_serves_it_and_lights_nothing(tmp_path):
    """An analysis-only failure while the log fold is fresh keeps the keys on
    last-good behind their own marker and does NOT falsely light `logs`."""
    clock = Clock(DURING_GRACE)
    manager = _analysis_manager(
        tmp_path, clock, published=PublishedRoutes(dead=("versions",))
    )
    stored = _store_farm_slot(manager, ts=clock.now - 1_800)

    _run_sweep(manager, clock.now)
    assert manager._analysis_failed is True

    out = asyncio.run(manager.fetch_and_compute())
    assert out["degraded"] == []
    assert out["operators_count"] == stored["operators_count"] == 1
    assert out["operator_rows"]
    assert out["analysis_as_of_hhmm"] is not None  # the OLD sweep's marker


def test_the_banner_clears_when_a_later_sweep_publishes(tmp_path):
    clock = Clock(DURING_GRACE)
    routes = PublishedRoutes(dead=("versions",))
    manager = _analysis_manager(tmp_path, clock, published=routes)
    _run_sweep(manager, clock.now)
    assert asyncio.run(manager.fetch_and_compute())["degraded"] == [SOURCE_LOGS]

    routes.dead.clear()                       # the publisher answers again
    clock.advance(TIER_FAILURE_BACKOFF_SECONDS[TIER_ANALYSIS] + 1)
    _run_sweep(manager, clock.now)
    assert manager._analysis_failed is False

    out = asyncio.run(manager.fetch_and_compute())
    assert out["degraded"] == []
    assert out["operators_count"] is not None

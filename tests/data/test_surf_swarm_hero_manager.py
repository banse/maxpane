"""No-I/O projection and eligibility tests for the native SWARM hero."""
from maxpane_dashboard.data import surfboard as hub
from maxpane_dashboard.data.surf_cache import SLOT_SWARM_LAUNCHES, SLOT_SWARM_SCORES
from tests.data.test_surf_manager_surfboard import manager  # shared offline clients/clock
from tests.data.test_surfboard import capture


async def test_swarm_hero_captures_current_cache_versions_and_route_clocks(manager, monkeypatch):
    m, clock = manager
    overview = hub.normalize_overview(capture("overview"))
    m.cache.store_last_good(hub.SOURCE_SLOTS["overview"], hub.source_envelope(overview, 990), ts=990)
    m.cache.store_last_good(hub.SOURCE_SLOTS["hourly"], hub.source_envelope(hub.normalize_hourly(capture("hourly")), 980), ts=980)
    m.cache.store_last_good(SLOT_SWARM_SCORES, dict(workflows=[dict(
        id="workflow", createdAt="1970-01-01T00:15:00Z", status="running", objective="same row")], workflows_ts=900), ts=950)
    m.cache.store_last_good(SLOT_SWARM_LAUNCHES, dict(launches_ts=980, sites_ts=550), ts=999)
    monkeypatch.setattr(m, "_swarm_launch_keys", lambda: dict(
        swarm_launch_summary={"by_status": [dict(status="live", count=4)]},
        swarm_site_rows=[dict(ens_name="current.eth", status="published")]))
    m._last_full_payload = dict(swarm_workflow_rows=[], swarm_launch_summary={"by_status": []})
    try:
        result = m._project_hub(refresh_legacy=False)["surf_swarm_hero"]
        assert result["fleet"]["online"] == overview["overview"]["agents_online"]
        assert result["output"]["steps"] == overview["overview"]["accepted_24h"]
        assert result["output"]["points_read_ts"] == 980
        assert result["workflow"]["objective"] == "same row" and result["workflow"]["age_s"] == 100
        assert result["workflows"]["state"] == "stale" and result["workflows"]["read_ts"] == 900
        assert result["launches"]["total"] == 4 and result["launches"]["read_ts"] == 980
        assert result["launches"]["state"] == "ok"
        assert result["sites"] == dict(state="stale", read_ts=550, count=1)
        m._cycle.assert_not_awaited()
    finally:
        await m.close()


async def test_failed_launch_route_does_not_stale_fresh_sites(manager, monkeypatch):
    m, _ = manager
    m.cache.store_last_good(SLOT_SWARM_LAUNCHES, dict(launches_ts=990, sites_ts=980), ts=995)
    m._swarm_launch_read_ok = False
    monkeypatch.setattr(m, "_swarm_launch_keys", lambda: dict(swarm_launch_summary={"by_status": []}, swarm_site_rows=[]))
    try:
        result = m._project_hub(refresh_legacy=False)["surf_swarm_hero"]
        assert result["launches"] == dict(state="stale", read_ts=990, total=0, statuses=[])
        assert result["sites"] == dict(state="ok", read_ts=980, count=0)
        assert result["workflows"]["state"] == "unavailable"
    finally:
        await m.close()


async def test_site_and_policy_failure_leave_successful_launch_route_fresh(manager):
    from unittest.mock import AsyncMock
    from maxpane_dashboard.data.surf_cache import TIER_SWARM_LAUNCHES
    m, clock = manager
    m.cache.store_last_good(SLOT_SWARM_LAUNCHES, dict(launches=[], launches_ts=900, sites=[], sites_ts=700), ts=900)
    m.swarm_client.fetch_launches = AsyncMock(return_value=[])
    m.swarm_client.fetch_sites = AsyncMock(return_value=None)
    m.swarm_client.fetch_launch_policies = AsyncMock(return_value=None)
    try:
        await m._pool_swarm_launches({TIER_SWARM_LAUNCHES}, clock.now)
        result = m._project_hub(refresh_legacy=False)["surf_swarm_hero"]
        assert result["launches"] == dict(state="ok", read_ts=1000, total=0, statuses=[])
        assert m.cache.last_failure_ts(TIER_SWARM_LAUNCHES) is None
        assert result["sites"] == dict(state="stale", read_ts=700, count=0)
        m.swarm_client.fetch_launches.assert_awaited_once()
        m.swarm_client.fetch_sites.assert_awaited_once()
        m.swarm_client.fetch_launch_policies.assert_awaited_once()
    finally:
        await m.close()


async def test_hourly_source_eligibility_uses_existing_task_and_ttl(manager):
    import asyncio
    m, clock = manager
    try:
        m._offer_hub_sources(clock.now)
        await asyncio.gather(*m._hub_source_tasks.values())
        m.swarm_client.fetch_steps_hourly.assert_not_awaited()
        m.set_swarm_active(True)
        m.swarm_client.fetch_steps_hourly.assert_not_awaited()  # eligibility flag is synchronous/no I/O
        m._offer_hub_sources(clock.now)
        first = m._hub_source_tasks["hourly"]
        m._offer_hub_sources(clock.now)
        assert m._hub_source_tasks["hourly"] is first
        await asyncio.gather(*m._hub_source_tasks.values())
        assert m.swarm_client.fetch_steps_hourly.await_count == 1
        assert "supply" not in m._hub_source_tasks
        clock.now += 59
        m._offer_hub_sources(clock.now)
        assert m._hub_source_tasks["hourly"] is first
        m.set_swarm_active(False)
        clock.now += 2
        m._offer_hub_sources(clock.now)
        await asyncio.gather(*m._hub_source_tasks.values())
        assert m.swarm_client.fetch_steps_hourly.await_count == 1
        m.set_swarm_active(True)
        m._offer_hub_sources(clock.now)
        await asyncio.gather(*m._hub_source_tasks.values())
        assert m.swarm_client.fetch_steps_hourly.await_count == 2
    finally:
        await m.close()

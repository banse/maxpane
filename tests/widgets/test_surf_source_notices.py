"""Source health stays internal; operational states and cached facts remain visible."""
import pytest

from tests.widgets.test_surf_agent_rack_hero import Harness as AgentHarness, payload as agent_payload
from tests.widgets.test_surf_oracles import Harness as OracleHarness, payload as oracle_payload
from tests.widgets.test_surf_work import Harness as WorkHarness, payload as work_payload
from tests.widgets.test_surf_swarm_fleet import render as fleet_render


def painted(app):
    return "\n".join(strip.text for strip in app.screen._compositor.render_strips())


@pytest.mark.parametrize("harness,make", [(WorkHarness, work_payload), (OracleHarness, oracle_payload)])
@pytest.mark.parametrize("state", ["stale", "unavailable"])
async def test_native_work_and_oracles_omit_source_notices(harness, make, state):
    data = make()
    data["state"] = state
    if state == "unavailable":
        data = None
    async with harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app).lower()
        assert "stale" not in output and "unavailable" not in output
        assert "loading" not in output
        if state == "stale":
            assert "blocked" in output
            assert "bunkervault" in output if harness is WorkHarness else "question 0" in output


async def test_agent_card_tooltips_and_footers_keep_clocks_without_source_notices():
    data = agent_payload()
    for source in data.values():
        source["state"] = "stale"
    data["status"].update(live_state="offline", meter_state="offline")
    data["seat"].update(live_state="offline", api_status="revoked")
    async with AgentHarness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app)
        assert "revoked" in output and "BunkerVault" not in output
        cards = list(pilot.app.query("AgentRackCard"))
        assert len(cards) == 12
        for card in cards:
            tooltip = card.tooltip.plain.lower()
            assert "as of" in tooltip
            assert not any(word in tooltip for word in ("stale", "retained", "unavailable", "load failed"))
        assert not any(word in output.lower() for word in ("stale", "unavailable", "load failed"))


async def test_fleet_missing_values_remain_dashes_and_known_zero_stays_zero():
    output = await fleet_render(None, None)
    assert "unavailable" not in output and "loading" not in output
    assert "runtime    —" in output and "tokens/job —" in output


async def test_external_work_prose_is_not_filtered_as_a_source_notice():
    data = work_payload()
    data["jobs"][0]["objective"] = "Repair stale cache when the provider is unavailable"
    async with WorkHarness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert data["jobs"][0]["objective"] in painted(pilot.app)

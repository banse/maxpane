"""Source-isolated projections for the six native SWARM hero cards."""
from copy import deepcopy

import pytest

from maxpane_dashboard.data import surf_swarm_hero as hero


@pytest.fixture
def snapshot():
    return dict(
        overview=dict(state="ok", read_ts=990, payload={"overview": dict(
            agents_online=966, working_now=8, seats_enrolled=1972,
            accepted_24h=2621, jobs_24h=224, oracles_24h=48)}),
        hourly=dict(state="ok", read_ts=980, payload=dict(accepted=list(range(24)))),
        workflow_rows=[dict(workflow_id="older", status="completed", created_ts=800, objective="old"),
                       dict(workflow_id="latest", status="running", created_ts=970, objective="current")],
        workflow_source=dict(state="ok", read_ts=900),
        launch_summary=dict(by_status=[dict(status="live", count=47), dict(status="parked", count=2)]),
        launch_source=dict(state="ok", read_ts=950),
        site_rows=[dict(ens_name="a.eth", status="published", superseded_by=None),
                   dict(ens_name="b.eth", status="superseded", superseded_by=None),
                   dict(ens_name="c.eth", status="published", superseded_by="new")],
        site_source=dict(state="ok", read_ts=750), now=1000,
    )


def test_six_section_field_contract_and_native_metric_meanings(snapshot):
    from maxpane_dashboard.data.surf_models import SURF_SWARM_HERO_FIELDS, SURF_SWARM_HERO_STATUS_FIELDS
    before = deepcopy(snapshot)
    result = hero.project(**snapshot)
    assert set(result) == set(SURF_SWARM_HERO_FIELDS)
    for name, fields in SURF_SWARM_HERO_FIELDS.items():
        assert set(result[name]) == set(fields)
    for name in ("workflows", "launches"):
        assert all(set(row) == set(SURF_SWARM_HERO_STATUS_FIELDS) for row in result[name]["statuses"])
    assert result["fleet"] == dict(state="ok", read_ts=990, online=966, working=8, enrolled=1972)
    assert result["output"] == dict(state="ok", read_ts=990, steps=2621, jobs=224, oracles=48,
                                    points=[3, 12, 21, 30, 39, 48, 57, 66], points_state="ok", points_read_ts=980)
    assert result["workflows"] == dict(state="ok", read_ts=900, total=2,
                                       statuses=[dict(status="completed", count=1), dict(status="running", count=1)])
    assert result["launches"] == dict(state="ok", read_ts=950, total=49,
                                      statuses=[dict(status="live", count=47), dict(status="parked", count=2)])
    assert result["workflow"] == dict(state="ok", read_ts=900, objective="current", age_s=30, status="running")
    assert result["sites"] == dict(state="ok", read_ts=750, count=1)
    assert snapshot == before


def test_hourly_failure_and_fresh_overview_keep_separate_clocks(snapshot):
    snapshot["hourly"].update(state="stale", read_ts=600)
    output = hero.project(**snapshot)["output"]
    assert output["state"] == "ok" and output["read_ts"] == 990
    assert output["steps"] == 2621
    assert output["points_state"] == "stale" and output["points_read_ts"] == 600
    snapshot["hourly"] = None
    output = hero.project(**snapshot)["output"]
    assert output["state"] == "ok" and output["points_state"] == "unavailable"
    assert output["points"] is None


def test_latest_workflow_text_and_age_share_newest_row_with_stable_tie_break(snapshot):
    snapshot["workflow_rows"] += [dict(workflow_id="z", created_ts=970, objective="tie winner", status="blocked"),
                                   dict(workflow_id="future", created_ts=1001, objective="future", status="running"),
                                   dict(workflow_id="bad", created_ts=True, objective="bad", status="running")]
    result = hero.project(**snapshot)["workflow"]
    assert (result["objective"], result["age_s"], result["status"]) == ("tie winner", 30, "blocked")
    snapshot["workflow_rows"].reverse()
    assert hero.project(**snapshot)["workflow"] == result


def test_latest_workflow_unknown_objective_is_not_empty_catalogue(snapshot):
    snapshot["workflow_rows"] = [dict(workflow_id="latest", created_ts=999, objective=None, status="running")]
    result = hero.project(**snapshot)["workflow"]
    assert result["objective"] is None and result["age_s"] == 1 and result["status"] == "running"
    snapshot["workflow_rows"] = [dict(workflow_id="bad", created_ts=None, objective="bad")]
    assert hero.project(**snapshot)["workflow"]["state"] == "unavailable"


def test_invalid_nonempty_workflow_list_cannot_claim_no_workflows(snapshot):
    snapshot["workflow_rows"] = [None, 5]
    assert hero.project(**snapshot)["workflow"]["state"] == "unavailable"


def test_empty_catalogues_are_zero_and_unread_is_unknown(snapshot):
    snapshot.update(workflow_rows=[], launch_summary={"by_status": []}, site_rows=[])
    result = hero.project(**snapshot)
    assert result["workflows"]["total"] == result["launches"]["total"] == result["sites"]["count"] == 0
    assert result["workflows"]["statuses"] == result["launches"]["statuses"] == []
    assert result["workflow"]["state"] == "ok" and result["workflow"]["objective"] is None
    snapshot.update(workflow_rows=None, launch_summary=None, site_rows=None)
    result = hero.project(**snapshot)
    assert all(result[name]["state"] == "unavailable" for name in ("workflows", "workflow", "launches", "sites"))
    assert result["workflows"]["total"] is result["launches"]["total"] is result["sites"]["count"] is None


def test_malformed_cache_numbers_and_histories_do_not_become_facts(snapshot):
    snapshot["overview"]["payload"]["overview"].update(agents_online=True, working_now=-1)
    snapshot["hourly"]["payload"]["accepted"][0] = True
    snapshot["launch_summary"]["by_status"][0]["count"] = -1
    result = hero.project(**snapshot)
    assert result["fleet"]["online"] is result["fleet"]["working"] is None
    assert result["fleet"]["enrolled"] == 1972
    assert result["output"]["points"] is None and result["output"]["points_state"] == "unavailable"
    assert result["launches"]["total"] is None and result["launches"]["state"] == "unavailable"


def test_current_sites_share_the_existing_panel_predicate(snapshot):
    from maxpane_dashboard.analytics.surf_launch_sites import is_current_site
    snapshot["site_rows"] += [dict(ens_name="d.eth", status="pending"), dict(ens_name=None, status="published")]
    assert hero.project(**snapshot)["sites"]["count"] == sum(map(is_current_site, snapshot["site_rows"])) == 2


def test_stale_catalogues_retain_values_and_their_own_clocks(snapshot):
    for key in ("workflow_source", "launch_source", "site_source"):
        snapshot[key]["state"] = "stale"
    result = hero.project(**snapshot)
    for section, stamp in (("workflows", 900), ("workflow", 900), ("launches", 950), ("sites", 750)):
        assert result[section]["state"] == "stale" and result[section]["read_ts"] == stamp
    assert result["workflows"]["total"] == 2 and result["launches"]["total"] == 49

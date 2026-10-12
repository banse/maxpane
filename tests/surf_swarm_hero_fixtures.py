"""Project the existing mixed-date screen corpus into the new hero contract."""
from maxpane_dashboard.data.surf_swarm_hero import project
from maxpane_dashboard.data.surfboard import normalize_hourly, normalize_overview
from tests.data.test_surfboard import capture


def screen_hero(data):
    workflows = data.get("swarm_workflow_rows")
    # Layout fixtures combine captures from different days. Give their newest
    # valid record a synthetic snapshot eight minutes later, without live time.
    stamps = [data.get("as_of") or 1]
    stamps += [row["created_ts"] for row in workflows or []
               if isinstance(row, dict) and type(row.get("created_ts")) in (int, float)]
    now = max(stamps) + 480
    source = dict(state="ok", read_ts=now)
    overview = normalize_overview(capture("overview"))
    overview["overview"].update(agents_online=data.get("swarm_agents_online"),
        working_now=data.get("swarm_working_now"), seats_enrolled=data.get("swarm_agents_enrolled"),
        accepted_24h=data.get("swarm_accepted_today"))
    return project(overview=dict(source, payload=overview),
        hourly=dict(source, payload=normalize_hourly(capture("hourly"))),
        workflow_rows=workflows, workflow_source=source,
        launch_summary=data.get("swarm_launch_summary"), launch_source=source,
        site_rows=data.get("swarm_site_rows"), site_source=source, now=now)

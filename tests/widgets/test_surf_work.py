"""Painted and keyboard contracts for the work desk; never uses live reads."""
import asyncio
from copy import deepcopy

import pytest
from rich.style import Style
from textual.app import App
from textual.widgets import Input, Tree

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf.work import SurfWorkBody, SurfWorkHero


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError("widget tests must never request the network")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


def payload():
    return dict(state="ok", read_ts=10000, now_ts=10030, partial=True,
        jobs_loaded=3, workflows_loaded=2, details_loaded=2, details_expected=2,
        summary=dict(jobs=2, workflows=1, seats=2, build=1, review=1, blocked=1),
        jobs=[dict(id="job-a", state="executing", template="contracts", objective="BunkerVault [limits]", created_ts=9000, updated_ts=9990, detail_state="ok", blocked_reason=None,
            nodes=[dict(key="vault", role="implement", state="working", seat=393, agent_id="worker", attempt=2, revisions=1, depends_on=["spec"], updated_ts=9990, dispatch_note="Build withdrawal limits", dispatch_ts=9990, failure=None, verdict=None),
                   dict(key="spec", role="review", state="working", seat=827, attempt=1, revisions=0, depends_on=[], updated_ts=9980, dispatch_note=None, failure=None, verdict=dict(status="pass", detail="Interface accepted"))]),
              dict(id="job-b", state="blocked", template="frontend", objective="Vault frontend", created_ts=9100, updated_ts=9980, detail_state="not_loaded", blocked_reason="waiting for contract", nodes=None),
              dict(id="job-c", state="executing", template="fix", objective="Repair logging", created_ts=8500, updated_ts=9900, detail_state="unavailable", nodes=None)],
        workflows=[dict(id="flow-a", status="executing", objective="BunkerVault", contracts_job_id="job-a", frontend_job_id="job-b", created_ts=8900, updated_ts=9990, failure=None, waiting_for_hosting=False),
                   dict(id="flow-old", status="completed", objective="Old completed workflow", contracts_job_id="old", frontend_job_id=None)])


class Harness(App):
    CSS = "Screen { padding: 1; background: $background; color: $text; } SurfWorkBody { margin-top: 1; }"
    def __init__(self, data=None, *, view=None):
        super().__init__()
        self.data = data
        self.view = view
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield SurfWorkHero()
        yield SurfWorkBody()
    def on_mount(self):
        if self.view is not None:
            self.query_one(SurfWorkBody)._filter = self.view
        self.query_one(SurfWorkHero).update_data(surf_work=self.data)
        self.query_one(SurfWorkBody).update_data(surf_work=self.data)


async def test_default_window_shows_all_recent_states_by_latest_activity():
    data = payload()
    data.update(now_ts=100_000, projects=[])
    data['jobs'] = [dict(data['jobs'][2], id=state, objective=f'{state} recently',
                        state=state, created_ts=1, updated_ts=99_999, nodes=[])
                    for state in ('executing', 'completed', 'blocked', 'failed')]
    data['jobs'].extend([
        dict(data['jobs'][0], id='old', objective='Old activity', updated_ts=13_599),
        dict(data['jobs'][0], id='unknown', objective='Unknown activity', created_ts=None, updated_ts=None),
        dict(data['jobs'][0], id='boundary', objective='Cutoff included', updated_ts=13_600),
    ])
    data['workflows'] = [dict(id=state, status=state, objective=f'{state} workflow',
                             created_ts=1, updated_ts=99_999)
                         for state in ('completed', 'blocked', 'failed', 'future-state')]
    data['workflows'].append(dict(id='old-flow', status='executing', objective='Old workflow', created_ts=1))
    async with Harness(data).run_test(size=(149, 55)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        assert body._filter == '24h'
        assert '24H' in painted(app, '#work-navigation')
        for state in ('executing', 'completed', 'blocked', 'failed'):
            assert f'{state} recently' in painted(app, '#work-jobs-panel')
        for state in ('completed', 'blocked', 'failed', 'future-state'):
            assert f'workflow:{state}' in body._entries
        output = painted(app, '#work-navigation')
        assert 'Cutoff included' in output
        assert 'Old activity' not in output and 'Unknown activity' not in output
        assert 'Old workflow' not in output
        select(app.query_one('#work-tree', Tree), 'workflow:completed')
        await pilot.pause()
        region = app.query_one('#work-detail-panel').region
        completed = [segment for strip in app.screen._compositor.render_strips()[region.y:region.bottom]
                     for segment in strip.crop(region.x, region.right) if segment.text == 'completed']
        assert completed and completed[0].style.color.get_truecolor(app.ansi_theme) == (9, 155, 43)
        body.cycle_filter()
        await pilot.pause()
        assert body._filter == 'open'
        assert 'workflow:old-flow' in body._entries


async def test_recent_workflow_does_not_make_old_child_recent_or_duplicate_jobs():
    data = project_payload()
    data.update(now_ts=100_000)
    data['workflows'][0].update(updated_ts=99_999, status='completed')
    data['jobs'][0].update(updated_ts=99_999)
    data['projects'][0]['workflow_ids'] = ['flow-a']
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        assert {'project:project-a', 'workflow:flow-a', 'job:job-a'} <= body._entries.keys()
        assert 'job:job-b' not in body._entries
        assert 'Earlier release' not in painted(app, '#work-navigation')
        assert node(app.query_one('#work-tree', Tree), 'job:job-a').parent.data[0] == 'workflow:flow-a'
        assert not app.query_one('#work-jobs-tree', Tree).root.children[0].data
        # Full linked context remains inspectable in details.
        select(app.query_one('#work-tree', Tree), 'workflow:flow-a')
        await pilot.pause()
        assert 'job-b' in painted(app, '#work-detail-panel')


async def test_empty_24h_workflows_fall_back_to_latest_three_then_return_to_recent():
    data = payload()
    data.update(now_ts=200_000, read_ts=200_000, jobs=[], jobs_loaded=0,
                workflows_loaded=5, projects=[])
    data['workflows'] = [dict(id=f'flow-{i}', status='blocked' if i == 4 else 'completed',
                             objective=f'Older workflow {i}', created_ts=60_000 - i,
                             updated_ts=70_000 + i, contracts_job_id=None, frontend_job_id=None)
                         for i in range(5)]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        tree = app.query_one('#work-tree', Tree)
        assert [n.data[0] for n in tree.root.children if n.data] == [
            'workflow:flow-4', 'workflow:flow-3', 'workflow:flow-2']
        output = painted(app, '#work-tree-panel')
        assert 'LATEST 3' in output
        assert 'Older workflow 4' in output and 'Older workflow 2' in output
        assert 'Older workflow 1' not in output
        select(tree, 'workflow:flow-3')
        await pilot.pause()
        assert 'Older workflow 3' in painted(app, '#work-detail-panel')
        body.update_data(surf_work=deepcopy(data))
        await pilot.pause()
        assert body._selected == 'workflow:flow-3'
        data['workflows'][0]['updated_ts'] = 199_999
        body.update_data(surf_work=data)
        await pilot.pause()
        assert [n.data[0] for n in tree.root.children if n.data] == ['workflow:flow-0']
        assert 'LATEST 3' not in painted(app, '#work-tree-panel')


def painted(app, selector):
    region = app.query_one(selector).region
    return "\n".join(strip.crop(region.x, region.right).text for strip in app.screen._compositor.render_strips()[region.y:region.bottom])


async def test_unavailable_empty_tree_remains_interactive_without_color(monkeypatch):
    monkeypatch.setenv('NO_COLOR', '1')
    async with Harness(None).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        body = pilot.app.query_one(SurfWorkBody)
        body.focus_find()
        await pilot.press('a', 'b')
        assert pilot.app.query_one('#work-find', Input).value == 'ab'
        assert 'unavailable' not in painted(pilot.app, '#work-navigation')


@pytest.mark.parametrize("state", ["initial", "ok", "partial", "stale", "unavailable", "empty"])
async def test_hero_captions_share_inner_bottom_border_and_color(state, monkeypatch):
    data = payload()
    data["state"] = "ok" if state == "empty" else state
    if state == "empty":
        data["summary"] = dict.fromkeys(data["summary"], 0)
    if state == "initial":
        monkeypatch.setattr(Harness, "on_mount", lambda self: None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        for key, caption in (("jobs", "executing"), ("workflows", "in progress"),
                             ("seats", "assigned seats"), ("build", "building"),
                             ("review", "reviewing"), ("blocked", "needs attention")):
            card = app.query_one("#hero-work-" + key)
            region = card.region
            rows = [row.crop(region.x, region.right) for row in
                    app.screen._compositor.render_strips()[region.y:region.bottom]]
            bottom = next(row for row in rows if "└" in row.text)
            assert caption in bottom.text
            assert caption not in rows[-1].text
            assert not card.border_subtitle
            start = bottom.text.index(caption)
            corner = bottom.text.index("└")
            frame_style = list(bottom.crop(corner, corner + 1))[0].style
            assert all(segment.style == frame_style for segment in bottom.crop(start, start + len(caption)))


def node(tree, key):
    def walk(parent):
        for child in parent.children:
            yield child
            yield from walk(child)
    return next(n for selector in ("#work-tree", "#work-jobs-tree")
                for n in walk(tree.app.query_one(selector, Tree).root) if n.data and n.data[0] == key)


def select(tree, key):
    target = node(tree, key)
    target.tree.select_node(target)


def move(tree, key):
    target = node(tree, key)
    target.tree.move_cursor(target)


def project_payload():
    data = payload()
    previous = deepcopy(data["jobs"][0])
    previous.update(id="11111111-1111-4111-8111-111111111111", objective="Earlier release", state="completed", updated_ts=11000)
    previous["nodes"] = [dict(previous["nodes"][0], key="legacy_step", seat=999, state="accepted")]
    blocked = dict(previous, id="previous-blocked", objective="Earlier blocked attempt", state="blocked", nodes=[])
    data["jobs"].extend([previous, blocked])
    data["projects"] = [dict(id="project-a", objective="Vault project", job_ids=[previous["id"], blocked["id"], "job-a", "job-b"], workflow_ids=[], active_job_ids=["job-a"])]
    data["jobs_loaded"] = len(data["jobs"])
    return data


async def test_open_project_history_includes_completed_but_excludes_blocked_versions():
    data = project_payload()
    data["workflows"] = []
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        output = painted(app, "#work-navigation")
        assert all(text in output for text in ["Earlier release", "BunkerVault", "Repair logging"]), output
        assert "Vault project" not in output
        assert "Earlier blocked attempt" not in output
        assert output.index("JOBS") < output.index("Earlier release")
        assert "legacy_step" not in output
        assert not node(tree, "job:" + data["jobs"][3]["id"]).is_expanded
        assert node(tree, "job:job-a").is_expanded
        assert "BunkerVault [limits]" in painted(app, "#work-detail-panel")
        node(tree, "job:" + data["jobs"][3]["id"]).expand()
        await pilot.pause()
        assert "legacy_step" in painted(app, "#work-navigation")



async def test_running_jobs_use_accent_and_completed_jobs_use_dark_green():
    data = project_payload()
    data["workflows"] = []
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        node(tree, "job:" + data["jobs"][3]["id"]).expand()
        await pilot.pause()

        def color(selector, text):
            region = app.query_one(selector).region
            segments = [segment for strip in app.screen._compositor.render_strips()[region.y:region.bottom]
                        for segment in strip.crop(region.x, region.right) if text in segment.text]
            assert segments, text
            return segments[0].style.color.get_truecolor(app.ansi_theme)

        heading_green = color("#hero-work-seats", "WORKING")
        completed_green = (9, 155, 43)  # Matrix foreground dimmed against its background.
        assert completed_green != heading_green
        assert color("#work-navigation", "Repair logging") == heading_green
        assert color("#work-navigation", "Earlier release") == completed_green
        assert color("#work-navigation", "legacy_step") == completed_green
        select(tree, "job:" + data["jobs"][3]["id"])
        await pilot.pause()
        assert color("#work-detail-panel", "completed") == completed_green
        assert color("#work-detail-panel", "accepted") == completed_green
        assert color("#work-detail-panel", "legacy_step") != heading_green
        select(tree, "step:" + data["jobs"][3]["id"] + ":legacy_step")
        await pilot.pause()
        assert color("#work-detail-panel", "accepted") == completed_green



async def test_project_nests_open_workflows_and_releases_terminal_jobs():
    data = project_payload()
    data["projects"][0].update(workflow_ids=["flow-a", "flow-old", "flow-duplicate"], active_job_ids=["job-a", "job-c"])
    data["projects"][0]["job_ids"].append("job-c")
    data["workflows"][1]["contracts_job_id"] = data["jobs"][3]["id"]
    data["workflows"].append(dict(data["workflows"][0], id="flow-duplicate", objective="Second workflow reference"))
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        output = painted(app, "#work-navigation")
        assert "Vault project" in output and "Old completed workflow" not in output
        assert "OTHER JOBS" not in output
        assert node(tree, "workflow:flow-a").parent is node(tree, "project:project-a")
        assert node(tree, "job:" + data["jobs"][3]["id"]).parent is app.query_one("#work-jobs-tree", Tree).root
        def jobs(parent):
            return [child.data[0] for child in parent.children if child.data and child.data[1] == "job"] + [key for child in parent.children for key in jobs(child)]
        keys = jobs(tree.root) + jobs(app.query_one("#work-jobs-tree", Tree).root)
        assert len(keys) == len(set(keys)) == 3
        assert "BunkerVault [limits]" in painted(app, "#work-detail-panel")



@pytest.mark.parametrize("query", ["Earlier release", "legacy_step", "999"])
async def test_project_history_search_reveals_steps_and_restores_collapse(query):
    data = project_payload()
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        body = app.query_one(SurfWorkBody)
        body.focus_find()
        app.query_one("#work-find", Input).value = query
        await pilot.pause()
        output = painted(app, "#work-navigation")
        assert all(text in output for text in ["Earlier release", "legacy_step", "#999"]), output
        assert "Vault project" not in output
        assert "Repair logging" not in output
        assert app.query_one("#hero-work-jobs").data.digits == "2"
        body.close_find()
        await pilot.pause()
        assert "Earlier release" in painted(app, "#work-navigation")
        assert "legacy_step" not in painted(app, "#work-navigation")



async def test_project_filters_exclude_historical_working_nodes_but_keep_parent_path():
    data = project_payload()
    data['projects'][0]['workflow_ids'] = ['flow-a']
    data["jobs"][3]["nodes"][0].update(state="working", role="implement")
    data["jobs"][3]["nodes"].append(dict(data["jobs"][3]["nodes"][0], role="review", key="legacy_review"))
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        body = pilot.app.query_one(SurfWorkBody)
        body.cycle_filter()  # Open -> Blocked -> Build
        body.cycle_filter()
        await pilot.pause()
        output = painted(pilot.app, "#work-navigation")
        assert "Vault project" in output and "BunkerVault" in output
        assert "Earlier release" not in output
        body.cycle_filter()
        await pilot.pause()
        assert "Vault project" in painted(pilot.app, "#work-navigation")
        assert "Earlier release" not in painted(pilot.app, "#work-navigation")
        body.cycle_filter()  # Review -> 24H -> Open -> Blocked
        body.cycle_filter()
        body.cycle_filter()
        await pilot.pause()
        output = painted(pilot.app, "#work-navigation")
        assert "Vault project" in output and "Earlier blocked attempt" in output
        assert pilot.app.query_one("#hero-work-blocked").data.digits == "1"



async def test_project_history_selection_expansion_and_removal_follow_fresh_snapshot():
    data = project_payload()
    data['projects'][0]['workflow_ids'] = ['flow-a']
    previous_id = data["jobs"][3]["id"]
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        body = app.query_one(SurfWorkBody)
        tree = app.query_one("#work-tree", Tree)
        node(tree, "job:" + previous_id).expand()
        select(tree, f"step:{previous_id}:legacy_step")
        await pilot.pause()
        body.update_data(surf_work=deepcopy(data))
        await pilot.pause()
        assert node(tree, "job:" + previous_id).is_expanded
        assert "legacy_step" in painted(app, "#work-detail-panel")
        node(tree, "project:project-a").collapse()
        body.update_data(surf_work=deepcopy(data))
        await pilot.pause()
        assert not node(tree, "project:project-a").is_expanded
        assert "legacy_step" in painted(app, "#work-detail-panel")
        data.update(projects=[], jobs=[], workflows=[])
        body.update_data(surf_work=data)
        await pilot.pause()
        assert "No jobs loaded" in painted(app, "#work-navigation")
        assert "legacy_step" not in painted(app, "#work-detail-panel")



async def test_project_details_show_linked_history_unknown_states_and_literal_prose():
    data = project_payload()
    data['projects'][0]['workflow_ids'] = ['flow-a']
    previous_id = data["jobs"][3]["id"]
    data["projects"][0]["objective"] = "部署 [bold] project\x1b\u202e"
    data["projects"][0]["job_ids"].extend(["unknown-job", "missing-job"])
    data["jobs"].append(dict(id="unknown-job", state=None, objective="Unknown version", nodes=None))
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        select(tree, "project:project-a")
        await pilot.pause()
        detail = painted(app, "#work-detail-panel")
        assert all(text in detail for text in ["SELECTED PROJECT", "部署 [bold]", previous_id, "completed", "blocked", "executing", "unknown", "not loaded"]), detail
        assert "\x1b" not in detail and "\u202e" not in detail
        region = app.query_one("#work-detail-panel").region
        segments = [seg for strip in app.screen._compositor.render_strips()[region.y:region.bottom] for seg in strip.crop(region.x, region.right)]
        assert any(seg.style and seg.style.link and previous_id in seg.style.link for seg in segments)
        select(tree, "job:job-a")
        await pilot.pause()
        assert previous_id in painted(app, "#work-detail-panel")
        node(tree, "project:project-a").expand()
        await pilot.pause()
        assert "job not loaded" in painted(app, "#work-navigation")



async def test_project_details_include_workflow_siblings_outside_version_ids():
    data = project_payload()
    data["projects"][0].update(job_ids=["job-a"], workflow_ids=["flow-a", "missing-workflow"])
    data["jobs"][1]["state"] = None
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        assert "workflow not loaded" in painted(app, "#work-navigation")
        select(tree, "project:project-a")
        await pilot.pause()
        assert "job-b" in painted(app, "#work-detail-panel")
        assert "unknown" in painted(app, "#work-detail-panel")
        select(tree, "workflow:flow-a")
        await pilot.pause()
        assert "unknown" in painted(app, "#work-detail-panel")
        select(tree, "job:job-b")
        await pilot.pause()
        assert "job-a" in painted(app, "#work-detail-panel")



async def test_six_cards_tree_and_default_job_detail_are_painted():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == ["JOBS", "WORKFLOWS", "SEATS", "BUILD", "REVIEW", "BLOCKED"]
        assert {card.region.height for card in cards} == {9}
        assert max(c.region.width for c in cards) - min(c.region.width for c in cards) <= 1
        tree = painted(app, "#work-navigation")
        assert all(value in tree for value in ["WORKFLOWS", "loaded", "BunkerVault", "JOBS", "Repair logging", "#393", "#827"])
        assert "Old completed" not in tree
        detail = painted(app, "#work-detail-panel")
        assert all(value in detail for value in ["SELECTED JOB", "BunkerVault [limits]", "executing", "CREATED", "LAST UPDATE", "vault", "#393", "Build withdrawal limits"]), detail


@pytest.mark.parametrize('status', ['completed', 'paused', 'blocked', 'future-state'])
async def test_inactive_workflow_does_not_hide_followup_jobs(status):
    data = payload()
    data['workflows'] = [dict(data['workflows'][0], status=status)]
    data['projects'] = [dict(id='project-a', objective='Earlier project',
                            workflow_ids=['flow-a'], job_ids=['job-a', 'job-c'], active_job_ids=['job-c'])]
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        body = app.query_one(SurfWorkBody)
        assert 'workflow:flow-a' not in body._entries
        assert 'project:project-a' not in body._entries
        jobs_tree = app.query_one('#work-jobs-tree', Tree)
        assert node(jobs_tree, 'job:job-a').parent is jobs_tree.root
        assert node(jobs_tree, 'job:job-c').parent is jobs_tree.root
        output = painted(app, '#work-jobs-panel')
        assert 'BunkerVault [limits]' in output and 'Repair logging' in output
        # Search remains a route to historical original workflow details.
        body.focus_find()
        app.query_one('#work-find', Input).value = 'BunkerVault'
        await pilot.pause()
        assert 'workflow:flow-a' in body._entries
        select(app.query_one('#work-tree', Tree), 'workflow:flow-a')
        await pilot.pause()
        assert status in painted(app, '#work-detail-panel')
        body.close_find()
        await pilot.pause()
        assert 'workflow:flow-a' not in body._entries
        assert 'project:project-a' not in body._entries



@pytest.mark.parametrize('workflow_ids', [[], ['flow-old'], ['missing-workflow']])
async def test_project_without_visible_workflow_keeps_jobs_and_history_in_jobs(workflow_ids):
    data = project_payload()
    previous_id = data['jobs'][3]['id']
    data['projects'][0]['workflow_ids'] = workflow_ids
    data['projects'][0]['job_ids'].append('missing-job')
    data['workflows'] = [dict(data['workflows'][1], contracts_job_id=previous_id)]
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        workflows, jobs = app.query_one('#work-tree', Tree), app.query_one('#work-jobs-tree', Tree)
        assert all(child.data is None for child in workflows.root.children)
        assert 'Vault project' not in painted(app, '#work-tree-panel')
        keys = [child.data[0] for child in jobs.root.children if child.data]
        assert sorted(keys) == sorted(['job:job-a', 'job:job-c', 'job:' + previous_id, 'missing:missing-job'])
        select(jobs, 'job:job-a')
        await pilot.pause()
        assert previous_id in painted(app, '#work-detail-panel')
        body.focus_find()
        app.query_one('#work-find', Input).value = 'Vault project'
        await pilot.pause()
        assert 'Earlier release' in painted(app, '#work-navigation')
        assert 'BunkerVault' in painted(app, '#work-jobs-panel')
        assert 'Repair logging' not in painted(app, '#work-jobs-panel')



async def test_paused_workflow_remains_inspectable_in_blocked_filter():
    data = payload()
    data['workflows'] = [dict(data['workflows'][0], status='paused')]
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        body = pilot.app.query_one(SurfWorkBody)
        body.cycle_filter()
        await pilot.pause()
        tree = pilot.app.query_one('#work-tree', Tree)
        select(tree, 'workflow:flow-a')
        await pilot.pause()
        assert 'paused' in painted(pilot.app, '#work-detail-panel')



async def test_keyboard_selection_step_detail_and_refresh_preserve_identity_and_collapse():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        select(tree, "step:job-a:vault")
        await pilot.pause()
        assert "DEPENDENCIES" in painted(app, "#work-detail-panel")
        assert "spec" in painted(app, "#work-detail-panel")
        assert "ATTEMPT" in painted(app, "#work-detail-panel")
        node(tree, "job:job-a").collapse()
        app.query_one(SurfWorkBody).update_data(surf_work=deepcopy(payload()))
        await pilot.pause()
        assert not node(tree, "job:job-a").is_expanded
        assert "DEPENDENCIES" in painted(app, "#work-detail-panel")
        select(tree, "job:job-c")
        app.query_one(SurfWorkBody).focus_tree()
        await pilot.press("enter")
        assert app.focused.id == "work-detail-scroll"
        assert "—" in painted(app, "#work-detail-panel") and "unavailable" not in painted(app, "#work-detail-panel")


async def test_find_and_filter_are_local_and_restore_tree_focus():
    async with Harness(payload(), view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        body = app.query_one(SurfWorkBody)
        body.focus_find()
        app.query_one("#work-find", Input).value = "Repair"
        await pilot.pause()
        output = painted(app, "#work-navigation")
        assert "Repair logging" in output and "BunkerVault" not in output
        assert body.close_find() is True
        await pilot.pause()
        assert app.focused.id == "work-jobs-tree"
        assert body.close_find() is False
        body.cycle_filter()  # Open -> Blocked -> Build
        body.cycle_filter()
        await pilot.pause()
        assert body._filter == "build" and "Build" in painted(app, "#work-navigation")
        assert "Repair logging" not in painted(app, "#work-navigation")
        body.cycle_filter()
        await pilot.pause()
        assert body._filter == "review" and "Review" in painted(app, "#work-navigation")
        body.cycle_filter()  # Review -> 24H -> Open -> Blocked
        body.cycle_filter()
        body.cycle_filter()
        await pilot.pause()
        assert "BunkerVault" in painted(app, "#work-detail-panel")
        tree = app.query_one("#work-tree", Tree)
        select(tree, "job:job-b")
        await pilot.pause()
        assert "Vault frontend" in painted(app, "#work-detail-panel")



async def test_missing_reads_and_missing_linked_jobs_are_explicit():
    data = payload()
    data["workflows"][0]["frontend_job_id"] = "missing-id"
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "not loaded" in painted(app, "#work-navigation")
        app.query_one(SurfWorkHero).update_data(surf_work=None)
        app.query_one(SurfWorkBody).update_data(surf_work=None)
        await pilot.pause()
        assert "unavailable" not in painted(app, "#work-navigation")
        assert "-- shown" in painted(app, "#work-jobs-panel")
        assert all("unavailable" not in painted(app, f"#hero-work-{key}") for key in ["jobs", "workflows", "seats", "build", "review", "blocked"])



async def test_third_party_prose_preserves_brackets_cjk_and_address_copy_without_guessing_chain():
    data = payload()
    address = "0x" + "12" * 20
    data["jobs"][0]["objective"] = f"部署 [bold] vault {address}\x1b\u202e"
    data["jobs"][0]["nodes"][0]["dispatch_note"] = "[red] 审查界面"
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        detail = painted(app, "#work-detail-panel")
        assert "[bold]" in detail and "部署" in detail and "⧉" in detail
        assert "[red] 审查界面" in detail
        assert "\x1b" not in detail and "\u202e" not in detail
        segments = [segment for strip in app.screen._compositor.render_strips() for segment in strip]
        assert any(segment.style and segment.style.meta.get("@click", "").startswith("app.copy_address") for segment in segments)
        assert not any(segment.style and segment.style.link and "etherscan" in segment.style.link for segment in segments)


async def test_long_objective_keeps_live_fields_visible_and_step_columns_aligned():
    data = payload()
    data["jobs"][0]["objective"] = "Build a contract with verified controls " * 120
    data["jobs"][0]["nodes"][0]["key"] = "withdrawal_limits"
    data["jobs"][0]["nodes"][1]["key"] = "review"
    data["workflows"][0]["objective"] = "巨大なワークフロー " * 20
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "#work-detail-panel")
        assert all(value in output for value in ["STATE", "LAST UPDATE", "STEP", "#393", "#827", "Build withdrawal limits"])
        first = next(line for line in output.splitlines() if "withdrawal_limits" in line)
        second = next(line for line in output.splitlines() if "#827" in line)
        assert first.index("#393") == second.index("#827")
        assert first.index("working") == second.index("working")
        tree = painted(pilot.app, "#work-navigation")
        assert "巨大" in tree and "‹ widen" in tree
        assert "executing" in next(line for line in tree.splitlines() if "巨大" in line)
        assert "#393" in tree and "working" in tree


async def test_blocked_workflow_selection_survives_refresh_and_exposes_missing_job():
    data = payload()
    data["workflows"].insert(0, dict(id="flow-blocked", status="blocked", objective="Blocked deployment", contracts_job_id="missing", frontend_job_id=None, created_ts=10001))
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        output = painted(app, "#work-navigation")
        assert "BunkerVault" in output and "JOBS" in output
        assert "Blocked deployment" not in output
        app.query_one(SurfWorkBody).cycle_filter()
        await pilot.pause()
        blocked = node(tree, "workflow:flow-blocked")
        assert blocked.allow_expand
        blocked.expand()
        tree.focus()
        await pilot.pause()
        tree.move_cursor(blocked)
        app.query_one(SurfWorkBody).focus_tree()
        await pilot.pause()
        assert "Blocked deployment" in painted(app, "#work-detail-panel")
        app.query_one(SurfWorkBody).update_data(surf_work=deepcopy(data))
        await pilot.pause()
        assert tree.cursor_node is node(tree, "workflow:flow-blocked")
        assert "job not loaded" in painted(app, "#work-navigation")



async def test_known_zero_stale_and_unknown_are_not_fresh_activity():
    data = payload()
    data.update(state="stale", read_ts=9000)
    data["summary"].update(jobs=0, seats=None, blocked=0)
    data["jobs"][0]["nodes"][0].update(state="unknown", seat=None, attempt=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "stale" not in painted(app, "#hero-work-jobs")
        assert app.query_one("#hero-work-jobs").data.digits == "0"
        assert "--" not in painted(app, "#hero-work-seats")
        assert app.query_one("#hero-work-seats").source_record.digits == "--"
        tree = app.query_one("#work-tree", Tree)
        select(tree, "step:job-a:vault")
        await pilot.pause()
        output = painted(app, "#work-detail-panel")
        assert "unknown" in output and "--" in output
        assert "#None" not in output
        region = app.query_one("#work-detail-panel").region
        tokens = [seg for strip in app.screen._compositor.render_strips()[region.y:region.bottom] for seg in strip.crop(region.x, region.right)]
        assert any("unknown" in seg.text and seg.style and seg.style.color and seg.style.color.get_truecolor(app.ansi_theme) == (158, 158, 158) for seg in tokens)


async def test_selecting_a_new_job_returns_scrolled_details_to_top():
    data = payload()
    data["jobs"][0]["objective"] = "Long objective " * 400
    data["jobs"][2]["objective"] = "Second long objective " * 400
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        scroller = app.query_one("#work-detail-scroll")
        scroller.scroll_end(animate=False)
        await pilot.pause()
        assert scroller.scroll_y > 0
        tree = app.query_one("#work-jobs-tree", Tree)
        tree.focus()
        await pilot.pause()
        move(tree, "job:job-c")
        async with asyncio.timeout(2):
            while scroller.scroll_y != 0:
                await pilot.pause()
        assert scroller.scroll_y == 0
        assert "STATE" in painted(app, "#work-detail-panel")


async def test_default_selection_uses_latest_update_and_keeps_superseded_history():
    data = payload()
    data["jobs"][2]["updated_ts"] = 10000
    data["jobs"].append(dict(id="old-job", state="superseded", objective="Replaced objective"))
    data["workflows"].append(dict(id="old-flow", status="superseded", objective="Replaced workflow"))
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "Repair logging" in painted(pilot.app, "#work-detail-panel")
        assert "Replaced workflow" not in painted(pilot.app, "#work-navigation")
        assert "Replaced objective" in painted(pilot.app, "#work-navigation")
        pilot.app.query_one('#work-find', Input).value = 'Replaced'
        await pilot.pause()
        assert "Replaced workflow" in painted(pilot.app, "#work-navigation")



@pytest.mark.parametrize("width", [125, 130, 149])
async def test_hero_advertises_caption_clipping_at_its_actual_inner_budget(width):
    async with Harness(payload()).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "#hero-work-blocked")
        assert ("‹" in output) == ("needs attention" not in output)


async def test_find_workflow_by_id_keeps_its_job_path():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        body = pilot.app.query_one(SurfWorkBody)
        body.focus_find()
        pilot.app.query_one("#work-find", Input).value = "flow-a"
        await pilot.pause()
        output = painted(pilot.app, "#work-navigation")
        assert "BunkerVault" in output and "vault" in output
        assert "No matching work" not in output


@pytest.mark.parametrize("linked", [None, "job-a", "missing-job"])
async def test_blocked_filter_keeps_workflow_without_blocked_child(linked):
    data = payload()
    data["workflows"] = [dict(id="flow-blocked", status="blocked", objective="Awaiting deployment", contracts_job_id=linked, frontend_job_id=None)]
    data["jobs"] = [dict(data["jobs"][0], state="completed")]
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        body = pilot.app.query_one(SurfWorkBody)
        body.cycle_filter()
        await pilot.pause()
        output = painted(pilot.app, "#work-navigation")
        assert "Awaiting deployment" in output
        if linked:
            tree = pilot.app.query_one("#work-tree", Tree)
            select(tree, "workflow:flow-blocked")
            await pilot.pause()
            assert "Contracts" in painted(pilot.app, "#work-detail-panel")



async def test_default_without_executing_job_selects_newest_unfinished_workflow():
    data = payload()
    data["jobs"] = [dict(data["jobs"][0], state="completed")]
    data["workflows"].append(dict(id="flow-new", status="deployment", objective="Awaiting deployment", created_ts=9999))
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        detail = painted(pilot.app, "#work-detail-panel")
        assert "SELECTED WORKFLOW" in detail and "Awaiting deployment" in detail


async def test_job_and_step_details_include_template_related_job_and_note_age():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        detail = painted(app, "#work-detail-panel")
        assert "TEMPLATE" in detail and "contracts" in detail
        assert "RELATED JOBS" in detail and "job-b" in detail
        assert "40s ago" in detail
        tree = app.query_one("#work-tree", Tree)
        select(tree, "step:job-a:vault")
        await pilot.pause()
        assert "40s ago" in painted(app, "#work-detail-panel")


@pytest.mark.parametrize("reverse", [False, True])
async def test_default_tied_jobs_use_stable_id_after_page_reordering(reverse):
    data = payload()
    first = data["jobs"][0]
    data["jobs"] = [dict(first, id="job-y", objective="Tie earlier id"), dict(first, id="job-z", objective="Tie later id")]
    data["workflows"] = []
    if reverse:
        data["jobs"].reverse()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "Tie later id" in painted(pilot.app, "#work-detail-panel")


@pytest.mark.parametrize("key,child_text", [("project:project-a", "BunkerVault"), ("job:job-a", "vault")])
async def test_mouse_expanders_toggle_top_level_and_nested_branches(key, child_text):
    data = project_payload()
    data["projects"][0]["workflow_ids"] = ["flow-a"]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        branch = node(tree, key)
        tree = branch.tree
        panel = '#work-tree-panel' if tree.id == 'work-tree' else '#work-jobs-panel'

        def arrow_position():
            for y, strip in enumerate(app.screen._compositor.render_strips()):
                x = 0
                for segment in strip:
                    if tree.region.y <= y < tree.region.bottom and segment.style and segment.style.meta.get("node") == branch.id:
                        for glyph in ("▼", "▶"):
                            if glyph in segment.text:
                                return x + segment.text.index(glyph), y
                    x += segment.cell_length
            pytest.fail("branch arrow must be visible and clickable")

        assert child_text in painted(app, panel)
        await pilot.click(offset=arrow_position())
        await pilot.pause()
        assert not branch.is_expanded
        assert child_text not in painted(app, panel)
        assert app.focused is tree
        await pilot.click(offset=arrow_position())
        await pilot.pause()
        assert branch.is_expanded
        assert child_text in painted(app, panel)


async def test_mouse_label_selects_without_folding_or_leaving_tree():
    data = project_payload()
    data['projects'][0]['workflow_ids'] = ['flow-a']
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, tree = pilot.app, pilot.app.query_one("#work-tree", Tree)
        branch = node(tree, "project:project-a")
        for _ in range(2):
            for y, strip in enumerate(app.screen._compositor.render_strips()):
                if "Vault project" in strip.text and tree.region.y <= y < tree.region.bottom:
                    await pilot.click(offset=(strip.text.index("Vault project") + 2, y))
                    break
            else:
                pytest.fail("visible workflow label required")
            await pilot.pause()
            assert branch.is_expanded and tree.cursor_node is branch
            assert app.focused is tree
            assert "SELECTED PROJECT" in painted(app, "#work-detail-panel")


async def test_open_and_blocked_tabs_partition_work_and_keep_history():
    data = project_payload()
    data['projects'][0]['workflow_ids'] = ['flow-a']
    data['jobs'].append(dict(id='blocked-other', state='blocked', objective='Blocked standalone'))
    data['workflows'].append(dict(id='blocked-flow', status='blocked', objective='Blocked workflow', contracts_job_id=None, frontend_job_id=None))
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        assert body._filter == 'open'
        text = painted(app, '#work-navigation')
        assert 'Old completed workflow' not in text and 'Earlier release' in text
        assert 'Earlier blocked attempt' not in text and 'Blocked standalone' not in text and 'Blocked workflow' not in text
        title = app.query_one('#work-tree-panel .panel-title')
        for y, strip in enumerate(app.screen._compositor.render_strips()):
            if y == title.region.y:
                await pilot.click(offset=(strip.text.index('Blocked') + 2, y))
                break
        await pilot.pause()
        text = painted(app, '#work-navigation')
        assert body._filter == 'blocked'
        assert all(word in text for word in ('Vault project', 'Earlier blocked attempt', 'Blocked standalone', 'Blocked workflow'))
        assert 'Earlier release' not in text and 'Repair logging' not in text
        assert all(edge[0] == '' for edge in app.query_one('#work-navigation').styles.border)
        assert all(edge[0] == '' for edge in app.query_one('#work-detail-panel').styles.border)



async def test_workflow_and_standalone_job_trees_share_detail_and_preserve_navigation():
    data = project_payload()
    data['projects'][0]['workflow_ids'] = ['flow-a']
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        workflow_panel, jobs_panel = app.query_one('#work-tree-panel'), app.query_one('#work-jobs-panel')
        assert workflow_panel.region.bottom <= jobs_panel.region.y
        assert jobs_panel.region.height > workflow_panel.region.height
        assert 'WORKFLOWS' in painted(app, '#work-tree-panel')
        assert 'JOBS' in painted(app, '#work-jobs-panel')
        workflows, jobs = app.query_one('#work-tree', Tree), app.query_one('#work-jobs-tree', Tree)
        assert node(workflows, 'workflow:flow-a').parent is node(workflows, 'project:project-a')
        assert all(child.data[1] in ('project', 'workflow', 'missing workflow') for child in workflows.root.children)
        assert node(jobs, 'job:job-a').parent is node(workflows, 'workflow:flow-a')
        assert node(jobs, 'job:job-c').parent is jobs.root
        assert 'Earlier release' in painted(app, '#work-jobs-panel')
        workflows.select_node(node(jobs, 'step:job-a:vault'))
        await pilot.pause()
        assert 'DEPENDENCIES' in painted(app, '#work-detail-panel')
        node(jobs, 'job:job-a').collapse()
        body.update_data(surf_work=deepcopy(data))
        await pilot.pause()
        assert not node(jobs, 'job:job-a').is_expanded
        assert 'DEPENDENCIES' in painted(app, '#work-detail-panel')
        body.focus_tree()
        await pilot.pause()
        assert app.focused is workflows
        jobs.move_cursor(node(jobs, 'job:job-c'))
        await pilot.pause()
        assert 'DEPENDENCIES' in painted(app, '#work-detail-panel')
        workflows.select_node(node(workflows, 'workflow:flow-a'))
        await pilot.pause()
        assert 'SELECTED WORKFLOW' in painted(app, '#work-detail-panel')
        assert node(jobs, 'job:job-c').parent is jobs.root
        body.focus_tree()
        await pilot.pause()
        assert app.focused is workflows
        body.focus_find()
        app.query_one('#work-find', Input).value = 'flow-a'
        await pilot.pause()
        assert 'BunkerVault' in painted(app, '#work-tree-panel')
        assert 'BunkerVault' not in painted(app, '#work-jobs-panel')
        assert 'Repair logging' not in painted(app, '#work-jobs-panel')



@pytest.mark.parametrize('job_state', ['completed', 'executing'])
async def test_stopped_workflow_does_not_own_jobs_in_open_or_role_filters(job_state):
    data = payload()
    data['workflows'] = [dict(id='flow-blocked', status='blocked', objective='Awaiting deployment',
                              contracts_job_id='job-a', frontend_job_id=None)]
    data['jobs'] = [dict(data['jobs'][0], state=job_state)]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        for choice in ('open', 'build', 'review'):
            body._filter = choice
            body._rebuild()
            await pilot.pause()
            assert 'Awaiting deployment' not in painted(app, '#work-tree-panel')
            assert ('BunkerVault' in painted(app, '#work-jobs-panel')) == (choice == 'open' or job_state == 'executing')
        body._filter = 'blocked'
        body._rebuild()
        await pilot.pause()
        assert 'Awaiting deployment' in painted(app, '#work-tree-panel')


async def test_mouse_returns_to_same_cursor_in_other_work_tree():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        for selector, label, selected, heading in (
            ('#work-tree', 'BunkerVault', 'workflow:flow-a', 'SELECTED WORKFLOW'),
            ('#work-jobs-tree', 'Repair logging', 'job:job-c', 'SELECTED JOB'),
            ('#work-tree', 'BunkerVault', 'workflow:flow-a', 'SELECTED WORKFLOW'),
            ('#work-jobs-tree', 'Repair logging', 'job:job-c', 'SELECTED JOB'),
        ):
            tree = app.query_one(selector, Tree)
            region = tree.region
            rows = app.screen._compositor.render_strips()
            y = next(y for y in range(region.y, region.bottom)
                     if label in rows[y].crop(region.x, region.right).text)
            x = region.x + rows[y].crop(region.x, region.right).text.index(label) + 2
            await pilot.click(offset=(x, y))
            await pilot.pause()
            assert body._selected == selected
            assert app.focused is tree
            assert heading in painted(app, '#work-detail-panel')
            assert label in painted(app, '#work-detail-panel')


@pytest.mark.parametrize('in_project', [False, True])
async def test_workflow_keeps_jobs_and_steps_out_of_standalone_tree(in_project):
    data = payload()
    data['jobs'][1].update(state='completed', nodes=[dict(data['jobs'][0]['nodes'][0], key='frontend', state='accepted')])
    if in_project:
        data['projects'] = [dict(id='project-a', objective='Vault project', workflow_ids=['flow-a'],
                                 job_ids=['job-a', 'job-b', 'job-c'], active_job_ids=['job-a'])]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfWorkBody)
        tree, jobs = app.query_one('#work-tree', Tree), app.query_one('#work-jobs-tree', Tree)
        workflow = node(tree, 'workflow:flow-a')
        assert workflow.allow_expand
        assert node(tree, 'job:job-a').parent is workflow
        assert node(tree, 'job:job-b').parent is workflow
        assert node(tree, 'step:job-a:vault').parent is node(tree, 'job:job-a')
        assert 'vault' in painted(app, '#work-tree-panel')
        assert 'Repair logging' in painted(app, '#work-jobs-panel')
        assert 'BunkerVault' not in painted(app, '#work-jobs-panel')
        assert 'JOBS · 1 shown' in painted(app, '#work-jobs-panel')
        assert [child.data[0] for child in jobs.root.children if child.data] == ['job:job-c']
        select(tree, 'step:job-a:vault')
        await pilot.pause()
        assert 'DEPENDENCIES' in painted(app, '#work-detail-panel')
        body.update_data(surf_work=deepcopy(data))
        await pilot.pause()
        body.focus_tree()
        await pilot.pause()
        assert app.focused is tree
        assert 'DEPENDENCIES' in painted(app, '#work-detail-panel')
        body.focus_find()
        app.query_one('#work-find', Input).value = 'frontend'
        await pilot.pause()
        assert node(tree, 'step:job-b:frontend').tree is tree
        assert 'frontend' in painted(app, '#work-tree-panel')
        assert 'Repair logging' not in painted(app, '#work-jobs-panel')


async def test_missing_workflow_job_stays_under_its_workflow():
    data = payload()
    data['workflows'][0]['frontend_job_id'] = 'missing-id'
    async with Harness(data, view="open").run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one('#work-tree', Tree)
        missing = node(tree, 'missing:missing-id')
        assert missing.parent is node(tree, 'workflow:flow-a')
        assert 'job not loaded' in painted(app, '#work-tree-panel')
        assert 'missing-id' not in painted(app, '#work-jobs-panel')

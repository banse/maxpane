"""Painted and keyboard contracts for the work desk; never uses live reads."""
import asyncio
from copy import deepcopy

import pytest
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
    def __init__(self, data=None):
        super().__init__()
        self.data = data
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield SurfWorkHero()
        yield SurfWorkBody()
    def on_mount(self):
        self.query_one(SurfWorkHero).update_data(surf_work=self.data)
        self.query_one(SurfWorkBody).update_data(surf_work=self.data)


def painted(app, selector):
    region = app.query_one(selector).region
    return "\n".join(strip.crop(region.x, region.right).text for strip in app.screen._compositor.render_strips()[region.y:region.bottom])


def node(tree, key):
    def walk(parent):
        for child in parent.children:
            yield child
            yield from walk(child)
    return next(n for n in walk(tree.root) if n.data and n.data[0] == key)


async def test_six_cards_tree_and_default_job_detail_are_painted():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == ["JOBS", "WORKFLOWS", "SEATS", "BUILD", "REVIEW", "BLOCKED"]
        assert {card.region.height for card in cards} == {9}
        assert max(c.region.width for c in cards) - min(c.region.width for c in cards) <= 1
        tree = painted(app, "#work-tree-panel")
        assert all(value in tree for value in ["WORK TREE", "loaded", "BunkerVault", "OTHER JOBS", "Repair logging", "#393", "#827"])
        assert "Old completed" not in tree
        detail = painted(app, "#work-detail-panel")
        assert all(value in detail for value in ["SELECTED JOB", "BunkerVault [limits]", "executing", "CREATED", "LAST UPDATE", "vault", "#393", "Build withdrawal limits"]), detail


async def test_keyboard_selection_step_detail_and_refresh_preserve_identity_and_collapse():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        tree.select_node(node(tree, "step:job-a:vault"))
        await pilot.pause()
        assert "DEPENDENCIES" in painted(app, "#work-detail-panel")
        assert "spec" in painted(app, "#work-detail-panel")
        assert "ATTEMPT" in painted(app, "#work-detail-panel")
        node(tree, "workflow:flow-a").collapse()
        app.query_one(SurfWorkBody).update_data(surf_work=deepcopy(payload()))
        await pilot.pause()
        assert not node(tree, "workflow:flow-a").is_expanded
        assert "DEPENDENCIES" in painted(app, "#work-detail-panel")
        tree.select_node(node(tree, "job:job-c"))
        app.query_one(SurfWorkBody).focus_tree()
        await pilot.press("enter")
        assert app.focused.id == "work-detail-scroll"
        assert "—" in painted(app, "#work-detail-panel") and "unavailable" not in painted(app, "#work-detail-panel")


async def test_find_and_filter_are_local_and_restore_tree_focus():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        body = app.query_one(SurfWorkBody)
        body.focus_find()
        app.query_one("#work-find", Input).value = "Repair"
        await pilot.pause()
        output = painted(app, "#work-tree-panel")
        assert "Repair logging" in output and "BunkerVault" not in output
        assert body.close_find() is True
        await pilot.pause()
        assert app.focused.id == "work-tree"
        assert body.close_find() is False
        body.cycle_filter()
        await pilot.pause()
        assert "build" in painted(app, "#work-tree-panel")
        assert "Repair logging" not in painted(app, "#work-tree-panel")
        body.cycle_filter()
        await pilot.pause()
        assert "review" in painted(app, "#work-tree-panel")
        body.cycle_filter()
        await pilot.pause()
        assert "BunkerVault" in painted(app, "#work-detail-panel")
        tree = app.query_one("#work-tree", Tree)
        tree.select_node(node(tree, "job:job-b"))
        await pilot.pause()
        assert "Vault frontend" in painted(app, "#work-detail-panel")


async def test_missing_reads_and_missing_linked_jobs_are_explicit():
    data = payload()
    data["workflows"][0]["frontend_job_id"] = "missing-id"
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert "not loaded" in painted(app, "#work-tree-panel")
        app.query_one(SurfWorkHero).update_data(surf_work=None)
        app.query_one(SurfWorkBody).update_data(surf_work=None)
        await pilot.pause()
        assert "unavailable" not in painted(app, "#work-tree-panel")
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
        tree = painted(pilot.app, "#work-tree-panel")
        assert "巨大" in tree and "‹ widen" in tree
        assert "executing" in next(line for line in tree.splitlines() if "巨大" in line)
        assert "#393" in tree and "working" in tree


async def test_active_work_precedes_blocked_workflows_and_user_expansion_survives_refresh():
    data = payload()
    data["workflows"].insert(0, dict(id="flow-blocked", status="blocked", objective="Blocked deployment", contracts_job_id="missing", frontend_job_id=None, created_ts=10001))
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        output = painted(app, "#work-tree-panel")
        assert output.index("BunkerVault") < output.index("OTHER JOBS") < output.index("Blocked deployment")
        blocked = node(tree, "workflow:flow-blocked")
        assert not blocked.is_expanded
        tree.move_cursor(blocked)
        app.query_one(SurfWorkBody).focus_tree()
        await pilot.press("right")
        assert blocked.is_expanded
        app.query_one(SurfWorkBody).update_data(surf_work=deepcopy(data))
        await pilot.pause()
        assert node(tree, "workflow:flow-blocked").is_expanded
        assert "job not loaded" in painted(app, "#work-tree-panel")


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
        assert "--" in painted(app, "#hero-work-seats")
        tree = app.query_one("#work-tree", Tree)
        tree.select_node(node(tree, "step:job-a:vault"))
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
        tree = app.query_one("#work-tree", Tree)
        tree.move_cursor(node(tree, "job:job-c"))
        async with asyncio.timeout(2):
            while scroller.scroll_y != 0:
                await pilot.pause()
        assert scroller.scroll_y == 0
        assert "STATE" in painted(app, "#work-detail-panel")


async def test_default_selection_uses_latest_update_and_hides_superseded_work():
    data = payload()
    data["jobs"][2]["updated_ts"] = 10000
    data["jobs"].append(dict(id="old-job", state="superseded", objective="Replaced objective"))
    data["workflows"].append(dict(id="old-flow", status="superseded", objective="Replaced workflow"))
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "Repair logging" in painted(pilot.app, "#work-detail-panel")
        assert "Replaced" not in painted(pilot.app, "#work-tree-panel")


@pytest.mark.parametrize("width", [125, 130])
async def test_hero_advertises_footer_clipping_at_its_actual_border_budget(width):
    async with Harness(payload()).run_test(size=(width, 45)) as pilot:
        await pilot.pause()
        output = painted(pilot.app, "#hero-work-blocked")
        assert ("‹ widen" in output) == ("needs attention" not in output)


async def test_find_workflow_by_id_keeps_its_job_path():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        body = pilot.app.query_one(SurfWorkBody)
        body.focus_find()
        pilot.app.query_one("#work-find", Input).value = "flow-a"
        await pilot.pause()
        output = painted(pilot.app, "#work-tree-panel")
        assert "BunkerVault" in output and "Contracts" in output
        assert "No matching work" not in output


@pytest.mark.parametrize("linked", [None, "job-a", "missing-job"])
async def test_blocked_filter_keeps_workflow_without_blocked_child(linked):
    data = payload()
    data["workflows"] = [dict(id="flow-blocked", status="blocked", objective="Awaiting deployment", contracts_job_id=linked, frontend_job_id=None)]
    data["jobs"] = [dict(data["jobs"][0], state="completed")]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        body = pilot.app.query_one(SurfWorkBody)
        for _ in range(3):
            body.cycle_filter()
        await pilot.pause()
        output = painted(pilot.app, "#work-tree-panel")
        assert "Awaiting deployment" in output
        if linked:
            tree = pilot.app.query_one("#work-tree", Tree)
            node(tree, "workflow:flow-blocked").expand()
            await pilot.pause()
            assert "Contracts" in painted(pilot.app, "#work-tree-panel")


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
        tree.select_node(node(tree, "step:job-a:vault"))
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


@pytest.mark.parametrize("key,child_text", [("workflow:flow-a", "Contracts"), ("job:job-a", "vault")])
async def test_mouse_expanders_toggle_top_level_and_nested_branches(key, child_text):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one("#work-tree", Tree)
        branch = node(tree, key)

        def arrow_position():
            for y, strip in enumerate(app.screen._compositor.render_strips()):
                x = 0
                for segment in strip:
                    if segment.style and segment.style.meta.get("node") == branch.id:
                        for glyph in ("▼", "▶"):
                            if glyph in segment.text:
                                return x + segment.text.index(glyph), y
                    x += segment.cell_length
            pytest.fail("branch arrow must be visible and clickable")

        assert child_text in painted(app, "#work-tree-panel")
        await pilot.click(offset=arrow_position())
        await pilot.pause()
        assert not branch.is_expanded
        assert child_text not in painted(app, "#work-tree-panel")
        assert app.focused is tree
        await pilot.click(offset=arrow_position())
        await pilot.pause()
        assert branch.is_expanded
        assert child_text in painted(app, "#work-tree-panel")

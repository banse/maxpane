"""Oracle desk paint and interaction contracts; all reads are injected."""
from copy import deepcopy

import pytest
from textual.app import App
from textual.widgets import DataTable, Input, Tree

from maxpane_dashboard.themes import THEMES
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from maxpane_dashboard.widgets.surf.oracles import SurfOraclesBody, SurfOraclesHero
from tests.widgets.address_probe import icon_targets, link_targets


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    async def refuse(*args, **kwargs):
        raise AssertionError("no widget network")
    monkeypatch.setattr("httpx.AsyncClient.send", refuse)


def payload():
    rows = [dict(id=str(i), job_id=f"00000000-0000-4000-8000-{i + 1:012d}",
                 status=status, chain_id=1 if i != 2 else 8453,
                 question=f"Question {i} [literal]", created_ts=9900, updated_ts=9990)
            for i, status in enumerate(("attested", "assessing", "disagreed", "blocked", "mystery"))]
    members = [dict(seat=seat, job_id=rows[0]["job_id"], submission_hash=str(i + 1)*64,
                    node_key="oracle_assess", panel_state="agreed", panel_agreed=2,
                    panel_quorum=2, panel_size=3, panel_answer_type="bool", panel_answer_bool=True,
                    oracle_member_ok=True, oracle_seat_answer="true", oracle_notes=f"Evidence {i}",
                    oracle_question=rows[0]["question"], oracle_chain_id=1)
               for i, seat in enumerate((527, None))]
    detail = dict(rows[0], panel_answer_type="bool", panel_answer_bool=True, panel_figure=None,
                  agreed=2, quorum=2, panel_size=3, member_count=2, members=members, truncated=False)
    return dict(state="ok", partial=True, read_ts=10000, now_ts=10030, rows=rows,
                selected_id="0", detail=detail, detail_state="ok", detail_read_ts=10000)


class Harness(App):
    CSS = "Screen { padding: 1; } SurfOraclesBody { margin-top: 1; }"
    def __init__(self, data):
        super().__init__()
        self.data, self.requests, self.answers = data, [], []
        self.register_theme(THEMES["matrix"])
        self.theme = "matrix"
    def compose(self):
        yield SurfOraclesHero()
        yield SurfOraclesBody()
    def on_mount(self):
        self.query_one(SurfOraclesHero).update_data(surf_oracles=self.data)
        self.query_one(SurfOraclesBody).update_data(surf_oracles=self.data)
    def on_surf_oracles_body_request_selected(self, event):
        self.requests.append(event.request_id)
    def on_surf_oracles_body_answer_selected(self, event):
        self.answers.append(event.row)


def painted(app, selector):
    region = app.query_one(selector).region
    return "\n".join(strip.crop(region.x, region.right).text for strip in
                     app.screen._compositor.render_strips()[region.y:region.bottom])


@pytest.mark.parametrize("state", ["initial", "ok", "partial", "stale", "unavailable", "empty"])
async def test_hero_captions_share_inner_bottom_border_and_color(state, monkeypatch):
    data = payload()
    data["state"] = "ok" if state == "empty" else state
    if state in ("empty", "unavailable"):
        data.update(rows=[] if state == "empty" else None, detail=None)
    if state == "initial":
        monkeypatch.setattr(Harness, "on_mount", lambda self: None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        for key, _title, _heading, caption in SurfOraclesHero.CARDS:
            card = app.query_one("#hero-oracle-" + key)
            region = card.region
            rows = [row.crop(region.x, region.right) for row in
                    app.screen._compositor.render_strips()[region.y:region.bottom]]
            bottom = next(row for row in rows if "└" in row.text)
            assert caption in bottom.text
            assert caption not in rows[-1].text
            assert not card.border_subtitle
            if state == "partial":
                assert "partial" in str(card.tooltip)
            start = bottom.text.index(caption)
            corner = bottom.text.index("└")
            frame_style = list(bottom.crop(corner, corner + 1))[0].style
            assert all(segment.style == frame_style for segment in bottom.crop(start, start + len(caption)))


async def test_hero_counts_unknown_states_coverage_and_approved_layout():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [c.data.digits for c in cards] == ["5", "1", "1", "1", "1", "2"]
        assert all(c.region.height == 9 for c in cards)
        assert "1 other" in painted(app, "#oracle-coverage")
        assert "LATEST 100" in painted(app, "#oracle-coverage")
        assert "LATEST 100" in painted(app, "#hero-oracle-requests")
        assert "partial" not in painted(app, "#oracle-coverage")
        assert "partial" not in painted(app, SurfOraclesHero)
        assert "mystery" in painted(app, "#oracle-requests")
        assert "NO QUORUM" in painted(app, SurfOraclesHero)
        assert "YES" in painted(app, "#oracle-summary")
        assert "Question 0 [literal]" in painted(app, "#oracle-summary")
        assert app.query_one("#oracle-request-panel").size.width > 1.8 * app.query_one("#oracle-detail-panel").size.width


@pytest.mark.parametrize("rows,expected", [(None, "--"), ([], "0")])
async def test_unavailable_and_empty_counts_are_distinct(rows, expected):
    data = payload() | dict(rows=rows, state="unavailable" if rows is None else "ok", detail=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert pilot.app.query_one(NewsHeroCard).data.digits == expected
        assert ("No matching requests" in painted(pilot.app, SurfOraclesBody)) == (rows == [])
        assert "unavailable" not in painted(pilot.app, SurfOraclesBody)


async def test_selection_clears_wrong_detail_and_requests_exact_new_id():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        app.query_one("#oracle-requests", DataTable).move_cursor(row=1)
        await pilot.pause()
        assert app.requests[-1] == "1"
        assert "loading" in painted(app, "#oracle-summary")
        assert "YES" not in painted(app, "#oracle-summary")
        assert not app.query_one(Tree).root.children
        newer = payload() | dict(now_ts=10031)
        app.query_one(SurfOraclesBody).update_data(surf_oracles=newer)
        await pilot.pause()
        assert "loading" in painted(app, "#oracle-summary")
        assert app.requests == ["1"]


async def test_refresh_preserves_tree_nodes_collapse_and_table_scroll():
    data = payload()
    data["rows"] += [dict(data["rows"][1], id=str(i)) for i in range(5, 60)]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree, table = app.query_one(Tree), app.query_one(DataTable)
        group, seat = tree.root.children[0], tree.root.children[0].children[0]
        seat.collapse()
        table.scroll_to(y=20, animate=False, immediate=True)
        app.query_one(SurfOraclesBody).update_data(surf_oracles=deepcopy(data) | dict(now_ts=10031))
        await pilot.pause()
        assert tree.root.children[0] is group
        assert group.children[0] is seat and not seat.is_expanded
        assert table.scroll_y == 20
        assert app.requests == []


async def test_filter_search_and_selection_disappearance_clear_old_summary():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfOraclesBody)
        body.cycle_filter()
        await pilot.pause()
        assert app.requests[-1] == "1"
        assert "YES" not in painted(app, "#oracle-summary")
        body.focus_find()
        await pilot.press("f", "c")
        await pilot.pause()
        assert app.query_one(Input).value == "fc"
        assert "No matching requests" in painted(app, "#oracle-summary")
        assert body.close_find()
        await pilot.pause()
        assert app.focused is app.query_one(DataTable)
        assert not body.close_find()
        assert [c.data.digits for c in app.query(NewsHeroCard)][0] == "5"


@pytest.mark.parametrize("depth", [0, 1])
async def test_nested_mouse_space_and_arrows_keep_expander_actions(depth):
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, tree = pilot.app, pilot.app.query_one(Tree)
        branch = tree.root.children[0]
        if depth:
            branch = branch.children[0]
        def arrow():
            for y, strip in enumerate(app.screen._compositor.render_strips()):
                x = 0
                for segment in strip:
                    if segment.style and segment.style.meta.get("node") == branch.id:
                        for glyph in ("▼", "▶"):
                            if glyph in segment.text:
                                return x + segment.text.index(glyph), y
                    x += segment.cell_length
            pytest.fail("missing branch arrow")
        assert branch.is_expanded
        await pilot.click(offset=arrow())
        await pilot.pause()
        assert not branch.is_expanded
        tree.move_cursor(branch)
        await pilot.press("space")
        assert branch.is_expanded
        await pilot.press("left")
        assert not branch.is_expanded
        await pilot.press("right")
        assert branch.is_expanded


async def test_answer_text_click_selects_without_popup_and_panels_are_borderless():
    async with Harness(payload()).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, tree = pilot.app, pilot.app.query_one(Tree)
        branch = tree.root.children[0].children[0]
        leaf = branch.children[0]
        tree.move_cursor(leaf)
        await pilot.pause()
        label = ' '.join(leaf.label.plain.split())
        for y, strip in enumerate(app.screen._compositor.render_strips()):
            if label in strip.text:
                await pilot.click(offset=(strip.text.index(label) + 2, y))
                break
        else:
            pytest.fail('visible answer text required: ' + painted(app, '#oracle-answers'))
        await pilot.pause()
        assert tree.cursor_node is leaf and branch.is_expanded
        assert app.answers == []
        await pilot.press('enter')
        assert app.answers == [leaf.data]
        for selector in ('#oracle-request-panel', '#oracle-detail-panel'):
            assert all(edge[0] == '' for edge in app.query_one(selector).styles.border)


async def test_answer_leaf_posts_exact_record_and_unknown_seat_is_not_guessed():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        tree = pilot.app.query_one(Tree)
        second = tree.root.children[0].children[1]
        second.expand()
        tree.select_node(second.children[-1])
        await pilot.pause()
        assert pilot.app.answers == [data["detail"]["members"][1]]
        assert pilot.app.answers[0] is data["detail"]["members"][1]
        assert "22222222" in painted(pilot.app, "#oracle-answers")


async def test_addresses_are_copyable_linked_by_chain_and_numeric_summary_wraps():
    address = "0x" + "a"*40
    data = payload()
    data["rows"][0]["question"] = "Check " + address
    data["detail"]["question"] = "Check " + address
    data["detail"]["members"][0]["oracle_notes"] = address
    number = "1234567890" * 7 + "98765432"
    data["detail"].update(panel_answer_type="uint256", panel_answer_bool=None, panel_figure=number)
    async with Harness(data).run_test(size=(200, 60)) as pilot:
        await pilot.pause()
        app = pilot.app
        assert address in {row[2] for row in icon_targets(app)}
        assert any(row[2] == "etherscan" and row[4] == address for row in link_targets(app))
        assert number in "".join(painted(app, "#oracle-summary").split())
        assert "⧉" in painted(app, "#oracle-requests")


async def test_stale_and_detail_unavailable_have_independent_read_clocks():
    data = payload() | dict(state="stale", detail_state="unavailable", detail=None)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "stale" not in painted(pilot.app, "#oracle-coverage")
        assert "as of" in painted(pilot.app, "#oracle-coverage")
        assert "unavailable" not in painted(pilot.app, "#oracle-summary")
        assert "YES" not in painted(pilot.app, "#oracle-summary")


async def test_other_filter_chain_and_missing_network_count():
    data = payload()
    data["rows"][-1]["chain_id"] = None
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, body = pilot.app, pilot.app.query_one(SurfOraclesBody)
        assert app.query_one("#hero-oracle-networks", NewsHeroCard).data.digits == "--"
        for _ in range(5):
            body.cycle_filter()
        await pilot.pause()
        assert list(app.query_one(DataTable).rows)[0].value == "4"
        assert len(app.query_one(DataTable).rows) == 1
        body.cycle_filter()
        body.cycle_chain()
        await pilot.pause()
        assert len(app.query_one(DataTable).rows) == 3


@pytest.mark.parametrize("value,expected", [(False, "NO"), (None, "—"), ("false", "—"), (0, "—")])
async def test_consensus_bool_is_strict(value, expected):
    data = payload()
    data["detail"]["panel_answer_bool"] = value
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert expected + " · bool" in painted(pilot.app, "#oracle-summary")


async def test_disappeared_selection_requests_first_visible_and_unknown_age_stays_unknown():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        data["rows"] = data["rows"][1:]
        data["rows"][0]["created_ts"] = data["now_ts"] + 100
        pilot.app.query_one(SurfOraclesBody).update_data(surf_oracles=data)
        await pilot.pause()
        assert pilot.app.requests == ["1"]
        assert "loading" in painted(pilot.app, "#oracle-summary")
        assert " · --" in painted(pilot.app, "#oracle-summary")


async def test_request_detail_identity_mismatch_never_renders_previous_answer():
    data = payload()
    data["detail"]["job_id"] = data["rows"][1]["job_id"]
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert "mismatch" not in painted(pilot.app, "#oracle-summary")
        assert "Question 0 [literal]" in painted(pilot.app, "#oracle-summary")
        assert "YES" not in painted(pilot.app, "#oracle-summary")
        assert not pilot.app.query_one(Tree).root.children


async def test_mutated_members_refresh_preserves_collapse_and_updates_popup_record():
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, tree = pilot.app, pilot.app.query_one(Tree)
        tree.root.children[0].children[0].collapse()
        data["detail"]["members"][0]["oracle_notes"] = "Changed evidence"
        app.query_one(SurfOraclesBody).update_data(surf_oracles=data)
        await pilot.pause()
        seat = tree.root.children[0].children[0]
        assert not seat.is_expanded
        seat.expand()
        await pilot.pause()
        assert "Changed evidence" in painted(app, "#oracle-answers")
        latest = deepcopy(data)
        app.query_one(SurfOraclesBody).update_data(surf_oracles=latest)
        tree.select_node(seat.children[-1])
        await pilot.pause()
        assert app.answers[-1] is latest["detail"]["members"][0]


@pytest.mark.parametrize("chain", [1, 56])
async def test_narrow_tree_address_and_note_keep_copy_target_and_only_known_explorer(chain):
    address = "0x" + "b" * 40
    data = payload()
    data["detail"]["members"][0].update(oracle_notes="Proof " + address, oracle_chain_id=chain,
                                        panel_answer_type="address[]", oracle_seat_answer=address)
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        region = app.query_one("#oracle-answers").region
        targets = [(x, y, value) for x, y, value in icon_targets(app) if region.contains(x, y)]
        assert len(targets) == 2 and all(value == address for _, _, value in targets)
        links = [row for row in link_targets(app) if region.contains(row[0], row[1])]
        assert bool(links) is (chain == 1)
        assert not app.query_one(Tree).show_horizontal_scrollbar


async def test_leaf_mouse_opens_exact_second_attempt_and_responsive_questions_grow():
    data = payload()
    data["detail"]["members"][1]["seat"] = 527
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, tree = pilot.app, pilot.app.query_one(Tree)
        second = tree.root.children[0].children[1]
        second.expand()
        await pilot.pause()
        leaf = second.children[-1]
        found = None
        for y, strip in enumerate(app.screen._compositor.render_strips()):
            x = 0
            for segment in strip:
                if segment.style and segment.style.meta.get("node") == leaf.id and "open full answer" in segment.text:
                    found = (x, y)
                x += segment.cell_length
        assert found is not None
        await pilot.click(offset=found)
        await pilot.pause()
        assert app.answers[-1] is data["detail"]["members"][1]
        before = app.query_one(DataTable).ordered_columns[-1].width
        await pilot.resize_terminal(190, 45)
        await pilot.pause()
        assert app.query_one(DataTable).ordered_columns[-1].width > before


@pytest.mark.parametrize("leaf_index", [0, 1, 2])
async def test_refreshed_member_evidence_keeps_current_leaf_cursor(leaf_index):
    data = payload()
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app, tree = pilot.app, pilot.app.query_one(Tree)
        tree.focus()
        tree.move_cursor(tree.root.children[0].children[0].children[leaf_index])
        before = tree.cursor_node.label.plain
        update = deepcopy(data)
        update["detail"]["members"][1]["oracle_notes"] = "New evidence from other seat"
        app.query_one(SurfOraclesBody).update_data(surf_oracles=update)
        await pilot.pause()
        assert tree.cursor_node is not None
        assert tree.cursor_node.label.plain == before


@pytest.mark.parametrize("members,expected", [(None, "ANSWERS"), ([], "No answer records loaded")])
async def test_unread_members_are_distinct_from_a_known_empty_panel(members, expected):
    data = payload()
    data["detail"]["members"] = members
    async with Harness(data).run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        assert expected in painted(pilot.app, "#oracle-detail-panel")


@pytest.mark.parametrize("width", [110, 149, 170])
@pytest.mark.parametrize("field", ["question", "panel_figure"])
async def test_summary_address_and_copy_icon_wrap_as_one_unit(width, field):
    from maxpane_dashboard.widgets.explorer import parse_open_action
    address = "0x5A0b54D5dc17e0AadC383d2db43B0a0D3E029c4c"
    data = payload()
    data["detail"][field] = "Inspect " + address
    if field == "panel_figure":
        data["detail"]["panel_answer_type"] = "address[]"
    else:
        data["rows"][0]["question"] = data["detail"][field]
    async with Harness(data).run_test(size=(width, 60)) as pilot:
        await pilot.pause()
        app = pilot.app
        region = app.query_one("#oracle-summary").region
        targets = [(x, y, value) for x, y, value in icon_targets(app) if region.contains(x, y)]
        assert len(targets) == 1 and targets[0][2] == address
        x, y, _ = targets[0]
        preceding = app.screen.get_style_at(x - 2, y)
        parsed = parse_open_action(preceding.meta.get("@click"))
        assert parsed is not None and parsed[2] == address
        assert preceding.link.endswith(address)
        row = app.screen._compositor.render_strips()[y].crop(region.x, region.right).text
        import re
        assert re.search(r"0x[0-9a-fA-F]+(?:…[0-9a-fA-F]+)? ⧉", row), row
        assert not app.query_one("#oracle-detail-panel").show_horizontal_scrollbar

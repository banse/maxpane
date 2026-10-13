"""Offline ORACLES preview: request selection and nested answer inspection."""
from collections import Counter

import pytest
from textual.widgets import DataTable, Tree

from scripts.surf_oracles_demo import MOCK_REQUESTS, SurfOraclesDemo
from maxpane_dashboard.screens.oracle_answer import OracleAnswerScreen
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    async def refuse(*args, **kwargs):
        raise AssertionError("mockup must not use network or clipboard")

    def refuse_state(*args, **kwargs):
        raise AssertionError("mockup must not access user configuration or cache")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)
    monkeypatch.setattr("maxpane_dashboard.clipboard.copy_text", refuse)
    for target in ("maxpane_dashboard.config._read_config", "maxpane_dashboard.config._write_config",
                   "maxpane_dashboard.data.surf_cache.SurfCache.load", "maxpane_dashboard.data.surf_cache.SurfCache.save"):
        monkeypatch.setattr(target, refuse_state)


def test_mock_counts_and_answer_groups_are_coherent():
    assert len(MOCK_REQUESTS) == 100
    assert Counter(row["status"] for row in MOCK_REQUESTS) == {
        "assessing": 7, "attested": 86, "disagreed": 5, "blocked": 2}
    assert len({row["chain"] for row in MOCK_REQUESTS}) == 3
    selected = MOCK_REQUESTS[1]
    assert len(selected["members"]) == selected["panel_size"] == 17
    assert Counter(row["panel_state"] for row in selected["members"]) == {"agreed": 13, "outvoted": 4}


async def test_six_equal_rack_cards_and_split_detail_fit_owner_size():
    async with SurfOraclesDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "REQUESTS", "ASSESSING", "ATTESTED", "NO QUORUM", "BLOCKED", "NETWORKS"]
        assert [card.data.digits for card in cards] == ["100", "7", "86", "5", "2", "3"]
        assert {card.region.height for card in cards} == {9}
        assert len({card.region.y for card in cards}) == 1
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        for card in cards:
            text = painted(app, card)
            assert card.data.title in text and card.data.heading in text
            assert all(corner in text for corner in "┌┐└┘")
        left, right = app.query_one("#requests-panel"), app.query_one("#detail-panel")
        assert left.region.width >= 1.8 * right.region.width
        assert cards[0].region.bottom < left.region.y == right.region.y
        assert left.region.right < right.region.x
        assert left.region.bottom == right.region.bottom < app.query_one("#demo-footer").region.y
        assert "MOCK DATA" in painted(app)
        assert "100 loaded" in painted(app, left)
        assert "Is the collection floor price above the requested threshold?" in painted(app, left)
        assert not app.query_one(DataTable).max_scroll_x
        assert "YES" in painted(app, right) and "13 agreed" in painted(app, right)
        assert "17 seats" in painted(app, right) and "seat 527" in painted(app, right)
        assert not app.query_one("#viewport").max_scroll_x
        assert not app.query_one("#viewport").max_scroll_y


async def test_request_selection_and_no_quorum_do_not_imply_accepted_answer():
    async with SurfOraclesDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        table = pilot.app.query_one(DataTable)
        table.focus()
        await pilot.press("down")
        await pilot.pause()
        detail = painted(pilot.app, pilot.app.query_one("#detail-panel"))
        assert "NO QUORUM" in detail and "closed" in detail
        assert "11 agreed" in detail and "No attested answer" in detail
        await pilot.press("up", "up")
        await pilot.pause()
        detail = painted(pilot.app, pilot.app.query_one("#detail-panel"))
        assert "ASSESSING" in detail and "Awaiting agreement" in detail
        assert "AGREED · 13" not in detail
        assert "— agreed" in detail
        # A click on the blocked request updates the same pane, not an old answer.
        await pilot.click("#requests", offset=(9, 5))
        await pilot.pause()
        detail = painted(pilot.app, pilot.app.query_one("#detail-panel"))
        assert "BLOCKED" in detail and "No answer records loaded" in detail
        assert "seat 527" not in detail and "YES" not in detail
        table.focus()
        await pilot.press("up", "up", "up", "enter")
        await pilot.pause()
        assert pilot.app.focused is pilot.app.query_one(Tree)
        assert "YES" in painted(pilot.app, pilot.app.query_one("#detail-panel"))


async def test_nested_mouse_toggle_and_existing_answer_popup():
    async with SurfOraclesDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        tree = app.query_one(Tree)
        group = tree.root.children[0]
        seat = group.children[0]
        assert group.is_expanded and seat.is_expanded

        async def click_expander(node):
            for y, strip in enumerate(app.screen._compositor.render_strips()):
                x = 0
                for segment in strip:
                    meta = segment.style.meta if segment.style else {}
                    if meta.get("toggle") and meta.get("line") == node.line and tree.region.contains(x, y):
                        await pilot.click(offset=(x, y))
                        await pilot.pause()
                        return
                    x += segment.cell_length
            pytest.fail("nested expander did not reach compositor")

        await click_expander(seat)
        assert not seat.is_expanded
        await click_expander(seat)
        assert seat.is_expanded
        tree.move_cursor(seat)
        tree.focus()
        await pilot.press("space")
        await pilot.pause()
        assert not seat.is_expanded
        await pilot.press("space")
        await pilot.pause()
        assert seat.is_expanded
        tree.move_cursor(seat.children[-1])
        tree.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, OracleAnswerScreen)
        assert app.screen.row["submission_hash"] == MOCK_REQUESTS[1]["members"][0]["submission_hash"]
        assert "QUESTION" in painted(app) and "NOTES" in painted(app)
        assert "this seat" in painted(app) and "YES" in painted(app)
        await pilot.press("escape")
        await pilot.pause()
        assert "REQUESTS" in painted(app) and "seat 527" in painted(app)


async def test_filters_empty_result_and_resize_recover():
    async with SurfOraclesDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        await pilot.press("f")
        await pilot.pause()
        assert app.query_one(DataTable).row_count == 7
        await pilot.press("/")
        await pilot.press(*"zzzz")
        await pilot.pause()
        assert app.query_one(DataTable).row_count == 0
        assert "No matching requests" in painted(app)
        await pilot.press("escape")
        await pilot.pause()
        assert app.query_one(DataTable).row_count == 7
        await pilot.resize_terminal(100, 28)
        await pilot.pause()
        view = app.query_one("#viewport")
        assert view.max_scroll_x > 0 and view.max_scroll_y > 0
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not view.max_scroll_x and not view.max_scroll_y
        assert "SELECTED REQUEST" in painted(app)
        question_width = app.query_one(DataTable).ordered_columns[-1].width
        await pilot.resize_terminal(180, 45)
        await pilot.pause()
        assert app.query_one(DataTable).ordered_columns[-1].width > question_width
        assert not app.query_one(DataTable).max_scroll_x

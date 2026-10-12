"""Selected LEADERBOARD mock through the real compositor, with I/O refused."""
import pytest
from rich.color import Color
from textual.widgets import DataTable

from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from scripts.surf_leaderboard_hero_demo import MOCK_CARDS, MOCK_DATA, SurfLeaderboardHeroDemo
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    async def refuse(*args, **kwargs):
        raise AssertionError("the leaderboard mock must not use network or clipboard")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)
    monkeypatch.setattr("maxpane_dashboard.clipboard.copy_text", refuse)

    def refuse_state(*args, **kwargs):
        raise AssertionError("the leaderboard mock must not read or write user state")

    monkeypatch.setattr("maxpane_dashboard.config._read_config", refuse_state)
    monkeypatch.setattr("maxpane_dashboard.config._write_config", refuse_state)
    monkeypatch.setattr("maxpane_dashboard.data.surf_cache.SurfCache.load", refuse_state)
    monkeypatch.setattr("maxpane_dashboard.data.surf_cache.SurfCache.save", refuse_state)


async def test_leaderboard_heroes_fit_and_paint_selected_content_at_owner_size():
    async with SurfLeaderboardHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "TOP SEAT", "RECORDED", "ACCEPT RATE", "OUTCOMES", "WORKERS", "EFFORT"]
        assert {card.region.height for card in cards} == {9}
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        assert len({card.region.y for card in cards}) == 1
        assert all(a.region.right < b.region.x for a, b in zip(cards, cards[1:]))
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        body = app.query_one("#leaderboard-body")
        assert body.region.y > cards[0].region.bottom
        assert body.region.bottom < app.query_one("#demo-footer").region.y
        viewport = app.query_one("#viewport")
        assert not viewport.max_scroll_x and not viewport.max_scroll_y
        for card in cards:
            output = painted(app, card)
            assert f"⊙ {card.data.title}" in output
            assert card.data.heading in output and card.data.footer in output
            assert all(corner in output for corner in "┌┐└┘")
            if card.data.subtitle:
                assert card.data.subtitle in output
        for index, label, value in (
            (3, "rejected", "2k"), (3, "failed", "1k"), (3, "pending", "1k"),
            (4, "live", "966"), (4, "working", "24"), (4, "capacity", "2,880"),
            (5, "receipts", "18.4k"), (5, "turns", "580k"), (5, "hours", "18k"),
        ):
            assert any(label in line and value in line for line in painted(app, cards[index]).splitlines())
        # The selected values must reach the compositor as large digit glyphs.
        assert "╭─╴╶─╮╶─┐" in painted(app, cards[0])  # 527
        recorded = painted(app, cards[1])
        assert " SEATS " in recorded
        assert "╶╮ ╭─╮╶─╮╷ ╷" in recorded  # 1024
        assert any("└" in line and "100k attempts" in line and "┘" in line
                   for line in recorded.splitlines())
        assert "╰─┤├─╮ │ │" in painted(app, cards[2])  # 96.0 middle row
        strips = app.screen._compositor.render_strips()
        inset = next(strip.crop(cards[1].region.x, cards[1].region.right)
                     for strip in strips[cards[1].region.y:cards[1].region.bottom] if " SEATS " in strip.text)
        edge = next(segment for segment in inset if "┌" in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()["background"])
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])
        for widget_id in ("#demo-title", "#demo-footer"):
            assert "MOCK DATA" in painted(app, app.query_one(widget_id))
        text = painted(app, body)
        for word in ("LEADERBOARD", "FLEET", "#527", "4180", "RECEIPTS", "580,000", "18,000 h"):
            assert word in text
        assert "Loading" not in text and "unavailable" not in text
        table = app.query_one(DataTable)
        assert table.row_count == 1024 and table.max_scroll_x == 0
        table.move_cursor(row=1023, scroll=True)
        await pilot.pause()
        assert f"#{MOCK_DATA['swarm_board_rows'][-1]['token_id']}" in painted(app, table)


async def test_leaderboard_mock_narrow_scroll_and_resize_recovery():
    async with SurfLeaderboardHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = pilot.app.query_one("#viewport")
        assert viewport.max_scroll_x > 0 and viewport.max_scroll_y > 0
        assert len(pilot.app.query(NewsHeroCard)) == 6
        viewport.scroll_to(x=viewport.max_scroll_x, y=0, animate=False)
        await pilot.pause()
        assert "EFFORT" in painted(pilot.app) and "CONTRIBUTORS" in painted(pilot.app)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.max_scroll_x and not viewport.max_scroll_y
        assert "TOP SEAT" in painted(pilot.app) and "EFFORT" in painted(pilot.app)


def test_leaderboard_mock_totals_and_rank_are_coherent():
    summary, rows = MOCK_DATA["swarm_board_summary"], MOCK_DATA["swarm_board_rows"]
    assert len({row["token_id"] for row in rows}) == len(rows) == summary["seats"] == 1024
    for key, total in (("attempts", 100000), ("accepted", 96000), ("rejected", 2000), ("failed", 1000), ("pending", 1000)):
        assert sum(row[key] for row in rows) == summary[key] == total
    for row in rows:
        assert row["attempts"] == sum(row[key] for key in ("accepted", "rejected", "failed", "pending"))
        assert row["accept_rate"] == pytest.approx(row["accepted"] / row["attempts"])
    assert rows == sorted(rows, key=lambda row: (-row["accepted"], -row["accept_rate"], row["token_id"]))
    assert [row["rank"] for row in rows] == list(range(1, 1025))
    assert rows[0]["token_id"] == 527 and rows[0]["accepted"] == 4180
    assert sum(row["live_state"] != "offline" for row in rows) == summary["live"] == 966
    assert sum(row["working"] for row in rows) == summary["working"] == 24
    concurrency = MOCK_DATA["swarm_fleet"]["concurrency"]
    assert sum(row["count"] for row in concurrency) == summary["live"]
    assert sum(int(row["value"]) * row["count"] for row in concurrency) == summary["capacity"] == 2880
    assert summary["receipts"] == summary["receipt_attempts"] == 18400
    assert summary["turns"] == 580000 and summary["wall_clock_ms"] == 18000 * 3600000
    with pytest.raises(ValueError, match="six"):
        SurfLeaderboardHeroDemo(cards=MOCK_CARDS[:-1])

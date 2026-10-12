"""PROTOCOL proposal 1 through the real Textual compositor, without I/O."""
import pytest
from rich.color import Color

from scripts.surf_protocol_hero_demo import MOCK_CARDS, MOCK_DATA, SurfProtocolHeroDemo
from maxpane_dashboard.widgets.surf.news_hero import NewsHeroCard
from tests.screens.test_surf_news_hero_demo import painted


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))

    async def refuse(*args, **kwargs):
        raise AssertionError("the protocol mock must not use network or clipboard")

    monkeypatch.setattr("httpx.AsyncClient.send", refuse)
    monkeypatch.setattr("maxpane_dashboard.clipboard.copy_text", refuse)


async def test_protocol_heroes_fit_and_paint_selected_content_at_owner_size():
    async with SurfProtocolHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        app = pilot.app
        cards = list(app.query(NewsHeroCard))
        assert [card.data.title for card in cards] == [
            "TOTALS", "INVENTORY", "REWARD SPLIT", "UNSETTLED", "DELIVERY", "CHECKS"]
        assert {card.region.height for card in cards} == {9}
        assert max(card.region.width for card in cards) - min(card.region.width for card in cards) <= 1
        assert len({card.region.y for card in cards}) == 1
        assert all(a.region.right < b.region.x for a, b in zip(cards, cards[1:]))
        assert cards[0].region.x >= 1 and cards[-1].region.right < 149
        assert app.query_one("#protocol-body").region.y > cards[0].region.bottom
        viewport = app.query_one("#viewport")
        assert not viewport.max_scroll_x
        for card in cards:
            output = painted(app, card)
            assert f"⊙ {card.data.title}" in output
            assert card.data.heading in output and card.data.footer in output
            assert all(corner in output for corner in "┌┐└┘")
        for index, label, value in (
            (0, "burned", "33.3k"), (0, "rewarded", "5.9k"), (0, "fees", "3.8k"),
            (1, "cap", "840k"), (1, "reserve", "835k"), (1, "headroom", "5k"),
            (2, "staking", "30%"), (2, "nodes", "30%"), (2, "bonding*", "40%"),
            (3, "burn", "120"), (3, "rewards", "21"),
            (4, "queued", "7.44k"), (4, "ready", "250"), (4, "cap", "1.2k/d"),
        ):
            assert any(label in line and value in line for line in painted(app, cards[index]).splitlines())
        assert "* DERIVED" in painted(app, cards[2])
        for word in ("reconciled", "drift 0.0 bps", "distributor"):
            assert word in painted(app, cards[5])
        strips = app.screen._compositor.render_strips()
        inset = next(strip.crop(cards[0].region.x, cards[0].region.right)
                     for strip in strips if " IMD " in strip.text)
        edge = next(segment for segment in inset if "┌" in segment.text)
        assert edge.style.bgcolor == Color.parse(app.get_css_variables()["background"])
        assert edge.style.color == Color.parse(app.get_css_variables()["accent"])
        assert "MOCK DATA" in painted(app, app.query_one("#demo-title"))
        assert "MOCK DATA" in painted(app, app.query_one("#demo-footer"))
        body = painted(app, app.query_one("#protocol-body"))
        for word in ("THE SPLIT", "THE RATCHET", "HATCHES", "sIMD VAULT",
                     "33,300", "reconciled", "840.0K", "835.0K", "7.964000"):
            assert word in body
        assert "Loading" not in body
        viewport.scroll_to(y=viewport.max_scroll_y, animate=False)
        await pilot.pause()
        assert "drip rate caps delivery, not earnings" in painted(app)


async def test_protocol_mock_narrow_scroll_and_resize_recovery():
    async with SurfProtocolHeroDemo().run_test(size=(149, 45)) as pilot:
        await pilot.pause()
        await pilot.resize_terminal(100, 30)
        await pilot.pause()
        viewport = pilot.app.query_one("#viewport")
        assert viewport.max_scroll_x > 0 and viewport.max_scroll_y > 0
        assert len(pilot.app.query(NewsHeroCard)) == 6
        viewport.scroll_to(x=viewport.max_scroll_x, y=0, animate=False)
        await pilot.pause()
        assert "CHECKS" in painted(pilot.app) and "ACCOUNTING" in painted(pilot.app)
        await pilot.resize_terminal(149, 45)
        await pilot.pause()
        assert not viewport.max_scroll_x
        assert "TOTALS" in painted(pilot.app) and "CHECKS" in painted(pilot.app)


def test_protocol_mock_accounting_is_coherent():
    data = MOCK_DATA
    assert data["pool4_inventory_cap"] - data["pool4_tokens_in_pool"] == data["pool4_cap_headroom"]
    reward = data["pool4_total_rewarded"]
    assert reward / (reward + data["pool4_total_burned"]) * 10000 == pytest.approx(data["pool4_reward_share_bps"])
    assert sum(data[f"pool4_distributor_{leg}_bps"] for leg in ("staking", "nodes", "bonding")) == 10000
    assert sum(data[f"pool4_distributor_{leg}_earned"] for leg in ("staking", "nodes", "bonding")) == pytest.approx(reward)
    assert data["pool4_drippable"] <= data["pool4_backlog_imd"]
    assert data["pool4_backlog_imd"] / data["pool4_drip_per_day"] == data["pool4_backlog_days"]
    assert data["pool4_vault_assets"] / data["pool4_vault_shares"] == pytest.approx(data["pool4_share_price"])
    with pytest.raises(ValueError, match="six"):
        SurfProtocolHeroDemo(cards=MOCK_CARDS[:-1])

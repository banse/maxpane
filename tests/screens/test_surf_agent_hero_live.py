"""AGENT rack integration through the production screen dispatch and compositor."""
import pytest
from textual.widgets import DataTable
from maxpane_dashboard.widgets.surf.agent_rack_hero import SurfSwarmAgentRackHero
from maxpane_dashboard.widgets.surf import SurfSwarmAgentHero, SurfSwarmSeatCards, SurfSwarmSeatRecord
from maxpane_dashboard.widgets.surf.swarm_record_filter import SurfRecordFilterEditor
from tests.screens.test_surf_screen import _surf_app, _frozen_payload, _region_text, _ThemedHarness
from tests.widgets.test_surf_agent_rack_hero import payload


@pytest.mark.parametrize('width', [132, 149])
async def test_agent_rack_replaces_both_old_rows_and_preserves_record_filter(width):
    data = _frozen_payload(surf_agent_hero=payload())
    data['surf_agent_hero']['status']['current_action'] = 'implementing'
    async with _surf_app(payload=data).run_test(size=(width, 45)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.press("a")
        hero = screen.query_one(SurfSwarmAgentRackHero)
        assert hero.display and hero.region.height == 19
        assert sum(node.display for node in screen.query(".surf-hero")) == 1
        assert not list(screen.query(SurfSwarmAgentHero))
        assert not list(screen.query(SurfSwarmSeatCards))
        cards = list(hero.children)
        assert len(cards) == 12 and {card.region.height for card in cards} == {9}
        text = _region_text(pilot.app, hero)
        for expected in ("AGENT", "SEAT", "96%", "ERC-8004 #8127", "$120.82", "example.eth ⧉",
                         "EARNINGS", "4 new", "RESEARCH", "ORACLE"):
            assert expected in text
        assert 'implementing' in _region_text(pilot.app, hero.query_one('#hero-status'))
        assert "paid " not in _region_text(pilot.app, hero.query_one('#hero-rewards'))
        for key in ('owner', 'models', 'nodes', 'runtime', 'rewards'):
            assert not str(hero.query_one('#hero-' + key).border_subtitle)
        record = screen.query_one(SurfSwarmSeatRecord)
        assert record.display and record.region.y == hero.region.bottom + 1
        title = record.query_one('.panel-title')
        table = record.query_one(DataTable)
        assert title.region.y == record.region.y
        assert title.region.y == 22
        assert table.region.y == 23
        assert table.region.height == 20
        assert table.region.y == title.region.bottom
        title_gap = screen._compositor.render_strips()[title.region.y - 1].crop(record.region.x, record.region.right)
        assert not title_gap.text.strip()
        assert table.region.bottom == record.region.bottom - 1
        gap = screen._compositor.render_strips()[table.region.bottom].crop(record.region.x, record.region.right)
        assert not gap.text.strip()
        await pilot.press("f")
        assert not record.display and screen.query_one(SurfRecordFilterEditor).display
        assert _region_text(pilot.app, hero) == text
        await pilot.press("escape")
        assert record.display and not screen.query_one(SurfRecordFilterEditor).display
        changed = payload()
        changed['status'].update(current_action='testing')
        screen._data_manager._payload = dict(data, surf_agent_hero=changed)
        await screen._do_refresh()
        await pilot.pause()
        assert 'testing' in _region_text(pilot.app, hero.query_one('#hero-status'))
        changed['status'].update(live_state='idle', working=0, meter_state='idle')
        await screen._do_refresh()
        await pilot.pause()
        assert 'testing' not in _region_text(pilot.app, hero.query_one('#hero-status'))
        assert 'ready' in _region_text(pilot.app, hero.query_one('#hero-seat'))
        changed = payload()
        changed["seat"].update(token_id=7, state="pending", agent_id=None)
        changed["owner"].update(state="pending")
        screen._data_manager._payload = dict(data, surf_agent_hero=changed)
        await screen._do_refresh()
        await pilot.pause()
        assert "ERC-8004 #--" in _region_text(pilot.app, hero.query_one("#hero-seat"))
        assert hero.query_one('#hero-seat').data.digits == '7'
        assert "example.eth" not in _region_text(pilot.app, hero.query_one("#hero-owner"))
        assert "96%" in _region_text(pilot.app, hero)
        await pilot.press("escape")
        assert not hero.display


@pytest.mark.parametrize("themed", [False, True])
async def test_record_title_sits_above_table_with_gap_before_widget(monkeypatch, themed):
    if not themed:
        monkeypatch.setattr(_ThemedHarness, "CSS_PATH", [])
    data = _frozen_payload(surf_agent_hero=payload())
    async with _surf_app(payload=data).run_test(size=(149, 45)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.press("a")
        record = screen.query_one(SurfSwarmSeatRecord)
        table = record.query_one(DataTable)
        title = record.query_one('.panel-title')
        for width, height, table_height in ((149, 45, 20), (134, 29, 4), (134, 28, 4), (149, 45, 20)):
            await pilot.resize_terminal(width, height)
            await pilot.pause()
            assert title.region.y == 22
            assert (table.region.y, table.region.height, table.region.bottom) == (23, table_height, 23 + table_height)
            rows = screen._compositor.render_strips()
            assert not rows[21].text.strip()
            assert "RECORD" in rows[22].text
            assert "when" in rows[23].text
        before = table.region
        await pilot.press("f", "escape")
        assert record.display and table.region == before

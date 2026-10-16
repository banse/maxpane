"""Native oracle layout measurement; unbounded questions/answers scroll locally."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from maxpane_dashboard.data.surf_oracles import decode_detail, decode_page, project_detail
from maxpane_dashboard.screens.surf import (
    SurfScreen, SURF_ORACLES_FULL_LAYOUT_COLUMNS, SURF_ORACLES_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf.oracles import SurfOraclesHero
from tests.screens.test_surf_screen import (
    _FakeManager, _ThemedHarness, _frozen_payload, _region_text, _screen_text,
)
from tests.screens._sweeps import boundary_set


def oracle_payload(kind="capture"):
    raw = json.loads(Path("tests/fixtures/surf/oracles/captured.json").read_text())
    now = raw["read_ts"]
    rows, partial = decode_page(raw["requests"], now=now)
    detail = project_detail(decode_detail(raw["details"][rows[0]["id"]], rows[0], read_ts=now))
    data = dict(rows=rows, partial=partial, state="ok", read_ts=now, now_ts=now,
                selected_id=rows[0]["id"], detail=detail, detail_state="ok", detail_read_ts=now)
    if kind == "complete":
        data["partial"] = False
    elif kind == "empty":
        data.update(rows=[], partial=False, selected_id=None, detail=None)
    elif kind == "unavailable":
        data.update(rows=None, read_ts=None, state="unavailable", selected_id=None, detail=None)
    elif kind == "stale":
        data.update(state="stale", detail_state="stale")
    elif kind == "stress":
        rows[0]["question"] = detail["question"] = "[bold] 部署 contracts and assess results " * 30
    return _frozen_payload(surf_oracles=data)


async def _render(payload, size):
    screen = SurfScreen(_FakeManager(payload))
    screen.start_refresh = Mock()
    screen.open_mode("oracles")
    async with _ThemedHarness(screen).run_test(size=size) as pilot:
        await screen._do_refresh()
        await pilot.pause()
        cards = list(screen.query_one(SurfOraclesHero).children)
        missing = []
        for card in cards:
            text = _region_text(pilot.app, card)
            expected = [card.data.title, card.data.heading, card.data.subtitle]
            missing.extend(f"{card.id}:{word}" for word in expected if word not in text)
        body = screen.query_one("#surf-oracles-body")
        panels = [screen.query_one("#oracle-request-panel"), screen.query_one("#oracle-detail-panel")]
        table = screen.query_one("#oracle-requests")
        status = screen.query_one(StatusBar)
        return dict(missing=missing,
                    marked_cards=[card.id for card in cards if "‹" in _region_text(pilot.app, card)],
                    overflow=[p.id for p in panels if p.region.right > body.region.right or p.region.bottom > body.region.bottom],
                    status_whole=status.region.bottom <= size[1] and "esc back" in _region_text(pilot.app, status),
                    taller="‹ taller" in _region_text(pilot.app, screen.query_one("#title-bar")),
                    widths=[c.region.width for c in cards], heights=[c.region.height for c in cards],
                    panel_widths=[p.region.width for p in panels],
                    question_width=table.ordered_columns[-1].width,
                    table_headers=all(c.label.plain in _region_text(pilot.app, table) for c in table.ordered_columns),
                    body_bottom=body.region.bottom, status_top=status.region.y,
                    text=_screen_text(pilot.app))


@pytest.mark.parametrize("kind", ["capture", "complete", "stress", "empty", "stale", "unavailable"])
@pytest.mark.parametrize("size", [(149, 45), (SURF_ORACLES_FULL_LAYOUT_COLUMNS, SURF_ORACLES_FULL_LAYOUT_ROWS)])
async def test_oracles_fixed_chrome_at_owner_size_and_pin(kind, size):
    result = await _render(oracle_payload(kind), size)
    assert not result["missing"] and not result["overflow"], result
    assert not result["taller"] and result["status_whole"] and result["table_headers"]
    assert result["panel_widths"][0] > result["panel_widths"][1] * 1.8
    assert result["question_width"] >= 48
    assert max(result["widths"]) - min(result["widths"]) <= 1
    assert set(result["heights"]) == {9}
    assert result["body_bottom"] < result["status_top"]


@pytest.mark.sweep
async def test_oracles_width_pin_is_bound_by_requests_inner_caption():
    pin = SURF_ORACLES_FULL_LAYOUT_COLUMNS
    for width in boundary_set(pin, 110, 149):
        result = await _render(oracle_payload("complete"), (width, 45))
        assert bool(result["missing"]) == (width < pin), result
        assert {word.split(":")[0] for word in result["missing"]} <= set(result["marked_cards"])
        if width == pin - 1:
            assert result["missing"] == ["hero-oracle-requests:request history"]
        if width >= pin:
            assert not result["marked_cards"] and result["table_headers"]


@pytest.mark.sweep
async def test_oracles_height_pin_is_bound_by_child_panels():
    below = await _render(oracle_payload(), (149, SURF_ORACLES_FULL_LAYOUT_ROWS - 1))
    whole = await _render(oracle_payload(), (149, SURF_ORACLES_FULL_LAYOUT_ROWS))
    assert below["taller"] and not whole["taller"]
    assert below["overflow"] and not whole["overflow"]
    assert not below["missing"] and below["status_whole"]

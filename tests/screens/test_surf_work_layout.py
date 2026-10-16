"""In-situ WORK measurement: fixed chrome must fit; work/prose scroll inside."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from maxpane_dashboard.data.surf_work import project, snapshot
from maxpane_dashboard.screens.surf import (
    SurfScreen, SURF_WORK_FULL_LAYOUT_COLUMNS, SURF_WORK_FULL_LAYOUT_ROWS,
)
from maxpane_dashboard.widgets.status_bar import StatusBar
from maxpane_dashboard.widgets.surf.work import SurfWorkHero
from tests.screens.test_surf_screen import (
    _FakeManager, _ThemedHarness, _frozen_payload, _region_text, _screen_text,
)
from tests.screens._sweeps import boundary_set


def work_payload(kind="capture"):
    raw = json.loads(Path("tests/fixtures/surf/work/captured.json").read_text())
    work = project(snapshot(raw["jobs"], raw["workflows"],
                            {row["id"]: row for row in raw["details"]},
                            read_ts=raw["read_ts"]), now=raw["read_ts"])
    if kind == "empty":
        work = project(snapshot([], [], {}, read_ts=raw["read_ts"]), now=raw["read_ts"])
    elif kind == "unavailable":
        work = project(None, now=raw["read_ts"])
    elif kind == "stale":
        work["state"] = "stale"
    elif kind == "stress":
        work["summary"] = dict.fromkeys(work["summary"], 100)
        work["jobs"][0]["objective"] = "[bold] 部署 contracts and review dependencies " * 30
    return _frozen_payload(surf_work=work)


async def _render(payload, size):
    screen = SurfScreen(_FakeManager(payload))
    screen.start_refresh = Mock()
    screen.open_mode("work")
    async with _ThemedHarness(screen).run_test(size=size) as pilot:
        await screen._do_refresh()
        await pilot.pause()
        cards = list(screen.query_one(SurfWorkHero).children)
        missing = []
        for card in cards:
            text = _region_text(pilot.app, card)
            expected = [card.data.title, card.data.heading, card.data.subtitle]
            missing.extend(f"{card.id}:{word}" for word in expected if word not in text)
            assert "stale" not in text and "unavailable" not in text
        status = screen.query_one(StatusBar)
        body = screen.query_one("#surf-work-body")
        panels = [screen.query_one("#work-tree-panel"), screen.query_one("#work-detail-panel")]
        overflow = [p.id for p in panels if p.region.right > body.region.right or p.region.bottom > body.region.bottom]
        return {
            "missing": missing, "overflow": overflow,
            "marked_cards": [card.id for card in cards if "‹" in _region_text(pilot.app, card)],
            "status_whole": status.region.bottom <= size[1] and "esc back" in _region_text(pilot.app, status),
            "taller": "‹ taller" in _region_text(pilot.app, screen.query_one("#title-bar")),
            "widths": [c.region.width for c in cards],
            "panel_widths": [p.region.width for p in panels],
            "heights": [c.region.height for c in cards],
            "body_bottom": body.region.bottom, "status_top": status.region.y,
            "text": _screen_text(pilot.app),
        }


async def test_short_terminal_keeps_heroes_visible_and_marks_body_scroll():
    result = await _render(work_payload(), (149, 28))
    assert result["taller"]
    assert not result["missing"]
    assert result["status_whole"]


@pytest.mark.sweep
@pytest.mark.parametrize("kind", ["capture", "stress", "empty", "unavailable", "stale"])
@pytest.mark.parametrize("size", [(SURF_WORK_FULL_LAYOUT_COLUMNS, SURF_WORK_FULL_LAYOUT_ROWS), (149, 45)])
async def test_work_fixed_chrome_fits_at_pin_and_owner_size(kind, size):
    result = await _render(work_payload(kind), size)
    assert not result["missing"] and not result["overflow"], result
    assert not result["taller"] and result["status_whole"]
    assert max(result["widths"]) - min(result["widths"]) <= 1
    assert abs(result["panel_widths"][0] - result["panel_widths"][1]) <= 1
    assert set(result["heights"]) == {9}
    assert result["body_bottom"] < result["status_top"]


@pytest.mark.sweep
async def test_work_width_pin_is_bound_by_blocked_inner_caption():
    pin = SURF_WORK_FULL_LAYOUT_COLUMNS
    for width in boundary_set(pin, 110, 149):
        result = await _render(work_payload(), (width, 45))
        assert bool(result["missing"]) == (width < pin), result
        assert {word.split(":")[0] for word in result["missing"]} <= set(result["marked_cards"])
        if width == pin - 1:
            assert result["missing"] == ["hero-work-blocked:needs attention"]
        if width >= pin:
            assert not result["marked_cards"]


@pytest.mark.sweep
async def test_work_row_pin_is_bound_by_panel_floors():
    pin = SURF_WORK_FULL_LAYOUT_ROWS
    below = await _render(work_payload(), (149, pin - 1))
    whole = await _render(work_payload(), (149, pin))
    assert set(below["overflow"]) == {"work-tree-panel", "work-detail-panel"}
    assert below["taller"] and not whole["taller"]
    assert not whole["overflow"]


def test_work_body_css_copies_agree():
    from tests.screens.test_surf_screen import _css_rules, _surf_stylesheet_block
    selector = "#surf-work-body"
    assert _css_rules(SurfScreen.DEFAULT_CSS)[selector] == _css_rules(_surf_stylesheet_block())[selector]

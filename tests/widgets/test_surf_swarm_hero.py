"""The swarm hero -- six boxes on ``panels.HeroRow`` (WP5, on screen since WP7).

Every assertion is against composited output (``render_strips()``), never
the content string. The harness gives the boxes the geometry the stylesheet
does (``width: 1fr``, ``text-wrap: nowrap``): the box class itself states
none (``rules/widgets.md``, ``HeroBoxBase``).
"""

from __future__ import annotations

import inspect

from textual.app import App

from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.surf.swarm_hero import (
    BOX_IDS,
    SurfSwarmHeroBox,
    SurfSwarmHero,
)

#: A healthy swarm, the corpus's own shape (``/health`` on 2026-09-21).
KW = {
    "swarm_agents_online": 27,
    "swarm_agents_enrolled": 32,
    "swarm_working_now": 2,
    "swarm_accepted_today": 1177,
    "swarm_queue_total": 68,
    "swarm_breaker": {"tripped": False, "detail": None},
    "swarm_services_up": {"verifier": True, "publisher": True, "deployer": True},
    "swarm_health_status": "ok",
}

#: Room for the full explicit mixed service line (46 cells); production
#: pin clipping is separately checked in the real screen harness.
SIZE = (360, 8)

AGENTS, WORKING, ACCEPTED, LAUNCHES, WORKFLOWS, SITES = BOX_IDS


class _A(App):
    #: The stylesheet's stand-in: geometry only, no colours.
    CSS = """
    SurfSwarmHero > SurfSwarmHeroBox {
        width: 1fr;
        height: 5;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def compose(self):
        yield SurfSwarmHero()


async def _render(polls: list[dict], size=SIZE):
    """Feed every poll in order; return ``(pilot.app, rows)`` after the last."""
    app = _A()
    async with app.run_test(size=size) as pilot:
        hero = pilot.app.query_one(SurfSwarmHero)
        for poll in polls:
            hero.update_data(**poll)
            await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        regions = {
            box_id: pilot.app.query_one(f"#{box_id}").region for box_id in BOX_IDS
        }
        styles = {}
        for box_id, region in regions.items():
            for y in range(region.y, region.y + region.height):
                for x in range(region.x, region.x + region.width):
                    styles[(x, y)] = pilot.app.screen.get_style_at(x, y)
    return rows, regions, styles


def _slice(rows, region) -> list[str]:
    return [
        rows[y][region.x: region.x + region.width].rstrip()
        for y in range(region.y, min(region.y + region.height, len(rows)))
    ]


async def _box(box_id: str, **kwargs) -> str:
    rows, regions, _styles = await _render([{**KW, **kwargs}])
    return "\n".join(_slice(rows, regions[box_id]))


# -- contract ---------------------------------------------------------------


def test_update_data_takes_exactly_the_frozen_keys_in_order():
    expected = SWARM_WIDGET_SIGNATURES["SurfSwarmHero"]
    params = inspect.signature(SurfSwarmHero.update_data).parameters
    named = tuple(
        name for name, p in params.items()
        if name != "self" and p.kind is not p.VAR_KEYWORD
    )
    assert named == expected
    assert set(named) == set(expected)
    assert any(p.kind is p.VAR_KEYWORD for p in params.values()), (
        "the screen splats the whole flat dict; **_kwargs is mandatory"
    )


async def test_no_args_renders_unavailable_in_every_box_and_never_loading():
    rows, regions, _ = await _render([{}])
    for box_id in BOX_IDS:
        text = "\n".join(_slice(rows, regions[box_id]))
        assert "unavailable" in text, (box_id, text)
        assert "Loading" not in text, (box_id, text)


async def test_every_key_none_renders_unavailable_in_every_box():
    rows, regions, _ = await _render([{k: None for k in KW}])
    for box_id in BOX_IDS:
        text = "\n".join(_slice(rows, regions[box_id]))
        assert "unavailable" in text, (box_id, text)


async def test_the_six_labels_stand_in_row_order():
    rows, regions, _ = await _render([KW])
    label_y = regions[AGENTS].y
    line = rows[label_y]
    order = [line.index(w) for w in ("AGENTS", "WORKING", "ACCEPTED 24h", "LAUNCHES", "WORKFLOWS", "SITES")]
    assert order == sorted(order), line


async def test_label_blank_value_geometry():
    """``HeroRow``'s box: label row, one blank, the value -- ``body_y == label_y + 2``."""
    rows, regions, _ = await _render([KW])
    region = regions[AGENTS]
    box = _slice(rows, region)
    label_y = next(i for i, r in enumerate(box) if "AGENTS" in r)
    body_y = next(i for i, r in enumerate(box) if "27/32" in r)
    assert body_y == label_y + 2, box
    assert box[label_y + 1].strip() == "", box


# -- AGENTS -----------------------------------------------------------------


async def test_agents_is_online_over_enrolled():
    assert "27/32" in await _box(AGENTS)


async def test_agents_missing_half_is_a_dash_not_a_zero():
    text = await _box(AGENTS, swarm_agents_online=None)
    assert "--/32" in text, text
    assert "0/32" not in text
    text = await _box(AGENTS, swarm_agents_enrolled=None)
    assert "27/--" in text, text


async def test_agents_both_missing_is_unavailable():
    text = await _box(AGENTS, swarm_agents_online=None, swarm_agents_enrolled=None)
    assert "unavailable" in text, text
    assert "/" not in text.splitlines()[-1] if text.splitlines() else True


async def test_agents_zero_online_is_a_real_zero():
    text = await _box(AGENTS, swarm_agents_online=0)
    assert "0/32" in text, text
    assert "unavailable" not in text


# -- WORKING / ACCEPTED 24h / QUEUE -------------------------------------------


async def test_working_three_states():
    assert "2" in (await _box(WORKING)).splitlines()[2]
    zero = await _box(WORKING, swarm_working_now=0)
    assert zero.splitlines()[2].strip() == "0 quiet", zero
    assert "unavailable" in await _box(WORKING, swarm_working_now=None)


async def test_accepted_24h_is_grouped_and_three_states():
    assert "1,177" in await _box(ACCEPTED)
    zero = await _box(ACCEPTED, swarm_accepted_today=0)
    assert zero.splitlines()[2].strip() == "0", zero
    assert "unavailable" in await _box(ACCEPTED, swarm_accepted_today=None)




import pytest

@pytest.mark.parametrize("size", [(138, 8), (96, 8)])
async def test_summary_cards_keep_only_whole_pairs(size):
    payload = {**KW,
        "swarm_launch_summary": {"by_status": [{"status": "live", "count": 75}, {"status": "parked", "count": 25}]},
        "swarm_workflow_rows": [{"status": "completed"}] * 102 + [{"status": "blocked"}] * 28 + [{}],
        "swarm_site_rows": [{"ens_name": "a.site.identitymd.eth", "status": "named"}] * 90 +
                           [{"ens_name": "b.site.identitymd.eth", "status": "failed"}] +
                           [{"ens_name": "old.site.identitymd.eth", "status": "superseded"}],
    }
    rows, regions, styles = await _render([payload], size=size)
    for box, total, pairs in ((LAUNCHES, "100", ["75 live", "25 parked"]),
                             (WORKFLOWS, "131", ["102 completed", "28 blocked"]),
                             (SITES, "91", ["90 named", "1 failed"])):
        lines = _slice(rows, regions[box])
        assert lines[2].strip() == total
        from rich.cells import cell_len
        room = regions[box].width - 2
        fitted = []
        for pair in pairs:
            if cell_len(" · ".join([*fitted, pair])) <= room:
                fitted.append(pair)
        assert lines[3].strip() == " · ".join(fitted)
        assert "…" not in lines[3]


@pytest.mark.parametrize("key,box", [("swarm_launch_summary", LAUNCHES), ("swarm_workflow_rows", WORKFLOWS), ("swarm_site_rows", SITES)])
async def test_summary_cards_distinguish_unavailable_from_empty(key, box):
    rows, regions, styles = await _render([{key: None}])
    region = regions[box]
    y = next(y for y in range(region.y, region.bottom) if "unavailable" in rows[y][region.x:region.right])
    x = rows[y].index("unavailable", region.x)
    assert styles[x, y].color.get_truecolor() == _A().ansi_theme.ansi_colors[3]
    empty = {"by_status": []} if key == "swarm_launch_summary" else []
    text = await _box(box, **{key: empty})
    assert text.splitlines()[2].strip() == "0"

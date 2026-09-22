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
    ALL_SERVICES_UP,
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

AGENTS, WORKING, ACCEPTED, QUEUE, BREAKER, SERVICES = BOX_IDS


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
    order = [line.index(w) for w in ("AGENTS", "WORKING", "ACCEPTED 24h", "QUEUE", "BREAKER", "SERVICES")]
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


async def test_queue_three_states_and_zero_is_real():
    assert "68" in await _box(QUEUE)
    zero = await _box(QUEUE, swarm_queue_total=0)
    assert zero.splitlines()[2].strip() == "0", zero
    assert "unavailable" in await _box(QUEUE, swarm_queue_total=None)


async def test_a_malformed_count_lands_on_unavailable_not_the_previous_poll():
    """MEDI-38: the body is built inside ``render_box``'s guard."""
    rows, regions, _ = await _render([KW, {**KW, "swarm_queue_total": "lots"}])
    text = "\n".join(_slice(rows, regions[QUEUE]))
    assert "68" not in text, text
    assert "unavailable" in text or "--" in text, text


# -- BREAKER ----------------------------------------------------------------


async def test_breaker_not_tripped_says_closed():
    text = await _box(BREAKER)
    assert "closed" in text, text
    assert "tripped" not in text


async def test_breaker_tripped_shows_the_detail_and_it_is_the_red_the_down_word_wears():
    """Textual resolves ``red`` to the theme's triplet, so colour is asserted
    as a property read off one composited frame: the tripped detail and a
    *down* service word share a colour, and an *up* word does not."""
    rows, regions, styles = await _render([{
        **KW,
        "swarm_breaker": {"tripped": True, "detail": "deploy failed twice"},
        "swarm_services_up": {"verifier": False, "publisher": True, "deployer": True},
    }])
    region = regions[BREAKER]
    box = _slice(rows, region)
    body_y = next(i for i, r in enumerate(box) if "deploy failed twice" in r)
    x = region.x + box[body_y].index("deploy")
    detail_colour = styles[(x, region.y + body_y)].color
    assert detail_colour is not None
    s_region = regions[SERVICES]
    s_box = _slice(rows, s_region)
    s_y = next(i for i, r in enumerate(s_box) if "verifier" in r)
    down, up = [styles[(s_region.x + s_box[s_y].index(word), s_region.y + s_y)].color
                for word in ("down", "up")]
    assert down == detail_colour, (down, detail_colour)
    assert up != down, (up, down)


async def test_breaker_tripped_without_detail_says_open():
    text = await _box(BREAKER, swarm_breaker={"tripped": True, "detail": None})
    assert "open" in text, text


async def test_breaker_none_and_non_dict_are_unavailable():
    assert "unavailable" in await _box(BREAKER, swarm_breaker=None)
    assert "unavailable" in await _box(BREAKER, swarm_breaker="tripped")
    assert "unavailable" in await _box(BREAKER, swarm_breaker=["tripped"])


async def test_a_hostile_breaker_detail_renders_literally_and_a_theme_token_does_not_raise():
    text = await _box(BREAKER, swarm_breaker={"tripped": True, "detail": "bad [/x] tag"})
    assert "[/x]" in text, text
    assert "unavailable" not in text
    text = await _box(BREAKER, swarm_breaker={"tripped": True, "detail": "[$success] deploy"})
    assert "[$success] deploy" in text, text


async def test_a_long_breaker_detail_is_clipped_to_the_box_not_wrapped():
    detail = "x" * 200
    rows, regions, _ = await _render([{**KW, "swarm_breaker": {"tripped": True, "detail": detail}}])
    region = regions[BREAKER]
    box = _slice(rows, region)
    value_rows = [r for r in box if "x" in r]
    assert len(value_rows) == 1, box
    assert value_rows[0].rstrip().endswith("…"), value_rows


# -- SERVICES ---------------------------------------------------------------


async def test_all_services_up_summarises_instead_of_listing():
    text = await _box(SERVICES)
    assert ALL_SERVICES_UP in text, text
    assert "●" not in text
    assert "?" not in text


async def test_a_down_service_lists_every_service_with_its_own_word():
    rows, regions, styles = await _render([
        {**KW, "swarm_services_up": {"verifier": False, "publisher": True, "deployer": True}}
    ])
    region = regions[SERVICES]
    box = _slice(rows, region)
    text = "\n".join(box)
    assert ALL_SERVICES_UP not in text
    assert "verifier down publisher up deployer up" in text
    body_y = next(i for i, r in enumerate(box) if "verifier" in r)
    line = box[body_y]
    positions = [line.index("down"), line.index("up"), line.rindex("up")]
    colours = [styles[(region.x + x, region.y + body_y)].color for x in positions]
    assert colours[1] == colours[2] != colours[0], colours


async def test_an_unreported_service_is_explicit_not_down():
    text = await _box(SERVICES, swarm_services_up={"verifier": True, "publisher": None, "deployer": True})
    assert "verifier up publisher unreported deployer up" in text
    assert "down" not in text


async def test_a_none_or_non_dict_services_payload_is_unavailable():
    """The whole read failed -- ``unavailable``, not three ``unreported`` (the common
    rule: a dict that is ``None`` is unavailable; a *missing field* inside a
    dict is the per-service ``unreported``)."""
    assert "unavailable" in await _box(SERVICES, swarm_services_up=None)
    assert "unavailable" in await _box(SERVICES, swarm_services_up="up")


async def test_a_dict_missing_a_service_marks_only_that_one_unreported():
    text = await _box(SERVICES, swarm_services_up={"verifier": True, "publisher": True})
    line = next(r for r in text.splitlines() if "deployer" in r)
    assert "deployer unreported" in line, line
    assert line.count(" up") == 2, line
    assert "unavailable" not in text


import pytest


def _painted_style(app,box_id,word):
    region=app.query_one('#'+box_id).region
    lines=[''.join(segment.text for segment in strip) for strip in app.screen._compositor.render_strips()]
    y=next(y for y in range(region.y,region.bottom) if word in lines[y][region.x:region.right])
    return app.screen.get_style_at(lines[y].index(word,region.x),y)


@pytest.mark.parametrize('patch,box,word,color',[
    ({'swarm_working_now':2},WORKING,'2',2),
    ({'swarm_working_now':None},WORKING,'unavailable',3),
    ({'swarm_breaker':{'tripped':False,'detail':None}},BREAKER,'closed',2),
    ({'swarm_breaker':{'tripped':True,'detail':'failed twice'}},BREAKER,'open',1),
    ({'swarm_health_status':'ok'},SERVICES,'ok',2),
    ({'swarm_health_status':'degraded'},SERVICES,'degraded',1),
    ({'swarm_health_status':None},SERVICES,'unavailable',3),
])
async def test_polish_hero_state_words_have_composited_colors(patch,box,word,color):
    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmHero).update_data(**{**KW,**patch})
        await pilot.pause()
        style=_painted_style(pilot.app,box,word)
        assert style.color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]
        if box in (WORKING,QUEUE) and word!='unavailable':assert style.bold


async def test_polish_quiet_zero_is_dim_but_remains_a_real_zero():
    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmHero).update_data(**{**KW,'swarm_working_now':0})
        await pilot.pause()
        zero=_painted_style(pilot.app,WORKING,'0')
        quiet=_painted_style(pilot.app,WORKING,'quiet')
        normal=_painted_style(pilot.app,QUEUE,'68')
        assert zero.color==quiet.color and zero.color!=normal.color
        assert zero.bold


async def test_polish_each_service_keeps_its_name_and_semantic_color():
    async with _A().run_test(size=SIZE) as pilot:
        hero=pilot.app.query_one(SurfSwarmHero)
        hero.update_data(**{**KW,'swarm_services_up':{'verifier':False,'publisher':True,'deployer':None},'swarm_health_status':'ok'})
        await pilot.pause()
        for word,color in (('verifier',1),('publisher',2),('ok',2)):
            assert _painted_style(pilot.app,SERVICES,word).color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[color]
        assert _painted_style(pilot.app,SERVICES,'deployer').color not in (
            _painted_style(pilot.app,SERVICES,'verifier').color,
            _painted_style(pilot.app,SERVICES,'publisher').color)
        hero.update_data(**{**KW,'swarm_health_status':'ok'});await pilot.pause()
        assert _painted_style(pilot.app,SERVICES,'all services up').color.get_truecolor()==pilot.app.ansi_theme.ansi_colors[2]


async def test_polish_health_word_is_sanitized_and_independent_of_service_read():
    text=await _box(SERVICES,swarm_services_up=None,swarm_health_status='[/x]degraded')
    assert 'unavailable' in text and 'health degraded' in text and '[/x]' not in text
    text=await _box(SERVICES,swarm_health_status='maintenance-'+'x'*80)
    assert 'health maintenance-' in text and '…' in text


async def test_polish_mixed_services_remain_distinct_without_color():
    rows, regions, _ = await _render([{**KW, 'swarm_services_up': {
        'verifier': False, 'publisher': True, 'deployer': None,
    }}], size=(360, 8))
    text = '\n'.join(_slice(rows, regions[SERVICES]))
    assert 'verifier down publisher up deployer unreported' in text
    assert 'health ok' in text
    assert 'unavailable' not in text
    unread = await _box(SERVICES, swarm_services_up=None)
    assert 'unavailable' in unread and 'unreported' not in unread


@pytest.mark.parametrize("count", [0, 68])
async def test_queue_count_is_bold_without_status_color(count):
    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmHero).update_data(**{**KW, 'swarm_queue_total': count})
        await pilot.pause()
        queue = _painted_style(pilot.app, QUEUE, str(count))
        default_color = pilot.app.query_one('#' + QUEUE).rich_style.color
        assert queue.bold
        assert queue.color == default_color


async def test_unavailable_queue_keeps_its_yellow_word():
    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SurfSwarmHero).update_data(**{**KW, 'swarm_queue_total': None})
        await pilot.pause()
        style = _painted_style(pilot.app, QUEUE, 'unavailable')
        assert style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[3]

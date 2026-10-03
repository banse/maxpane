"""AGENT merged seat cards: OWNER, RUNTIME, MODEL, FEEDBACK, COLLAB and NODES.

Composited assertions only, under the real stylesheet. The payloads are
**folded** from the committed ``/seats`` capture
(``seat_420``) and the v3 ``/contributors`` capture by the manager's own
fold functions, and the expected numbers are read back off that fold, not
typed by hand. Each row is mounted alone, so the screen-scoped card widths do
not apply and the cards split the row evenly. That is why the values are read
at :data:`SIZE`, a wide terminal where no card has to cut a number. Geometry
at the pin is the layout sweep's job (``tests/screens/test_surf_swarm_layout.py``).
"""

from __future__ import annotations

import copy
import inspect
from types import SimpleNamespace

import pytest
from rich.cells import cell_len
from rich.color import Color
from textual.app import App

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.surf._fmt import fmt_win_rate, mmdd_hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf.swarm_agent_cards import (
    SEAT_BOX_IDS,
    SurfSwarmSeatCards,
)
from maxpane_dashboard.widgets.surf._swarm_seat import (
    NODE_TITLES,
    _whole,
)
from tests.surf_swarm_fixtures import (swarm_agent_sources, swarm_capture_v4, swarm_capture_v5,
                                       swarm_seat_capture)

#: Wide enough that every card holds its values whole when the row splits evenly.
SIZE = (200, 7)

_SEAT = swarm_seat_capture("seat_420")
SUMMARY = fold.seat_summary_from_seat(_SEAT)
NODE_ROWS = fold.seat_node_rows(_SEAT)
TEAMMATES = fold.seat_teammates(_SEAT)
CONTRIB = swarm_agent_sources(420)["swarm_seat_contrib"]


class _Themed(App):
    CSS_PATH = CSS_PATH


def _seat_kwargs(**over):
    return {"swarm_seat_summary": copy.deepcopy(SUMMARY), "swarm_seat_state": "ok",
            "swarm_seat_teammates": copy.deepcopy(TEAMMATES),
            "swarm_seat_owner_ens": None, "swarm_seat_node_rows": copy.deepcopy(NODE_ROWS), **over}


async def _cards(cls, ids, kwargs, size=SIZE) -> dict[str, str]:
    """Each card's composited region, keyed like *ids* (the cards share rows)."""
    async with _Themed().run_test(size=size) as pilot:
        await pilot.app.mount(cls())
        row = pilot.app.query_one(cls)
        row.update_data(**kwargs)
        await pilot.pause()
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        out = {}
        for key, box_id in ids.items():
            region = pilot.app.query_one(f"#{box_id}").region
            out[key] = "\n".join(
                rows[y][region.x: region.x + region.width].rstrip()
                for y in range(max(region.y, 0), min(region.y + region.height, len(rows))))
        return out


def _lines(box: str) -> list[str]:
    """A card's non-blank content lines, border and padding stripped."""
    out = []
    for row in box.split("\n"):
        inner = row.strip().strip("│┌┐└┘─╭╮╰╯").strip()
        if inner:
            out.append(inner)
    return out


async def _seat(**over):
    return await _cards(SurfSwarmSeatCards, SEAT_BOX_IDS, _seat_kwargs(**over))


# -- the contract -------------------------------------------------------------------


@pytest.mark.parametrize("cls", [SurfSwarmSeatCards])
def test_update_data_names_exactly_the_signature_in_order(cls):
    sig = inspect.signature(cls.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SWARM_WIDGET_SIGNATURES[cls.__name__]


# -- SEAT row -----------------------------------------------------------------------


async def test_the_seat_row_shows_every_seats_value():
    boxes = await _seat()
    assert SUMMARY["owner"][:6] in boxes["owner"]
    assert mmdd_hhmm(SUMMARY["paired_ts"]) in boxes["owner"]
    assert "⧉" in boxes["owner"]
    assert SUMMARY["runtime"] in boxes["runtime"]
    assert f"{fmt_int(SUMMARY['devices'])} device" in boxes["runtime"]
    for key in ("sent", "submitted", "queued"):
        assert f"{fmt_int(SUMMARY['review_status'][key])} {key}" in boxes["feedback"]
    assert f"{fmt_int(SUMMARY['collaborators'])} seats" in boxes["collab"]
    assert f"#{TEAMMATES[0]['token_id']} ×{TEAMMATES[0]['shared_jobs']}" in boxes["collab"]
    assert "more" not in boxes["collab"]


#: A forward-verified name as the manager serves it (``data/ens.py`` checks it).
ENS_NAME = "surfsurf.eth"


async def test_owner_shows_the_ens_name_in_place_of_the_address():
    """Owner 2026-09-22: a named owner reads as its name; the icon still copies the address."""
    boxes = await _seat(swarm_seat_owner_ens=ENS_NAME)
    assert ENS_NAME in boxes["owner"] and "⧉" in boxes["owner"]
    assert SUMMARY["owner"][:6] not in boxes["owner"]
    assert mmdd_hhmm(SUMMARY["paired_ts"]) in boxes["owner"]


@pytest.mark.parametrize("name", [None, "", 42])
async def test_owner_without_a_usable_name_shows_the_address(name):
    boxes = await _seat(swarm_seat_owner_ens=name)
    assert SUMMARY["owner"][:6] in boxes["owner"] and "⧉" in boxes["owner"]


async def test_a_hostile_ens_name_is_shown_literally_and_fitted():
    boxes = await _seat(swarm_seat_owner_ens="[/x][b]" + "n" * 60 + ".eth")
    line = _lines(boxes["owner"])[1]
    assert line.startswith("[/x][b]") and "…" in line


# -- MODEL (F54): the seat's advertised runtimes[].premiumModel pairs -------------------

#: The v4 ``seat_420`` capture serves ``claude-fable-5-1`` / ``high`` in
#: ``runtimes[].premiumModel``; the older ``seats/`` capture serves no model.
ADVERTISED = fold.seat_summary_from_seat(swarm_capture_v4("seat_420"))["models"]


def _pairs(*models, effort="high"):
    return [{"model": m, "effort": effort} for m in models]


async def _model(models, size=SIZE, words=(), **over) -> SimpleNamespace:
    """MODEL painted with ``swarm_seat_summary``'s ``models`` set to *models*:
    its content ``lines``, the composited ``style`` of each of *words*, its
    ``tooltip``, its content width (``room``), the lines CSS truncated
    (``clipped``, empty when every line was fitted) and the theme's ``yellow``."""
    from tests.screens.test_surf_screen import _css_clipped_lines
    kwargs = _seat_kwargs(swarm_seat_summary=dict(copy.deepcopy(SUMMARY), models=models))
    kwargs.update(over)
    async with _Themed().run_test(size=size) as pilot:
        await pilot.app.mount(SurfSwarmSeatCards())
        cards = pilot.app.query_one(SurfSwarmSeatCards)
        cards.update_data(**kwargs)
        await pilot.pause()
        await pilot.pause()
        box = cards.query_one("#" + SEAT_BOX_IDS["model"])
        painted = ["".join(seg.text for seg in strip)
                   for strip in pilot.app.screen._compositor.render_strips()]
        region = box.region
        ys = range(max(region.y, 0), min(region.bottom, len(painted)))
        rows = [painted[y][region.x: region.right].rstrip() for y in ys]
        styles = {}
        for word in words:
            y = next(y for y in ys if word in painted[y][region.x: region.right])
            styles[word] = pilot.app.screen.get_style_at(painted[y].index(word, region.x), y)
        return SimpleNamespace(lines=_lines("\n".join(rows)), style=styles, tooltip=box.tooltip,
                               room=box.content_size.width, clipped=_css_clipped_lines(pilot.app, box),
                               yellow=Color.parse("yellow").get_truecolor(pilot.app.ansi_theme))


async def test_model_shows_the_captured_pair_short_and_bold_with_its_effort_dim():
    """Owner F54: the short model in bold, then the effort dim -- the title's own dim."""
    assert ADVERTISED == [{"model": "claude-fable-5-1", "effort": "high"}]
    r = await _model(ADVERTISED, words=("MODEL", "fable 5.1", "high"))
    lines, style = r.lines, r.style
    assert lines == ["MODEL", "fable 5.1 high"]
    assert style["fable 5.1"].bold
    assert style["fable 5.1"].color != style["MODEL"].color
    assert style["high"].color == style["MODEL"].color and not style["high"].bold


async def test_model_without_an_effort_shows_the_model_alone():
    r = await _model([{"model": "gpt-5.5-codex", "effort": None}])
    assert r.lines == ["MODEL", "codex 5.5"]


@pytest.mark.parametrize("n, shown", [
    (1, ["fable 5.1 high"]),
    (3, ["fable 5.1 high", "opus 5 high", "sonnet 5 high"]),
    (4, ["fable 5.1 high", "opus 5 high", "+2 more"]),
    (5, ["fable 5.1 high", "opus 5 high", "+3 more"]),
])
async def test_model_shows_three_pairs_whole_and_folds_more_into_two_and_a_count(n, shown):
    """NODES' shape: three or fewer all show; more show two and a dim ``+N more``."""
    models = _pairs("claude-fable-5-1", "claude-opus-5", "claude-sonnet-5", "claude-haiku-5", "gpt-6-astra")[:n]
    r = await _model(models, words=("MODEL",) + (("more",) if n > 3 else ()))
    assert r.lines == ["MODEL", *shown]
    if n > 3:
        assert r.style["more"].color == r.style["MODEL"].color and not r.style["more"].bold


async def test_model_served_empty_is_a_real_negative_and_unread_is_unavailable():
    """``[]``: the seat serves runtimes and advertises no model -- dim, not a
    failure. ``None``: no runtimes list was served -- yellow ``unavailable``."""
    empty = await _model([], words=("MODEL", "not advertised"))
    assert empty.lines == ["MODEL", "not advertised"] and empty.tooltip is None
    assert empty.style["not advertised"].color == empty.style["MODEL"].color
    unread = await _model(None, words=("unavailable",))
    assert unread.lines == ["MODEL", "unavailable"] and unread.tooltip is None
    assert unread.style["unavailable"].color.get_truecolor(None) == unread.yellow


async def test_model_from_a_capture_with_no_premium_model_says_not_advertised():
    """The older ``seats/`` capture serves runtimes without ``premiumModel``."""
    assert SUMMARY["models"] == []
    boxes = await _seat()
    assert _lines(boxes["model"]) == ["MODEL", "not advertised"]


#: Card width at a 139-column terminal with the row split evenly (no screen CSS).
NARROW = (139, 7)


@pytest.mark.parametrize("model, effort, head", [
    ("x" * 60, "high", "x"),
    ("unknown\n\tmodel-" + "y" * 50, "high", "unknown m"),
    ("claude-fable-5-1", "e" * 60, "fable 5.1"),
])
async def test_a_long_model_or_effort_is_flattened_and_fitted_with_a_visible_ellipsis(model, effort, head):
    """Model ids are third-party text: flattened, cut with ``…``, never past the card."""
    r = await _model([{"model": model, "effort": effort}], size=NARROW)
    line = r.lines[1]
    assert line.startswith(head) and "…" in line, line
    assert cell_len(line) <= r.room and not r.clipped, (line, r.room, r.clipped)
    if effort == "high":
        assert line.endswith("… high"), line


async def test_a_markup_shaped_model_renders_literally():
    """``short_model`` strips whole bracket runs, so ``[[b]/x]`` reaches the card
    as ``[/x]``: appended to a ``Text``, it is drawn, never parsed."""
    r = await _model([{"model": "[[b]/x]", "effort": "[b]"}])
    assert r.lines == ["MODEL", "[/x] [b]"]
    assert r.tooltip.plain == "[[b]/x] · [b]"


async def test_model_tooltip_lists_every_pair_raw_and_flattened():
    """The card shortens and folds; hovering shows every advertised pair as served."""
    from rich.text import Text
    models = [{"model": "claude-fable-5-1", "effort": "high"}, {"model": "claude-opus-5", "effort": None},
              {"model": "mystery\n[/x]", "effort": "max"}, {"model": "gpt-6-astra", "effort": "xhigh"}]
    r = await _model(models)
    assert r.lines[-1] == "+2 more"
    assert isinstance(r.tooltip, Text)
    assert r.tooltip.plain.splitlines() == [
        "claude-fable-5-1 · high", "claude-opus-5", "mystery [/x] · max", "gpt-6-astra · xhigh",
    ]
    one = await _model(ADVERTISED)
    assert one.tooltip.plain == "claude-fable-5-1 · high"


@pytest.mark.parametrize("over", [
    {"swarm_seat_state": "busy"},
    {"swarm_seat_state": "pending"},
    {"swarm_seat_state": "unknown_seat"},
    {"swarm_seat_state": None},
    {"swarm_seat_summary": None},
    {"swarm_seat_summary": dict(SUMMARY, models=[])},
    {"swarm_seat_summary": dict(SUMMARY, models=None)},
])
async def test_model_tooltip_is_cleared_on_the_next_paint(over):
    """Like RUNTIME's and NODES': a gated, empty or unread repaint carries none."""
    async with _Themed().run_test(size=SIZE) as pilot:
        await pilot.app.mount(SurfSwarmSeatCards())
        cards = pilot.app.query_one(SurfSwarmSeatCards)
        box = cards.query_one("#" + SEAT_BOX_IDS["model"])
        cards.update_data(**_seat_kwargs(swarm_seat_summary=dict(SUMMARY, models=ADVERTISED)))
        await pilot.pause()
        assert box.tooltip is not None
        cards.update_data(**_seat_kwargs(**over))
        await pilot.pause()
        assert box.tooltip is None


@pytest.mark.parametrize("state, needle", [("pending", "loading"), ("busy", "busy · retrying"), ("error", "unavailable")])
async def test_a_seat_state_replaces_every_seats_card(state, needle):
    boxes = await _seat(swarm_seat_state=state)
    for key in ("owner", "runtime", "feedback", "model", "collab", "nodes"):
        assert needle in boxes[key].lower(), key


async def test_never_paired_is_said_once_per_row():
    boxes = await _seat(swarm_seat_state="unknown_seat")
    assert "\n".join(boxes.values()).count(NEVER_PAIRED_WORDS) == 1
    assert "—" in boxes["nodes"] and "—" in boxes["collab"]


async def test_a_long_runtime_is_fitted_with_a_visible_ellipsis():
    summary = copy.deepcopy(SUMMARY)
    summary["runtime"] = "x" * 200
    boxes = await _seat(swarm_seat_summary=summary)
    first = _lines(boxes["runtime"])[1]  # line 0 is the title
    assert first.endswith("…")


@pytest.mark.parametrize("value,shown", [(999, "999"), (1_000, "1K"), (999_499, "999K"),
                                         (999_600, "1M"), (1_000_000, "1M"), (2_600_000, "3M")])
def test_whole_carries_a_rounded_thousand_thousands_into_millions(value, shown):
    """F66: 999,600 read ``1000K``."""
    assert _whole(value) == shown


def _row(key, **over):
    return {"node_key": key, "attempts": 2, "accepted": 1, **over}


async def test_nodes_show_two_of_four_and_count_the_rest():
    rows = [_row("mystery", attempts=1), _row("build_contract_project", attempts=1),
            _row("adversarial_review", attempts=1),
            _row("oracle_assess", attempts=263, accepted=224)]
    boxes = await _seat(swarm_seat_node_rows=rows)
    assert _lines(boxes["nodes"]) == ["NODES", "ORACLE 224 85.2 %", "REVIEW 1 100.0 %", "+2 more"]


_FOUR_NODES = [_row("mystery\n[/x]", attempts=1), _row("build_contract_project", attempts=1),
               _row("adversarial_review", attempts=1, accepted=1),
               _row("oracle_assess", attempts=2630, accepted=2224), _row("hunt_d", attempts=None)]


async def _nodes_tooltip(**over):
    async with _Themed().run_test(size=SIZE) as pilot:
        await pilot.app.mount(SurfSwarmSeatCards())
        cards = pilot.app.query_one(SurfSwarmSeatCards)
        cards.update_data(**_seat_kwargs(swarm_seat_node_rows=_FOUR_NODES))
        await pilot.pause()
        first = cards.query_one("#" + SEAT_BOX_IDS["nodes"]).tooltip
        cards.update_data(**_seat_kwargs(**over))
        await pilot.pause()
        return first, cards.query_one("#" + SEAT_BOX_IDS["nodes"]).tooltip


async def test_nodes_more_tooltip_lists_every_node_with_exact_counts():
    """Owner 2026-10-02: hovering ``+N more`` lists every node the seat worked, like RUNTIME's."""
    from rich.text import Text
    tooltip, _ = await _nodes_tooltip()
    assert isinstance(tooltip, Text)
    assert tooltip.plain.splitlines() == [
        "ORACLE 2,224 of 2,630 · 84.6 %",
        "REVIEW 1 of 1 · 100.0 %",
        "BUILD 1 of 1 · 100.0 %",
        "mystery [/x] 1 of 1 · 100.0 %",
        "hunt_d 1 · —",
    ]


@pytest.mark.parametrize("over", [
    {"swarm_seat_node_rows": _FOUR_NODES[:3]},
    {"swarm_seat_node_rows": None},
    {"swarm_seat_state": "busy"},
    {"swarm_seat_state": "pending"},
])
async def test_nodes_tooltip_only_while_more_is_shown(over):
    first, after = await _nodes_tooltip(**over)
    assert first is not None
    assert after is None


async def test_three_nodes_all_show_in_count_attempt_and_key_order():
    rows = [_row("build_contract_project"), _row("adversarial_review"), _row("oracle_assess")]
    boxes = await _seat(swarm_seat_node_rows=rows)
    assert _lines(boxes["nodes"]) == ["NODES", "ORACLE 1 50.0 %", "REVIEW 1 50.0 %", "BUILD 1 50.0 %"]


async def test_collab_keeps_count_and_only_two_sorted_teammates():
    summary = {**SUMMARY, "collaborators": 261}
    mates = [{"token_id": t, "shared_jobs": n} for t, n in [(9, 1), (1731, 151), (1626, 161), (1, 151)]]
    boxes = await _seat(swarm_seat_summary=summary, swarm_seat_teammates=mates)
    assert _lines(boxes["collab"]) == ["COLLAB", "261 seats", "#1626 ×161", "#1 ×151"]


@pytest.mark.parametrize(('value','nodes','mates'), [(None, 'unavailable', 'unavailable'), ([], 'no nodes yet', 'none yet')])
async def test_empty_and_unread_nodes_and_teammates_differ(value, nodes, mates):
    boxes = await _seat(swarm_seat_node_rows=value, swarm_seat_teammates=value)
    assert _lines(boxes['nodes']) == ['NODES', nodes]
    assert _lines(boxes['collab'])[-1] == mates


async def test_unknown_node_is_literal_flattened_and_fitted_and_unread_attempts_dash():
    boxes = await _seat(swarm_seat_node_rows=[_row('evil\n[/x]' + 'z'*100, attempts=None)])
    line = _lines(boxes['nodes'])[1]
    assert line.startswith('evil [/x]') and line.endswith('… 1 —')


async def test_nodes_ignore_chain_only_and_zero_counts():
    boxes = await _seat(swarm_seat_node_rows=[_row('oracle_assess', attempts=None, accepted=0, onchain=12)])
    assert _lines(boxes['nodes']) == ['NODES', 'no nodes yet']


async def test_nodes_shorten_counts_without_cutting():
    boxes = await _cards(SurfSwarmSeatCards, SEAT_BOX_IDS,
                        _seat_kwargs(swarm_seat_node_rows=[_row('oracle_assess', attempts=99999, accepted=99999)]),
                        size=(144, 7))
    assert 'ORACLE 100K 100.0 %' in boxes['nodes']
    assert '…' not in boxes['nodes']


async def test_submission_capture_420_merged_cards():
    from tests.data.test_surf_swarm_answers import capture as swarm_submission_capture
    seat = swarm_submission_capture('seat_420')
    boxes = await _seat(swarm_seat_summary=fold.seat_summary_from_seat(seat),
                        swarm_seat_teammates=fold.seat_teammates(seat),
                        swarm_seat_node_rows=fold.seat_node_rows(seat))
    assert _lines(boxes['collab']) == ['COLLAB', '232 seats', '#1626 ×158', '#1731 ×150']
    assert _lines(boxes['nodes']) == ['NODES', 'ORACLE 219 85.5 %', 'REVIEW 1 100.0 %', '+2 more']


async def test_plan_screenshot_values_remain_a_synthetic_layout_case():
    boxes = await _seat(swarm_seat_summary={**SUMMARY, 'collaborators':261},
                        swarm_seat_teammates=[{'token_id':1626,'shared_jobs':161},
                                              {'token_id':1731,'shared_jobs':151}],
                        swarm_seat_node_rows=[_row('oracle_assess',accepted=224,attempts=263),
                                              _row('adversarial_review',attempts=1),
                                              _row('build_contract_project',attempts=1),
                                              _row('hunt_d',accepted=0,attempts=1)])
    assert _lines(boxes['collab']) == ['COLLAB','261 seats','#1626 ×161','#1731 ×151']
    assert _lines(boxes['nodes']) == ['NODES','ORACLE 224 85.2 %','REVIEW 1 100.0 %','+2 more']


@pytest.mark.parametrize("accepted,attempts,expected", [(224, 263, "224 85.2 %"), (2224, 2630, "2,224 84.6 %")])
async def test_long_unknown_node_keeps_exact_accepted_count(accepted, attempts, expected):
    boxes = await _cards(SurfSwarmSeatCards, SEAT_BOX_IDS,
                         _seat_kwargs(swarm_seat_node_rows=[_row("x" * 40, accepted=accepted, attempts=attempts)]),
                         size=(139, 7))
    line = _lines(boxes["nodes"])[1]
    assert "…" in line
    assert line.endswith(" " + expected)


@pytest.mark.parametrize('width', [139, 58])
@pytest.mark.parametrize('runtime,latest,daemon,majority,runtime_up,daemon_up,basis', [
    ('claude 2.1.278 (Claude Code)', '2.1.282', '0.1.0+abc', ('0.1.0+abc',2,3), True, False, 'latest claude-code 2.1.282'),
    ('codex codex-cli 0.155.0-alpha.9.2', '0.155.0', '0.1.0+abc', ('0.1.0+abc',2,3), True, False, 'latest codex 0.155.0'),
    ('claude 9.0.0', '2.1.282', '0.1.0+abc', ('0.1.0+abc',2,3), False, False, 'npm, as of 17:33'),
    ('unknown [/x]', '2.1.282', '0.1.0+abc', ('0.1.0+abc',2,3), False, False, 'runtime not checked'),
    ('claude 2.1.278 (Claude Code)', None, '0.1.0+abc', ('0.1.0+abc',2,3), False, False, 'update check unavailable'),
    ('claude 2.1.282', '2.1.282', '0.1.0+def', ('0.1.0+abc',2,3), False, True, 'fleet daemon 0.1.0+abc on 2/3'),
    ('claude 2.1.282', '2.1.282', '0.1.0+def', None, False, False, 'no fleet majority'),
])
async def test_runtime_card_checks_fit_arrows_and_explain_basis(width, runtime, latest, daemon, majority,
                                                               runtime_up, daemon_up, basis):
    from rich.text import Text
    from tests.screens.test_surf_screen import _frozen_payload, _surf_app, _region_text
    payload = _frozen_payload()
    runtime_id = runtime.partition(' ')[0]
    payload.update(swarm_seat_state='ok',
                   swarm_seat_summary={**SUMMARY, 'runtime':runtime, 'daemon':daemon},
                   swarm_runtime_latest={runtime_id:latest},
                   swarm_runtime_as_of_hhmm={runtime_id:'17:33'}, swarm_fleet_daemon=majority)
    async with _surf_app(payload).run_test(size=(width, 35)) as pilot:
        screen = pilot.app.screen
        await screen._do_refresh()
        await pilot.press('a')
        box = screen.query_one('#surf-swarm-card-runtime')
        assert isinstance(box.tooltip, Text)
        assert basis in box.tooltip.plain
        rows = _region_text(pilot.app, box).splitlines()
        arrows = [(y, line.index('↑')) for y, line in enumerate(rows) if '↑' in line]
        assert len(arrows) == int(runtime_up) + int(daemon_up)
        for y, x in arrows:
            style = screen.get_style_at(box.region.x + x, box.region.y + y)
            assert style.color.get_truecolor() == pilot.app.ansi_theme.ansi_colors[3]
        if not runtime_up and not daemon_up:
            # Compare the actual painted region against the old, unchecked path.
            before = rows
            cards = screen.query_one(SurfSwarmSeatCards)
            cards.update_data(**{key:payload.get(key) for key in SWARM_WIDGET_SIGNATURES['SurfSwarmSeatCards']
                                 if key not in ('swarm_runtime_latest','swarm_runtime_as_of_hhmm','swarm_fleet_daemon')})
            await pilot.pause()
            assert _region_text(pilot.app, box).splitlines() == before


@pytest.mark.parametrize('latest,expected', [
    (None, 'update check pending'),
    ({}, 'update check pending'),
    ({'codex': '0.156.1'}, 'update check pending'),
    ({'claude': None}, 'update check unavailable'),
    ({'claude': '[/x]'}, 'update check unavailable'),
    ({'claude': '2.1.282'}, 'latest claude-code 2.1.282 (npm, as of 17:33)'),
])
async def test_runtime_tooltip_distinguishes_pending_from_failed_without_changing_body(latest, expected):
    from rich.text import Text
    from tests.screens.test_surf_screen import _region_text
    kwargs = _seat_kwargs(swarm_seat_summary={**SUMMARY, 'runtime': 'claude 9.0.0'},
                          swarm_runtime_as_of_hhmm={'claude': '17:33'})
    async with _Themed().run_test(size=SIZE) as pilot:
        await pilot.app.mount(SurfSwarmSeatCards())
        cards = pilot.app.query_one(SurfSwarmSeatCards)
        box = cards.query_one('#' + SEAT_BOX_IDS['runtime'])
        cards.update_data(**kwargs, swarm_runtime_latest={'claude': '2.1.282'})
        await pilot.pause()
        before = _region_text(pilot.app, box)
        cards.update_data(**kwargs, swarm_runtime_latest=latest)
        await pilot.pause()
        assert isinstance(box.tooltip, Text)
        assert box.tooltip.plain == expected + '\nno fleet majority'
        assert _region_text(pilot.app, box) == before


@pytest.mark.parametrize('state,summary', [
    ('busy', SUMMARY), ('pending', SUMMARY), ('unknown_seat', SUMMARY), ('unavailable', SUMMARY), ('ok', None),
])
async def test_gated_runtime_clears_previous_seat_tooltip(state, summary):
    async with _Themed().run_test(size=SIZE) as pilot:
        await pilot.app.mount(SurfSwarmSeatCards())
        cards = pilot.app.query_one(SurfSwarmSeatCards)
        box = cards.query_one('#' + SEAT_BOX_IDS['runtime'])
        cards.update_data(**_seat_kwargs())
        await pilot.pause()
        assert box.tooltip is not None
        cards.update_data(**_seat_kwargs(swarm_seat_state=state, swarm_seat_summary=summary))
        await pilot.pause()
        assert box.tooltip is None

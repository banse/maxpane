"""SEAT RECORD (``SurfSwarmSeatVerdicts``) -- the seat's lifetime record from ``/seats``.

Composited assertions only. Summaries are **folded** from the committed
``/seats`` captures by ``data/surf_swarm.seat_summary_from_seat`` (the
manager's own fold) and every expected number is read off that fold or the
fixture, never hand-typed. The per-class contract is imposed against
``SWARM_WIDGET_SIGNATURES`` (flipped in WP5).

The panel renders at ``SIZE`` = its stylesheet ``max-width`` (46), the width
it has at the AGENT pin; the owner cell's icon and link are read back off the
compositor (``tests/widgets/address_probe``).
"""

from __future__ import annotations

import copy
import inspect
import re
from pathlib import Path

import pytest
from rich.cells import cell_len

from textual.app import App

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.data.surf_swarm import seat_summary_from_seat
from maxpane_dashboard.widgets.explorer import ETHEREUM
from maxpane_dashboard.widgets.fmt import hhmm, mmdd
from maxpane_dashboard.widgets.surf._fmt import EXPLORER
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf.swarm_seat_verdicts import (
    BLOCK_IDS,
    NO_FEEDBACK_LINE,
    PANEL_MAX_WIDTH,
    ROW_IDS,
    VALUE_COLS,
    SurfSwarmSeatVerdicts,
)
from tests.surf_swarm_fixtures import swarm_seat_capture
from tests.widgets.address_probe import LinkRecorder, icon_targets, link_targets
from tests.widgets.surf_compositing import composite_lines

SIGNATURE = SWARM_WIDGET_SIGNATURES["SurfSwarmSeatVerdicts"]

SEAT_420 = swarm_seat_capture("seat_420")
SUMMARY = seat_summary_from_seat(SEAT_420)
AS_OF = "04:06"
#: The panel's ``max-width: 46`` (``minimal.tcss``), the width it gets at the
#: AGENT pin; 16 rows hold the title, its blank and all eleven body lines.
SIZE = (46, 16)
_DROP = object()


def _folded(name: str = "seat_420", **changes) -> dict:
    payload = copy.deepcopy(swarm_seat_capture(name))
    for key, value in changes.items():
        if value is _DROP:
            payload.pop(key, None)
        else:
            payload[key] = value
    return seat_summary_from_seat(payload)


async def _record(**kwargs) -> list[str]:
    kwargs.setdefault("swarm_seat_summary", SUMMARY)
    kwargs.setdefault("swarm_seat_state", "ok")
    kwargs.setdefault("swarm_seat_as_of_hhmm", AS_OF)
    return await composite_lines(SurfSwarmSeatVerdicts, SIZE, css_path=CSS_PATH, **kwargs)


def _row_with(lines, needle):
    return next(line for line in lines if needle in line)


# -- the self-imposed contract -----------------------------------------------------


def test_update_data_names_exactly_the_target_signature_in_order():
    sig = inspect.signature(SurfSwarmSeatVerdicts.update_data)
    params = [n for n, p in sig.parameters.items() if n != "self" and p.kind is not p.VAR_KEYWORD]
    assert tuple(params) == SIGNATURE
    assert any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())


async def test_no_args_and_all_none_render_unavailable_on_every_line_without_raising():
    bare = "\n".join(await composite_lines(SurfSwarmSeatVerdicts, SIZE, css_path=CSS_PATH))
    assert "Loading" not in bare
    assert bare.count("unavailable") == len(ROW_IDS) + len(BLOCK_IDS), bare
    none = "\n".join(await composite_lines(
        SurfSwarmSeatVerdicts, SIZE, css_path=CSS_PATH, **{k: None for k in SIGNATURE},
    ))
    assert none == bare


async def test_the_loading_seed_lands_on_the_first_row_only():
    class _A(App):
        def compose(self):
            yield SurfSwarmSeatVerdicts()

    async with _A().run_test(size=SIZE) as pilot:
        await pilot.pause()
        strips = pilot.app.screen._compositor.render_strips()
        rows = ["".join(seg.text for seg in strip) for strip in strips]
        loading = [y for y, r in enumerate(rows) if "Loading" in r]
        assert len(loading) == 1
        title_y = next(y for y, r in enumerate(rows) if "SEAT RECORD" in r)
        assert loading[0] == title_y + 2, rows[: loading[0] + 1]


# -- the #420 record, folded ---------------------------------------------------------


async def test_the_defect_seat_renders_its_lifetime_record():
    lines = await _record()
    status = SUMMARY["review_status"]
    pending = status["submitted"] + status["queued"]
    accepted = _row_with(lines, "accepted")
    assert f"{SUMMARY['accepted']} of {SUMMARY['attempts']}" in accepted and "●" in accepted
    # Q-M: pending is a subset of the reviews, and the status rows add up to it.
    assert f"{SUMMARY['reviewed']} · {pending} pending" in _row_with(lines, "reviewed")
    assert f" {status['sent']}" in _row_with(lines, "sent")
    assert (f"{status['submitted']} submitted · {status['queued']} queued"
            in _row_with(lines, "pending "))
    assert f"{SUMMARY['mean_score']:.2f} ({SUMMARY['scored']} scored)" in _row_with(lines, "score")
    paired = SUMMARY["paired_ts"]
    assert f"{mmdd(paired)} {hhmm(paired)}" in _row_with(lines, "paired")
    roles = _row_with(lines, "by role")
    for entry in SUMMARY["roles"]:
        assert f"{entry['role']} {entry['count']}" in roles
    assert "unavailable" not in "\n".join(lines)


@pytest.mark.guard
def test_the_panel_width_the_fits_follow_is_the_stylesheets():
    """``PANEL_MAX_WIDTH`` is a hand-typed copy of ``minimal.tcss``; bind the two."""
    css = Path(CSS_PATH).read_text()
    block = re.search(r"^SurfSwarmSeatVerdicts \{(.*?)\}", css, re.S | re.M)
    assert block, "minimal.tcss lost its SurfSwarmSeatVerdicts block"
    width = re.search(r"max-width:\s*(\d+);", block.group(1))
    assert width and int(width.group(1)) == PANEL_MAX_WIDTH == SIZE[0]


async def test_the_largest_seat_fits_its_roles_and_counts_the_rest():
    """Seat #0's roles do not fit whole at the panel's width: the line keeps
    the busiest in the fold's order and says how many it left out."""
    roles = _folded("seat_0")["roles"]
    whole = " · ".join(f"{r['role']} {r['count']}" for r in roles)
    assert len(roles) >= 2 and cell_len(whole) > VALUE_COLS, "the capture must overflow"
    line = _row_with(await _record(swarm_seat_summary=_folded("seat_0")), "by role")
    first = roles[0]
    assert f"{first['role']} {first['count']} · +{len(roles) - 1} more" in line
    for dropped in roles[1:]:
        assert f"{dropped['role']} {dropped['count']}" not in line
    assert cell_len(line) <= SIZE[0] and "…" not in line


async def test_the_runtime_is_clipped_visibly_to_the_panel():
    """``claude 2.1.278 (Claude Code)`` is 28 cells; the row keeps a visible cut."""
    runtime = _row_with(await _record(), "runtime")
    head = SUMMARY["runtime"].split(" (")[0]
    assert head in runtime and runtime.rstrip().endswith("…"), runtime


async def test_the_title_carries_the_marker():
    text = "\n".join(await _record())
    assert "SEAT RECORD" in text and f"as of {AS_OF}" in text and "VERDICTS" not in text
    bare = "\n".join(await _record(swarm_seat_as_of_hhmm=""))
    assert "as of" not in bare


async def test_the_retired_rows_are_gone():
    """D2: ``/seats`` serves no rejections, revisions, codes or working-now."""
    text = "\n".join(await _record())
    for word in ("rejected", "revisions", "rejection codes", "working", "first seen"):
        assert word not in text, word


# -- the owner cell -----------------------------------------------------------------


class _LinkedHarness(LinkRecorder, App):
    CSS_PATH = CSS_PATH

    def compose(self):
        yield SurfSwarmSeatVerdicts()


async def test_the_owner_carries_its_copy_icon_and_links_the_package_explorer():
    owner = SUMMARY["owner"]
    async with _LinkedHarness().run_test(size=SIZE) as pilot:
        panel = pilot.app.query_one(SurfSwarmSeatVerdicts)
        panel.update_data(swarm_seat_summary=SUMMARY, swarm_seat_state="ok",
                          swarm_seat_as_of_hhmm=AS_OF)
        await pilot.pause()
        icons = icon_targets(pilot.app)
        links = link_targets(pilot.app)
    assert [address for _x, _y, address in icons] == [owner]
    icon_x, icon_y, _ = icons[0]
    linked = [t for t in links if t[1] == icon_y]
    assert linked and {t[2] for t in linked} == {ETHEREUM.name} and EXPLORER is ETHEREUM
    assert {(t[3], t[4]) for t in linked} == {("address", owner)}
    # The link is on the shown window, never on the icon.
    assert all(t[0] < icon_x for t in linked)


async def test_the_owner_is_windowed_and_whole_on_its_row():
    owner = SUMMARY["owner"]
    row = _row_with(await _record(), "owner")
    assert owner not in row and "…" in row and row.rstrip().endswith("⧉")
    assert owner[-6:] in row and owner[:10] in row


async def test_an_owner_that_is_not_an_address_gets_no_icon_and_no_link():
    bad = dict(SUMMARY, owner="0xnot-an-address")
    async with _LinkedHarness().run_test(size=SIZE) as pilot:
        panel = pilot.app.query_one(SurfSwarmSeatVerdicts)
        panel.update_data(swarm_seat_summary=bad, swarm_seat_state="ok")
        await pilot.pause()
        assert icon_targets(pilot.app) == [] and link_targets(pilot.app) == []


# -- hostile third-party text -----------------------------------------------------------


async def test_a_hostile_runtime_and_role_render_stripped_and_never_raise():
    """``sanitize_cell`` strips bracket runs before it escapes: the words survive,
    the tag does not, and the row does not fall back to ``unavailable``."""
    hostile = dict(SUMMARY, runtime="[/x]PWNED 1.0",
                   roles=[{"role": "[/x]evil", "count": 3}, {"role": "[$success]", "count": 1}])
    lines = await _record(swarm_seat_summary=hostile)
    runtime = _row_with(lines, "runtime")
    assert "PWNED 1.0" in runtime and "[/x]" not in runtime and "unavailable" not in runtime
    roles = _row_with(lines, "by role")
    assert "evil 3" in roles and "[/x]" not in roles and "unavailable" not in roles


async def test_a_nested_bracket_runtime_is_escaped_not_parsed():
    lines = await _record(swarm_seat_summary=dict(SUMMARY, runtime="[[inner]/word] v1"))
    runtime = _row_with(lines, "runtime")
    assert "[/word] v1" in runtime and "unavailable" not in runtime


# -- the seat state ------------------------------------------------------------------


async def test_a_failed_read_is_unavailable_on_every_line_behind_the_marker():
    lines = await _record(swarm_seat_state=None, swarm_seat_summary=None)
    text = "\n".join(lines)
    assert f"SEAT RECORD · as of {AS_OF}" in text
    assert text.count("unavailable") == len(ROW_IDS) + len(BLOCK_IDS)
    assert " 0 of " not in text and NEVER_PAIRED_WORDS not in text


async def test_pending_says_loading_once_and_paints_no_number_of_another_seat():
    """A switch in flight: seat #420's summary is handed in under ``pending``
    and none of it may reach a pixel."""
    text = "\n".join(await _record(swarm_seat_state="pending"))
    assert text.count("Loading...") == 1
    assert f"{SUMMARY['accepted']} of" not in text and "scored" not in text
    assert "unavailable" not in text and "⧉" not in text


async def test_a_seat_that_never_paired_says_so_and_nothing_else():
    text = "\n".join(await _record(swarm_seat_state="unknown_seat", swarm_seat_summary=None))
    assert text.count(NEVER_PAIRED_WORDS) == 1
    assert "unavailable" not in text and "Loading" not in text and "accepted" not in text


async def test_a_malformed_state_is_unavailable():
    text = "\n".join(await _record(swarm_seat_state="garbage"))
    assert text.count("unavailable") == len(ROW_IDS) + len(BLOCK_IDS)


# -- zeros, missing fields and malformed values -----------------------------------------


async def test_a_zero_record_renders_zeros_not_unavailable():
    zero = _folded(attempts=0, accepted=0, work=[], reviews=[], collaborators=[])
    lines = await _record(swarm_seat_summary=zero)
    accepted = _row_with(lines, "accepted")
    assert "0 of 0" in accepted and "○" in accepted
    assert "0 · 0 pending" in _row_with(lines, "reviewed")
    assert "0 submitted · 0 queued" in _row_with(lines, "pending ")
    assert NO_FEEDBACK_LINE in _row_with(lines, "score")
    assert "none" in _row_with(lines, "by role")
    for needle in ("accepted", "reviewed", "sent", "pending ", "score", "by role"):
        assert "unavailable" not in _row_with(lines, needle), needle


async def test_a_seat_that_runs_nothing_says_none_never_unavailable():
    """Seat #0 serves ``runtimes: []`` -- a real negative, which the fold
    carries as ``""`` (WP3 review: it used to fold to ``None`` and render a
    false ``unavailable``)."""
    summary = _folded("seat_0")
    assert summary["runtime"] == ""
    lines = await _record(swarm_seat_summary=summary)
    runtime = _row_with(lines, "runtime")
    assert "none" in runtime and "unavailable" not in runtime
    assert "unavailable" not in _row_with(lines, "accepted")
    assert "⧉" in _row_with(lines, "owner")


async def test_a_runtime_the_source_did_not_carry_says_unavailable_on_that_row_only():
    summary = dict(_folded("seat_420"), runtime=None)
    lines = await _record(swarm_seat_summary=summary)
    runtime = _row_with(lines, "runtime")
    assert "unavailable" in runtime and "none" not in runtime
    assert "unavailable" not in _row_with(lines, "accepted")


async def test_a_field_the_source_did_not_carry_is_unavailable_on_its_own_row_only():
    missing = _folded(attempts=_DROP, pairedAt=_DROP)
    lines = await _record(swarm_seat_summary=missing)
    accepted = _row_with(lines, "accepted")
    assert "unavailable" in accepted and " of " not in accepted
    assert "unavailable" in _row_with(lines, "paired")
    assert f"{SUMMARY['reviewed']} · " in _row_with(lines, "reviewed")


async def test_a_malformed_counter_lands_on_its_own_row_only():
    lines = await _record(swarm_seat_summary=dict(SUMMARY, accepted="lots",
                                                  review_status={"sent": True}))
    assert "unavailable" in _row_with(lines, "accepted")
    assert "unavailable" in _row_with(lines, "sent")
    assert "-- pending" in _row_with(lines, "reviewed")
    assert f"{SUMMARY['mean_score']:.2f}" in _row_with(lines, "score")


async def test_a_malformed_summary_is_unavailable_everywhere():
    text = "\n".join(await _record(swarm_seat_summary=["not", "a", "dict"]))
    assert text.count("unavailable") == len(ROW_IDS) + len(BLOCK_IDS)

"""The `s` SWARM body's and the `a` AGENT body's measured layout (swarm v2, WP7).

Four pins live here and nowhere else: ``SURF_SWARM_FULL_LAYOUT_COLUMNS`` /
``_ROWS`` for the ``s`` body and ``SURF_AGENT_FULL_LAYOUT_COLUMNS`` /
``_ROWS`` for the ``a`` body. Their measurement method, their binding panel
or container and every named exception are in their own ``#:`` blocks in
``screens/surf.py``; this file is what makes those blocks fail when they
stop being true.

**Re-swept from scratch on 2026-09-21.** Swarm v2 replaced every v1 panel
(THE FIELD, QUEUE, JUST SHIPPED, the v1 hero and THROUGHPUT) with a new
grid -- CAPABILITY beside THROUGHPUT, IN FLIGHT beside LAUNCHES, SITES
beneath -- and added the AGENT body (ROSTER beside SEAT RECORD, RECORD,
FEEDBACK; re-swept again the same day when the body moved onto the lifetime
``/seats`` record, ``docs/surf_agent_seats_plan.md`` WP6). Nothing in this file compares against the v1 numbers (116 / 28)
or the v1 exceptions (``FIELD_NEVER_CLEARS_BELOW``,
``SHIPPED_NEVER_CLEARS_BELOW``); ``docs/decisions.md`` keeps them.

The geometry invariants are the pool4-market file's: at and above a column
pin **whole** means no panel marked besides the named exceptions, no
CSS-clipped line, no hidden ``DataTable`` column and no widget region
extending past its own container's, and no CSS-clipped line in the body's
own hero (whose boxes ellipsise); below it something *other than* an
exception must advertise the loss. The region check is unconditional -- an
exception may keep marking, never paint past its row. At and above a row
pin the screen-wide ``‹ taller`` is dark; below it, lit; and wherever a
registered container scrolls the marker is lit (``_SCROLL_COLUMNS``).

Sizes are boundary sets (``tests/screens/_sweeps.py``): the band's ends,
the pin and every measured threshold +-1, never the pin alone.
"""

from __future__ import annotations

import copy
import datetime as dt

import pytest
from textual.widgets import DataTable

import maxpane_dashboard.data.surf_swarm as sw
from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.analytics.surf_swarm_signals import (
    launch_summary,
    skill_summary,
)
from maxpane_dashboard.screens.surf import (
    AGENT_BODY_ID,
    AGENT_TOP_ID,
    SURF_AGENT_FULL_LAYOUT_COLUMNS,
    SURF_AGENT_FULL_LAYOUT_ROWS,
    SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS,
    SURF_POOL4_USER_FULL_LAYOUT_COLUMNS,
    SURF_SWARM_FULL_LAYOUT_COLUMNS,
    SURF_SWARM_FULL_LAYOUT_ROWS,
    SWARM_BODY_ID,
    SWARM_BOTTOM_ID,
    SWARM_TOP_ID,
    TALLER_HINT,
    SurfScreen,
)
from maxpane_dashboard.widgets.surf import (
    SurfSwarmAgentHero,
    SurfSwarmCapability,
    SurfSwarmHero,
    SurfSwarmInFlight,
    SurfSwarmLaunches,
    SurfSwarmRoster,
    SurfSwarmSeatFeedback,
    SurfSwarmSeatRecord,
    SurfSwarmSeatVerdicts,
    SurfSwarmSites,
    SurfSwarmThroughput,
)
from tests.screens._sweeps import boundary_set
from tests.screens.test_surf_screen import (
    _css_clipped_lines,
    _frozen_payload,
    _region_text,
    _screen_text,
    _surf_app,
)
from tests.surf_swarm_fixtures import (
    swarm_capture_v2,
    swarm_details_v2,
    swarm_manifest_v2,
    swarm_seat_capture,
)

# ---------------------------------------------------------------------------
# The measured numbers
# ---------------------------------------------------------------------------

#: What the sweeps found, restated by hand so the pins cannot drift on their
#: own: a pin that moves without a re-sweep reddens the agreement test.
MEASURED_SWARM_COLUMNS = 141
MEASURED_SWARM_ROWS = 42
MEASURED_AGENT_COLUMNS = 134
MEASURED_AGENT_ROWS = 40

#: The `s` body's two named exceptions (``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s
#: block): the outer width at which each one's own ``‹`` goes dark on the
#: capture. Both sit past the width sweep's band, so folding either into
#: "whole" would make the property unpassable rather than strict.
INFLIGHT_NEVER_CLEARS_BELOW = 190
LAUNCHES_NEVER_CLEARS_BELOW = 205
#: LAUNCHES hides a column behind its horizontal scrollbar under this width
#: and none from it -- the ``4fr : 5fr`` seam's one job at the pin.
LAUNCHES_HIDES_NO_COLUMN_FROM = 138

#: The `a` body's one named exception: RECORD's ``objective`` column is the
#: job's free text and lights ``‹`` while any of it is cut. On the capture
#: (seat #0's lifetime ``work[]``, objectives of 186-198 cells) it clears
#: here; on the worst case (400 characters) it never does. Re-measured for
#: the ``/seats`` record (WP6): it was 168 on the verifier ``detail`` column.
RECORD_NEVER_CLEARS_BELOW = 268

#: Measured tier edges the width sweeps straddle (+-1 each).
_S_THRESHOLDS = (
    116,  # SITES `full` from here (and the v1 column pin, crossed on purpose)
    132,  # CAPABILITY `compact` from here
    LAUNCHES_HIDES_NO_COLUMN_FROM,
    145,  # IN FLIGHT `compact` from here
)
_A_THRESHOLDS = (
    79,   # RECORD `compact` from here
    87,   # FEEDBACK `compact` from here; SEAT RECORD clips no line from here (capture)
    90,   # RECORD `full` from here (still marked for its objective)
    93,   # SEAT RECORD clips no line from here (worst case: the longer runtime)
    97,   # FEEDBACK `full` from here
    102,  # the hero clips no box from here (capture)
    105,  # ROSTER hides no column from here (capture)
    107,  # ROSTER hides no column from here (worst case: 30 seats)
    120,  # ROSTER `compact` from here; the hero clips no box from here
          # (worst case: SCORE's `(99,999 scored)`; 125 while REVIEWED was one line)
)

_EXCLUDED_FROM_WHOLE = {
    "s": {"SurfSwarmInFlight", "SurfSwarmLaunches"},
    "a": {"SurfSwarmSeatRecord"},
}
_BINDING_PANEL = {"s": "SurfSwarmCapability", "a": "SurfSwarmRoster"}
_COLUMN_PIN = {"s": SURF_SWARM_FULL_LAYOUT_COLUMNS, "a": SURF_AGENT_FULL_LAYOUT_COLUMNS}
_ROW_PIN = {"s": SURF_SWARM_FULL_LAYOUT_ROWS, "a": SURF_AGENT_FULL_LAYOUT_ROWS}
_BODY_ID = {"s": SWARM_BODY_ID, "a": AGENT_BODY_ID}
#: Each body's own hero. Its boxes are ``text-overflow: ellipsis``, so a box
#: too narrow for its value is a CSS-clipped line like any panel's, and it
#: counts as one: at and above the pin none may be clipped.
_HERO = {"s": SurfSwarmHero, "a": SurfSwarmAgentHero}
_TOP_ID = {"s": SWARM_TOP_ID, "a": AGENT_TOP_ID}
#: The `height: auto` panel whose fixed line count is its row's floor.
_FLOOR_PANEL = {"s": "SurfSwarmThroughput", "a": "SurfSwarmSeatVerdicts"}

#: Each panel's own direct container, named rather than derived so a
#: restructure that moves a panel fails loudly here. SITES, RECORD and
#: FEEDBACK are the body's direct children.
_CONTAINER_OF = {
    "s": {
        SurfSwarmCapability: SWARM_TOP_ID,
        SurfSwarmThroughput: SWARM_TOP_ID,
        SurfSwarmInFlight: SWARM_BOTTOM_ID,
        SurfSwarmLaunches: SWARM_BOTTOM_ID,
        SurfSwarmSites: SWARM_BODY_ID,
    },
    "a": {
        SurfSwarmRoster: AGENT_TOP_ID,
        SurfSwarmSeatVerdicts: AGENT_TOP_ID,
        SurfSwarmSeatRecord: AGENT_BODY_ID,
        SurfSwarmSeatFeedback: AGENT_BODY_ID,
    },
}
#: The containers ``_SCROLL_COLUMNS`` registers per mode -- restated by hand
#: (the screen's dict is keyed by mode word); the marker test binds the two.
_REGISTERED_SCROLLERS = {
    "s": (SWARM_BODY_ID, SWARM_TOP_ID),
    "a": (AGENT_BODY_ID, AGENT_TOP_ID),
}

_COLUMN_SWEEP_HEIGHT = 80
_ROW_SWEEP_WIDTH = 150

# ---------------------------------------------------------------------------
# Payloads: the committed v2 corpus and the plan's worst cases
# ---------------------------------------------------------------------------

_NOW = dt.datetime.fromisoformat(
    swarm_manifest_v2()["captured_at"].replace("Z", "+00:00")
).timestamp()


def _seat_keys(seat: dict) -> dict:
    """The AGENT body's seat-tier keys for one committed ``/seats`` capture,
    folded as ``SurfManager._swarm_seat_keys`` folds a read for the selected
    token (the WP1b fold, ``docs/surf_agent_seats_plan.md``)."""
    return {
        "swarm_seat_state": "ok",
        "swarm_seat_summary": sw.seat_summary_from_seat(seat),
        "swarm_seat_work_rows": sw.seat_work_rows(seat),
        "swarm_seat_feedback_rows": sw.seat_review_rows(seat),
    }


def _corpus_keys() -> dict:
    """Every v2 contract key folded from the committed capture, as the
    manager would (``data/surf_swarm.py`` folds, ``analytics`` summaries).

    The roster is the ``/jobs`` window fold; the selected seat is the most
    active one there (``choose_seat``, nothing saved), which is seat #0 --
    the largest committed ``/seats`` capture (26 work, 202 reviews) -- and
    its record is the WP1b fold over that capture."""
    health = swarm_capture_v2("health")
    jobs = swarm_capture_v2("jobs")["jobs"]
    details = swarm_details_v2()
    skills = swarm_capture_v2("skills")["skills"]
    launches = swarm_capture_v2("launches")["launches"]
    sites = swarm_capture_v2("sites")["sites"]
    seen = sw.merge_seen({}, jobs, details, now_ts=_NOW, cap=None, max_age_s=10**9)
    hf = sw.health_facts(health)
    skill_rows = sw.skill_rows(skills)
    launch_rows = sw.launch_rows(launches)
    seat_rows = sw.seat_rows(details, seen)
    selected = sw.choose_seat(seat_rows, None, None)
    token = selected["token_id"]
    seat = swarm_seat_capture(f"seat_{token}")
    assert sw.seat_state(seat, token) == "ok", "the corpus's most active seat has a capture"
    return {
        "swarm_agents_online": hf.get("agents_online"),
        "swarm_agents_enrolled": hf.get("agents_enrolled"),
        "swarm_working_now": hf.get("working_now"),
        "swarm_accepted_today": hf.get("accepted_today"),
        "swarm_queue_total": sw.queue_total(health),
        "swarm_breaker": sw.breaker(health),
        "swarm_services_up": hf.get("services_up"),
        "swarm_inflight_rows": sw.inflight_rows(jobs, details, now_ts=_NOW),
        "swarm_throughput": sw.throughput_facts(jobs, seen, now_ts=_NOW),
        "swarm_skill_rows": skill_rows,
        "swarm_skill_summary": skill_summary(skill_rows),
        "swarm_launch_rows": launch_rows,
        "swarm_launch_summary": launch_summary(launch_rows),
        "swarm_site_rows": sw.site_rows(sites),
        "swarm_seat_rows": seat_rows,
        "swarm_seat_selected": selected,
        "swarm_roster_window": sw.roster_window(jobs),
        **_seat_keys(seat),
        "swarm_seat_as_of_hhmm": "00:08",
        "swarm_scores_as_of_hhmm": "00:08",
        "swarm_as_of_hhmm": "00:08",
        "swarm_stale": False,
        "swarm_network": "SEPOLIA",
    }


def _cycle(rows: list, n: int) -> list:
    return [copy.deepcopy(rows[i % len(rows)]) for i in range(n)]


def _capture_payload() -> dict:
    return _frozen_payload(**_corpus_keys())


def _worst_swarm_payload() -> dict:
    """The plan's `s` worst case: 30 launches carrying 55 artifacts, 30
    skills, 10 sites, 25 in-flight rows with 200-character objectives."""
    k = _corpus_keys()
    launches = _cycle(k["swarm_launch_rows"], 30)
    artifacts = 0
    for i, row in enumerate(launches):
        row["launch_number"] = 1000 + i
        want = 2 if i < 25 else 1
        base = row["artifacts"] or [{
            "role": "token", "name": "Curve Flow v2",
            "address": "0x200E710aCAA6A93bbc77146026328C40F1d60fB1",
            "tx_hash": "0x" + "33" * 32, "block_number": 8_950_001,
        }]
        row["artifacts"] = _cycle(base, want)
        row["artifact_count"] = want
        artifacts += want
    assert artifacts == 55, artifacts
    inflight = _cycle(k["swarm_inflight_rows"], 25)
    for i, row in enumerate(inflight):
        row["job_id"] = f"{i:08x}-worst-case-job"
        row["objective"] = (
            "build the ERC-4626 vault and wire its deposit and withdraw paths "
            "through the launchpad adapter "
        ) * 2
        row["template"] = "build_contract_project_long_template_name"
        row["node_key"] = "build_contract_project"
        row["agent_token"] = 1548 + i
    skills = _cycle(k["swarm_skill_rows"], 30)
    k.update({
        "swarm_launch_rows": launches, "swarm_launch_summary": launch_summary(launches),
        "swarm_skill_rows": skills, "swarm_skill_summary": skill_summary(skills),
        "swarm_site_rows": _cycle(k["swarm_site_rows"], 10),
        "swarm_inflight_rows": inflight,
    })
    return _frozen_payload(**k)


def _worst_agent_payload() -> dict:
    """The `a` worst case on the lifetime record: 30 roster seats; the
    selected seat's RECORD at its 40-row cap with 400-character objectives
    and long node keys; FEEDBACK over seat #0's 202 reviews with #420's
    queued and submitted rows on top (every status and chain cell shape);
    SEAT RECORD with #420's longest runtime and a full owner address; every
    lifetime counter stretched to five digits (four for a part of one).

    Every row is a WP1b fold of a committed ``/seats`` capture, then
    lengthened -- never hand-typed from scratch."""
    k = _corpus_keys()
    seats = _cycle(k["swarm_seat_rows"], 30)
    for i, row in enumerate(seats):
        row["token_id"] = 1000 + i
        row["agent_id"] = str(50000 + i)
        row["nodes"] = 40 - i
    seats[0]["token_id"] = k["swarm_seat_selected"]["token_id"]
    seats[0]["agent_id"] = k["swarm_seat_selected"]["agent_id"]
    seat0 = swarm_seat_capture("seat_0")
    seat420 = swarm_seat_capture("seat_420")
    work = _cycle(sw.seat_work_rows(seat0), 40)
    for i, row in enumerate(work):
        row["job_id"] = f"{i:08x}-worst-case-job"
        row["node_key"] = "build_contract_project_with_a_long_key"
        row["objective"] = (
            "build the ERC-4626 vault and wire its deposit and withdraw paths "
            "through the launchpad adapter, then re-sweep every pinned layout; " * 6
        )[:400]
    pending = [r for r in sw.seat_review_rows(seat420) if r["status"] != "sent"]
    assert {r["status"] for r in pending} == {"submitted", "queued"}
    feedback = pending + sw.seat_review_rows(seat0)
    summary = sw.seat_summary_from_seat(seat0)
    summary["runtime"] = sw.seat_summary_from_seat(seat420)["runtime"]
    assert summary["owner"] and summary["runtime"]
    # The lifetime counters have no ceiling -- seat #0 already has 202
    # reviews, and a worst case that keeps the capture's 202 is the narrow
    # case (the fix-round finding: ``1,202 · 13 pending`` clipped at the pin
    # while ``202 · 13 pending`` fitted). Stretched to a realistic ceiling
    # instead. The lifetime totals get five digits (~500x #0's 202 reviews
    # and 209 attempts, years of a seat at the capture's rate) and a part of
    # one four (``9,999 of 99,999``). ``submitted`` and ``queued`` are not
    # lifetime counters but a backlog that drains as scores land on chain
    # (#0 holds 13, #420 6), so three digits each -- ~75x the largest seen
    # -- whose sum is the four-digit ``1,998 pending``, the hero's widest
    # plausible form. Four digits of ``submitted`` alone clip SEAT RECORD's
    # ``pending`` row at every width (``9,000 submitted · 999 que…`` under
    # its ``max-width: 46``); that is filed, not measured into this case.
    # The split still sums to ``reviewed`` (Q-M).
    summary.update(
        attempts=99_999, accepted=9_999, reviewed=99_999, scored=99_999,
        collaborators=9_999,
        review_status={"sent": 98_001, "submitted": 999, "queued": 999},
    )
    assert sum(summary["review_status"].values()) == summary["reviewed"]
    k.update({
        "swarm_seat_rows": seats, "swarm_seat_work_rows": work,
        "swarm_seat_feedback_rows": feedback, "swarm_seat_summary": summary,
    })
    return _frozen_payload(**k)


PAYLOADS = {
    "capture": _capture_payload,
    "worst-s": _worst_swarm_payload,
    "worst-a": _worst_agent_payload,
}
_WORST = {"s": "worst-s", "a": "worst-a"}

# ---------------------------------------------------------------------------
# Compositing
# ---------------------------------------------------------------------------


def _widgets(screen, key: str) -> dict[str, object]:
    """The body's own panels, resolved through the body container -- never
    ``screen.query_one(cls)``, which could answer from a body that is not
    on screen."""
    body = screen.query_one(f"#{_BODY_ID[key]}")
    out = {}
    for cls in _CONTAINER_OF[key]:
        found = list(body.query(cls))
        assert len(found) == 1, f"{cls.__name__}: {len(found)} instances inside the body"
        out[cls.__name__] = found[0]
    return out


def _overflow(screen, key: str, widgets: dict) -> list[tuple[str, int]]:
    """Every panel whose region extends past its own container's.

    A bounded ``1fr`` child Textual lays out past its parent's edge is
    cropped by the compositor with no glyph and no scrollbar -- neither the
    marker nor the clipped-line check can see it (the v1 THROUGHPUT defect
    of 2026-09-17). Horizontal overflow is always a defect. Vertical
    overflow is one only where the container does not scroll: a child
    pushed below a scrolling body is the scroll itself, and the marker test
    answers for that.
    """
    out = []
    for cls, cid in _CONTAINER_OF[key].items():
        container = screen.query_one(f"#{cid}")
        c, w = container.region, widgets[cls.__name__].region
        over = max(w.x + w.width - (c.x + c.width), 0) + max(c.x - w.x, 0)
        if not container.show_vertical_scrollbar:
            over += max(w.y + w.height - (c.y + c.height), 0) + max(c.y - w.y, 0)
        if over:
            out.append((cls.__name__, over))
    return out


async def _render(payload: dict | None, size: tuple[int, int], key: str) -> dict:
    """Open body *key* at *size* and hand back everything measured from it."""
    app = _surf_app(payload)
    async with app.run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.pause()
        await pilot.press(key)
        await pilot.pause()
        await pilot.pause()
        screen = pilot.app.screen
        widgets = _widgets(screen, key)
        marked = {name for name, w in widgets.items() if "‹" in _region_text(pilot.app, w)}
        hidden = {}
        for name, w in widgets.items():
            tables = list(w.query(DataTable))
            if tables:
                hidden[name] = tables[0].max_scroll_x
        clipped = [
            (name, line)
            for name, w in widgets.items()
            for line in _css_clipped_lines(pilot.app, w)
        ]
        hero = screen.query_one(_HERO[key])
        clipped += [(type(hero).__name__, line) for line in _css_clipped_lines(pilot.app, hero)]
        scroll = {
            cid: screen.query_one(f"#{cid}").show_vertical_scrollbar
            for cid in set(_CONTAINER_OF[key].values())
        }
        top = screen.query_one(f"#{_TOP_ID[key]}")
        return {
            "marked": marked,
            "marked_besides_exceptions": marked - _EXCLUDED_FROM_WHOLE[key],
            "tiers": {name: getattr(w, "_tier", None) for name, w in widgets.items()},
            "widths": {name: w.size.width for name, w in widgets.items()},
            "heights": {name: w.region.height for name, w in widgets.items()},
            "hidden": hidden,
            "clipped": clipped,
            "overflow": _overflow(screen, key, widgets),
            "taller": TALLER_HINT in _screen_text(pilot.app).split("\n")[0],
            "scroll": scroll,
            "top_height": top.region.height,
            "top_floor": int(top.styles.min_height.value),
        }


def _assert_whole(r: dict, where: str) -> None:
    assert not r["marked_besides_exceptions"], (where, sorted(r["marked_besides_exceptions"]))
    assert not r["clipped"], f"{where}: a line is CSS-clipped and nothing says so: {r['clipped']}"
    assert not any(r["hidden"].values()), (
        f"{where}: a table hides columns behind a horizontal scroll with no marker: {r['hidden']}"
    )


# ---------------------------------------------------------------------------
# The column pins
# ---------------------------------------------------------------------------

_WIDTH_SWEEP = (
    [("s", "capture", w) for w in boundary_set(SURF_SWARM_FULL_LAYOUT_COLUMNS, 60, 159, *_S_THRESHOLDS)]
    + [("s", "worst-s", w) for w in boundary_set(SURF_SWARM_FULL_LAYOUT_COLUMNS, 126, 156, *_S_THRESHOLDS)]
    + [("a", "capture", w) for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 159, *_A_THRESHOLDS)]
    + [("a", "worst-a", w) for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 149, *_A_THRESHOLDS)]
)


@pytest.mark.parametrize("key,payload_name,width", _WIDTH_SWEEP)
async def test_the_body_is_whole_from_its_pinned_width(key, payload_name, width) -> None:
    """The sweep, both bodies. Whole means every panel but the named
    exceptions, no CSS-clipped line, no hidden column and no region past
    its container -- the region check applies to the exceptions too. Below
    the pin something other than an exception must advertise the loss."""
    r = await _render(PAYLOADS[payload_name](), (width, _COLUMN_SWEEP_HEIGHT), key)
    where = f"{key}/{payload_name} at {width}"
    assert not r["overflow"], f"{where}: a panel's region extends past its container's: {r['overflow']}"
    if width >= _COLUMN_PIN[key]:
        _assert_whole(r, where)
    else:
        assert r["marked_besides_exceptions"] or r["clipped"] or any(r["hidden"].values()), (
            f"{where}: nothing besides the named exceptions advertises the loss"
        )


@pytest.mark.parametrize("key", sorted(_COLUMN_PIN))
@pytest.mark.parametrize("payload_name", sorted(PAYLOADS))
async def test_the_column_pin_is_whole_for_every_payload(key, payload_name) -> None:
    r = await _render(PAYLOADS[payload_name](), (_COLUMN_PIN[key], _COLUMN_SWEEP_HEIGHT), key)
    assert not r["overflow"], (key, payload_name, r["overflow"])
    _assert_whole(r, f"{key}/{payload_name} at the pin")
    assert r["tiers"][_BINDING_PANEL[key]] == "full", r["tiers"]


@pytest.mark.parametrize("key", sorted(_COLUMN_PIN))
async def test_the_column_pin_is_not_loose(key) -> None:
    """One column under the pin the binding panel the block names -- and
    only it, besides the exceptions -- is marked and short of ``full``, on
    the capture and on the worst case alike (the two agreed at every width
    swept, so the pin is the panel's, not a payload's)."""
    pin = _COLUMN_PIN[key]
    for payload_name in ("capture", _WORST[key]):
        under = await _render(PAYLOADS[payload_name](), (pin - 1, _COLUMN_SWEEP_HEIGHT), key)
        assert under["marked_besides_exceptions"] == {_BINDING_PANEL[key]}, (
            payload_name, sorted(under["marked_besides_exceptions"]),
        )
        assert under["tiers"][_BINDING_PANEL[key]] != "full", under["tiers"]
        assert not under["overflow"], under["overflow"]


async def test_the_exceptions_are_marked_at_the_pin_and_clear_where_the_blocks_say() -> None:
    """An exception is excluded from "whole" because it is genuinely marked
    there; each clears at a real, reachable width -- neither is a marker
    that is always lit (the v1 JUST SHIPPED defect)."""
    at_pin = await _render(_capture_payload(), (SURF_SWARM_FULL_LAYOUT_COLUMNS, _COLUMN_SWEEP_HEIGHT), "s")
    assert _EXCLUDED_FROM_WHOLE["s"] <= at_pin["marked"], sorted(at_pin["marked"])
    for name, edge in (
        ("SurfSwarmInFlight", INFLIGHT_NEVER_CLEARS_BELOW),
        ("SurfSwarmLaunches", LAUNCHES_NEVER_CLEARS_BELOW),
    ):
        below = await _render(_capture_payload(), (edge - 1, _COLUMN_SWEEP_HEIGHT), "s")
        at = await _render(_capture_payload(), (edge, _COLUMN_SWEEP_HEIGHT), "s")
        assert name in below["marked"], (name, edge - 1, sorted(below["marked"]))
        assert name not in at["marked"], (name, edge, sorted(at["marked"]))
        assert at["tiers"][name] == "full", at["tiers"]

    at_pin = await _render(_capture_payload(), (SURF_AGENT_FULL_LAYOUT_COLUMNS, _COLUMN_SWEEP_HEIGHT), "a")
    assert "SurfSwarmSeatRecord" in at_pin["marked"], sorted(at_pin["marked"])
    below = await _render(_capture_payload(), (RECORD_NEVER_CLEARS_BELOW - 1, _COLUMN_SWEEP_HEIGHT), "a")
    at = await _render(_capture_payload(), (RECORD_NEVER_CLEARS_BELOW, _COLUMN_SWEEP_HEIGHT), "a")
    assert "SurfSwarmSeatRecord" in below["marked"], sorted(below["marked"])
    assert "SurfSwarmSeatRecord" not in at["marked"], sorted(at["marked"])
    assert at["tiers"]["SurfSwarmSeatRecord"] == "full", at["tiers"]
    worst = await _render(_worst_agent_payload(), (RECORD_NEVER_CLEARS_BELOW, _COLUMN_SWEEP_HEIGHT), "a")
    assert "SurfSwarmSeatRecord" in worst["marked"], (
        "a 400-character objective cleared where the capture's 198 do -- the block says it never does"
    )


async def test_launches_hides_no_column_from_the_measured_width() -> None:
    """The ``4fr : 5fr`` seam's one job: no hidden LAUNCHES column at the
    pin or at the app-wide pin, with the edge one column under 138."""
    below = await _render(_capture_payload(), (LAUNCHES_HIDES_NO_COLUMN_FROM - 1, _COLUMN_SWEEP_HEIGHT), "s")
    at = await _render(_capture_payload(), (LAUNCHES_HIDES_NO_COLUMN_FROM, _COLUMN_SWEEP_HEIGHT), "s")
    assert below["hidden"]["SurfSwarmLaunches"] > 0, below["hidden"]
    assert at["hidden"]["SurfSwarmLaunches"] == 0, at["hidden"]
    for width in (SURF_SWARM_FULL_LAYOUT_COLUMNS, FULL_LAYOUT_COLUMNS):
        r = await _render(_worst_swarm_payload(), (width, _COLUMN_SWEEP_HEIGHT), "s")
        assert r["hidden"]["SurfSwarmLaunches"] == 0, (width, r["hidden"])


def test_the_pins_are_the_measured_numbers_and_fit_the_app() -> None:
    """The agreement between the constants and the sweep results, and the
    relations the blocks state. The swarm body is now the widest body on
    the screen -- wider than LAUNCHPAD's 138 and POOL4 MARKET's 119, which
    the v1 file ordered the other way -- and still under the app-wide 143."""
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS == MEASURED_SWARM_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_ROWS == MEASURED_SWARM_ROWS
    assert SURF_AGENT_FULL_LAYOUT_COLUMNS == MEASURED_AGENT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_ROWS == MEASURED_AGENT_ROWS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS > SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS > SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_COLUMNS < SURF_SWARM_FULL_LAYOUT_COLUMNS
    assert LAUNCHES_HIDES_NO_COLUMN_FROM <= SURF_SWARM_FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_ROWS < SURF_SWARM_FULL_LAYOUT_ROWS


# ---------------------------------------------------------------------------
# The row pins
# ---------------------------------------------------------------------------

_HEIGHT_SWEEP = (
    [("s", "capture", r) for r in boundary_set(SURF_SWARM_FULL_LAYOUT_ROWS, 20, 61, 28, 31, 35, 58)]
    + [("s", "worst-s", r) for r in boundary_set(SURF_SWARM_FULL_LAYOUT_ROWS, 30, 50, 31, 35)]
    + [("a", "capture", r) for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 20, 61, 31, 35)]
    + [("a", "worst-a", r) for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 30, 50, 31, 35)]
)


@pytest.mark.parametrize("key,payload_name,rows", _HEIGHT_SWEEP)
async def test_the_body_is_whole_from_its_pinned_height(key, payload_name, rows) -> None:
    """150 columns is past both width pins, so nothing here measures a
    width. At and above the pin ``‹ taller`` is dark; below it, lit. The
    band crosses the owner's 31 and 35 rows, the v1 row pin (28) and the
    58 the `s` top row needed before its floor."""
    r = await _render(PAYLOADS[payload_name](), (_ROW_SWEEP_WIDTH, rows), key)
    if rows >= _ROW_PIN[key]:
        assert not r["taller"], (key, payload_name, rows)
    else:
        assert r["taller"], f"{key}/{payload_name} at {rows}: whole one row under the pin -- loose"


@pytest.mark.parametrize("key", sorted(_ROW_PIN))
async def test_the_row_pin_holds_at_the_column_pin_too(key) -> None:
    """Re-confirmed at the body's own column pin, so the row threshold is not
    an artefact of the 150-column sweep width."""
    pin = _ROW_PIN[key]
    under = await _render(_capture_payload(), (_COLUMN_PIN[key], pin - 1), key)
    at = await _render(_capture_payload(), (_COLUMN_PIN[key], pin), key)
    assert under["taller"] and under["scroll"][_BODY_ID[key]], under["scroll"]
    assert not at["taller"] and not any(at["scroll"].values()), at["scroll"]


@pytest.mark.parametrize("key", sorted(_ROW_PIN))
async def test_the_top_row_floor_is_its_auto_height_panels_own_lines(key) -> None:
    """The one number in the swarm CSS that is not a tier width: each top
    row's ``min-height`` is the fixed line count of its ``height: auto``
    panel (THROUGHPUT sixteen, SEAT RECORD thirteen). Bound here so the floor
    cannot drift from the content it equals: at the pin the panel, the row
    and the floor are one height, and the row never scrolls inside itself
    -- not even at 20 rows, on the worst case."""
    at = await _render(_capture_payload(), (_COLUMN_PIN[key], _ROW_PIN[key]), key)
    floor = at["top_floor"]
    assert at["heights"][_FLOOR_PANEL[key]] == floor == at["top_height"], (
        at["heights"][_FLOOR_PANEL[key]], floor, at["top_height"],
    )
    short = await _render(PAYLOADS[_WORST[key]](), (_COLUMN_PIN[key], 20), key)
    assert short["heights"][_FLOOR_PANEL[key]] == floor, short["heights"]
    assert not short["scroll"][_TOP_ID[key]], "the floored top row is scrolling inside itself"


async def test_no_height_loses_a_row_of_either_body_in_silence() -> None:
    """Wherever a registered container scrolls the marker is lit, and where
    none does it is dark -- neither a silent loss nor a marker crying wolf,
    swept six rows under each pin to twelve over it on the worst case, at
    the body's own column pin."""
    for key in sorted(_ROW_PIN):
        for rows in range(_ROW_PIN[key] - 6, _ROW_PIN[key] + 13):
            r = await _render(PAYLOADS[_WORST[key]](), (_COLUMN_PIN[key], rows), key)
            scrolling = any(r["scroll"][cid] for cid in _REGISTERED_SCROLLERS[key])
            assert r["taller"] == scrolling, (
                key, rows, r["scroll"],
                "body scrolling with the marker dark" if scrolling else "marker lit with nothing scrolling",
            )


# ---------------------------------------------------------------------------
# The key hint
# ---------------------------------------------------------------------------

KEY_HINT_PHRASE = "l launchpad · 4 pool4 · s swarm · a agent"

#: The narrowest terminal at which the WHOLE status bar composites -- the
#: left label through ``3 errors`` and the right label
#: (``maxpane v0.8.3 · textual-dark · surf``) -- measured 2026-09-21 on the
#: frozen payload: 131 with this phrase (left label 93 cells), 121 with the
#: v1 phrase (83). The bar is whole at both swarm pins (134, 141), at
#: LAUNCHPAD's 138 and at the app-wide 143; under 131 the compositor crops
#: the right label at the terminal edge, as it did under 121 before WP7 --
#: the ``4`` body's 119 never had a whole bar with either phrase.
STATUS_BAR_WHOLE_FROM = 131


def test_the_key_hint_is_the_measured_phrase() -> None:
    assert SurfScreen.KEY_HINTS == f"[dim]{KEY_HINT_PHRASE}[/]"


async def _bar_state(width: int) -> tuple[bool, str]:
    """Whether the whole bar composites at *width*, and its line."""
    from maxpane_dashboard.widgets.status_bar import StatusBar

    async with _surf_app(_frozen_payload()).run_test(size=(width, 50)) as pilot:
        await pilot.pause()
        bar = pilot.app.screen.query_one(StatusBar)
        right = bar.query_one("#status-right")
        line = _screen_text(pilot.app).split("\n")[bar.region.y]
        whole = (
            KEY_HINT_PHRASE in line
            and " poll" in line
            and right.region.x + right.region.width <= bar.region.x + bar.region.width
        )
        return whole, line


@pytest.mark.parametrize(
    "width",
    sorted({
        STATUS_BAR_WHOLE_FROM, SURF_AGENT_FULL_LAYOUT_COLUMNS,
        SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_COLUMNS,
        FULL_LAYOUT_COLUMNS,
    }),
)
async def test_the_key_hint_fits_the_status_bar(width) -> None:
    """The phrase gained ``· a agent`` in WP7 and the whole bar must still
    land on the composited status line at every pin the phrase is read at.
    ``l launchpad`` never shortens.

    **What an over-long hint actually does** (measured 2026-09-21 with a
    forty-cell prefix): the left ``Static`` is ``width: auto``, so nothing
    shortens the phrase -- the compositor crops the *bar* at the terminal
    edge and the poll word, the error count and the right label fall off
    the screen while the phrase stays whole. The v1 test grepped for the
    phrase alone and could not fail on that; this one asserts the right
    label's region ends inside the bar's and the poll word is composited
    (a one-word growth of the phrase reddens it at 134 and 141).
    """
    whole, line = await _bar_state(width)
    assert whole, (width, "the bar is cropped by the terminal edge", line)


async def test_the_status_bar_edge_is_where_it_was_measured() -> None:
    """:data:`STATUS_BAR_WHOLE_FROM` is measured, not loose: one column under
    it the right label is cropped."""
    under, line = await _bar_state(STATUS_BAR_WHOLE_FROM - 1)
    assert not under, (STATUS_BAR_WHOLE_FROM - 1, "the bar is whole a column early", line)
    assert STATUS_BAR_WHOLE_FROM <= SURF_AGENT_FULL_LAYOUT_COLUMNS

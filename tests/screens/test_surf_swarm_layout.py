"""Measured SWARM, AGENT and BOARD layouts.

Each body has column and row pins in ``screens/surf.py``. Their measurement
method, binding panel or container, and named exceptions live in the ``#:``
blocks beside those constants; these tests fail when the blocks stop being
true. BOARD and the complete status-text edge were measured on 2026-09-22.

**Re-swept from scratch on 2026-09-21.** Swarm v2 replaced every v1 panel
(THE FIELD, QUEUE, JUST SHIPPED, the v1 hero and THROUGHPUT) with a new
grid -- CAPABILITY beside THROUGHPUT, IN FLIGHT beside LAUNCHES, SITES
beneath. AGENT now shows SEAT beside BY NODE above RECORD, re-swept
on 2026-09-22 for the seat-details handover. Nothing in this file compares against the v1 numbers (116 / 28)
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
from tests.screens.test_surf_screen import _status_bar_whole
from tests.surf_swarm_fixtures import swarm_agent_sources, swarm_capture_v3, swarm_capture_v4
from textual.widgets import DataTable
from maxpane_dashboard.widgets.surf import SurfSwarmBoardHero, SurfSwarmLeaderboard, SurfSwarmFleet

import maxpane_dashboard.data.surf_swarm as sw
from maxpane_dashboard.__main__ import FULL_LAYOUT_COLUMNS
from maxpane_dashboard.analytics.surf_swarm_signals import (
    launch_summary,
    skill_summary,
)
from maxpane_dashboard.screens.surf import (
    BOARD_BODY_ID, SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS,
    AGENT_BODY_ID,
    AGENT_TOP_ID,
    SURF_AGENT_FULL_LAYOUT_COLUMNS,
    SURF_AGENT_FULL_LAYOUT_ROWS,
    RECORD_NEVER_CLEARS_BELOW,
    CAPABILITY_OPTIONAL_FULL_COLUMNS,
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
    SurfSwarmSeatNodes,
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
MEASURED_AGENT_COLUMNS = 138
MEASURED_AGENT_ROWS = 32

#: The `s` body's two named exceptions (``SURF_SWARM_FULL_LAYOUT_COLUMNS``'s
#: block): the outer width at which each one's own ``‹`` goes dark on the
#: capture. Both sit past the width sweep's band, so folding either into
#: "whole" would make the property unpassable rather than strict.
INFLIGHT_NEVER_CLEARS_BELOW = 222
LAUNCHES_NEVER_CLEARS_BELOW = 205
#: LAUNCHES hides a column behind its horizontal scrollbar under this width
#: and none from it -- the ``4fr : 5fr`` seam's one job at the pin.
LAUNCHES_HIDES_NO_COLUMN_FROM = 138

#: Measured tier edges the width sweeps straddle (+-1 each).
_S_THRESHOLDS = (
    87, 93, 108, 116,  # SITES selected columns/tiers; THROUGHPUT fixed lines
    132, 138, 141,    # CAPABILITY compact/full; LAUNCHES selected columns
    177, 222,        # IN FLIGHT compact/full (notes may still clip)
    180, 205,        # LAUNCHES compact/full
)
_A_THRESHOLDS = (
    61, 63, 70,  # RECORD columns; unselected SEAT failure labels clear
    85, 119, # unchanged RECORD compact/full tiers
    105,     # BY NODE selected columns stop clipping
    106, 108,# SEAT fixed lines whole: #420/v3 and #0 captures
    125,     # BY NODE compact
    128,     # SEAT five-digit contributor line whole
    134,     # all AGENT hero fixed content whole
    138,     # BY NODE full
    134,     # complete status bar; BY NODE binds at138
)


_EXCLUDED_FROM_WHOLE = {
    "s": {"SurfSwarmInFlight", "SurfSwarmLaunches"},
    "a": {"SurfSwarmSeatRecord"},
    "b": set(),
}
_BINDING_PANEL = {"s": "SurfSwarmCapability", "a": "SurfSwarmSeatNodes"}
_COLUMN_PIN = {"s": SURF_SWARM_FULL_LAYOUT_COLUMNS, "a": SURF_AGENT_FULL_LAYOUT_COLUMNS}
_ROW_PIN = {"s": SURF_SWARM_FULL_LAYOUT_ROWS, "a": SURF_AGENT_FULL_LAYOUT_ROWS}
_BODY_ID = {"s": SWARM_BODY_ID, "a": AGENT_BODY_ID, "b": BOARD_BODY_ID}
#: Each body's own hero. Its boxes are ``text-overflow: ellipsis``, so a box
#: too narrow for its value is a CSS-clipped line like any panel's, and it
#: counts as one: at and above the pin none may be clipped.
_HERO = {"s": SurfSwarmHero, "a": SurfSwarmAgentHero, "b": SurfSwarmBoardHero}
_TOP_ID = {"s": SWARM_TOP_ID, "a": AGENT_TOP_ID, "b": BOARD_BODY_ID}
#: The `height: auto` panel whose fixed line count is its row's floor.
_FLOOR_PANEL = {"s": "SurfSwarmThroughput", "a": "SurfSwarmSeatVerdicts"}

#: Each panel's own direct container, named rather than derived so a
#: restructure that moves a panel fails loudly here. SITES and RECORD are
#: their bodies' direct children.
_CONTAINER_OF = {
    "b": {SurfSwarmLeaderboard: BOARD_BODY_ID, SurfSwarmFleet: BOARD_BODY_ID},
    "s": {
        SurfSwarmCapability: SWARM_TOP_ID,
        SurfSwarmThroughput: SWARM_TOP_ID,
        SurfSwarmInFlight: SWARM_BOTTOM_ID,
        SurfSwarmLaunches: SWARM_BOTTOM_ID,
        SurfSwarmSites: SWARM_BODY_ID,
    },
    "a": {
        SurfSwarmSeatNodes: AGENT_TOP_ID,
        SurfSwarmSeatVerdicts: AGENT_TOP_ID,
        SurfSwarmSeatRecord: AGENT_BODY_ID,
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
        "swarm_seat_node_rows": sw.seat_node_rows(seat),
        "swarm_seat_teammates": sw.seat_teammates(seat),
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
    selected = sw.choose_seat(seat_rows, None)
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
        "swarm_seat_selected": selected,
        **_seat_keys(seat),
        **swarm_agent_sources(token),
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


def _capture420_payload(name="seat_420") -> dict:
    payload = _capture_payload()
    seat = swarm_seat_capture(name)
    payload.update(_seat_keys(seat), **swarm_agent_sources(420))
    payload["swarm_seat_selected"] = {"token_id": 420, "agent_id": str(seat["agentId"]), "selected_by": "saved"}
    return payload


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
        row["note"] = "dispatch " + "n" * 300
        row["note_kind"] = "dispatch"
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
    """Thirty nodes, 999 teammates, 64-character keys and five-digit counts;
    forty work rows with launch names and 500-character answers. Distinct
    reviews and raw entries differ; node, status and role totals agree. Source
    rows come from committed captures, then their values are stretched."""
    k = _corpus_keys()
    seat0 = swarm_seat_capture("seat_0")
    seat420 = swarm_seat_capture("seat_420")
    work = _cycle(sw.seat_work_rows(seat0), 40)
    for i, row in enumerate(work):
        row["job_id"] = f"{i:08x}-worst-case-job"
        row["node_key"] = "x"*64
        row["launch"] = "evm_project"*6
        row["answer_state"] = "read"
        row["model"] = "claude-sonnet-5"
        row["took_s"] = 3840
        row["answer"] = (
            "build the ERC-4626 vault and wire its deposit and withdraw paths "
            "through the launchpad adapter, then re-sweep every pinned layout; " * 6
        )[:500]
    nodes = _cycle(sw.seat_node_rows(seat0), 30)
    for i, row in enumerate(nodes):
        row.update(
            node_key=f"node{i}_" + "x" * 58,
            reviewed=55_526 if i == 0 else 1,
            won=9_970 if i == 0 else 1,
            onchain=45_527 if i == 0 else 1,
            queued=9_999 if i == 0 else 0,
        )
    teammates = [{"token_id":i,"agent_id":str(i+50_000),"shared_jobs":999-i} for i in range(999)]
    summary = sw.seat_summary_from_seat(seat0)
    summary["runtime"] = sw.seat_summary_from_seat(seat420)["runtime"]
    assert summary["owner"] and summary["runtime"]
    summary.update(
        attempts=99_999, accepted=9_999, reviewed=55_555,
        review_entries=99_999, scored=55_555, collaborators=999,
        review_status={"sent": 35_557, "submitted": 9_999, "queued": 9_999},
        roles=[{"role": "implement", "count": 55_000},
               {"role": "review", "count": 400},
               {"role": "integrate", "count": 155}],
        win_rate=9_999/99_999,
    )
    assert sum(summary["review_status"].values()) == summary["reviewed"]
    assert sum(row["reviewed"] for row in nodes) == summary["reviewed"]
    assert sum(row["won"] for row in nodes) == summary["accepted"]
    assert sum(row["onchain"] for row in nodes) == (
        summary["review_status"]["sent"] + summary["review_status"]["submitted"]
    )
    assert sum(row["queued"] for row in nodes) == summary["review_status"]["queued"]
    assert sum(row["count"] for row in summary["roles"]) == summary["reviewed"]
    assert summary["reviewed"] < summary["review_entries"]
    k.update({
        "swarm_seat_work_rows": work, "swarm_seat_node_rows": nodes,
        "swarm_seat_teammates": teammates, "swarm_seat_summary": summary,
    })
    k["swarm_seat_live"] = dict(k["swarm_seat_live"], live=True, live_state="working", working=99_999, max_concurrency=99_999,
        failures=99_999, paused_until_ts=1_758_456_000, skills=99_999,
        profiles=["profile"+str(i)+"x"*64 for i in range(20)], platform="platform"+"x"*64)
    k["swarm_seat_contrib"] = dict(k["swarm_seat_contrib"], attempts=99_999, accepted=55_555,
        rejected=11_111, pending=33_333, turns=99_999, wall_clock_s=99_999, rank=999, ranked_of=999)
    return _frozen_payload(**k)


def _v3_agent_payload(kind="v3"):
    payload = _capture420_payload()
    payload.update(_seat_keys(swarm_capture_v3("seat_420_with_contributors")))
    if kind in ("pending", "seats-unavailable"):
        payload["swarm_seat_state"] = "pending" if kind == "pending" else None
    elif kind == "workers-unavailable":
        payload.update(swarm_seat_live=None, swarm_workers_as_of_hhmm=None)
    elif kind == "contributors-unavailable":
        payload.update(swarm_seat_contrib=None, swarm_board_as_of_hhmm=None)
    elif kind == "absent":
        payload.update(swarm_agent_sources(99999))
        payload["swarm_seat_selected"] = dict(token_id=99999,agent_id=None,selected_by="saved")
        payload.update(swarm_seat_state="unknown_seat",swarm_seat_summary=None)
    elif kind == "no-seat":
        payload.update(swarm_seat_selected=None,swarm_seat_live=None,swarm_seat_contrib=None,
                       swarm_seat_summary=None,swarm_seat_state=None,
                       swarm_workers_as_of_hhmm=None,swarm_board_as_of_hhmm=None)
    return payload


def _v3_swarm_payload():
    payload = _capture_payload()
    names = ("job_5a4dfb13_dispatch_note", "job_33016bad_two_node_verdict", "job_0ed3e9f8_blocked")
    details = [swarm_capture_v3(name) for name in names]
    payload["swarm_inflight_rows"] = sw.inflight_rows(details, {row["id"]:row for row in details}, now_ts=1_790_042_100)
    return payload


def _polish_agent_payload():
    """Committed v4 seat420 with exact captured submission matches; cap is40.

    Job33016bad remains at its source index125, outside the displayed window.
    The first two jobs have committed captures; other rows stay not_read.
    """
    payload = _capture420_payload()
    payload.update(_seat_keys(swarm_capture_v4("seat_420")))
    payload["swarm_seat_live"] = sw.seat_live(swarm_capture_v4("workers"), 420)
    answers = {}
    for name in ("submissions_73d7dcd7", "submissions_76296dcd", "submissions_33016bad"):
        capture = swarm_capture_v4(name)
        for item in capture["submissions"]:
            if int(item["seat"]["tokenId"]) != 420:
                continue
            point = sw.submission_answer(capture, capture["jobId"], item["hash"], 420)
            answers.setdefault(capture["jobId"], {})[item["hash"]] = dict(point,read_ts=1000.,terminal=True)
    payload["swarm_seat_work_rows"] = sw.enrich_work_rows(payload["swarm_seat_work_rows"], answers)
    return payload


def _polish_swarm_payload():
    payload = _capture_payload()
    payload["swarm_skill_rows"] = sw.skill_rows(swarm_capture_v4("skills")["skills"])
    payload["swarm_skill_summary"] = skill_summary(payload["swarm_skill_rows"])
    return payload


PAYLOADS = {
    "capture": _capture_payload,
    "capture420": _capture420_payload,
    "duplicates420": lambda: _capture420_payload("seat_420_duplicated_reviews"),
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
        from maxpane_dashboard.widgets.status_bar import StatusBar
        bar = screen.query_one(StatusBar)
        right = bar.query_one("#status-right")
        line = _screen_text(pilot.app).split("\n")[bar.region.y]
        status_whole = KEY_HINT_PHRASE in line and _status_bar_whole(pilot.app)
        # Only the explicitly optional two CAPABILITY columns may be shed
        # at baseline. Every original column, no clipping and no hidden scroll
        # remain prerequisites; this is not a whole-panel exception.
        optional_only = set()
        if key == "s":
            capability = widgets["SurfSwarmCapability"]
            columns = tuple(str(c.label) for c in capability.query_one(DataTable).columns.values())
            if (capability._tier == "baseline" and columns ==
                    ("skill", "v", "role", "tier", "judge", "checks", "requires")
                    and not capability._clipped and not hidden["SurfSwarmCapability"]
                    and not any(name == "SurfSwarmCapability" for name, _ in clipped)):
                optional_only.add("SurfSwarmCapability")
        return {
            "status_whole": status_whole,
            "marked": marked,
            "marked_besides_exceptions": marked - _EXCLUDED_FROM_WHOLE[key] - optional_only,
            "tiers": {name: getattr(w, "_tier", None) for name, w in widgets.items()},
            "widths": {name: w.size.width for name, w in widgets.items()},
            "heights": {name: w.region.height for name, w in widgets.items()},
            "hidden": hidden,
            "columns": {name: tuple(str(c.label) for c in w.query_one(DataTable).columns.values()) for name,w in widgets.items() if list(w.query(DataTable))},
            "clipped": clipped,
            "overflow": _overflow(screen, key, widgets),
            "taller": TALLER_HINT in _screen_text(pilot.app).split("\n")[0],
            "scroll": scroll,
            "top_height": top.region.height,
            "top_floor": int(top.styles.min_height.value) if top.styles.min_height is not None else 0,
            "clipped_fields": {name: set(getattr(w, "_clipped_fields", ())) for name,w in widgets.items()},
        }


def _assert_whole(r: dict, where: str) -> None:
    assert r["status_whole"], (where, "status bar cropped")
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
    + [("a", "capture", w) for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 225, *_A_THRESHOLDS)]
    + [("a", name, w) for name in ("capture420", "duplicates420")
       for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 225, *_A_THRESHOLDS)]
    + [("a", "worst-a", w) for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 225, *_A_THRESHOLDS)]
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
        assert r["marked_besides_exceptions"] or r["clipped"] or any(
            value for name, value in r["hidden"].items() if name not in _EXCLUDED_FROM_WHOLE[key]
        ), (
            f"{where}: nothing besides the named exceptions advertises the loss"
        )


@pytest.mark.parametrize("key", sorted(_COLUMN_PIN))
@pytest.mark.parametrize("payload_name", sorted(PAYLOADS))
async def test_the_column_pin_is_whole_for_every_payload(key, payload_name) -> None:
    r = await _render(PAYLOADS[payload_name](), (_COLUMN_PIN[key], _COLUMN_SWEEP_HEIGHT), key)
    assert not r["overflow"], (key, payload_name, r["overflow"])
    _assert_whole(r, f"{key}/{payload_name} at the pin")
    if _BINDING_PANEL[key] == "SurfSwarmCapability":
        assert r["tiers"]["SurfSwarmCapability"] == "baseline", r["tiers"]
        assert r["columns"]["SurfSwarmCapability"] == ("skill","v","role","tier","judge","checks","requires")
    elif _BINDING_PANEL[key] != "StatusBar":
        assert r["tiers"][_BINDING_PANEL[key]] == "full", r["tiers"]
    assert r["status_whole"]


@pytest.mark.parametrize("key", sorted(_COLUMN_PIN))
async def test_the_column_pin_is_not_loose(key) -> None:
    """One column under the pin the binding panel the block names -- and
    only it, besides the exceptions -- is marked and short of ``full``, on
    the capture and on the worst case alike (the two agreed at every width
    swept, so the pin is the panel's, not a payload's)."""
    pin = _COLUMN_PIN[key]
    for payload_name in ("capture", _WORST[key]):
        under = await _render(PAYLOADS[payload_name](), (pin - 1, _COLUMN_SWEEP_HEIGHT), key)
        if _BINDING_PANEL[key] == "StatusBar":
            assert not under["status_whole"], "status bar fits below its full-layout pin"
            assert not under["overflow"]
            continue
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
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS >= SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS > SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_COLUMNS <= SURF_SWARM_FULL_LAYOUT_COLUMNS
    assert LAUNCHES_HIDES_NO_COLUMN_FROM <= SURF_SWARM_FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_ROWS < SURF_SWARM_FULL_LAYOUT_ROWS


# ---------------------------------------------------------------------------
# The row pins
# ---------------------------------------------------------------------------

_HEIGHT_SWEEP = (
    [("s", "capture", r) for r in boundary_set(SURF_SWARM_FULL_LAYOUT_ROWS, 20, 61, 28, 31, 35, 58)]
    + [("s", "worst-s", r) for r in boundary_set(SURF_SWARM_FULL_LAYOUT_ROWS, 30, 50, 31, 35)]
    + [("a", "capture", r) for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 20, 61, 31, 35)]
    + [("a", name, r) for name in ("capture420", "duplicates420")
       for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 20, 61, 31, 35)]
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
    panel (THROUGHPUT sixteen, SEAT thirteen). Bound here so the floor
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

KEY_HINT_PHRASE = "l launchpad · 4 pl4 · s swm · a agt · b brd"

#: Whole status bar measured after §11 abbreviations: cropped through 133,
#: whole from 134, including poll/errors and full right version/theme/game text.
#: Body binders are now LAUNCHPAD 138, SWARM 141, AGENT 138 and BOARD 141.
#: Pool4 protocol 99 and market 119 retain their body-only status exceptions.
STATUS_BAR_WHOLE_FROM = 134


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
            and _status_bar_whole(pilot.app)
        )
        return whole, line


@pytest.mark.parametrize(
    "width",
    sorted({
        STATUS_BAR_WHOLE_FROM, SURF_AGENT_FULL_LAYOUT_COLUMNS,
        SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS, SURF_SWARM_FULL_LAYOUT_COLUMNS,
        SURF_BOARD_FULL_LAYOUT_COLUMNS, FULL_LAYOUT_COLUMNS,
    }),
)
async def test_the_key_hint_fits_the_status_bar(width) -> None:
    """The phrase gained ``· b board`` in WP4 and the whole bar must still
    land on the composited status line at every pin the phrase is read at.
    ``l launchpad`` never shortens.

    **What an over-long hint actually does** (measured 2026-09-21 with a
    forty-cell prefix): the left ``Static`` is ``width: auto``, so nothing
    shortens the phrase -- the compositor crops the *bar* at the terminal
    edge and the poll word, the error count and the right label fall off
    the screen while the phrase stays whole. The v1 test grepped for the
    phrase alone and could not fail on that; this one asserts the right
    label's region ends inside the bar's, its complete expected text is
    composited, and the poll word remains visible. Region bounds alone
    previously passed with the final letter cropped.
    """
    whole, line = await _bar_state(width)
    assert whole, (width, "the bar is cropped by the terminal edge", line)


async def test_the_status_bar_edge_is_where_it_was_measured() -> None:
    """:data:`STATUS_BAR_WHOLE_FROM` is measured, not loose: one column under
    it the right label is cropped."""
    under, line = await _bar_state(STATUS_BAR_WHOLE_FROM - 1)
    assert not under, (STATUS_BAR_WHOLE_FROM - 1, "the bar is whole a column early", line)
    assert STATUS_BAR_WHOLE_FROM <= SURF_AGENT_FULL_LAYOUT_COLUMNS


def _board_payload(kind="capture"):
    from tests.surf_swarm_fixtures import swarm_board_payload, swarm_capture_v3
    payload=_capture_payload()
    payload.update(swarm_board_payload())
    if kind == "v4":
        from tests.surf_swarm_fixtures import swarm_capture_v4
        payload["swarm_fleet"] = sw.fleet(swarm_capture_v4("workers"))
    if kind in ("workers-unread", "contributors-unread", "unread"):
        contributors=None if kind in ("contributors-unread","unread") else swarm_capture_v3("contributors")
        workers=None if kind in ("workers-unread","unread") else swarm_capture_v3("workers")
        payload.update(swarm_board_summary=sw.board_summary(contributors,workers),
                       swarm_board_rows=sw.board_rows(contributors,workers),swarm_fleet=sw.fleet(workers),
                       swarm_board_as_of_hhmm=None if contributors is None else "03:01",
                       swarm_workers_as_of_hhmm=None if workers is None else "04:02")
    if kind=="worst":
        payload=copy.deepcopy(payload)
        row=payload["swarm_board_rows"][0]
        payload["swarm_board_rows"]=[dict(row,rank=i+1,token_id=i,runtime="r"*64,
            devices=99,attempts=99999,accepted=55555,rejected=11111,pending=33333,
            accept_rate=55555/99999,turns=99999,wall_clock_s=99999,
            live_state="working",working=99999) for i in range(999)]
        payload["swarm_board_summary"].update(seats=999,live=99999,paused=99,
            working=99999,capacity=99999,attempts=99999*999,accepted=55555*999,
            rejected=11111*999,pending=33333*999,receipts=99999,tokens_per_completed_job=99999)
        payload["swarm_fleet"].update(
            daemons=[{"value":str(i)+"d"*64,"count":99999-i} for i in range(20)],
            runtimes=[{"value":"r"*64,"count":99999}],
            models=[{"model":"m"*64,"effort":"xhigh","count":99999},
                    {"model":None,"effort":None,"count":99999}],
            paused=[{"token_id":i,"until_ts":1758456000+i,"failures":99999} for i in range(99)])
    return payload


def _assert_board_whole(result,where):
    if where == "worst":
        result = dict(result, marked_besides_exceptions=result["marked_besides_exceptions"] - {"SurfSwarmLeaderboard"})
    _assert_whole(result,where)
    assert result["tiers"]["SurfSwarmLeaderboard"]=="full",result
    assert result["columns"]["SurfSwarmLeaderboard"] == ("#▲","seat","runtime","dev","att","acc","rej","pend","rate","turns","hrs","state"),result
    allowed = {"runtime"} if where == "worst" else set()
    assert result["clipped_fields"]["SurfSwarmLeaderboard"] <= allowed,result


@pytest.mark.parametrize("kind",["capture","v4","worst","workers-unread","contributors-unread","unread"])
async def test_board_full_layout_pin_has_all_columns_and_source_labels(kind):
    result=await _render(_board_payload(kind),(SURF_BOARD_FULL_LAYOUT_COLUMNS,SURF_BOARD_FULL_LAYOUT_ROWS),'b')
    _assert_board_whole(result,kind)
    assert not result['overflow'] and not result['taller'],result

@pytest.mark.parametrize('width',boundary_set(SURF_BOARD_FULL_LAYOUT_COLUMNS,60,225,86,92,94,97,98,121,126,132,133,141))
@pytest.mark.parametrize('kind',['capture','v4','worst'])
async def test_board_width_boundaries(width,kind):
    result=await _render(_board_payload(kind),(width,80),'b')
    assert not result['overflow'],result
    if width>=SURF_BOARD_FULL_LAYOUT_COLUMNS:_assert_board_whole(result,kind)
    else:
        assert 'SurfSwarmLeaderboard' in result['marked'], result
        assert len(result['columns']['SurfSwarmLeaderboard']) < 12, result

@pytest.mark.parametrize('height',boundary_set(SURF_BOARD_FULL_LAYOUT_ROWS,20,61,31,35))
@pytest.mark.parametrize('kind',['capture','v4','worst'])
async def test_board_height_boundaries(height,kind):
    result=await _render(_board_payload(kind),(SURF_BOARD_FULL_LAYOUT_COLUMNS,height),'b')
    measured_rows = SURF_BOARD_FULL_LAYOUT_ROWS - (kind == 'v4')
    assert result['taller']==(height<measured_rows),result

async def test_board_width_pin_is_not_loose():
    result=await _render(_board_payload(),(SURF_BOARD_FULL_LAYOUT_COLUMNS-1,80),'b')
    assert 'SurfSwarmLeaderboard' in result['marked'], result
    assert len(result['columns']['SurfSwarmLeaderboard']) < 12, result


@pytest.mark.parametrize("kind", ["v3","pending","seats-unavailable","workers-unavailable","contributors-unavailable","absent","no-seat"])
async def test_agent_independent_sources_are_whole_at_the_full_pin(kind):
    result=await _render(_v3_agent_payload(kind),(SURF_AGENT_FULL_LAYOUT_COLUMNS,SURF_AGENT_FULL_LAYOUT_ROWS),'a')
    _assert_whole(result,kind)
    assert not result['taller'] and not result['overflow'],result


@pytest.mark.parametrize("payload_name,edge", [("v3",532),("worst",1558)])
async def test_inflight_note_marker_clears_at_its_measured_content_width(payload_name,edge):
    payload=_v3_swarm_payload() if payload_name=="v3" else _worst_swarm_payload()
    for width in (edge-1,edge):
        result=await _render(payload,(width,80),'s')
        assert ("SurfSwarmInFlight" in result['marked']) == (width<edge),result
        assert result['tiers']['SurfSwarmInFlight']=="full",result
        assert not result['overflow'],result


@pytest.mark.parametrize("kind,edge", [("v3",208),("worst",240)])
async def test_agent_contributor_lines_follow_actual_screen_room_without_raising_pin(kind,edge):
    payload = _v3_agent_payload() if kind == "v3" else _worst_agent_payload()
    turns = "2189 turns" if kind == "v3" else "99999 turns"
    async with _surf_app(payload).run_test(size=(138,32)) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press("a")
        for width,one_line in ((138,False),(edge-1,False),(edge,True),(138,False)):
            await pilot.resize_terminal(width,32)
            await pilot.pause()
            seat = pilot.app.screen.query_one(SurfSwarmSeatVerdicts)
            rows = _region_text(pilot.app,seat).splitlines()
            first = next(line for line in rows if "contributors " in line)
            assert (turns in first) is one_line, (width,rows)
            assert seat.query_one("#surf-swarm-verdicts-contributor-time").display is not one_line
            assert pilot.app.screen.query_one(SurfSwarmSeatNodes)._tier == "full"


@pytest.mark.parametrize("kind", ["capture", "worst"])
async def test_board_polish_row_pin_is_tight_and_keeps_fleet_whole(kind):
    below = await _render(_board_payload(kind), (SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS-1), 'b')
    at = await _render(_board_payload(kind), (SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS), 'b')
    assert below['taller'] and any(below['scroll'].values()), below
    assert not at['taller'] and not any(at['scroll'].values()), at
    assert at['heights']['SurfSwarmFleet'] == 16, at
    _assert_board_whole(at,kind)


async def test_polish_record_answer_clearance_matches_committed_v4_window():
    payload=_polish_agent_payload()
    rows=payload["swarm_seat_work_rows"]
    assert len(rows)==191 and rows[0]["job_id"].startswith("76296dcd")
    assert rows[1]["job_id"].startswith("73d7dcd7") and rows[125]["job_id"].startswith("33016bad")
    name="SurfSwarmSeatRecord"
    for width,marked in ((RECORD_NEVER_CLEARS_BELOW-1,True),(RECORD_NEVER_CLEARS_BELOW,False)):
        r=await _render(payload,(width,80),"a")
        assert (name in r["marked"])==marked, (width,r["marked"])
        assert not r["hidden"][name] and not r["overflow"]
        assert r["columns"][name]==("when","job","node","role","state","launch","sub","model","took","answer")
    stress=await _render(_worst_agent_payload(),(RECORD_NEVER_CLEARS_BELOW,80),"a")
    assert name in stress["marked"], "the 500-character answer must still advertise actual clipping"


async def test_polish_agent_retains_existing_pin_with_enriched_record():
    for rows,taller in ((31,True),(32,False)):
        r=await _render(_polish_agent_payload(),(138,rows),"a")
        assert r["taller"]==taller
        assert not r["clipped"] and not r["overflow"] and not any(r["hidden"].values())
        assert r["columns"]["SurfSwarmSeatRecord"]==("when","job","node","state","model","took","answer")


async def test_polish_capability_optional_tier_preserves_baseline_and_clears_at_measured_onset():
    name="SurfSwarmCapability"
    original=("skill","v","role","tier","judge","checks","requires")
    for width in (141,CAPABILITY_OPTIONAL_FULL_COLUMNS-1,CAPABILITY_OPTIONAL_FULL_COLUMNS):
        r=await _render(_polish_swarm_payload(),(width,42),"s")
        full=width>=CAPABILITY_OPTIONAL_FULL_COLUMNS
        assert r["columns"][name]==original+(("inf","acc/att") if full else ())
        assert (name in r["marked"])== (not full)
        assert name not in r["marked_besides_exceptions"]
        assert r["tiers"][name]==("full" if full else "baseline")
        assert not r["hidden"][name] and not r["clipped"] and not r["overflow"] and not r["taller"]
    below=await _render(_polish_swarm_payload(),(140,42),"s")
    assert "checks" not in below["columns"][name]
    assert name in below["marked_besides_exceptions"]
    short=await _render(_polish_swarm_payload(),(141,41),"s")
    assert short["taller"]


def test_polish_capability_full_tier_cap_agrees_in_both_stylesheets():
    import re
    from tests.test_surf_registration import _surf_block
    for css in (SurfScreen.DEFAULT_CSS,_surf_block()):
        rule=re.search(r'SurfSwarmCapability\s*\{([^}]+)\}',css).group(1)
        assert re.search(r'max-width:\s*118;',rule),rule

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

**SWARM re-swept again on 2026-10-03** (``docs/surf_swarm_workflows_spec.md``
WP5): WORKFLOWS took CAPABILITY's place beside THROUGHPUT (CAPABILITY is
parked, its optional-tier sweep retired with it), and THROUGHPUT opens
**collapsed** behind ``x``. Both SWARM pins are certified on every SWARM
payload -- the capture, the worst case, the v3 executing notes and F47's
extra-states payload -- the column pin (141 -> 138, LAUNCHES binds) in both
fold states, the row pin (42 -> 35) collapsed, as the body opens: the
expanded panel needs more rows, and the silent-loss sweep holds it to
lighting the marker wherever it does, in both fold states.

**Layout v3, 2026-10-05:** the owner approved the live 200×48 view before
hardening. IN FLIGHT and the inline fold are retired. LAUNCHES is beside
THROUGHPUT; WORKFLOWS and SITES fill the next rows. The measured pin is
129×35, bound by SITES and the complete status bar. LAUNCHES remains a
content exception. The popup tests own states/cancel reasons and workflow
scrolling; this file measures the body that stays behind those popups.

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
from tests.surf_swarm_fixtures import (swarm_agent_sources, swarm_capture_v3, swarm_capture_v4,
                                       swarm_oracle_capture, swarm_oracle_rows)
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
    SURF_AGENT_FULL_LAYOUT_COLUMNS,
    SURF_AGENT_FULL_LAYOUT_ROWS,
    RECORD_NEVER_CLEARS_BELOW,
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
    SurfSwarmHero,
    SurfSwarmLaunches,
    SurfSwarmSeatCards,
    SurfSwarmSeatRecord,
    SurfSwarmSites,
    SurfSwarmLatestLaunches,
    SurfSwarmWorkflows,
)
from tests.screens._sweeps import boundary_set
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES
from tests.screens.test_surf_screen import (
    _css_clipped_lines,
    _frozen_payload,
    _region_text,
    _screen_text,
    _surf_app,
)
from tests.surf_swarm_fixtures import (
    swarm_capture_v2,
    swarm_capture_v6,
    swarm_details_v2,
    swarm_manifest_v2,
    swarm_seat_capture,
)

# ---------------------------------------------------------------------------
# The measured numbers
# ---------------------------------------------------------------------------

#: What the sweeps found, restated by hand so the pins cannot drift on their
#: own: a pin that moves without a re-sweep reddens the agreement test.
MEASURED_SWARM_COLUMNS = 129
MEASURED_SWARM_ROWS = 35
MEASURED_AGENT_COLUMNS = 139
MEASURED_AGENT_ROWS = 25

#: Full-width LAUNCHES clears the capture's marker at 171 (157 before liq). The production
#: payload may keep marking a parked reason; that is content, not a hidden column.
LAUNCHES_NEVER_CLEARS_BELOW = 171
#: Measured at 35 rows; without vertical scrolling at 80 rows the onset is 75.
LAUNCHES_HIDES_NO_COLUMN_FROM = 77

#: Every measured edge enters the width boundary set.
_S_THRESHOLDS = (
    75, 77,       # LAUNCHES no hidden columns at 80/35 rows
    93,           # LATEST LAUNCHES fixed-width plateau
    101, 103,     # SITES no hidden columns at 80/35 rows
    109, 119,     # WORKFLOWS compact/full in the shared top row
    91, 116, 130, 157, 171,  # LAUNCHES tight liq/compact/compact liq/roomy/full
    121, 129,     # SITES compact/full; status bar whole from 129
)
_A_THRESHOLDS = (
    99, 107, # RECORD compact/full with panel/tok and short models, 2026-09-23
    116, 117, 129,  # captured hero, pending RANK, five-digit stress hero
    126,     # MODEL's 14-cell lines whole (F54, 2026-10-03)
    129,     # complete status bar (layout v3 hint)
    139,     # seat row whole: OWNER's address + icon (binds since the grid)
)


_EXCLUDED_FROM_WHOLE = {
    "s": {"SurfSwarmLaunches"},
    "a": {"SurfSwarmSeatRecord"},
    "b": set(),
}
#: AGENT's binder is its seat-card row (OWNER), whose cards ellipsise rather
#: than mark: one column under the pin it is the one clipped widget. SWARM's
#: is LAUNCHES since CAPABILITY was parked (2026-10-03): one column under the
#: pin it hides its last column behind its own horizontal scrollbar.
#: 2026-10-05: SITES and the full status bar both bind SWARM at 129.
_BINDING_PANEL = {"s": "SurfSwarmSites", "a": "SurfSwarmSeatCards"}
#: Binders built from hero-style boxes: they clip with ``…`` and never mark.
_ELLIPSIS_BINDERS = {"SurfSwarmAgentHero", "SurfSwarmSeatCards"}
#: Binders whose loss under the pin is a ``DataTable`` column behind the
#: table's own horizontal scrollbar. LAUNCHES is also a named exception (its
#: ``‹`` is lit far past the pin), so its marker cannot be the evidence: the
#: hidden column and the visible scrollbar are.
_HIDDEN_COLUMN_BINDERS = {"SurfSwarmLaunches"}
_COLUMN_PIN = {"s": SURF_SWARM_FULL_LAYOUT_COLUMNS, "a": SURF_AGENT_FULL_LAYOUT_COLUMNS}
_ROW_PIN = {"s": SURF_SWARM_FULL_LAYOUT_ROWS, "a": SURF_AGENT_FULL_LAYOUT_ROWS}
_BODY_ID = {"s": SWARM_BODY_ID, "a": AGENT_BODY_ID, "b": BOARD_BODY_ID}
#: Each body's own hero. Its boxes are ``text-overflow: ellipsis``, so a box
#: too narrow for its value is a CSS-clipped line like any panel's, and it
#: counts as one: at and above the pin none may be clipped.
_HERO = {"s": SurfSwarmHero, "a": SurfSwarmAgentHero, "b": SurfSwarmBoardHero}
#: The AGENT body has no top row since its card rows replaced SEAT | BY NODE
#: (2026-09-22): the cards are fixed-height, so only the body can scroll.
_TOP_ID = {"s": SWARM_TOP_ID, "a": AGENT_BODY_ID, "b": BOARD_BODY_ID}
#: The `height: auto` panel whose fixed line count is its row's floor.
_FLOOR_PANEL = {"s": "SurfSwarmLatestLaunches"}

#: Each panel's own direct container, named rather than derived so a
#: restructure that moves a panel fails loudly here. SITES and RECORD are
#: their bodies' direct children.
_CONTAINER_OF = {
    "b": {SurfSwarmLeaderboard: BOARD_BODY_ID, SurfSwarmFleet: BOARD_BODY_ID},
    "s": {
        SurfSwarmWorkflows: SWARM_TOP_ID,
        SurfSwarmLatestLaunches: SWARM_TOP_ID,
        SurfSwarmLaunches: SWARM_BOTTOM_ID,
        SurfSwarmSites: SWARM_BODY_ID,
    },
    "a": {
        SurfSwarmSeatCards: AGENT_BODY_ID,
        SurfSwarmSeatRecord: AGENT_BODY_ID,
    },
}
#: The containers ``_SCROLL_COLUMNS`` registers per mode -- restated by hand
#: (the screen's dict is keyed by mode word); the marker test binds the two.
_REGISTERED_SCROLLERS = {
    "s": (SWARM_BODY_ID, SWARM_TOP_ID),
    "a": (AGENT_BODY_ID,),
}

_COLUMN_SWEEP_HEIGHT = 80
#: SWARM's own column-width sweep runs here, not at ``_COLUMN_SWEEP_HEIGHT``
#: (final review I1, 2026-10-04). LAUNCHES' ``DataTable`` reserves its
#: vertical scrollbar's gutter from the *budget* a tier is chosen against
#: (``SwarmTableBase.GUTTER_COLS``) but only pays it in the table's actual
#: content width while that scrollbar is really painted -- which needs the
#: real row count to outrun the panel's visible rows, something a height of
#: 80 never triggers (the 12-row capture always fits). At 80 the no-hidden-
#: column edge for the capture and every worst-case SWARM payload measures
#: three columns looser (135, not 138) than at the row pin, where the real
#: scrollbar is live and the edge matches the documented pin exactly --
#: this was the gap the ``tight`` tier's own ``TIGHT_WIDTH`` was not
#: re-checked against (``swarm_launches._TIGHT_REPO_COLS``). SITES',
#: WORKFLOWS' and the status bar's onsets measure identically at both
#: heights (probed 2026-10-04), so only the LAUNCHES-bound checks move here;
#: AGENT's own binder (OWNER's seat-card row) is unaffected at either height
#: and keeps ``_COLUMN_SWEEP_HEIGHT``.
#: 2026-10-05: retain both heights; current LAUNCHES edges are 125/123.
_S_COLUMN_SWEEP_HEIGHT = SURF_SWARM_FULL_LAYOUT_ROWS
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
        "swarm_breaker": sw.breaker(health),
        "swarm_services_up": hf.get("services_up"),
        "swarm_inflight_rows": sw.inflight_rows(jobs, details, now_ts=_NOW),
        "swarm_throughput": sw.throughput_facts(jobs, seen, now_ts=_NOW),
        "swarm_skill_rows": skill_rows,
        "swarm_skill_summary": skill_summary(skill_rows),
        "swarm_launch_rows": launch_rows,
        "swarm_launch_summary": launch_summary(launch_rows),
        "swarm_site_rows": sw.site_rows(sites),
        # WORKFLOWS (2026-10-03): the committed ``limit=12`` page, the
        # widget's own row cap -- 8 blocked, 4 completed.
        "swarm_workflow_rows": sw.workflow_rows(swarm_capture_v6("workflows_limit12")["workflows"]),
        "swarm_seat_selected": selected,
        **_seat_keys(seat),
        **swarm_agent_sources(token),
        "swarm_seat_as_of_hhmm": "00:08",
        "swarm_scores_as_of_hhmm": "00:08",
        "swarm_workflows_as_of_hhmm": "00:08",
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
    skills (still served; CAPABILITY is parked), 10 sites, 25 in-flight rows
    with 200-character objectives, and WORKFLOWS' stress table."""
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
        "swarm_workflow_rows": _worst_workflow_rows(),
    })
    return _frozen_payload(**k)


def _worst_workflow_rows() -> list[dict]:
    """WORKFLOWS' stress table: the row cap (12) of the 100-row capture's
    failing rows -- the served failure naming ``0x…c0de`` first -- with an
    unknown 20-character status word, a hostile ``[/x]`` tag, a frontend job
    on every row and 6 KB objectives behind them."""
    rows = [r for r in sw.workflow_rows(swarm_capture_v6("workflows_100")["workflows"])
            if r["failure"]]
    rows.sort(key=lambda r: "0x000000000000000000000000000000000000c0de" not in r["failure"])
    rows = _cycle(rows, 12)
    for i, row in enumerate(rows):
        row["objective"] = ("Deploy the ERC-4626 vault and wire every path. " * 128)[:6000]
        row["frontend_job_id"] = row["frontend_job_id"] or row["contracts_job_id"]
        if i == 1:
            row["status"] = "waiting_for_hosting_"
        if i == 2:
            row["failure"] = "[/x] " + row["failure"]
    return rows


def _extra_states_swarm_payload() -> dict:
    """F47's canned regression (2026-09-22 live render at 142x42: one more
    ``states`` row than the capture cost THROUGHPUT a line it did not have):
    six states and three cancel reasons -- four more lines than the capture's
    two states and ``none``. Collapsed, none of them is painted."""
    payload = _capture_payload()
    payload["swarm_throughput"] = dict(
        payload["swarm_throughput"],
        states=[{"state": "completed", "count": 80}, {"state": "executing", "count": 9},
                {"state": "cancelled", "count": 6}, {"state": "blocked", "count": 3},
                {"state": "assigned", "count": 1}, {"state": "failed", "count": 1}],
        cancel_reasons=[{"reason": "owner cancelled the launch before dispatch", "count": 4},
                        {"reason": "verifier timed out", "count": 1},
                        {"reason": "duplicate", "count": 1}],
    )
    return payload


def _worst_agent_payload() -> dict:
    """Thirty nodes, 999 teammates, 64-character keys and five-digit counts;
    four advertised models, one a 60-character unknown id;
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
    # The three known keys get the named cards (fixed slots since
    # 2026-09-22) and the other 27 sum into OTHERS -- the committed seat_0
    # already serves two such keys. Five-digit counts land in ORACLE *and*
    # in OTHERS (the first unknown node), the narrowest card they can reach;
    # the pair splits the old single node's totals so they still agree with
    # the summary (OTHERS then reads ``5,011 of 50,011``).
    known = tuple(NODE_TITLES)
    for i, row in enumerate(nodes):
        big = {0: 0, len(known): 1}.get(i)
        row.update(
            node_key=known[i] if i < len(known) else f"node{i}_" + "x" * 58,
            reviewed=(27_764, 27_763)[big] if big is not None else 1,
            attempts=(49_986, 49_985)[big] if big is not None else 1,
            accepted=(4_986, 4_985)[big] if big is not None else 1,
            onchain=22_764 if big is not None else 1,
            queued=(5_000, 4_999)[big] if big is not None else 0,
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
        # MODEL (F54): four advertised pairs, sorted as the fold sorts them, so
        # the card shows two and ``+2 more``; the first is a long unknown id
        # the card fits with a visible ``…``.
        models=[{"model": "claude-experimental-frontier-preview-2026-10-01-long-context",
                 "effort": "xhigh"},
                {"model": "claude-fable-5-1", "effort": "high"},
                {"model": "claude-opus-5", "effort": None},
                {"model": "gpt-6-astra", "effort": "medium"}],
    )
    assert sum(summary["review_status"].values()) == summary["reviewed"]
    assert sum(row["reviewed"] for row in nodes) == summary["reviewed"]
    assert sum(row["accepted"] for row in nodes) == summary["accepted"]
    assert sum(row["attempts"] for row in nodes) == summary["attempts"]
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
    # OWNER shows a verified name in place of the address (2026-09-22); a
    # long one is fitted to the address's own 17 cells.
    k["swarm_seat_owner_ens"] = "[/x]" + "n" * 60 + ".eth"
    # F-S5 REWARDS: the widest amount before the compact form, on both lines
    # (``99,999.99 IMD`` over ``$99,999.99``).
    k["swarm_seat_rewards"] = {"imd": 99_999.99, "usd": 99_999.99, "seats": 9_999}
    k["swarm_seat_rewards_state"] = "ok"
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
    rows = sw.enrich_work_rows(payload["swarm_seat_work_rows"], answers)
    payload["swarm_seat_work_rows"] = swarm_oracle_rows(rows)
    return payload


def _production_swarm_payload():
    """v8 production rows plus explicit synthetic Base and RH examples; no live read."""
    from tests.surf_launch_fixtures import fixture, launch_row
    from maxpane_dashboard.analytics.surf_launch_sites import match_sites, site_job_facts
    from maxpane_dashboard.analytics.surf_launch_checks import extract_facts
    raw = fixture("launches_100")["launches"]
    rows = sw.launch_rows(raw)
    for number in (734, 737, 747):
        rows = [launch_row(number) if row["launch_number"] == number else row for row in rows]
    for chain, number, ticker, digit in ((8453, 800, "BASETEST", "b"), (4663, 801, "RHTEST", "c")):
        row = launch_row(chain_id=chain, launch_number=number, ticker=ticker,
                         launch_id=f"{number:08d}-0000-4000-8000-000000000000")
        row["token_address"] = "0x" + digit * 40
        for artifact in row["artifacts"]:
            if artifact["role"] == "token":
                artifact["address"] = row["token_address"]
        rows.append(row)
    sites = fixture("sites")["sites"]
    site_rows = sw.site_rows(sites)
    detail = fixture("launch_737")
    facts = dict(extract_facts(detail), row=detail)
    zto = next(site for site in sites if site["label"] == "zto")
    links = match_sites([zto], {detail["id"]: facts},
                       {zto["id"]: site_job_facts(fixture("job_zto_site"))}, [])
    linked = next(row for row in rows if row["launch_number"] == 737)
    linked.update(site_label=zto["label"], site_ens_name=zto["ensName"],
                  site_link_method=links[zto["id"]]["method"], site_link_trusted=True)
    for site in site_rows:
        if site["label"] == zto["label"]:
            site.update(production_link=True, link_trusted=True, launch_ticker="ZTO",
                        launch_number=737, link_method="named")
    captured = fixture("MANIFEST")["files"]["launches_100"]["captured_at"]
    return _frozen_payload(
        as_of=dt.datetime.fromisoformat(captured.replace("Z", "+00:00")).timestamp(),
        swarm_launch_rows=rows, swarm_launch_summary=launch_summary(rows), swarm_site_rows=site_rows,
        swarm_workflow_rows=sw.workflow_rows(fixture("workflows_100")["workflows"]),
        swarm_agents_online=None, swarm_agents_enrolled=None, swarm_working_now=None,
        swarm_accepted_today=None, swarm_throughput=None, swarm_health_status=None,
        swarm_breaker=None, swarm_services_up=None, swarm_launch_fired=[],
        swarm_launches_as_of_hhmm="00:38", swarm_workflows_as_of_hhmm="00:38")


PAYLOADS = {
    "production-s": _production_swarm_payload,
    "capture": _capture_payload,
    "capture420": _capture420_payload,
    "duplicates420": lambda: _capture420_payload("seat_420_duplicated_reviews"),
    "worst-s": _worst_swarm_payload,
    "worst-a": _worst_agent_payload,
    "v3-s": _v3_swarm_payload,
    "extra-states-s": _extra_states_swarm_payload,
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
    """Open body *key* at *size* and hand back everything measured from it.

    THROUGHPUT always paints its short form; x opens a separate modal."""
    app = _surf_app(payload)
    async with app.run_test(size=size) as pilot:
        await _open_body(pilot, key)
        return _measure(pilot, key)


async def _walk(payload: dict | None, sizes: list[tuple[int, int]], key: str) -> list[dict]:
    """``_render`` at each of *sizes*, in the order given, from ONE mounted app.

    A fresh mount per size pays the app's start-up and first refresh every
    time; a resize pays only the relayout. The two are interchangeable only
    while a resize paints what a fresh mount at that size paints:
    ``test_a_walk_measures_what_a_fresh_mount_measures`` binds that for the
    order SWARM's width sweep walks in. A body whose resize leaves something
    behind must not walk in that direction -- RECORD kept a two-row title
    after a shrink until c668e54, so an AGENT walk would go up, not down."""
    app = _surf_app(payload)
    async with app.run_test(size=sizes[0]) as pilot:
        await _open_body(pilot, key)
        out = [_measure(pilot, key)]
        for size in sizes[1:]:
            await pilot.resize_terminal(*size)
            await pilot.pause()
            out.append(_measure(pilot, key))
    return out


async def _open_body(pilot, key: str) -> None:
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press(key)
    await pilot.pause()
    await pilot.pause()


def _measure(pilot, key: str) -> dict:
    """Everything ``_render`` hands back, read off the body as it stands."""
    screen = pilot.app.screen
    widgets = _widgets(screen, key)
    marked = {name for name, w in widgets.items() if "‹" in _region_text(pilot.app, w)}
    hidden = {}
    hscroll = {}
    for name, w in widgets.items():
        tables = list(w.query(DataTable))
        if tables:
            # A deliberately hidden empty table has no on-screen columns to lose.
            hidden[name] = tables[0].max_scroll_x if tables[0].display else 0
            hscroll[name] = tables[0].show_horizontal_scrollbar if tables[0].display else False
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
    return {
        "status_whole": status_whole,
        "marked": marked,
        "marked_besides_exceptions": marked - _EXCLUDED_FROM_WHOLE[key],
        "tiers": {name: getattr(w, "_tier", None) for name, w in widgets.items()},
        "widths": {name: w.size.width for name, w in widgets.items()},
        "heights": {name: w.region.height for name, w in widgets.items()},
        "hidden": hidden,
        "hscroll": hscroll,
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

#: SWARM payloads; the body always shows short-form throughput since layout v3.
_S_PAYLOADS = ("capture", "worst-s", "v3-s", "extra-states-s", "production-s")

#: SWARM's width sweep: per payload, the widths one mounted app is walked
#: through in ascending order (``_walk``).
_S_WIDTH_WALKS = {
    "capture": boundary_set(SURF_SWARM_FULL_LAYOUT_COLUMNS, 60, 170, *_S_THRESHOLDS),
    **{name: boundary_set(SURF_SWARM_FULL_LAYOUT_COLUMNS, 126, 156, *_S_THRESHOLDS)
       for name in _S_PAYLOADS[1:]},
}

_WIDTH_SWEEP = (
    [("a", "capture", w) for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 225, *_A_THRESHOLDS)]
    + [("a", name, w) for name in ("capture420", "duplicates420")
       for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 225, *_A_THRESHOLDS)]
    + [("a", "worst-a", w) for w in boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 60, 225, *_A_THRESHOLDS)]
)


def _check_width(r: dict, key: str, payload_name: str, width: int) -> None:
    """Every non-exempt panel is whole at the pin; below it a marker, clipping or a hidden column exposes the loss."""
    where = f"{key}/{payload_name} at {width}"
    assert not r["overflow"], f"{where}: a panel's region extends past its container's: {r['overflow']}"
    if width >= _COLUMN_PIN[key]:
        _assert_whole(r, where)
    else:
        assert r["marked_besides_exceptions"] or r["clipped"] or any(
            value and r["hscroll"][name] for name, value in r["hidden"].items()
        ), (
            f"{where}: nothing advertises the loss"
        )


@pytest.mark.parametrize("key,payload_name,width", _WIDTH_SWEEP)
async def test_the_body_is_whole_from_its_pinned_width(key, payload_name, width) -> None:
    """AGENT's sweep, one fresh mount per width (``_check_width`` says what is checked)."""
    height = _S_COLUMN_SWEEP_HEIGHT if key == "s" else _COLUMN_SWEEP_HEIGHT
    r = await _render(PAYLOADS[payload_name](), (width, height), key)
    _check_width(r, key, payload_name, width)


@pytest.mark.parametrize("payload_name", _S_PAYLOADS)
async def test_the_swarm_body_is_whole_from_its_pinned_width(payload_name) -> None:
    """SWARM's sweep: the same checks, one app walked up through the widths."""
    widths = _S_WIDTH_WALKS[payload_name]
    results = await _walk(PAYLOADS[payload_name](), [(w, _S_COLUMN_SWEEP_HEIGHT) for w in widths],
                          "s")
    for width, r in zip(widths, results, strict=True):
        _check_width(r, "s", payload_name, width)


async def test_a_walk_measures_what_a_fresh_mount_measures() -> None:
    """``_walk`` stands in for ``_render`` in SWARM's width sweep only while
    the two hand back equal results. Checked on the capture at the band's
    ends and either side of the pin, in the order the sweep walks; the whole
    sweep was compared size by size, every payload and fold, when the walk
    replaced it (2026-10-05)."""
    pin = SURF_SWARM_FULL_LAYOUT_COLUMNS
    sizes = [(w, _S_COLUMN_SWEEP_HEIGHT) for w in (60, pin - 1, pin, 159)]
    walked = await _walk(PAYLOADS["capture"](), sizes, "s")
    for size, r in zip(sizes, walked, strict=True):
        fresh = await _render(PAYLOADS["capture"](), size, "s")
        assert r == fresh, (size, {k: (r[k], fresh[k]) for k in r if r[k] != fresh[k]})


_PIN_CASES = (
    [(key, name) for key in sorted(_COLUMN_PIN) for name in sorted(PAYLOADS)]
)


@pytest.mark.parametrize("key,payload_name", _PIN_CASES)
async def test_the_column_pin_is_whole_for_every_payload(key, payload_name) -> None:
    height = _S_COLUMN_SWEEP_HEIGHT if key == "s" else _COLUMN_SWEEP_HEIGHT
    r = await _render(PAYLOADS[payload_name](), (_COLUMN_PIN[key], height), key)
    assert not r["overflow"], (key, payload_name, r["overflow"])
    _assert_whole(r, f"{key}/{payload_name} at the pin")
    if key == "s":
        # Every panel at its widest tier except the named exceptions, which
        # mark at the pin by design (``test_the_exceptions_...`` below).
        tiers = {name: tier for name, tier in r["tiers"].items()
                 if tier is not None and name not in _EXCLUDED_FROM_WHOLE[key]}
        assert set(tiers.values()) == {"full"}, r["tiers"]
    elif _BINDING_PANEL[key] != "StatusBar" and _BINDING_PANEL[key] not in _ELLIPSIS_BINDERS:
        assert r["tiers"][_BINDING_PANEL[key]] == "full", r["tiers"]
    assert r["status_whole"]


@pytest.mark.parametrize("key", sorted(_COLUMN_PIN))
async def test_the_column_pin_is_not_loose(key) -> None:
    """One column under each pin its named binder loses content on capture and stress payloads. SWARM uses its real row-pin height."""
    pin = _COLUMN_PIN[key]
    height = _S_COLUMN_SWEEP_HEIGHT if key == "s" else _COLUMN_SWEEP_HEIGHT
    for payload_name in ("capture", _WORST[key]):
        under = await _render(PAYLOADS[payload_name](), (pin - 1, height), key)
        if _BINDING_PANEL[key] == "StatusBar":
            assert not under["status_whole"], "status bar fits below its full-layout pin"
            assert not under["overflow"]
            continue
        if _BINDING_PANEL[key] in _ELLIPSIS_BINDERS:
            assert {name for name, _ in under["clipped"]} == {_BINDING_PANEL[key]}, (
                payload_name, under["clipped"],
            )
            assert not under["marked_besides_exceptions"], under["marked_besides_exceptions"]
            assert under["status_whole"] and not under["overflow"]
            continue
        if _BINDING_PANEL[key] in _HIDDEN_COLUMN_BINDERS:
            binder = _BINDING_PANEL[key]
            assert {name for name, value in under["hidden"].items() if value} == {binder}, (
                payload_name, under["hidden"],
            )
            assert under["hscroll"][binder], "a hidden column with no scrollbar to say so"
            assert not under["marked_besides_exceptions"], under["marked_besides_exceptions"]
            assert not under["clipped"], under["clipped"]
            assert under["status_whole"] and not under["overflow"]
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
        ("SurfSwarmLaunches", LAUNCHES_NEVER_CLEARS_BELOW),
    ):
        below = await _render(_capture_payload(), (edge - 1, _COLUMN_SWEEP_HEIGHT), "s")
        at = await _render(_capture_payload(), (edge, _COLUMN_SWEEP_HEIGHT), "s")
        assert name in below["marked"], (name, edge - 1, sorted(below["marked"]))
        assert name not in at["marked"], (name, edge, sorted(at["marked"]))
        assert at["tiers"][name] == "full", at["tiers"]



async def test_launches_hides_no_column_from_the_measured_width() -> None:
    """At 35 rows LAUNCHES hides a column at 76 and none at 77; the body and app pins clear at both tested heights."""
    below = await _render(_capture_payload(), (LAUNCHES_HIDES_NO_COLUMN_FROM - 1, _S_COLUMN_SWEEP_HEIGHT), "s")
    at = await _render(_capture_payload(), (LAUNCHES_HIDES_NO_COLUMN_FROM, _S_COLUMN_SWEEP_HEIGHT), "s")
    assert below["hidden"]["SurfSwarmLaunches"] > 0, below["hidden"]
    assert at["hidden"]["SurfSwarmLaunches"] == 0, at["hidden"]
    for width in (SURF_SWARM_FULL_LAYOUT_COLUMNS, FULL_LAYOUT_COLUMNS):
        for height in (_S_COLUMN_SWEEP_HEIGHT, _COLUMN_SWEEP_HEIGHT):
            r = await _render(_worst_swarm_payload(), (width, height), "s")
            assert r["hidden"]["SurfSwarmLaunches"] == 0, (width, height, r["hidden"])


async def test_launches_no_hidden_column_onset_without_vertical_scroll() -> None:
    """At 80 rows the capture needs no vertical scrollbar: the no-hidden-column onset is 75."""
    below = await _render(_capture_payload(), (74, _COLUMN_SWEEP_HEIGHT), "s")
    at = await _render(_capture_payload(), (75, _COLUMN_SWEEP_HEIGHT), "s")
    assert below["hidden"]["SurfSwarmLaunches"] > 0, below["hidden"]
    assert at["hidden"]["SurfSwarmLaunches"] == 0, at["hidden"]


@pytest.mark.parametrize("width,tier,hidden", [
    (102, "tight", True), (103, "tight", False), (120, "tight", False),
    (121, "compact", False), (128, "compact", False), (129, "full", False),
])
async def test_sites_tiers_are_the_measured_onsets(width, tier, hidden) -> None:
    """At 35 rows SITES hides no columns from 103, reaches compact at 121 and full at 129. Wider labels and linked jobs are included."""
    r = await _render(_capture_payload(), (width, _S_COLUMN_SWEEP_HEIGHT), "s")
    assert r["tiers"]["SurfSwarmSites"] == tier, (width, r["tiers"]["SurfSwarmSites"])
    assert bool(r["hidden"]["SurfSwarmSites"]) is hidden, (width, r["hidden"])


@pytest.mark.parametrize("width,tier", [
    (108, "tight"), (109, "compact"), (118, "compact"), (119, "full"),
])
async def test_workflows_tiers_are_the_measured_onsets(width, tier) -> None:
    """The shared top-row workflow table reaches compact at 109 and full at 119."""
    r = await _render(_capture_payload(), (width, _S_COLUMN_SWEEP_HEIGHT), "s")
    assert r["tiers"]["SurfSwarmWorkflows"] == tier, (width, r["tiers"])


def test_the_pins_are_the_measured_numbers_and_fit_the_app() -> None:
    """Independent measured pins: SWARM 129x35, AGENT unchanged; the app-wide width remains 143."""
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS == MEASURED_SWARM_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_ROWS == MEASURED_SWARM_ROWS
    assert SURF_AGENT_FULL_LAYOUT_COLUMNS == MEASURED_AGENT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_ROWS == MEASURED_AGENT_ROWS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_COLUMNS <= FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS < SURF_LAUNCHPAD_FULL_LAYOUT_COLUMNS
    assert SURF_SWARM_FULL_LAYOUT_COLUMNS > SURF_POOL4_USER_FULL_LAYOUT_COLUMNS
    assert LAUNCHES_HIDES_NO_COLUMN_FROM < SURF_SWARM_FULL_LAYOUT_COLUMNS
    assert STATUS_BAR_WHOLE_FROM <= SURF_SWARM_FULL_LAYOUT_COLUMNS
    assert SURF_AGENT_FULL_LAYOUT_ROWS < SURF_SWARM_FULL_LAYOUT_ROWS


# ---------------------------------------------------------------------------
# The row pins
# ---------------------------------------------------------------------------

_HEIGHT_SWEEP = (
    [("s", "capture", r) for r in boundary_set(SURF_SWARM_FULL_LAYOUT_ROWS, 20, 61, 28, 31, 35, 58)]
    + [("s", name, r) for name in _S_PAYLOADS[1:]
       for r in boundary_set(SURF_SWARM_FULL_LAYOUT_ROWS, 30, 50, 31, 35)]
    + [("a", "capture", r) for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 20, 61, 31, 35)]
    + [("a", name, r) for name in ("capture420", "duplicates420")
       for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 20, 61, 31, 35)]
    + [("a", "worst-a", r) for r in boundary_set(SURF_AGENT_FULL_LAYOUT_ROWS, 20, 40, 24, 25, 26)]
)


@pytest.mark.parametrize("key,payload_name,rows", _HEIGHT_SWEEP)
async def test_the_body_is_whole_from_its_pinned_height(key, payload_name, rows) -> None:
    """At 150 columns, taller is lit below each row pin and dark from it. Extra throughput states are in a popup and cannot change body height."""
    r = await _render(PAYLOADS[payload_name](), (_ROW_SWEEP_WIDTH, rows), key)
    if rows >= _ROW_PIN[key]:
        assert not r["taller"], (key, payload_name, rows)
    else:
        assert r["taller"], f"{key}/{payload_name} at {rows}: whole one row under the pin -- loose"


@pytest.mark.parametrize("key", sorted(_ROW_PIN))
async def test_the_row_pin_holds_at_the_column_pin_too(key) -> None:
    """Re-confirmed at the body's own column pin, so the row threshold is not
    an artefact of the 150-column sweep width. At that exact point no table
    may hide a column behind its own horizontal scrollbar either (final
    review I1, 2026-10-04): this is the one size where LAUNCHES' real
    vertical scrollbar is live *and* the column pin is in force at once, so
    it is the size the original defect shipped under. Measured clean for
    both SWARM and AGENT (``probe4``/``probe9``, 2026-10-04), so both assert
    rather than one being weakened to report-only."""
    pin = _ROW_PIN[key]
    under = await _render(_capture_payload(), (_COLUMN_PIN[key], pin - 1), key)
    at = await _render(_capture_payload(), (_COLUMN_PIN[key], pin), key)
    assert under["taller"] and under["scroll"][_BODY_ID[key]], under["scroll"]
    assert not at["taller"] and not any(at["scroll"].values()), at["scroll"]
    assert not any(at["hidden"].values()), at["hidden"]
    assert not any(at["hscroll"].values()), at["hscroll"]


@pytest.mark.parametrize("key", sorted(_FLOOR_PANEL))
async def test_the_top_row_floor_fits_all_latest_launches_states(key) -> None:
    """The retained nine-line floor contains all five launch rows or the empty state."""
    for payload_name in _S_PAYLOADS:
        at = await _render(PAYLOADS[payload_name](), (_COLUMN_PIN[key], _ROW_PIN[key]), key)
        floor = at["top_floor"]
        assert at["heights"][_FLOOR_PANEL[key]] <= floor == at["top_height"] == 9, (
            payload_name, at["heights"][_FLOOR_PANEL[key]], floor, at["top_height"],
        )
    short = await _render(PAYLOADS[_WORST[key]](), (_COLUMN_PIN[key], 20), key)
    assert short["heights"][_FLOOR_PANEL[key]] <= floor, short["heights"]
    assert not short["scroll"][_TOP_ID[key]], "the floored top row is scrolling inside itself"


_SILENT_LOSS_CASES = (
    [("s", name) for name in ("worst-s", "extra-states-s")]
    + [("a", "worst-a")]
)


@pytest.mark.parametrize("key,payload_name", _SILENT_LOSS_CASES)
async def test_no_height_loses_a_row_of_either_body_in_silence(key, payload_name) -> None:
    """A registered scrolling container always lights taller. Fixed throughput content cannot extend past the top row without that warning."""
    for rows in boundary_set(_ROW_PIN[key], _ROW_PIN[key] - 6, _ROW_PIN[key] + 12):
        r = await _render(PAYLOADS[payload_name](), (_COLUMN_PIN[key], rows), key)
        scrolling = any(r["scroll"][cid] for cid in _REGISTERED_SCROLLERS[key])
        assert r["taller"] == scrolling, (
            key, payload_name, rows, r["scroll"],
            "body scrolling with the marker dark" if scrolling else "marker lit with nothing scrolling",
        )
        if key == "s" and not scrolling:
            # Nothing scrolls, so THROUGHPUT must be painting every line it has.
            assert r["heights"]["SurfSwarmLatestLaunches"] <= r["top_height"], (rows, r["heights"])


# ---------------------------------------------------------------------------
# The key hint
# ---------------------------------------------------------------------------

KEY_HINT_PHRASE = "x more · 4 pl4 · s swm · a agt · b brd"

#: Whole status bar measured after §11 abbreviations: cropped through 133,
#: whole from 134, including poll/errors and full right version/theme/game text.
#: Body binders are now LAUNCHPAD 138, SWARM 138 (LAUNCHES since 2026-10-03;
#: CAPABILITY bound 141 before it was parked), AGENT 139 and BOARD 141.
#: Pool4 protocol 99 and market 119 retain their body-only status exceptions.
#: 2026-10-05: x more replaces l launchpad; complete from 129, cropped at 128.
STATUS_BAR_WHOLE_FROM = 129


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
    """The whole current hint, poll word and complete right label must reach pixels at every listed body pin."""
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


@pytest.mark.parametrize("kind", ["capture", "worst"])
async def test_board_polish_row_pin_is_tight_and_keeps_fleet_whole(kind):
    below = await _render(_board_payload(kind), (SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS-1), 'b')
    at = await _render(_board_payload(kind), (SURF_BOARD_FULL_LAYOUT_COLUMNS, SURF_BOARD_FULL_LAYOUT_ROWS), 'b')
    assert below['taller'] and any(below['scroll'].values()), below
    assert not at['taller'] and not any(at['scroll'].values()), at
    assert at['heights']['SurfSwarmFleet'] == 22, at  # 16 + blank + five contributor lines
    _assert_board_whole(at,kind)


async def test_polish_record_answer_clearance_matches_committed_v4_window():
    payload=_polish_agent_payload()
    rows=payload["swarm_seat_work_rows"]
    assert {r["panel_state"] for r in rows[:40]} == {"agreed", "off_panel"}
    assert len(rows)==191 and rows[0]["job_id"].startswith("76296dcd")
    assert rows[1]["job_id"].startswith("73d7dcd7") and rows[125]["job_id"].startswith("33016bad")
    name="SurfSwarmSeatRecord"
    joined = await _render(payload, (RECORD_NEVER_CLEARS_BELOW-1,80), "a")
    assert name not in joined["marked"], "joined cuts use the popup affordance"
    # The existing 167-cell exception measures text without popup eligibility.
    # A missing hash exercises the remaining button-less fallback honestly.
    payload = dict(payload, swarm_seat_work_rows=[dict(row, **{
        key: None for key in row if key.startswith('oracle_') or key == 'submission_hash'}) for row in rows])
    for width,marked in ((RECORD_NEVER_CLEARS_BELOW-1,True),(RECORD_NEVER_CLEARS_BELOW,False)):
        r=await _render(payload,(width,80),"a")
        assert (name in r["marked"])==marked, (width,r["marked"])
        assert not r["hidden"][name] and not r["overflow"]
        assert r["columns"][name]==("when","job","node","state","model","took","tok","panel","answer")
    stress=await _render(_worst_agent_payload(),(RECORD_NEVER_CLEARS_BELOW,80),"a")
    assert name in stress["marked"], "the 500-character answer must still advertise actual clipping"


async def test_polish_agent_retains_existing_pin_with_enriched_record():
    for rows,taller in ((SURF_AGENT_FULL_LAYOUT_ROWS-1,True),(SURF_AGENT_FULL_LAYOUT_ROWS,False)):
        r=await _render(_polish_agent_payload(),(SURF_AGENT_FULL_LAYOUT_COLUMNS,rows),"a")
        assert r["taller"]==taller
        assert not r["clipped"] and not r["overflow"] and not any(r["hidden"].values())
        assert r["columns"]["SurfSwarmSeatRecord"]==("when","job","node","state","model","took","tok","panel","answer")


@pytest.mark.sweep
@pytest.mark.parametrize('width,tier',[(98,'tight'),(99,'compact'),(100,'compact'),
                                      (106,'compact'),(107,'full'),(108,'full')])
async def test_oracle_record_tier_onsets_in_agent_body(width,tier):
    result=await _render(_polish_agent_payload(),(width,80),'a')
    name='SurfSwarmSeatRecord'
    assert result['tiers'][name]==tier
    assert 'panel' in result['columns'][name] and 'role' not in result['columns'][name]
    assert ('tok' in result['columns'][name])==(tier=='full')
    assert not result['hidden'][name] and not result['overflow']


@pytest.mark.sweep
async def test_oracle_latest_seat_fits_existing_agent_pin():
    payload=_polish_agent_payload()
    payload.update(_seat_keys(swarm_oracle_capture('seat_420')))
    rows=payload['swarm_seat_work_rows']
    payload['swarm_seat_work_rows']=swarm_oracle_rows(rows)
    assert len(rows)==245 and sum(r['node_key']=='oracle_assess' for r in rows)==243
    for height in (24,25):
        result=await _render(payload,(139,height),'a')
        assert result['taller']==(height<SURF_AGENT_FULL_LAYOUT_ROWS)
        assert not result['overflow'] and not result['clipped'] and not any(result['hidden'].values())


@pytest.mark.parametrize('kind', ['capture', 'capture420', 'duplicates420', 'worst-a', 'polish',
                                  'v3', 'pending', 'seats-unavailable', 'workers-unavailable',
                                  'contributors-unavailable', 'absent', 'no-seat'])
@pytest.mark.parametrize('height', [20, 24, 25, 26, 40])
async def test_agent_merged_rows_boundary(kind, height):
    payload = (PAYLOADS[kind]() if kind in PAYLOADS else
               _polish_agent_payload() if kind == 'polish' else _v3_agent_payload(kind))
    result = await _render(payload, (SURF_AGENT_FULL_LAYOUT_COLUMNS, height), 'a')
    _assert_whole(result, (kind, height))
    assert result['taller'] == (height < SURF_AGENT_FULL_LAYOUT_ROWS)
    assert not result['overflow']


@pytest.mark.parametrize('kind', ['capture', 'capture420', 'duplicates420', 'worst-a', 'polish',
                                  'v3', 'pending', 'seats-unavailable', 'workers-unavailable',
                                  'contributors-unavailable', 'absent', 'no-seat'])
@pytest.mark.parametrize('width', boundary_set(SURF_AGENT_FULL_LAYOUT_COLUMNS, 125, 160, 129, 134))
async def test_agent_merged_cards_width_boundary(kind, width):
    payload = (PAYLOADS[kind]() if kind in PAYLOADS else
               _polish_agent_payload() if kind == 'polish' else _v3_agent_payload(kind))
    result = await _render(payload, (width, 80), 'a')
    assert not result['overflow']
    if width >= SURF_AGENT_FULL_LAYOUT_COLUMNS:
        _assert_whole(result, (kind, width))
    elif kind in ('capture', 'capture420', 'duplicates420', 'worst-a', 'polish', 'v3'):
        assert any(name == 'SurfSwarmSeatCards' for name, _ in result['clipped'])


async def test_busy_agent_words_fit_every_seat_box_at_unchanged_pins():
    from rich.color import Color
    from maxpane_dashboard.widgets.surf.swarm_agent_hero import BOX_IDS
    from maxpane_dashboard.widgets.surf.swarm_agent_cards import SEAT_BOX_IDS

    payload = _v3_agent_payload()
    payload.update(swarm_seat_state='busy', swarm_seat_read='busy')
    size = (SURF_AGENT_FULL_LAYOUT_COLUMNS, SURF_AGENT_FULL_LAYOUT_ROWS)
    result = await _render(payload, size, 'a')
    _assert_whole(result, 'busy')
    assert not result['taller'] and not result['overflow']
    async with _surf_app(payload).run_test(size=size) as pilot:
        await pilot.app.screen._do_refresh()
        await pilot.press('a')
        await pilot.pause()
        screen = pilot.app.screen
        for id_ in [BOX_IDS['accepted'], BOX_IDS['rewards'], *SEAT_BOX_IDS.values()]:
            box = screen.query_one('#' + id_)
            region = _region_text(pilot.app, box)
            if id_ == SEAT_BOX_IDS['collab']:
                assert 'busy · retrying' not in region
            else:
                assert 'busy · retrying' in region
            assert 'busy · retrying' in ' '.join(region.replace('│', ' ').split()), id_
            painted = [''.join(s.text for s in strip) for strip in screen._compositor.render_strips()]
            y = next(y for y in range(box.region.y, box.region.bottom)
                     if 'busy ·' in painted[y][box.region.x:box.region.right])
            x = painted[y].index('busy ·', box.region.x)
            style = screen.get_style_at(x, y)
            assert style.color.get_truecolor(pilot.app.ansi_theme) == Color.parse('yellow').get_truecolor(pilot.app.ansi_theme)
        assert screen.query_one('#' + SEAT_BOX_IDS['runtime']).tooltip is None


# ---------------------------------------------------------------------------
# RECORD's ``f`` filter editor (docs/surf_record_filter_spec.md)
# ---------------------------------------------------------------------------

#: The editor is not a pinned panel: it takes RECORD's place under the seat
#: cards, floors at RECORD's six rows and scrolls inside itself, so its
#: guarantee is geometry at every width -- nothing past its own region, no
#: CSS-clipped line, no horizontal scroll -- and every control reachable by
#: scrolling it. Four columns of groups from ``COMPACT_BELOW`` content cells,
#: two below; sized at both sides of that onset and at the AGENT pin.
_EDITOR_WIDTHS = (60, 101, 102, 103, SURF_AGENT_FULL_LAYOUT_COLUMNS, 170)


@pytest.mark.parametrize('payload_name', ['capture', 'worst-a'])
@pytest.mark.parametrize('width', _EDITOR_WIDTHS)
async def test_the_record_filter_editor_fits_and_reaches_every_control(payload_name, width):
    from textual.widgets import Button, Checkbox, Input, Select
    from maxpane_dashboard.widgets.filter_editor import APPLY_ID, FilterEditorBase
    from maxpane_dashboard.widgets.surf.swarm_record_filter import SurfRecordFilterEditor
    app = _surf_app(PAYLOADS[payload_name]())
    async with app.run_test(size=(width, SURF_AGENT_FULL_LAYOUT_ROWS)) as pilot:
        screen = await _open_agent_editor(pilot)
        editor = screen.query_one(SurfRecordFilterEditor)
        body = screen.query_one(f"#{AGENT_BODY_ID}")
        assert editor.region.height >= 6 and editor.region.width
        assert body.region.contains_region(editor.region) or body.show_vertical_scrollbar
        cards = screen.query_one(SurfSwarmSeatCards)
        assert cards.display and cards.region.height, "the cards stay above the editor"
        assert editor.region.y >= cards.region.bottom, (cards.region, editor.region)
        assert editor.has_class("compact-filter") == (editor.content_size.width < FilterEditorBase.COMPACT_BELOW)
        assert editor.max_scroll_x == 0, "the editor never scrolls sideways"
        assert not _css_clipped_lines(pilot.app, editor), (width, _css_clipped_lines(pilot.app, editor))
        if width >= SURF_AGENT_FULL_LAYOUT_COLUMNS:  # below it the hero ellipsises by design
            assert not _css_clipped_lines(pilot.app, screen.query_one(SurfSwarmAgentHero))
        controls = [*editor.query(Checkbox), *editor.query(Select), *editor.query(Input), *editor.query(Button)]
        assert len(editor.query(Checkbox)) >= 1 and len(controls) >= 9
        left, right = editor.content_region.x, editor.content_region.right
        for control in controls:
            editor.scroll_to_widget(control, animate=False, immediate=True)
            await pilot.pause()
            region = control.region
            assert left <= region.x and region.right <= right, (control, region, editor.content_region)
            assert editor.region.contains_region(region), (control.id, region, editor.region)
        editor.scroll_to_widget(screen.query_one(f"#{APPLY_ID}"), animate=False, immediate=True)
        await pilot.pause()
        assert "APPLY FILTER" in _region_text(pilot.app, editor)


async def _open_agent_editor(pilot):
    await pilot.app.screen._do_refresh()
    await pilot.pause()
    await pilot.press("a")
    await pilot.pause()
    await pilot.press("f")
    for _ in range(50):
        await pilot.pause()
        if pilot.app.screen._record_filter_open:
            break
    await pilot.pause()
    return pilot.app.screen


@pytest.mark.sweep
@pytest.mark.parametrize("payload_name", _S_PAYLOADS)
async def test_the_swarm_body_is_whole_at_eighty_rows(payload_name):
    width = SURF_SWARM_FULL_LAYOUT_COLUMNS
    r = await _render(PAYLOADS[payload_name](), (width, _COLUMN_SWEEP_HEIGHT),
                      "s")
    _check_width(r, "s", payload_name, width)


@pytest.mark.parametrize("width,tier", [(115, "tight"), (116, "compact"), (156, "compact"), (157, "roomy"), (170, "roomy"), (171, "full")])
async def test_v8_production_launch_tiers_are_measured_in_full_width_row(width, tier):
    r = await _render(_production_swarm_payload(), (width, 35), "s")
    assert r["tiers"]["SurfSwarmLaunches"] == tier
    assert r["hidden"]["SurfSwarmLaunches"] == 0

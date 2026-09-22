"""AGENT card rows two and three: SEAT cards (OWNER … TEAMMATES) and NODE cards (ROLES … BOARD).

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

import pytest
from rich.cells import cell_len
from textual.app import App

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data import surf_swarm as fold
from maxpane_dashboard.data.surf_models import SWARM_WIDGET_SIGNATURES
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.surf._fmt import fmt_win_rate, mmdd_hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import NEVER_PAIRED_WORDS
from maxpane_dashboard.widgets.surf.swarm_agent_cards import (
    NO_FEEDBACK_LINE,
    SEAT_BOX_IDS,
    SurfSwarmSeatCards,
)
from maxpane_dashboard.widgets.surf.swarm_node_cards import (
    NODE_BOX_IDS,
    NODE_CARDS,
    NODE_TITLES,
    ROLE_SHORT,
    SurfSwarmNodeCards,
)
from tests.surf_swarm_fixtures import swarm_agent_sources, swarm_capture_v5, swarm_seat_capture

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
            "swarm_seat_owner_ens": None, **over}


def _node_kwargs(**over):
    return {"swarm_seat_summary": copy.deepcopy(SUMMARY),
            "swarm_seat_node_rows": copy.deepcopy(NODE_ROWS),
            "swarm_seat_contrib": copy.deepcopy(CONTRIB),
            "swarm_seat_state": "ok", **over}


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


async def _nodes(**over):
    return await _cards(SurfSwarmNodeCards, NODE_BOX_IDS, _node_kwargs(**over))


# -- the contract -------------------------------------------------------------------


@pytest.mark.parametrize("cls", [SurfSwarmSeatCards, SurfSwarmNodeCards])
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
    assert f"on {fmt_int(SUMMARY['scored'])} scored" in boxes["score"]
    assert "entries" not in boxes["score"]  # reviewed == review_entries on this capture
    assert f"{fmt_int(SUMMARY['collaborators'])} seats" in boxes["collab"]
    assert f"#{TEAMMATES[0]['token_id']} ×{TEAMMATES[0]['shared_jobs']}" in boxes["teammates"]
    assert f"+{len(TEAMMATES) - 2} more" in boxes["teammates"]


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


async def test_score_shows_entries_only_when_they_differ_from_reviewed():
    summary = copy.deepcopy(SUMMARY)
    summary["review_entries"] = summary["reviewed"] + 3
    boxes = await _seat(swarm_seat_summary=summary)
    assert f"{fmt_int(summary['review_entries'])} entries" in boxes["score"]


async def test_score_with_nothing_scored_is_a_real_zero_not_a_failure():
    summary = copy.deepcopy(SUMMARY)
    summary.update(mean_score=None, scored=0)
    boxes = await _seat(swarm_seat_summary=summary)
    assert NO_FEEDBACK_LINE in boxes["score"]
    assert "unavailable" not in boxes["score"]


@pytest.mark.parametrize("state, needle", [("pending", "loading"), ("error", "unavailable")])
async def test_a_seat_state_replaces_every_seats_card_but_not_the_board(state, needle):
    boxes = await _seat(swarm_seat_state=state)
    for key in ("owner", "runtime", "feedback", "score", "collab", "teammates"):
        assert needle in boxes[key].lower(), key
    nodes = await _nodes(swarm_seat_state=state)
    assert needle in nodes["others"].lower()
    assert f"{fmt_int(CONTRIB['accepted'])} acc of" in nodes["board"]


async def test_never_paired_is_said_once_per_row():
    seat = await _seat(swarm_seat_state="unknown_seat")
    nodes = await _nodes(swarm_seat_state="unknown_seat")
    seat_text, node_text = "\n".join(seat.values()), "\n".join(nodes.values())
    assert seat_text.count(NEVER_PAIRED_WORDS) == 1 and NEVER_PAIRED_WORDS in seat["owner"]
    assert node_text.count(NEVER_PAIRED_WORDS) == 1 and NEVER_PAIRED_WORDS in nodes["roles"]
    assert "—" in seat["teammates"] and "—" in nodes["others"]
    assert f"{fmt_int(CONTRIB['accepted'])} acc of" in nodes["board"]


async def test_board_follows_the_contributors_read_not_the_seat():
    boxes = await _nodes(swarm_seat_contrib={**CONTRIB, "listed": False})
    assert "not listed" in boxes["board"]
    boxes = await _nodes(swarm_seat_contrib=None)
    assert "unavailable" in boxes["board"]


async def test_a_long_runtime_is_fitted_with_a_visible_ellipsis():
    summary = copy.deepcopy(SUMMARY)
    summary["runtime"] = "x" * 200
    boxes = await _seat(swarm_seat_summary=summary)
    first = _lines(boxes["runtime"])[1]  # line 0 is the title
    assert first.endswith("…")


# -- NODE row -----------------------------------------------------------------------


async def test_the_node_row_shows_roles_nodes_others_and_board():
    boxes = await _nodes()
    for role in SUMMARY["roles"]:
        assert f"{role['role']} {fmt_int(role['count'])}" in boxes["roles"]
    for i, row in enumerate(NODE_ROWS):
        box = boxes[f"node{i}"]
        assert _lines(box)[0].strip("│ ").startswith(NODE_TITLES[row["node_key"]])
        # The pre-status capture serves no per-node attempts: a count, no rate.
        assert row["attempts"] is None
        assert f"{fmt_int(row['accepted'])} accepted" in box
        assert f"chain {fmt_int(row['onchain'])}" in box
    for i in range(len(NODE_ROWS), NODE_CARDS):
        assert "—" in boxes[f"node{i}"]
    assert _lines(boxes["others"])[0] == "OTHERS"
    assert f"{fmt_int(CONTRIB['accepted'])} acc of {fmt_int(CONTRIB['attempts'])}" in boxes["board"]
    assert f"{fmt_int(CONTRIB['rejected'])} rejected" in boxes["board"]
    assert f"{fmt_int(CONTRIB['pending'])} pending" in boxes["board"]
    assert _lines(boxes["board"])[0] == "BOARD"  # owner 2026-09-22: no source clock


async def test_others_sums_every_node_after_the_named_cards():
    rows = [{"node_key": f"n{i}", "roles": ["implement"], "reviewed": 10 + i,
             "attempts": 10 + i, "accepted": i, "onchain": 5, "queued": 0}
            for i in range(NODE_CARDS + 3)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    rest = rows[NODE_CARDS:]
    others = boxes["others"]
    assert _lines(others)[0] == "OTHERS"
    accepted, attempts = sum(r["accepted"] for r in rest), sum(r["attempts"] for r in rest)
    assert f"{accepted} of {attempts}" in others
    assert fmt_win_rate(accepted / attempts) in others
    assert f"chain {sum(r['onchain'] for r in rest)}" in others
    for i in range(NODE_CARDS):
        assert f"n{i}" in boxes[f"node{i}"]


@pytest.mark.parametrize("n", [1, NODE_CARDS])
async def test_others_with_no_further_nodes_reads_zero_of_zero(n):
    """Owner 2026-09-22: a read list with nothing past the named cards is ``0 of 0``."""
    rows = [{"node_key": f"n{i}", "roles": [], "reviewed": 1, "attempts": 2,
             "accepted": 1, "onchain": 1, "queued": 0} for i in range(n)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    lines = _lines(boxes["others"])
    assert lines[1:] == ["0 of 0", "—", "chain 0"], lines


async def test_node_cards_shorten_roles_and_roles_keeps_them_whole():
    summary = copy.deepcopy(SUMMARY)
    summary["roles"] = [{"role": "implement", "count": 3}, {"role": "review", "count": 2}]
    row = {"node_key": "k", "roles": ["implement", "review", "judge"], "reviewed": 3,
           "attempts": 4, "accepted": 2, "onchain": 0, "queued": 0}
    boxes = await _nodes(swarm_seat_summary=summary, swarm_seat_node_rows=[row])
    assert ROLE_SHORT == {"implement": "impl", "review": "rev"}
    assert "impl · rev · judge" in boxes["node0"] and "implement" not in boxes["node0"]
    assert "implement 3" in boxes["roles"] and "review 2" in boxes["roles"]


async def test_the_node_rate_is_accepted_over_the_nodes_own_attempts():
    row = {"node_key": "k", "roles": [], "reviewed": 3, "attempts": 8, "accepted": 2,
           "onchain": 0, "queued": 0}
    boxes = await _nodes(swarm_seat_node_rows=[row])
    assert "2 of 8" in boxes["node0"]
    assert fmt_win_rate(2 / 8) in boxes["node0"]
    assert fmt_win_rate(2 / 3) not in boxes["node0"]
    assert fmt_win_rate(2 / SUMMARY["attempts"]) not in boxes["node0"]


async def test_the_live_v5_seat_reconciles_node_cards_with_the_hero():
    """2026-09-22 capture: work[] lists every attempt, so no node can exceed 100 %."""
    seat = swarm_capture_v5("seat_420")
    rows = fold.seat_node_rows(seat)
    summary = fold.seat_summary_from_seat(seat)
    assert sum(r["attempts"] for r in rows) == summary["attempts"] == 223
    assert sum(r["accepted"] for r in rows) == summary["accepted"] == 195
    boxes = await _nodes(swarm_seat_node_rows=rows, swarm_seat_summary=summary)
    oracle = next(i for i, r in enumerate(rows) if r["node_key"] == "oracle_assess")
    box = boxes[f"node{oracle}"]
    assert "ORACLE" in _lines(box)[0]
    assert "193 of 221" in box and fmt_win_rate(193 / 221) in box
    titles = {_lines(boxes[f"node{i}"])[0].strip("│╭╮─ ") for i in range(len(rows))}
    assert titles == {"ORACLE", "REVIEW", "BUILD"}
    assert len(rows) == NODE_CARDS and "0 of 0" in boxes["others"]


async def test_others_of_a_pre_status_payload_shows_no_rate():
    """Reviewer M1: with attempts unserved, OTHERS reads ``N accepted``, never ``N of 0``."""
    rows = [{"node_key": f"n{i}", "roles": [], "reviewed": 10 + i, "attempts": None,
             "accepted": i, "onchain": 0, "queued": 0} for i in range(NODE_CARDS + 2)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    accepted = sum(r["accepted"] for r in rows[NODE_CARDS:])
    assert f"{accepted} accepted" in boxes["others"] and " of " not in boxes["others"]


async def test_an_unknown_node_key_keeps_its_own_title():
    row = {"node_key": "future_node", "roles": [], "reviewed": 1, "attempts": 1,
           "accepted": 1, "onchain": 0, "queued": 0}
    boxes = await _nodes(swarm_seat_node_rows=[row])
    assert "future_node" in _lines(boxes["node0"])[0]


async def test_a_hostile_node_key_is_shown_literally():
    row = {"node_key": "[/x][b]evil", "roles": ["[red]r"], "reviewed": 1, "attempts": 1,
           "accepted": 1, "onchain": 1, "queued": 0}
    boxes = await _nodes(swarm_seat_node_rows=[row])
    assert "[/x][b]evil" in boxes["node0"]
    assert "[red]r" in boxes["node0"]


async def test_no_nodes_and_an_unread_list_differ():
    boxes = await _nodes(swarm_seat_node_rows=[])
    assert "no nodes yet" in boxes["node0"] and "—" in boxes["node1"]
    boxes = await _nodes(swarm_seat_node_rows=None)
    assert "unavailable" in boxes["node0"]
    assert "0 of 0" not in boxes["others"] and "—" in boxes["others"]


async def test_roles_and_teammates_fold_their_overflow():
    summary = copy.deepcopy(SUMMARY)
    summary["roles"] = [{"role": f"r{i}", "count": i + 1} for i in range(5)]
    boxes = await _nodes(swarm_seat_summary=summary)
    assert "+3 more" in boxes["roles"] and "r0 1" in boxes["roles"] and "r2" not in boxes["roles"]
    boxes = await _seat(swarm_seat_teammates=[])
    assert "none yet" in boxes["teammates"]
    boxes = await _seat(swarm_seat_teammates=None)
    assert "unavailable" in boxes["teammates"]


async def test_a_long_node_key_is_fitted_into_its_title():
    row = {"node_key": "k" * 120, "roles": [], "reviewed": 1, "attempts": 1, "accepted": 1,
           "onchain": 0, "queued": 0}
    boxes = await _nodes(swarm_seat_node_rows=[row])
    frame, title = boxes["node0"].split("\n")[:2]
    assert "k…" in title
    assert cell_len(title) == cell_len(frame)


async def test_a_long_role_name_is_fitted_so_its_count_survives():
    summary = copy.deepcopy(SUMMARY)
    summary["roles"] = [{"role": "r" * 200, "count": 71}]
    boxes = await _nodes(swarm_seat_summary=summary)
    line = _lines(boxes["roles"])[1]  # line 0 is the title
    assert line.endswith("… 71")

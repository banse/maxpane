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


async def _nodes(size=SIZE, **over):
    return await _cards(SurfSwarmNodeCards, NODE_BOX_IDS, _node_kwargs(**over), size=size)


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



def _row(key, **over):
    return {"node_key": key, "roles": [], "reviewed": 1, "attempts": 2, "accepted": 1,
            "onchain": 1, "queued": 0, **over}


CARD_KEYS = tuple(NODE_TITLES)

async def test_the_node_row_shows_roles_nodes_others_and_board():
    boxes = await _nodes()
    for role in SUMMARY["roles"]:
        assert f"{role['role']} {fmt_int(role['count'])}" in boxes["roles"]
    by_key = {r["node_key"]: r for r in NODE_ROWS}
    for i, key in enumerate(CARD_KEYS):
        box = boxes[f"node{i}"]
        assert _lines(box)[0] == NODE_TITLES[key], "a card is titled by its slot, worked or not"
        row = by_key.get(key)
        if row is None:
            assert _lines(box)[1:] == ["—"]
            continue
        # The pre-status capture serves no per-node attempts: a count, no rate.
        assert row["attempts"] is None
        assert f"{fmt_int(row['accepted'])} accepted" in box
        assert f"chain {fmt_int(row['onchain'])}" in box
    assert _lines(boxes["others"])[0] == "OTHERS"
    assert f"{fmt_int(CONTRIB['accepted'])} acc of {fmt_int(CONTRIB['attempts'])}" in boxes["board"]
    assert f"{fmt_int(CONTRIB['rejected'])} rejected" in boxes["board"]
    assert f"{fmt_int(CONTRIB['pending'])} pending" in boxes["board"]
    assert _lines(boxes["board"])[0] == "BOARD"  # owner 2026-09-22: no source clock


async def test_each_card_keeps_its_title_and_dashes_when_its_node_has_no_work():
    """Owner 2026-09-22 (image of a seat with only oracle work): REVIEW and BUILD
    keep their titles and read a dim dash, and so does an empty OTHERS."""
    boxes = await _nodes(swarm_seat_node_rows=[_row("oracle_assess", attempts=4, accepted=3)])
    assert [_lines(boxes[f"node{i}"])[0] for i in range(NODE_CARDS)] == ["ORACLE", "REVIEW", "BUILD"]
    assert "3 of 4" in boxes["node0"]
    for box in (boxes["node1"], boxes["node2"], boxes["others"]):
        assert _lines(box)[1:] == ["—"], box


async def test_the_card_order_follows_the_slots_not_the_folds_order():
    rows = [_row("build_contract_project", accepted=7, attempts=7),
            _row("oracle_assess", accepted=5, attempts=9)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    assert "5 of 9" in boxes["node0"] and "7 of 7" in boxes["node2"]
    assert _lines(boxes["node1"])[1:] == ["—"]


async def test_a_node_with_zero_values_dashes_its_card_and_others():
    rows = [_row("adversarial_review", attempts=0, accepted=0, onchain=0),
            _row("future_node", attempts=0, accepted=0, onchain=0),
            _row("other_node", attempts=None, accepted=0, onchain=0)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    assert _lines(boxes["node1"]) == ["REVIEW", "—"]
    assert _lines(boxes["others"]) == ["OTHERS", "—"], "0 of 0 is a dash (owner, 2026-09-22)"


async def test_others_sums_every_node_no_card_names():
    rest = [_row(f"n{i}", roles=["implement"], reviewed=10 + i, attempts=10 + i, accepted=i,
                 onchain=5) for i in range(4)]
    rows = [_row(key) for key in CARD_KEYS] + rest
    boxes = await _nodes(swarm_seat_node_rows=rows)
    others = boxes["others"]
    assert _lines(others)[0] == "OTHERS"
    accepted, attempts = sum(r["accepted"] for r in rest), sum(r["attempts"] for r in rest)
    assert f"{accepted} of {attempts}" in others
    assert fmt_win_rate(accepted / attempts) in others
    assert f"chain {sum(r['onchain'] for r in rest)}" in others
    for i in range(NODE_CARDS):
        assert "1 of 2" in boxes[f"node{i}"]


async def test_node_cards_shorten_roles_and_roles_keeps_them_whole():
    summary = copy.deepcopy(SUMMARY)
    summary["roles"] = [{"role": "implement", "count": 3}, {"role": "review", "count": 2}]
    row = {"node_key": "oracle_assess", "roles": ["implement", "review", "judge"], "reviewed": 3,
           "attempts": 4, "accepted": 2, "onchain": 0, "queued": 0}
    boxes = await _nodes(swarm_seat_summary=summary, swarm_seat_node_rows=[row])
    assert ROLE_SHORT == {"implement": "impl", "review": "rev"}
    assert "impl · rev · judge" in boxes["node0"] and "implement" not in boxes["node0"]
    assert "implement 3" in boxes["roles"] and "review 2" in boxes["roles"]


async def test_the_node_rate_is_accepted_over_the_nodes_own_attempts():
    row = {"node_key": "oracle_assess", "roles": [], "reviewed": 3, "attempts": 8, "accepted": 2,
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
    box = boxes["node0"]
    assert _lines(box)[0] == "ORACLE"
    assert "193 of 221" in box and fmt_win_rate(193 / 221) in box
    assert [_lines(boxes[f"node{i}"])[0] for i in range(NODE_CARDS)] == ["ORACLE", "REVIEW", "BUILD"]
    assert {r["node_key"] for r in rows} == set(CARD_KEYS)
    assert _lines(boxes["others"]) == ["OTHERS", "—"]


async def test_others_of_a_pre_status_payload_shows_no_rate():
    """Reviewer M1: with attempts unserved, OTHERS reads ``N accepted``, never ``N of 0``."""
    rows = [{"node_key": f"n{i}", "roles": [], "reviewed": 10 + i, "attempts": None,
             "accepted": i + 1, "onchain": 0, "queued": 0} for i in range(2)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    accepted = sum(r["accepted"] for r in rows)
    assert f"{accepted} accepted" in boxes["others"] and " of " not in boxes["others"]


async def test_an_unknown_node_key_never_titles_a_card_and_sums_into_others():
    """Titles are the slots' words since 2026-09-22, so an unknown, hostile or
    very long key cannot reach a title: it is counted in OTHERS, never shown."""
    rows = [_row("future_node", accepted=2, attempts=3),
            _row("[/x][b]evil", accepted=1, attempts=1),
            _row("k" * 120, accepted=1, attempts=2)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    assert [_lines(boxes[f"node{i}"])[0] for i in range(NODE_CARDS)] == ["ORACLE", "REVIEW", "BUILD"]
    text = "\n".join(boxes.values())
    assert "future_node" not in text and "evil" not in text and "kkk" not in text
    assert "4 of 6" in boxes["others"]


async def test_a_hostile_role_is_shown_literally():
    row = _row("oracle_assess", roles=["[red]r"])
    boxes = await _nodes(swarm_seat_node_rows=[row])
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


async def test_a_long_role_name_is_fitted_so_its_count_survives():
    summary = copy.deepcopy(SUMMARY)
    summary["roles"] = [{"role": "r" * 200, "count": 71}]
    boxes = await _nodes(swarm_seat_summary=summary)
    line = _lines(boxes["roles"])[1]  # line 0 is the title
    assert line.endswith("… 71")


async def test_a_node_with_only_chain_reviews_keeps_its_card_and_others():
    """Review 2026-09-23: the node fold counts ``accepted`` from work and
    ``onchain`` from reviews, so a reviews-only node has 0 accepted, no
    attempts and a real chain count -- that is not an empty card."""
    rows = [_row("oracle_assess", attempts=None, accepted=0, onchain=12),
            _row("manifest", attempts=None, accepted=0, onchain=3)]
    boxes = await _nodes(swarm_seat_node_rows=rows)
    assert "chain 12" in boxes["node0"] and _lines(boxes["node0"])[1:] != ["—"]
    assert "chain 3" in boxes["others"] and _lines(boxes["others"])[1:] != ["—"]


async def test_node_counts_go_compact_only_when_the_full_form_does_not_fit():
    """A number is never cut: ``99,9…`` became ``100K`` (review 2026-09-23)."""
    big = _row("manifest", attempts=99_970, accepted=9_970, onchain=45_527)
    narrow = await _nodes(swarm_seat_node_rows=[big], size=(110, 30))
    assert "10K of 100K" in narrow["others"] and "…" not in narrow["others"]
    assert "chain 45,527" in narrow["others"], "each line shortens only as far as it must"
    mid = await _nodes(swarm_seat_node_rows=[_row("manifest", attempts=50_011, accepted=5_011)],
                       size=(110, 30))
    assert "5.0K of 50.0K" in mid["others"], "one decimal first, whole thousands only if needed"
    wide = await _nodes(swarm_seat_node_rows=[big], size=(200, 30))
    assert "9,970 of 99,970" in wide["others"] and "chain 45,527" in wide["others"]

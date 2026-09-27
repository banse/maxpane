"""LEDGER (spec §8 LEDGER; contract §C.15): every accepted line, the plane's verdict beside it, never on one line.

Composited assertions only, on the WP1 healthy fixture folded by the manager's own
``fold_status_document`` and on hand-built rows in the frozen ``SEAT_ROW_KEYS["seat_tasks_rows"]``
shape. Mutation proofs: ``test_masked_key_never_reaches_the_ledger`` (proof 12, ledger half) --
drop ``redact`` from ``_word`` -> red; ``test_pending_is_yellow_never_green_and_unknown_is_a_question_mark``
-- paint pending green -> red.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from textual.app import App
from textual.widgets import DataTable

from maxpane_dashboard.app import CSS_PATH
from maxpane_dashboard.data.seat_models import SEAT_ROW_KEYS, SEAT_WIDGET_SIGNATURES, fold_status_document
from maxpane_dashboard.widgets import explorer as X
from maxpane_dashboard.widgets.swarm_table import SwarmTableBase, table_cols
from maxpane_dashboard.widgets.seat.ledger import COMPACT_WIDTH, FULL_WIDTH, TIGHT_WIDTH, SeatLedgerTable, older_line
from tests.widgets.address_probe import link_targets
from tests.widgets.surf_compositing import composite_lines

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
SIGNATURE = SEAT_WIDGET_SIGNATURES["SeatLedgerTable"]
GUTTER = SwarmTableBase.GUTTER_COLS
SIZE = (FULL_WIDTH + GUTTER, 12)
MASKED = "sk-svcac********"


def _healthy(**overrides) -> dict:
    flat = fold_status_document(json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8")))
    payload = {key: copy.deepcopy(flat[key]) for key in SIGNATURE}
    payload.update(overrides)
    return payload


def _row(**changes) -> dict:
    row = copy.deepcopy(_healthy()["seat_tasks_rows"][0])
    row.update(changes)
    return row


async def _ledger(size=SIZE, **payload) -> list[str]:
    return await composite_lines(SeatLedgerTable, size, css_path=CSS_PATH, region_only=True, **payload)


def _row_with(rows, needle) -> str:
    return next(line for line in rows if needle in line)


# -- shape ---------------------------------------------------------------------------------


def test_the_ten_columns_and_three_tiers_are_the_contract_s():
    keys = tuple(k for k, _l, _w in SeatLedgerTable.COLUMN_SPECS)
    assert keys == ("when", "node", "role", "model", "took", "turns", "out", "stored", "verdict", "lag")
    assert [l for _k, l, _w in SeatLedgerTable.COLUMN_SPECS] == ["when", "node", "role", "model~tier", "took", "turns", "out tok", "stored", "verdict", "lag"]
    assert [w for _k, _l, w in SeatLedgerTable.COLUMN_SPECS] == [11, 8, 9, 22, 7, 5, 7, 6, 22, 6]
    assert set(SeatLedgerTable.TIER_COLUMNS["full"]) == set(keys)
    assert set(SeatLedgerTable.TIER_COLUMNS["compact"]) == set(keys) - {"lag", "role"}
    assert SeatLedgerTable.TIER_COLUMNS["tight"] == ("when", "node", "took", "stored", "verdict")
    assert FULL_WIDTH == table_cols([11, 8, 9, 22, 7, 5, 7, 6, 22, 6]) == 123
    assert COMPACT_WIDTH == table_cols([11, 8, 22, 7, 5, 7, 6, 22]) == 104
    assert TIGHT_WIDTH == table_cols([11, 8, 7, 6, 22]) == 64
    assert SeatLedgerTable.LADDER.steps == (("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH))
    assert SeatLedgerTable.ROW_CAP == 20 and SeatLedgerTable.TITLE == "LEDGER" and SeatLedgerTable.TABLE_ID == "seat-ledger-table"


def test_the_folded_rows_carry_exactly_the_frozen_shape():
    for row in _healthy()["seat_tasks_rows"]:
        assert tuple(row) == SEAT_ROW_KEYS["seat_tasks_rows"]


async def test_none_is_unavailable_empty_is_the_sentence_and_no_args_never_raises():
    bare = "\n".join(await composite_lines(SeatLedgerTable, SIZE, css_path=CSS_PATH, region_only=True))
    assert "ledger unavailable" in bare and "Loading" not in bare
    empty = "\n".join(await _ledger(**_healthy(seat_tasks_rows=[])))
    assert "no tasks in the window" in empty and "unavailable" not in empty


# -- the healthy rows, every column -------------------------------------------------------


async def test_a_stored_accepted_row_renders_every_column():
    rows = await _ledger(**_healthy())
    header = _row_with(rows, "when").split()
    assert header == ["when", "node", "role", "model~tier", "took", "turns", "out", "tok", "stored", "verdict", "lag"]
    line = _row_with(rows, "0c1f9727")
    # the model column is 22 cells (contract §C.15), so ``luna 6 ~economy/standard`` (24) paints as ``luna 6 ~economy/stand…``
    for cell in ("0c1f9727", "implement", "luna 6 ~economy", "32 s", " 3 ", "812", "✓", "accepted +15m", "15m"):
        assert cell in line, (cell, line)
    failed = _row_with(rows, "7073b7a6")
    assert "failed runtime_error" in failed and "34 s" in failed and "✓" in failed
    assert rows[0].strip().startswith("LEDGER · as of ")


async def test_the_node_cell_links_the_row_s_job_on_the_imd_explorer():
    class _A(App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield SeatLedgerTable()

    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SeatLedgerTable).update_data(**_healthy())
        await pilot.pause()
        painted = ["".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips()]
        links = link_targets(pilot.app)
    y = next(i for i, line in enumerate(painted) if "0c1f9727" in line)
    x = painted[y].index("0c1f9727")
    job = _healthy()["seat_tasks_rows"][0]["jobId"]
    cells = [t for t in links if t[1] == y]
    assert [t[0] for t in cells] == list(range(x, x + 8)), "the whole shown node8, no more"
    assert {t[2:] for t in cells} == {("imd", "job", job, f"https://explorer.imd.fun/jobs/{job}")}
    assert X.is_job_id(job)


async def test_an_api_only_history_row_reads_api_and_a_bad_job_id_never_links():
    rows = [_row(nodeId8=None, nodeId=None), _row(jobId="not-a-uuid", nodeId8="deadbeef")]

    class _A(App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield SeatLedgerTable()

    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SeatLedgerTable).update_data(**_healthy(seat_tasks_rows=rows))
        await pilot.pause()
        painted = ["".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips()]
        links = link_targets(pilot.app)
    assert any(" api " in line for line in painted)
    assert all(t[4] != "not-a-uuid" for t in links)
    assert any("deadbeef" in line for line in painted)


# -- row states (spec §5.1 ledger rules, §8 LEDGER) --------------------------------------


@pytest.mark.parametrize("changes,cells", [
    ({"preAgentFailure": True, "agentRan": False, "durationS": 0.4, "model": None, "turns": None, "tokens": None}, ("0.4 s", "no agent")),
    ({"leaseClosed": True, "storedUtc": None, "hash12": None, "outcome": "unknown"}, ("no row", "—")),
    ({"cancelled": "superseded", "storedUtc": None, "hash12": None, "outcome": "unknown"}, ("cancelled superseded",)),
    ({"repair": True}, ("✓↻",)),
    ({"resent": True}, ("✓⟲",)),
    ({"sessionFiles": 2}, ("✓×2",)),
    ({"submittedUtc": None, "storedUtc": None, "hash12": None, "outcome": "unknown", "durationS": None}, ("—",)),
    ({"interruptedByRestart": True, "storedUtc": None, "hash12": None, "outcome": "unknown"}, ("interrupted by restart",)),
    ({"kind": "research", "role": None}, ("question",)),
    ({"outcome": "failed", "failureReason": None, "verdictLagS": None}, ("failed ·",)),
    ({"outcome": "rejected", "verdictLagS": 120}, ("rejected", "2m")),
], ids=lambda v: str(v)[:40])
async def test_row_states_render_their_marks(changes, cells):
    rows = await _ledger(**_healthy(seat_tasks_rows=[_row(**changes)]))
    line = _row_with(rows, "0c1f9727")
    for cell in cells:
        assert cell in line, (cell, line)


async def test_pending_is_yellow_never_green_and_unknown_is_a_question_mark():
    class _A(App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield SeatLedgerTable()

    async with _A().run_test(size=SIZE) as pilot:
        pilot.app.query_one(SeatLedgerTable).update_data(**_healthy(seat_tasks_rows=[_row(outcome="pending", verdictLagS=None)]))
        await pilot.pause()
        painted = ["".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips()]
        y = next(i for i, line in enumerate(painted) if "pending" in line)
        x = painted[y].index("pending")
        colour = pilot.app.screen.get_style_at(x, y).color.get_truecolor()
        ansi = pilot.app.ansi_theme.ansi_colors
        assert colour == ansi[3] and colour != ansi[2]
    down = _healthy(seat_tasks_rows=[_row(outcome="unknown", verdictLagS=None, acceptedAtApi=None)])
    down["seat_sources"] = copy.deepcopy(down["seat_sources"])
    down["seat_sources"]["seatWork"].update(ok=False, failures=3, unavailable=True)
    rows = await _ledger(**down)
    assert " ? " in _row_with(rows, "0c1f9727")
    offline = await _ledger(**_healthy(seat_offline=True, seat_tasks_rows=[_row(outcome="unknown", verdictLagS=None)]))
    assert "local only" in _row_with(offline, "0c1f9727")


# -- footer, cap, selection -------------------------------------------------------------------


def test_older_line_counts_past_the_cap():
    assert older_line(60, 20) == "+40 older · more" and older_line(20, 20) is None and older_line(None, 20) is None


async def test_the_footer_names_the_window_and_the_rows_past_the_cap():
    many = [_row(key=f"7/{i:08x}/2026-09-26T03:{i % 60:02d}:00.000Z", nodeId8=f"{i:08x}") for i in range(25)]
    window = dict(_healthy()["seat_tasks_window"], rows=291)
    rows = await _ledger((SIZE[0], 30), **_healthy(seat_tasks_rows=many, seat_tasks_window=window,
                                                  seat_ledger_footer="journald 09-22 12:00 → now · 291 rows · stored today 11 = plane 11 ✓"))
    text = "\n".join(rows)
    assert "+271 older · more" in text and "291 rows" in text and "stored today 11 = plane 11" in text
    assert sum(1 for line in rows if "2026" not in line and any(f"{i:08x}" in line for i in range(25))) == 20, "ROW_CAP is 20"


async def test_selected_row_follows_the_cursor():
    class _A(App):
        CSS_PATH = CSS_PATH

        def compose(self):
            yield SeatLedgerTable()

    async with _A().run_test(size=SIZE) as pilot:
        widget = pilot.app.query_one(SeatLedgerTable)
        widget.update_data(**_healthy())
        await pilot.pause()
        assert widget.selected_row()["nodeId8"] == "0c1f9727"
        widget.query_one(DataTable).move_cursor(row=1)
        await pilot.pause()
        assert widget.selected_row()["nodeId8"] == "7073b7a6"
        widget.update_data(**_healthy(seat_tasks_rows=None))
        await pilot.pause()
        assert widget.selected_row() is None


# -- tiers ----------------------------------------------------------------------------------


def test_the_tier_thresholds_descend():
    assert FULL_WIDTH > COMPACT_WIDTH > TIGHT_WIDTH > 0


async def test_one_below_full_sheds_lag_and_role_and_says_widen():
    full = await _ledger((FULL_WIDTH + GUTTER, 12), **_healthy())
    compact = await _ledger((FULL_WIDTH + GUTTER - 1, 12), **_healthy())
    assert "lag" in _row_with(full, "when").split() and "‹" not in "\n".join(full)
    header = _row_with(compact, "when").split()
    assert "lag" not in header and "role" not in header and "‹" in "\n".join(compact)
    assert "model~tier" in header


async def test_one_below_compact_keeps_only_the_tight_five():
    tight = await _ledger((COMPACT_WIDTH + GUTTER - 1, 12), **_healthy())
    header = _row_with(tight, "when").split()
    assert header == ["when", "node", "took", "stored", "verdict"]
    assert "accepted +15m" in _row_with(tight, "0c1f9727")


# -- hygiene ---------------------------------------------------------------------------------


async def test_masked_key_never_reaches_the_ledger():
    # spec §14 mutation proof 12, ledger half: the widget redacts every third-party cell itself (the model too).
    # ``strip_tags`` deletes the ``[redacted]`` placeholder, so the painted remnant is ``failed sk-``.
    hostile = _row(model=f"gpt-6-{MASKED}", failureReason=MASKED, outcome="failed", cancelled=None)
    rows = await _ledger((200, 12), **_healthy(seat_tasks_rows=[hostile]))
    text = "\n".join(rows)
    assert "sk-svcac" not in text and "failed sk-" in text


async def test_hostile_markup_and_a_non_dict_row_never_raise():
    rows = await _ledger(**_healthy(seat_tasks_rows=[_row(nodeId8="[/x]evil", model="[bold]m[/]"), "not a row", None]))
    text = "\n".join(rows)
    assert "[bold]" not in text and "evil" in text

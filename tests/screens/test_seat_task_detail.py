"""``»``/Enter on a LEDGER row: local facts and the plane's row, side by side (spec §8 LEDGER; contract §C.16).

Never prompts, tool outputs or summaries (safety §5.4): the objective and the agent's
sentence are third-party prose NOW already shows; API error *messages* are the raw
runtime error text -- only their statuses appear here. Composited assertions.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

from textual.app import App

from maxpane_dashboard.data.seat_models import fold_status_document
from maxpane_dashboard.screens.seat_task_detail import LOCAL_FIELDS, NEVER_SHOWN, PLANE_FIELDS, SeatTaskDetail, adapt_row
from maxpane_dashboard.widgets.explorer import IMD, url_for
from tests.widgets.address_probe import link_targets

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "seat"
SIZE = (120, 30)


def _row(**changes) -> dict:
    flat = fold_status_document(json.loads((FIXTURES / "status" / "status_v2_healthy.json").read_text(encoding="utf-8")))
    row = copy.deepcopy(flat["seat_tasks_rows"][0])
    row.update(changes)
    return row


class _A(App):
    def __init__(self, row: dict) -> None:
        super().__init__()
        self._row = row

    def on_mount(self) -> None:
        self.push_screen(SeatTaskDetail(self._row))


async def _text(row: dict) -> tuple[str, list]:
    async with _A(row).run_test(size=SIZE) as pilot:
        await pilot.pause()
        await pilot.pause()
        rows = ["".join(seg.text for seg in strip) for strip in pilot.app.screen._compositor.render_strips()]
        return "\n".join(rows), link_targets(pilot.app)


def test_adapt_row_feeds_the_frame_s_title_keys():
    row = _row()
    adapted = adapt_row(row)
    assert adapted["job_id"] == row["jobId"] and adapted["node_key"] == "oracle_assess" and adapted["role"] == "implement"
    assert isinstance(adapted["submitted_ts"], float) and isinstance(adapted["accepted_ts"], float)
    assert adapt_row(_row(nodeKey=None))["node_key"] == "0c1f9727"
    assert adapt_row({})["job_id"] is None and adapt_row({})["submitted_ts"] is None


def test_the_field_lists_are_disjoint_and_never_include_prose():
    assert not set(LOCAL_FIELDS) & set(PLANE_FIELDS)
    assert set(NEVER_SHOWN) == {"prompt", "summary", "toolOutput", "lastMessage", "lastMessageUtc"}
    assert not set(NEVER_SHOWN) & (set(LOCAL_FIELDS) | set(PLANE_FIELDS))
    assert SeatTaskDetail.TITLE_WORD == "TASK" and SeatTaskDetail.ID_PREFIX == "seat-task-detail" and SeatTaskDetail.SHOW_ROLE is True


async def test_the_title_and_both_sections_render_the_healthy_row():
    text, links = await _text(_row())
    assert "TASK · b1fb1439 · oracle_assess · implement · " in text
    assert "LOCAL" in text and "PLANE" in text
    assert "stored" in text and "c4d9714ffb95" in text
    assert "turns 3 (agent_messages)" in text and "in 17,864" in text and "out 812" in text and "cached 92,928" in text
    assert "ttft 1,807 ms" in text and "wall 22.4 s" in text and "turn-1 context 24,000" in text and "max turns 60" in text
    assert "phases: preparing → working → checking → bundling → uploading" in text
    assert "gpt-6-luna/medium ~economy/standard" in text
    assert "verdict accepted" in text and "lag 15m" in text
    assert "failure —" in text and "sources: row local · outcome api · reason none" in text
    assert "PRESS SPACE OR ESC TO CLOSE" in text


async def test_the_job_id_links_its_imd_page_and_nothing_else_links():
    row = _row()
    text, links = await _text(row)
    assert row["jobId"] in text, "the whole job id is shown (it is the ledger's join key, spec §13)"
    urls = {t[5] for t in links}
    assert urls == {url_for(IMD, "job", row["jobId"])}
    assert all(t[2] == "imd" and t[3] == "job" for t in links)


async def test_a_failed_row_names_the_enum_reason_and_class_only():
    text, _ = await _text(_row(outcome="failed", failureReason="runtime_error", failureClass="machine", verdictLagS=None, acceptedAtApi=None,
                               apiErrors=[{"status": 401, "message": "unexpected status 401 Unauthorized: sk-svcac******** TOOL OUTPUT", "atUtc": "x"}],
                               workDirAbnormal=True))
    assert "verdict failed" in text and "failure runtime_error (machine)" in text
    assert "api errors: 401 ×1" in text and "TOOL OUTPUT" not in text and "sk-svcac" not in text
    assert "work dir abnormal" in text


async def test_prompts_tool_output_and_summaries_never_appear():
    text, _ = await _text(_row(objective="PUBLIC API OBJECTIVE", prompt="PRIVATE PROMPT", toolOutput="PRIVATE TOOL OUTPUT", summary="PRIVATE SUMMARY", lastMessage="SENTENCE-PROSE-NEVER-HERE"))
    assert "PUBLIC API OBJECTIVE" in text
    assert all(word not in text for word in ("PRIVATE PROMPT", "PRIVATE TOOL OUTPUT", "PRIVATE SUMMARY", "SENTENCE-PROSE-NEVER-HERE"))


async def test_hostile_markup_and_a_sparse_row_never_raise():
    text, _ = await _text({"nodeKey": "[/x][bold]evil", "jobId": "not-a-uuid", "role": None})
    assert "evil" in text and "[bold]" not in text and "TASK" in text


async def test_escape_closes_the_modal():
    async with _A(_row()).run_test(size=SIZE) as pilot:
        await pilot.pause()
        assert isinstance(pilot.app.screen, SeatTaskDetail)
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(pilot.app.screen, SeatTaskDetail)

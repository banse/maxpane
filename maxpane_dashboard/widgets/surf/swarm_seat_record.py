"""RECORD: every work attempt in the selected seat's lifetime record.

Owner, 2026-09-23: when/job/node/state/model/took/panel/tok/answer.
Role is hidden; short model names make room for panel evidence and output tokens.

Since 2026-09-22 ``work[]`` lists pending, rejected and failed attempts beside
accepted ones. ``state`` shows the attempt's own status whenever it is not
``accepted`` (a failed attempt on a completed job must not read as a green
``completed``), and the job's state otherwise or under the pre-status shape.
Timestamps (submitted, else accepted) include month/day across midnight.
The job cell links a canonical job id to its IMD explorer page; the node
cell is the node's short word (:data:`_swarm_seat.NODE_TITLES`). Launch and
submission hash are not columns (owner, 2026-09-22: the answer gets the room);
a failed attempt's read answer is red. Answer takes the remaining width and
lights ``‹ widen`` when cut only if there is no popup button. The title has no blank row under it (owner,
2026-09-22, this panel only). The scrollable table caps at forty rows and
explicitly counts older rows; the seat state hides stale rows before rendering.
"""

from __future__ import annotations

import math

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import job_text
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, JOB_EXPLORER, mmdd_hhmm, short_model
from maxpane_dashboard.widgets.surf._oracle_answer import _PANEL_COLS, _STATE_COLORS, joined, record_answer, panel_text, can_open_submission, fit_popup_text, tok_text
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES, seat_state_line
from maxpane_dashboard.widgets.surf._swarm_table import CELL_PADDING, SwarmTableBase, table_cols

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "JOB_COLS",
    "NODE_COLS",
    "ANSWER_MIN_COLS",
    "TIGHT_WIDTH",
    "SurfSwarmSeatRecord",
    "older_line",
    "seat_footer",
]

EMPTY_LINE = "no work yet"

#: ``MM-DD HH:MM`` of ``submitted_ts`` (the work entry's ``submittedAt``), else
#: ``accepted_ts``: since 2026-09-22 ``work[]`` also lists pending, rejected
#: and failed attempts, which carry no ``acceptedAt``.
_WHEN_COLS = 11

#: The first eight characters of the job id. The fold's ids are UUIDs
#: (``ad7bebb8-fd1a-4268-b831-1c253a85ae4c``); the whole id is 36 cells and
#: no use on screen, the first group is how the swarm's own pages and this
#: repo's tests name a job. A head slice, never a head-and-tail window (that
#: is an address formatter's shape, ``tests/test_address_rule.py``). The
#: shown group links the whole id's explorer page (``address.job_text``).
JOB_COLS = 8

#: The widest known short word (``oracle``, ``review``; ``build`` 5). An
#: unknown node key is fitted to it with a visible ``…`` (owner, 2026-09-22:
#: the answer gets the cells the 22-cell keys took).
NODE_COLS = 6

#: ``completed`` is 9 -- the only ``jobState`` on the four captured seats; the
#: vocabulary is open and a longer word clips with ``…``.
_STATE_COLS = 9

#: The answer floor, certified with the AGENT body in polish WP6.
#: Above it the column takes every remaining cell.
ANSWER_MIN_COLS = 20

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("job", "job", JOB_COLS),
    ("node", "node", NODE_COLS),
    ("state", "state", _STATE_COLS),
    ("model", "model", 9),
    ("took", "took", 6),
    ("panel", "panel", _PANEL_COLS),
    ("tok", "tok", 6),
    ("answer", "answer", ANSWER_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "tok")
_TIGHT = tuple(key for key in _COMPACT if key not in ("answer", "model", "took"))
_TIERS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}


def _tier_width(keep) -> int:
    return table_cols([w for k, _l, w in _SPECS if k in keep])


#: Width tiers include DataTable cell padding; certified in the screen sweep.
FULL_WIDTH = _tier_width(_ALL)
COMPACT_WIDTH = _tier_width(_COMPACT)
TIGHT_WIDTH = _tier_width(_TIGHT)


def _word(value: object) -> str:
    """A third-party word flattened, or ``--`` for ``None``/empty."""
    text = flatten(value)
    return text if text else DASH


def _line_style(line: Text) -> str:
    """The one style a ``seat_state_line`` carries (a markup span or the Text's own)."""
    if line.style:
        return str(line.style)
    return str(line.spans[0].style) if line.spans else ""


def older_line(rows: object, cap: int | None) -> str | None:
    """``+N older`` for the rows past *cap*, or ``None`` when every row is shown."""
    if not isinstance(rows, list) or cap is None or len(rows) <= cap:
        return None
    return f"+{fmt_int(len(rows) - cap)} older"


def seat_footer(state: object, rows: object, cap: int | None) -> tuple[str, str] | None:
    """What a seat table's footer says instead of the base's, as ``(words, style)``.

    The seat state first (``_swarm_seat.seat_state_line``: pending, never
    paired, unavailable); then, for ``"ok"``, the ``+N older`` line when the
    rows run past *cap*. ``None`` leaves the base's own footer (the real-empty
    sentence, ``unavailable`` for an unread list, or none) standing.
    """
    line = seat_state_line(state)
    if line is not None:
        return line.plain, _line_style(line)
    older = older_line(rows, cap)
    return (older, "dim") if older else None


class SurfSwarmSeatRecord(SwarmTableBase):
    """RECORD -- lifetime work attempts in the source-provided order."""

    TITLE = "RECORD"
    TABLE_ID = "surf-swarm-seat-record-table"
    CURSOR_TYPE = "none"

    #: The one panel title with no blank row under it (owner, 2026-09-22):
    #: the exception to ``PanelBase``'s ``margin: 0 0 1 0``, stated here
    #: where the panel is declared and pinned in the title-blank-row test.
    DEFAULT_CSS = """
    SurfSwarmSeatRecord > .panel-title {
        margin: 0;
    }
    """
    #: Kept at 40 for lifetime rows (plan §9 G); the footer counts the rest.
    ROW_CAP = 40

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = _TIERS
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH),
    )
    EMPTY_LINE = EMPTY_LINE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._answer_cols = ANSWER_MIN_COLS
        self._state: object = None

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_work_rows=None,
        swarm_seat_state=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``**_kwargs``: the screen splats it)."""
        self._state = swarm_seat_state
        rows = swarm_seat_work_rows if swarm_seat_state == "ok" else None
        self.store(rows, swarm_seat_as_of_hhmm)

    def _repaint(self) -> None:
        super()._repaint()
        footer = seat_footer(self._state, (self._payload or {}).get("rows"), self.ROW_CAP)
        if footer is not None:
            words, style = footer
            self._write_footer((words,), style=style)

    # -- geometry -----------------------------------------------------------

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        if key != "answer":
            return width
        keep = self.TIER_COLUMNS.get(tier, ())
        others = [w for k, _l, w in _SPECS if k != "answer" and k in keep]
        spare = budget - table_cols(others) - CELL_PADDING if budget > 0 else 0
        self._answer_cols = max(ANSWER_MIN_COLS, spare)
        return self._answer_cols

    # -- the cells ----------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, object] | None:
        job_id = item.get("job_id")
        job = job_id[:JOB_COLS] if isinstance(job_id, str) and job_id else DASH
        status = item.get("work_status")
        state = _word(status if status not in (None, "accepted") else item.get("job_state"))
        color = _STATE_COLORS.get(state)
        state_cell = sanitize_cell(state, _STATE_COLS)
        if color:
            state_cell = f"[{color}]{state_cell}[/]"
        node_key = item.get("node_key")
        title = NODE_TITLES.get(node_key) if isinstance(node_key, str) else None
        answer = self._answer_cell(item)
        if state == "failed" and item.get("answer_state") == "read" and not joined(item):
            # Only a read answer takes the failed colour: the unread words keep
            # their own dim / yellow, which say why there is no answer (F65).
            answer.stylize("red")
        return {
            "when": mmdd_hhmm(item.get("submitted_ts") if item.get("submitted_ts") is not None
                              else item.get("accepted_ts")),
            "job": job_text(job_id, JOB_COLS, explorer=JOB_EXPLORER) if job != DASH else DASH,
            "node": title.lower() if title else sanitize_cell(_word(node_key), NODE_COLS),
            "state": state_cell,
            "model": self._usage_cell(item, "model", 9),
            "took": self._usage_cell(item, "took_s", 6),
            "panel": self._panel_cell(item),
            "tok": self._usage_cell(item, "output_tokens", 6),
            "answer": answer,
        }

    def _usage_cell(self, item: dict, key: str, width: int) -> str:
        # Metadata belongs to the same successful exact-hash submission read.
        if item.get("answer_state") not in ("read", "no_reply"):
            return EMDASH
        value = item.get(key)
        if key == "model":
            value = short_model(value)
        elif key == "output_tokens":
            value = tok_text(value)
        elif key == "took_s":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return EMDASH
            minutes = int(value) // 60
            if minutes >= 60:
                value = f"{minutes // 60}h {minutes % 60:02d}m"
            else:
                value = "<1m" if minutes == 0 else f"{minutes}m"
        return sanitize_cell(value, width) or EMDASH

    def _panel_cell(self, item: dict) -> Text:
        return panel_text(item)

    def _answer_cell(self, item: dict) -> Text:
        if joined(item):
            return record_answer(item, self._answer_cols)
        state = item.get("answer_state")
        style = ""
        if state != "read":
            words = {"not_read": "not read", "not_served": "not served", "no_reply": "no reply"}
            text = words.get(state, "unavailable")
            style = "dim" if state in words else "yellow"
        else:
            text = strip_tags(item.get("answer"))
        if item.get("panel_state") in ("outvoted", "no_quorum_out"):
            if item.get("panel_answer_type") == "bool":
                answer = item.get("panel_answer_bool")
                figure = ("YES" if answer else "NO") if type(answer) is bool else "unavail"
            else:
                figure = strip_tags(item.get("panel_figure")) or "unavail"
            text = f"panel {figure} · {text}"
        width = self._answer_cols
        eligible = can_open_submission(item)
        rendered, cut, button = fit_popup_text(item, text, width, 'open_submission' if eligible else None,
            force=item.get('work_status') in ('failed','rejected'), style=style)
        if cut and not button:
            self._clipped = True
        return rendered

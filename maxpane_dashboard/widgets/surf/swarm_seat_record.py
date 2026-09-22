"""RECORD: every won job in the selected seat's lifetime record.

Accepted timestamps include month/day across midnight. Launch is a sanitized
name or a real-none em dash. Submission hashes are plain eight-character
prefixes, never explorer links. Answer takes the remaining width and
lights ``‹ widen`` when cut. The scrollable table caps at forty rows and
explicitly counts older rows; the seat state hides stale rows before rendering.
"""

from __future__ import annotations

import math

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, mmdd_hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import seat_state_line
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

EMPTY_LINE = "no accepted work yet"

#: ``MM-DD HH:MM`` of ``accepted_ts`` (the work entry's ``acceptedAt``).
_WHEN_COLS = 11

#: The first eight characters of the job id. The fold's ids are UUIDs
#: (``ad7bebb8-fd1a-4268-b831-1c253a85ae4c``); the whole id is 36 cells and
#: no use on screen, the first group is how the swarm's own pages and this
#: repo's tests name a job. A head slice, never a head-and-tail window (that
#: is an address formatter's shape, ``tests/test_address_rule.py``).
JOB_COLS = 8

#: Node ``key`` <= 22 chars on every captured seat (``build_contract_project``
#: is 22, ``adversarial_review`` 18): the longest known key renders whole and
#: a longer, unseen one clips with a visible ``…``. BY NODE uses the same known node vocabulary.
NODE_COLS = 22

#: ``implement`` / ``integrate`` are 9; ``review`` 6.
_ROLE_COLS = 9

#: ``completed`` is 9 -- the only ``jobState`` on the four captured seats; the
#: vocabulary is open and a longer word clips with ``…``.
_STATE_COLS = 9

#: The answer floor, certified with the AGENT body in polish WP6.
#: Above it the column takes every remaining cell.
ANSWER_MIN_COLS = 20

_STATE_COLORS = {"completed": "green", "failed": "red", "cancelled": "red"}

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("job", "job", JOB_COLS),
    ("node", "node", NODE_COLS),
    ("role", "role", _ROLE_COLS),
    ("state", "state", _STATE_COLS),
    ("launch", "launch", 11),
    ("sub", "sub", 8),
    ("model", "model", 15),
    ("took", "took", 6),
    ("answer", "answer", ANSWER_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key not in ("role", "launch", "sub"))
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
    """RECORD -- lifetime accepted work in the source-provided order."""

    TITLE = "RECORD"
    TABLE_ID = "surf-swarm-seat-record-table"
    CURSOR_TYPE = "none"
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
        state = _word(item.get("job_state"))
        color = _STATE_COLORS.get(state)
        state_cell = sanitize_cell(state, _STATE_COLS)
        if color:
            state_cell = f"[{color}]{state_cell}[/]"
        return {
            "when": mmdd_hhmm(item.get("accepted_ts")),
            "launch": EMDASH if item.get("launch") is None else sanitize_cell(item["launch"], 11),
            "sub": Text(str(item["submission_hash"])[:8]) if item.get("submission_hash") else DASH,
            "job": sanitize_cell(job, JOB_COLS),
            "node": sanitize_cell(_word(item.get("node_key")), NODE_COLS),
            "role": sanitize_cell(_word(item.get("role")), _ROLE_COLS),
            "state": state_cell,
            "model": self._usage_cell(item, "model", 15),
            "took": self._usage_cell(item, "took_s", 6),
            "answer": self._answer_cell(item),
        }

    def _usage_cell(self, item: dict, key: str, width: int) -> str:
        # Metadata belongs to the same successful exact-hash submission read.
        if item.get("answer_state") not in ("read", "no_reply"):
            return EMDASH
        value = item.get(key)
        if key == "took_s":
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                return EMDASH
            minutes = int(value) // 60
            if minutes >= 60:
                value = f"{minutes // 60}h {minutes % 60:02d}m"
            else:
                value = "<1m" if minutes == 0 else f"{minutes}m"
        return sanitize_cell(value, width) or EMDASH

    def _answer_cell(self, item: dict) -> Text:
        state = item.get("answer_state")
        if state != "read":
            words = {"not_read": "not read", "not_served": "not served", "no_reply": "no reply"}
            return Text(words.get(state, "unavailable"), style="dim" if state in words else "yellow")
        text = strip_tags(item.get("answer"))
        width = self._answer_cols
        if rowfit.cell_len(text) > width:
            self._clipped = True
        return Text.from_markup(sanitize_cell(text, width))

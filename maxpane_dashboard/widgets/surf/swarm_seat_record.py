"""RECORD -- the selected seat's accepted work, lifetime, newest first (plan WP4).

Mounted on the AGENT body (``a``); this module only paints the
``swarm_seat_work_rows`` shape (``data/surf_models.SURF_ROW_KEYS``):
``job_id, node_key, role, job_state, objective, accepted_ts`` -- one row per
``/seats/{tokenId}`` ``work[]`` entry, i.e. every submission a job **used**
(``docs/surf_agent_seats_spec.md`` §3). The verifier-detail columns (try,
rev, verdict, detail) are gone: ``/seats`` does not serve them for lifetime
rows (decision D3). The tiered-table mechanics -- header per width tier, the
``as of`` marker and widen hint in the title, ``None`` vs ``[]`` -- are
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase`'s.

``objective`` takes the remaining budget. Every other column is a constant;
``objective`` is the job's free text (170-199 chars on every captured seat,
2026-09-21) and gets whatever the panel has left above
:data:`OBJECTIVE_MIN_COLS`, clipped with a visible ``…``. A clipped objective
lights the title's ``‹ widen`` even when no column was shed -- on the corpus
that is every row, as ``detail`` was before it.

The seat state (``swarm_seat_state``, ``widgets/surf/_swarm_seat.py``) is read
before any row: ``"pending"`` writes ``Loading...`` under the header,
``"unknown_seat"`` writes ``never paired`` (a real negative, never the
real-empty sentence; plan §9 L), and ``None`` or a malformed state writes
``unavailable``. Only ``"ok"`` paints rows: ``[]`` is :data:`EMPTY_LINE`,
``None`` is ``unavailable``. :func:`seat_footer` is that decision, shared
with FEEDBACK. Past :attr:`SurfSwarmSeatRecord.ROW_CAP` the footer names the
rows not shown: ``+N older`` (plan §9 G).

Colour is looked up on the raw ``job_state`` word and painted on the escaped
text (``completed`` green, ``failed``/``cancelled`` red, everything else
plain -- the vocabulary is open and an unknown word gets no colour, not a
guess). Every third-party string (node key, role, state, objective) goes
through ``markup_safety.sanitize_cell``.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import seat_state_line
from maxpane_dashboard.widgets.surf._swarm_table import CELL_PADDING, SwarmTableBase, table_cols

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "JOB_COLS",
    "NODE_COLS",
    "OBJECTIVE_MIN_COLS",
    "TIGHT_WIDTH",
    "SurfSwarmSeatRecord",
    "older_line",
    "seat_footer",
]

EMPTY_LINE = "no accepted work yet"

#: ``HH:MM`` of ``accepted_ts`` (the work entry's ``acceptedAt``).
_WHEN_COLS = 5

#: The first eight characters of the job id. The fold's ids are UUIDs
#: (``ad7bebb8-fd1a-4268-b831-1c253a85ae4c``); the whole id is 36 cells and
#: no use on screen, the first group is how the swarm's own pages and this
#: repo's tests name a job. A head slice, never a head-and-tail window (that
#: is an address formatter's shape, ``tests/test_address_rule.py``).
JOB_COLS = 8

#: Node ``key`` <= 22 chars on every captured seat (``build_contract_project``
#: is 22, ``adversarial_review`` 18): the longest known key renders whole and
#: a longer, unseen one clips with a visible ``…``. FEEDBACK imports this for
#: its own node column.
NODE_COLS = 22

#: ``implement`` / ``integrate`` are 9; ``review`` 6.
_ROLE_COLS = 9

#: ``completed`` is 9 -- the only ``jobState`` on the four captured seats; the
#: vocabulary is open and a longer word clips with ``…``.
_STATE_COLS = 9

#: The floor of the ``objective`` column. PROVISIONAL (plan WP4): a widget
#: constant, not a measured pin -- WP6 re-sweeps the AGENT body and owns
#: whether this floor, and so every tier below, moves. Above the floor the
#: column takes every cell the panel has left.
OBJECTIVE_MIN_COLS = 20

_STATE_COLORS = {"completed": "green", "failed": "red", "cancelled": "red"}

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("job", "job", JOB_COLS),
    ("node", "node", NODE_COLS),
    ("role", "role", _ROLE_COLS),
    ("state", "state", _STATE_COLS),
    ("objective", "objective", OBJECTIVE_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "role")
_TIGHT = tuple(key for key in _COMPACT if key != "objective")
_TIERS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}


def _tier_width(keep) -> int:
    return table_cols([w for k, _l, w in _SPECS if k in keep])


#: PROVISIONAL tiers (plan WP4), each a :func:`table_cols` sum -- WP6
#: measures them in situ. Every column with ``objective`` at its floor: 73
#: cells plus six columns' padding = 85.
FULL_WIDTH = _tier_width(_ALL)
#: Without ``role`` (9 + 2) = 74.
COMPACT_WIDTH = _tier_width(_COMPACT)
#: Without ``objective`` too (20 + 2) = 52.
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
    """RECORD -- the selected seat's accepted work, lifetime, newest first."""

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
        self._objective_cols = OBJECTIVE_MIN_COLS
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
        if key != "objective":
            return width
        keep = self.TIER_COLUMNS.get(tier, ())
        others = [w for k, _l, w in _SPECS if k != "objective" and k in keep]
        spare = budget - table_cols(others) - CELL_PADDING if budget > 0 else 0
        self._objective_cols = max(OBJECTIVE_MIN_COLS, spare)
        return self._objective_cols

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
            "when": hhmm(item.get("accepted_ts")),
            "job": sanitize_cell(job, JOB_COLS),
            "node": sanitize_cell(_word(item.get("node_key")), NODE_COLS),
            "role": sanitize_cell(_word(item.get("role")), _ROLE_COLS),
            "state": state_cell,
            "objective": self._objective_cell(item),
        }

    def _objective_cell(self, item: dict) -> str:
        text = flatten(item.get("objective"))
        if not text:
            return DASH
        width = self._objective_cols
        if rowfit.cell_len(text) > width:
            self._clipped = True
        return sanitize_cell(text, width)

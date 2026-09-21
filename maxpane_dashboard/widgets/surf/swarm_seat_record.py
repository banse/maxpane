"""RECORD -- the selected seat's nodes, newest first (swarm v2 plan A1, WP6a).

Mounted on the AGENT body (``a``) since WP7; this module only paints the
frozen ``swarm_seat_node_rows`` shape
(``data/surf_models.SURF_ROW_KEYS``): ``job_id, template, node_key, role,
state, attempt, revisions, verdict_status, rejection_code, failed_checks,
detail, at_ts``. The tiered-table mechanics -- header per width tier, the
``as of`` marker and widen hint in the title, ``None`` vs ``[]`` -- are
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase`'s.

Two kinds of node reach this table (WP3 landed, fact 5): a **detail** node
carries the verifier's full verdict; a **seen-slot** node -- a job the sweep
no longer reads, carried past the window by the cache's seen slot -- has
``None`` for ``attempt``, ``detail`` and ``node_key`` (when the slot stored
it without one) and ``[]`` for ``failed_checks``. Those render ``--``: the
slot did not record them, and this panel invents nothing.

``detail`` takes the remaining budget. Every other column is a constant;
``detail`` is the verifier's free text (63 chars in the corpus, 400 in A1's
worst case) and gets whatever the panel has left above
:data:`DETAIL_MIN_COLS`, clipped with a visible ``…``. A clipped detail
lights the title's ``‹ widen`` even when no column was shed: the marker
means "this panel is not showing you everything", and a cut verdict is
exactly that.

Colour is looked up on the raw state word and painted on the escaped text
(``working`` green, ``failed``/``rejected`` red, everything else plain --
the vocabulary is open and an unknown word gets no colour, not a guess).
``verdict`` appends the ``rejection_code`` in red after ``·`` when there is
one. Every third-party string (node key, role, state, verdict word, code,
detail, each failed check) goes through ``markup_safety.sanitize_cell``.
``swarm_network`` is accepted and never painted: a node's chain is not a
fact this table has (the frozen signature carries the key for the body's
uniform splat, as LAUNCHES does).
"""

from __future__ import annotations

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm
from maxpane_dashboard.widgets.surf._swarm_table import CELL_PADDING, SwarmTableBase, table_cols

__all__ = [
    "COMPACT_WIDTH",
    "DETAIL_MIN_COLS",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "JOB_COLS",
    "NODE_COLS",
    "TIGHT_WIDTH",
    "SurfSwarmSeatRecord",
]

EMPTY_LINE = "no nodes yet"

#: ``HH:MM`` of ``at_ts`` (the node's ``updatedAt`` / verdict stamp).
_WHEN_COLS = 5

#: The first eight characters of the job id. The fold's ids are UUIDs
#: (``ad7bebb8-fd1a-4268-b831-1c253a85ae4c``); the whole id is 36 cells and
#: no use on screen, the first group is how the swarm's own pages and this
#: repo's tests name a job. A head slice, never a head-and-tail window (that
#: is an address formatter's shape, ``tests/test_address_rule.py``).
JOB_COLS = 8

#: Node ``key`` <= 22 chars in the corpus (``build_contract_project`` is
#: 22, ``review_oracle`` 13): the longest known key renders whole and a
#: longer, unseen one clips with a visible ``…``. ``--`` for a seen-slot
#: node without one. FEEDBACK imports this for its own node column.
NODE_COLS = 22

#: ``implement`` / ``integrate`` are 9; ``review`` 6.
_ROLE_COLS = 9

#: ``accepted`` is 8 -- the longest state word the corpus has (``failed``,
#: ``working``, ``waiting``); the vocabulary is open and longer words clip.
_STATE_COLS = 8

#: ``attempt`` / ``revisions``: single digits in the corpus (the column
#: headers ``try`` / ``rev`` are the width).
_TALLY_COLS = 3

#: ``rejected · tests_failed``: the verdict word (8) plus `` · `` (3) and a
#: rejection code. No code was seen in the corpus (open vocabulary); 13
#: cells of code is the budget -- ``tests_failed`` (12) whole -- and a
#: longer one clips with ``…``.
_VERDICT_COLS = 24

#: The floor of the ``detail`` column: ``all checks passed`` is the corpus's
#: modal verdict detail and renders whole at 17. Above the floor the column
#: takes every cell the panel has left.
DETAIL_MIN_COLS = 17

_STATE_COLORS = {"working": "green", "failed": "red", "rejected": "red"}
_CHECKS_JOINER = " ✗ "

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("job", "job", JOB_COLS),
    ("node", "node", NODE_COLS),
    ("role", "role", _ROLE_COLS),
    ("state", "state", _STATE_COLS),
    ("try", "try", _TALLY_COLS),
    ("rev", "rev", _TALLY_COLS),
    ("verdict", "verdict", _VERDICT_COLS),
    ("detail", "detail", DETAIL_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key not in ("try", "rev"))
_TIGHT = tuple(key for key in _COMPACT if key != "detail")
_TIERS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}


def _tier_width(keep) -> int:
    return table_cols([w for k, _l, w in _SPECS if k in keep])


#: Every column with ``detail`` at its floor: 99 cells plus nine columns'
#: padding = 117.
FULL_WIDTH = _tier_width(_ALL)
#: Without ``try`` and ``rev`` (3 + 2 each) = 107.
COMPACT_WIDTH = _tier_width(_COMPACT)
#: Without ``detail`` too (17 + 2) = 88.
TIGHT_WIDTH = _tier_width(_TIGHT)


def _word(value: object) -> str:
    """A third-party word flattened, or ``--`` for ``None``/empty."""
    text = flatten(value)
    return text if text else DASH


class SurfSwarmSeatRecord(SwarmTableBase):
    """RECORD -- the selected seat's nodes, newest first."""

    TITLE = "RECORD"
    TABLE_ID = "surf-swarm-seat-record-table"
    CURSOR_TYPE = "none"
    #: A1's worst case: one seat on forty nodes.
    ROW_CAP = 40

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = _TIERS
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH),
    )
    EMPTY_LINE = EMPTY_LINE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._detail_cols = DETAIL_MIN_COLS

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_node_rows=None,
        swarm_seat_as_of_hhmm=None,
        swarm_network=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict; ``swarm_network`` is not painted."""
        self.store(swarm_seat_node_rows, swarm_seat_as_of_hhmm)

    # -- geometry -----------------------------------------------------------

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        if key != "detail":
            return width
        keep = self.TIER_COLUMNS.get(tier, ())
        others = [w for k, _l, w in _SPECS if k != "detail" and k in keep]
        spare = budget - table_cols(others) - CELL_PADDING if budget > 0 else 0
        self._detail_cols = max(DETAIL_MIN_COLS, spare)
        return self._detail_cols

    # -- the cells ----------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, object] | None:
        job_id = item.get("job_id")
        job = job_id[:JOB_COLS] if isinstance(job_id, str) and job_id else DASH
        state = _word(item.get("state"))
        color = _STATE_COLORS.get(state)
        state_cell = sanitize_cell(state, _STATE_COLS)
        if color:
            state_cell = f"[{color}]{state_cell}[/]"
        cells: dict[str, object] = {
            "when": hhmm(item.get("at_ts")),
            "job": sanitize_cell(job, JOB_COLS),
            "node": sanitize_cell(_word(item.get("node_key")), NODE_COLS),
            "role": sanitize_cell(_word(item.get("role")), _ROLE_COLS),
            "state": state_cell,
            "try": fmt_int(item.get("attempt")),
            "rev": fmt_int(item.get("revisions")),
            "verdict": self._verdict_cell(item),
            "detail": self._detail_cell(item),
        }
        return cells

    @staticmethod
    def _verdict_cell(item: dict) -> str:
        status = flatten(item.get("verdict_status"))
        code = flatten(item.get("rejection_code"))
        if not status and not code:
            return DASH
        if not code:
            return sanitize_cell(status, _VERDICT_COLS)
        head = status or DASH
        room = max(_VERDICT_COLS - rowfit.cell_len(head) - 3, 1)
        return f"{sanitize_cell(head, _VERDICT_COLS)} · [red]{sanitize_cell(code, room)}[/]"

    def _detail_cell(self, item: dict) -> str:
        detail = flatten(item.get("detail"))
        checks = item.get("failed_checks")
        words = [flatten(c) for c in checks if isinstance(c, str)] if isinstance(checks, list) else []
        words = [w for w in words if w]
        text = detail
        if words:
            text = f"{text}{_CHECKS_JOINER}{', '.join(words)}" if text else ", ".join(words)
        if not text:
            return DASH
        width = self._detail_cols
        if rowfit.cell_len(text) > width:
            self._clipped = True
        return sanitize_cell(text, width)

"""ROSTER -- every seat the sweep has seen, one row each; the AGENT body's picker.

Swarm v2 plan Amendment A1 (WP6a). ``SurfScreen``'s ``MODE_AGENT`` body
mounts it and its ``on_data_table_row_selected`` maps ``enter`` on a row to
``manager.select_seat(token)`` (WP7); this module only knows how to paint the
frozen ``swarm_seat_*`` contract.

The picker contract
-------------------
``CURSOR_TYPE = "row"`` and ``ROW_CAP = None``: the operator moves the cursor
and presses ``enter`` on a seat. Two things make that possible here rather
than in the screen: :meth:`SurfSwarmRoster.token_at` maps a painted row
index back to its ``token_id`` (rebuilt on every paint, aligned with the rows
the base actually added, so a skipped garbage row cannot shift the map by
one), and :attr:`SurfSwarmRoster.selected_token` /
:attr:`selected_row_index` expose the manager's selection, and the roster
moves its own cursor onto that row after every paint (:meth:`_place_cursor`
-- a resize repaint would otherwise reset it to row 0). The selected row is bold and prefixed ``▸``; the others
are indented two cells so the seat column stays aligned. The rows are
painted in the fold's order (``nodes`` desc) and never re-sorted.

The title says what the rows are folded from (``docs/surf_agent_seats_spec.md``
§3, decision D4): the roster is still the only seat list there is, and it is
folded from the ``/jobs`` window -- the newest 100 jobs, not every job -- so
its ``acc/rej/rev/score`` columns are window-scoped and the title says so::

    ROSTER · last 100 jobs since 02:26 · as of 04:06

``swarm_roster_window`` (``{jobs, oldest_ts}``, ``data/surf_swarm.roster_window``)
gives the words; ``since HH:MM`` is ``hhmm(oldest_ts)`` -- local time, like
every other swarm stamp -- and is left out when no job carried a stamp. A
window that was not read (``None``) or is malformed says
``ROSTER · job window unknown``: the title never drops the window words while
the rows show window-scoped numbers. The marker is the scores sweep's own
``swarm_scores_as_of_hhmm`` (plan §9 F): ``swarm_seat_as_of_hhmm`` is the seat
tier's now. :meth:`SwarmTableBase._render_title` builds on ``self.TITLE``, so
the window words ride in an instance-level ``TITLE`` and the base's ``as of``
clip and widen hint apply unchanged (no ``_swarm_table.py`` change, plan §9 P).

The tiered-table mechanics -- header per width tier, the ``as of`` marker
and widen hint in the title, ``None`` -> ``unavailable`` vs ``[]`` -> the
panel's own sentence written under the table -- are
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase`'s
(the one base under the ``s`` and ``a`` bodies' six tables since WP7).

Widths are the ``#:`` blocks' measurements; every tier is a
:func:`table_cols` sum of them and the ladder is widest first. The panel's
budget reserves :attr:`SwarmTableBase.GUTTER_COLS` for the table's own
vertical scrollbar, so the width requirement does not become a function of
the height (terminal-layout skill: *reserve the scrollbar gutter*).

Every third-party string (agent id, role word) goes through
``markup_safety.sanitize_cell`` before it meets the table; token ids are
integers, not addresses, and carry no copy icon. No clock: ``last`` is
``hhmm(last_active_ts)``, never an age.
"""

from __future__ import annotations

import logging

from textual.widgets import DataTable

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase, table_cols

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "SEAT_COLS",
    "TIGHT_WIDTH",
    "WINDOW_UNKNOWN",
    "SurfSwarmRoster",
    "window_words",
]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ROSTER
# ---------------------------------------------------------------------------

EMPTY_LINE = "no seat seen"

#: The title's window words when ``swarm_roster_window`` is unread or malformed.
WINDOW_UNKNOWN = "job window unknown"

#: ``▸ IDMD #1548``: the two-cell selection prefix, ``IDMD #`` (6) and a
#: token id. Corpus token ids are <= 4 digits (``1548``, 17 distinct seats,
#: 2026-09-21); a 5-digit id still fits, a 6-digit one clips with a visible
#: ``…``. The brief budgeted 10 for the id alone; the prefix is why it is 12.
SEAT_COLS = 12

#: ``agentId`` is a 5-digit string in the corpus (``50971``); escaped, clipped.
_AGENT_COLS = 6

#: Node and job counts: the most active corpus seat is on 8 nodes; ``1,000``
#: is five cells.
_COUNT_COLS = 5

#: The three known roles abbreviated and joined -- ``impl/rev/int`` is 12
#: cells exactly; an unknown role renders whole, escaped, and clips.
_ROLES_COLS = 12

#: ``acc`` / ``rej`` / ``rev`` -- the corpus maximum is single digits; four
#: cells keep the three-letter header whole.
_TALLY_COLS = 4

#: ``mean_score`` to one decimal: the corpus values are ``1`` and ``100``, so
#: ``100.0`` (5) is the widest; ``--`` when there is no feedback yet.
_SCORE_COLS = 5

#: ``HH:MM`` of ``last_active_ts``.
_LAST_COLS = 5

_ROLE_WORDS = {"implement": "impl", "review": "rev", "integrate": "int"}

_SPECS = (
    ("seat", "seat", SEAT_COLS),
    ("agent", "agent", _AGENT_COLS),
    ("nodes", "nodes", _COUNT_COLS),
    ("jobs", "jobs", _COUNT_COLS),
    ("roles", "roles", _ROLES_COLS),
    ("acc", "acc", _TALLY_COLS),
    ("rej", "rej", _TALLY_COLS),
    ("rev", "rev", _TALLY_COLS),
    ("score", "score", _SCORE_COLS),
    ("last", "last", _LAST_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "roles")
_TIGHT = tuple(key for key in _COMPACT if key not in ("rev", "last"))


def _tier_width(keep) -> int:
    return table_cols([w for k, _l, w in _SPECS if k in keep])


#: Every column: 62 cells of content plus ten columns' padding = 82.
FULL_WIDTH = _tier_width(_ALL)
#: Without ``roles`` (12 + 2) = 68.
COMPACT_WIDTH = _tier_width(_COMPACT)
#: Without ``roles``, ``rev`` (4 + 2) and ``last`` (5 + 2) = 55.
TIGHT_WIDTH = _tier_width(_TIGHT)


def _token(value: object) -> int | None:
    """A seat token as an ``int``; ``None`` for anything else (``bool`` included)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _count(value: object) -> int | None:
    """A job count: an ``int`` that is not a ``bool`` and not negative."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def window_words(window: object) -> str:
    """``last 100 jobs since 02:26`` for a read window; :data:`WINDOW_UNKNOWN` otherwise.

    ``since`` is left out when the window carries no usable stamp -- the job
    count alone still says the rows are a window.
    """
    if not isinstance(window, dict):
        return WINDOW_UNKNOWN
    jobs = _count(window.get("jobs"))
    if jobs is None:
        return WINDOW_UNKNOWN
    words = f"last {fmt_int(jobs)} jobs"
    since = hhmm(window.get("oldest_ts"), unknown="")
    return f"{words} since {since}" if since else words


def _roles_cell(roles: object) -> str:
    if not isinstance(roles, list):
        return DASH
    words = [_ROLE_WORDS.get(r, r) for r in roles if isinstance(r, str)]
    return "/".join(words) if words else DASH


class SurfSwarmRoster(SwarmTableBase):
    """ROSTER -- one row per seat seen; the AGENT body's picker."""

    TITLE = "ROSTER"
    TABLE_ID = "surf-swarm-roster-table"
    CURSOR_TYPE = "row"
    ROW_CAP = None

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH),
    )
    EMPTY_LINE = EMPTY_LINE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._tokens: list[int | None] = []
        self.selected_token: int | None = None

    # -- the picker's map ---------------------------------------------------

    def token_at(self, row_index: int) -> int | None:
        """The ``token_id`` painted at *row_index*, or ``None`` off the table."""
        if not isinstance(row_index, int) or row_index < 0:
            return None
        try:
            return self._tokens[row_index]
        except IndexError:
            return None

    @property
    def selected_row_index(self) -> int | None:
        """The painted row that carries the selected seat, or ``None``."""
        if self.selected_token is None:
            return None
        try:
            return self._tokens.index(self.selected_token)
        except ValueError:
            return None

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_rows=None,
        swarm_seat_selected=None,
        swarm_roster_window=None,
        swarm_scores_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``**_kwargs``: the screen splats it)."""
        selected = swarm_seat_selected if isinstance(swarm_seat_selected, dict) else {}
        self.selected_token = _token(selected.get("token_id"))
        self.TITLE = f"{type(self).TITLE} · {window_words(swarm_roster_window)}"
        self.store(swarm_seat_rows, swarm_scores_as_of_hhmm)

    def _repaint(self) -> None:
        self._tokens = []
        super()._repaint()
        try:
            painted = self.query_one(f"#{self.TABLE_ID}", DataTable).row_count
        except Exception:  # pragma: no cover - not composed
            return
        if len(self._tokens) != painted:
            # A row the base could not add after ``build_cells`` succeeded
            # would shift every later token by one -- and a wrong token is a
            # wrong seat selected. A map that says "nothing" is the safe one.
            logger.warning("%s: %d tokens for %d rows; map cleared",
                           type(self).__name__, len(self._tokens), painted)
            self._tokens = [None] * painted
        self._place_cursor()

    def _place_cursor(self) -> None:
        """Put the cursor on the selected seat's row after every paint.

        The base repaints on every resize (the tier is a function of width)
        and a repaint is ``clear()`` + ``add_row``, which resets the cursor
        to row 0 -- so the screen placing it once per dispatch was undone
        by the first resize after (found by WP7's own screen test: the
        cursor was on the selected row after ``_do_refresh`` and on row 0
        after ``a`` showed the body). The selection is the manager's
        (``swarm_seat_selected``); the ``▸`` and the cursor move together.
        """
        index = self.selected_row_index
        if index is None:
            return
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
            if table.cursor_row != index:
                table.move_cursor(row=index, animate=False)
        except Exception as exc:  # noqa: BLE001 -- cosmetic, never fatal
            logger.debug("%s: cursor not placed: %s", type(self).__name__, exc)

    # -- the cells ----------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, object] | None:
        token = _token(item.get("token_id"))
        selected = token is not None and token == self.selected_token
        prefix = "▸ " if selected else "  "
        # An identifier, not a quantity: never grouped (``IDMD #1,548`` is wrong).
        seat = f"{prefix}IDMD #{token if token is not None else DASH}"
        cells: dict[str, object] = {
            "seat": sanitize_cell(seat, SEAT_COLS),
            "agent": sanitize_cell(item.get("agent_id") or DASH, _AGENT_COLS),
            "nodes": fmt_int(item.get("nodes")),
            "jobs": fmt_int(item.get("jobs")),
            "roles": sanitize_cell(_roles_cell(item.get("roles")), _ROLES_COLS),
            "acc": fmt_int(item.get("accepted")),
            "rej": fmt_int(item.get("rejected")),
            "rev": fmt_int(item.get("revisions")),
            "score": (DASH if item.get("mean_score") is None
                      else fmt_float(item.get("mean_score"), ".1f")),
            "last": hhmm(item.get("last_active_ts")),
        }
        if selected:
            cells = {key: f"[bold]{value}[/]" for key, value in cells.items()}
        self._tokens.append(token)
        return cells

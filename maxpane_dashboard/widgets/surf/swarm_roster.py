"""ROSTER -- every seat the sweep has seen, one row each; the AGENT body's picker.

Swarm v2 plan Amendment A1 (WP6a). Unwired until WP7 exports the class,
mounts it on ``SurfScreen``'s ``MODE_AGENT`` body and binds
``DataTable.RowSelected`` -> ``manager.select_seat(token)``; this module only
knows how to paint the frozen ``swarm_seat_*`` contract.

The picker contract
-------------------
``CURSOR_TYPE = "row"`` and ``ROW_CAP = None``: the operator moves the cursor
and presses ``enter`` on a seat. Two things make that possible here rather
than in the screen: :meth:`SurfSwarmRoster.token_at` maps a painted row
index back to its ``token_id`` (rebuilt on every paint, aligned with the rows
the base actually added, so a skipped garbage row cannot shift the map by
one), and :attr:`SurfSwarmRoster.selected_token` /
:attr:`selected_row_index` expose the manager's selection so WP7 can move
the cursor onto it. The selected row is bold and prefixed ``▸``; the others
are indented two cells so the seat column stays aligned. The rows are
painted in the fold's order (``nodes`` desc) and never re-sorted.

:class:`SeatTableBase` -- the AGENT body's three tables
--------------------------------------------------------
ROSTER, RECORD (``swarm_seat_record.py``) and FEEDBACK
(``swarm_seat_feedback.py``) are all ``TableLeaderboard``\\ s that shed
columns by width tier, carry the slow tier's ``as of`` marker in their title
and distinguish an unread list (``None`` -> ``unavailable``) from a real
empty one (``[]`` -> their own sentence). ``TableLeaderboard`` states none
of that -- its ``COLUMNS`` are fixed at mount and its ``EMPTY_ROW`` paints
for ``None`` and ``[]`` alike -- so the shared mechanics live here once, as
a subclass the two sibling modules import. **Candidate hoist for WP7:** this
class belongs in a package-shared module (or beside the base in
``widgets/panels.py``) once WP7 owns the package; WP6a owns only its five
new files, so it lives in the first of them.

Why a footer line and not ``EMPTY_ROW``. A ``DataTable`` crops a cell to
its column, and the AGENT tables' first columns are five cells wide
(``when``) -- ``no nodes yet`` would render ``no no``. The degraded sentence
goes into a ``.panel-line`` ``Static`` under the table instead
(``swarm_shipped.py`` / ``pool4u_stakers.no_rows_line``'s idiom), the table
stays empty with its header, and ``EMPTY_ROW`` is the base's ``()`` no-op.

Widths are the ``#:`` blocks' measurements; every tier is a
:func:`table_cols` sum of them and the ladder is widest first. The panel's
budget reserves :attr:`SeatTableBase.GUTTER_COLS` for the table's own
vertical scrollbar, so the width requirement does not become a function of
the height (terminal-layout skill: *reserve the scrollbar gutter*).

Every third-party string (agent id, role word) goes through
``markup_safety.sanitize_cell`` before it meets the table; token ids are
integers, not addresses, and carry no copy icon. No clock: ``last`` is
``hhmm(last_active_ts)``, never an age.
"""

from __future__ import annotations

import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import sanitize_cell
from maxpane_dashboard.widgets.panels import TableLeaderboard
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "SEAT_COLS",
    "TIGHT_WIDTH",
    "SeatTableBase",
    "SurfSwarmRoster",
    "table_cols",
]

logger = logging.getLogger(__name__)

#: A ``DataTable`` pads every cell one cell on each side (``cell_padding``
#: defaults to 1), so a column costs ``width + 2``. :func:`rowfit.row_cols`
#: charges ``GAP`` (2) *between* cells -- the two adjoining pads -- and this
#: is the outer pair it does not.
_OUTER_PADDING = 2


def table_cols(widths) -> int:
    """Rendered width of a ``DataTable`` whose columns are ``widths`` cells."""
    return rowfit.row_cols(widths) + _OUTER_PADDING


class SeatTableBase(TableLeaderboard):
    """A ``TableLeaderboard`` that sheds columns by width tier -- see the module docstring.

    A subclass states :attr:`COLUMN_SPECS`, :attr:`SHED`, :attr:`LADDER`,
    :attr:`EMPTY_LINE` and implements :meth:`build_cells`; the base turns
    the active tier's keys into the base's tuple, installs the header the
    tier needs, paints the title with the marker and the widen hint, and
    writes the degraded sentence. :meth:`column_width` is the hook for a
    column whose width is not a constant (RECORD's ``detail`` takes the
    remaining budget; FEEDBACK's ``tx`` narrows at ``tight``).
    """

    #: ``(key, label, width)`` per column, the full tier, in table order.
    COLUMN_SPECS: tuple[tuple[str, str, int], ...] = ()

    #: tier name -> the column keys that tier sheds; ``full`` sheds none.
    SHED: dict[str, frozenset[str]] = {}

    #: Widest first; the last step's threshold is the floor and is not consulted.
    LADDER: rowfit.Ladder = rowfit.Ladder(("full", 0))

    #: The footer sentence for a real empty list (``[]``).
    EMPTY_LINE: str = "nothing yet"

    #: The footer sentence for an unread list (``None``) -- the shared word.
    UNAVAILABLE_LINE: str = "unavailable"

    #: Reserved for the table's own vertical scrollbar, so a roster that
    #: overflows its rows does not lose its last column's two cells to the
    #: nub: the width requirement must not depend on the height.
    GUTTER_COLS: int = 2

    #: The title's ``padding: 0 1`` (``PanelBase``), the room the hint fits in.
    TITLE_PADDING_COLS: int = 2

    #: The footer carries the sentence; the base's row is the no-op ``()``.
    EMPTY_ROW: tuple[str, ...] = ()

    DEFAULT_CSS = """
    SeatTableBase > DataTable {
        height: 1fr;
    }
    SeatTableBase > .panel-line {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._rows: object = None
        self._as_of: object = None
        self._seen = False
        self._tier = self.LADDER.steps[0][0]
        self._installed: tuple[tuple[str, int], ...] | None = None
        self._active_keys: tuple[str, ...] = ()
        self._widen = False

    # -- composition ------------------------------------------------------

    def compose_body(self) -> ComposeResult:
        yield DataTable(id=self.TABLE_ID)
        yield Static(Text(""), classes="panel-line", id=self._footer_id())

    def _footer_id(self) -> str:
        return f"{self.TABLE_ID}-footer"

    def on_mount(self) -> None:
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        except Exception:  # pragma: no cover - not composed
            return
        table.cursor_type = self.CURSOR_TYPE
        table.zebra_stripes = self.ZEBRA
        self._install_columns(table, self._layout(self._tier, self._budget()))

    def on_resize(self, _event=None) -> None:
        if self._seen:
            self._render_view()

    # -- geometry ----------------------------------------------------------

    def _budget(self) -> int:
        return max(self.size.width - self.GUTTER_COLS, 0)

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        """The width *key* renders at in *tier*; the spec's constant by default."""
        return width

    def _layout(self, tier: str, budget: int) -> tuple[tuple[str, int], ...]:
        shed = self.SHED.get(tier, frozenset())
        return tuple(
            (key, self.column_width(key, tier, budget, width))
            for key, _label, width in self.COLUMN_SPECS
            if key not in shed
        )

    def _install_columns(self, table: DataTable, layout: tuple[tuple[str, int], ...]) -> None:
        """(Re)build the header for *layout*; a no-op when it is already there."""
        if self._installed == layout:
            return
        labels = {key: label for key, label, _w in self.COLUMN_SPECS}
        try:
            table.clear(columns=True)
            for key, width in layout:
                table.add_column(labels[key], width=width, key=key)
        except Exception:  # pragma: no cover - defensive
            return
        self._installed = layout
        self._active_keys = tuple(key for key, _w in layout)

    # -- hooks --------------------------------------------------------------

    def build_cells(self, index: int, item) -> dict[str, object] | None:
        """Every column's cell for one item, keyed by column key; ``None`` skips it."""
        raise NotImplementedError

    def extra_widen(self) -> bool:
        """A subclass's own reason to light the hint (a clipped cell)."""
        return False

    def build_row(self, index: int, item) -> tuple | None:
        cells = self.build_cells(index, item)
        if cells is None:
            return None
        return tuple(cells[key] for key in self._active_keys)

    # -- rendering ----------------------------------------------------------

    def render_table(self, rows, *, footer=None) -> None:
        """Remember *rows* and paint them at the current width."""
        self._rows = rows
        self._seen = True
        self._render_view()

    def _render_view(self) -> None:
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        except Exception:  # not composed yet
            return
        budget = self._budget()
        self._tier = self.LADDER.tier_for(budget)
        self._install_columns(table, self._layout(self._tier, budget))
        rows = self._rows
        if isinstance(rows, list):
            super().render_table(rows)
            line = None if rows else (self.EMPTY_LINE, "dim")
        else:
            # ``None`` is "could not look"; anything else that is not a list
            # is a malformed payload (a hand-edited cache file) and reads the
            # same way -- never as a real empty.
            table.clear()
            line = (self.UNAVAILABLE_LINE, "yellow")
        self._widen = (bool(budget) and budget < self.LADDER.steps[0][1]) or self.extra_widen()
        self._render_footer(line)
        self._render_title()

    def _render_footer(self, line: tuple[str, str] | None) -> None:
        if line is None:
            self.write(f"#{self._footer_id()}", Text(""))
            return
        text, style = line
        self.write(f"#{self._footer_id()}", Text(text, style=style))

    def _render_title(self) -> None:
        base = self.TITLE
        if rowfit.has_marker(self._as_of):
            base += f" · as of {self._as_of}"
        room = max(self.size.width - self.TITLE_PADDING_COLS, 0)
        self.write(".panel-title", Text(rowfit.title_with_hint(base, self._widen, room)))


# ---------------------------------------------------------------------------
# ROSTER
# ---------------------------------------------------------------------------

EMPTY_LINE = "no seat seen"

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
_SHED = {
    "compact": frozenset({"roles"}),
    "tight": frozenset({"roles", "rev", "last"}),
}


def _tier_width(shed: frozenset[str]) -> int:
    return table_cols([w for k, _l, w in _SPECS if k not in shed])


#: Every column: 62 cells of content plus ten columns' padding = 82.
FULL_WIDTH = _tier_width(frozenset())
#: Without ``roles`` (12 + 2) = 68.
COMPACT_WIDTH = _tier_width(_SHED["compact"])
#: Without ``roles``, ``rev`` (4 + 2) and ``last`` (5 + 2) = 55.
TIGHT_WIDTH = _tier_width(_SHED["tight"])


def _token(value: object) -> int | None:
    """A seat token as an ``int``; ``None`` for anything else (``bool`` included)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def _roles_cell(roles: object) -> str:
    if not isinstance(roles, list):
        return DASH
    words = [_ROLE_WORDS.get(r, r) for r in roles if isinstance(r, str)]
    return "/".join(words) if words else DASH


class SurfSwarmRoster(SeatTableBase):
    """ROSTER -- one row per seat seen; the AGENT body's picker."""

    TITLE = "ROSTER"
    TABLE_ID = "surf-swarm-roster-table"
    CURSOR_TYPE = "row"
    ROW_CAP = None

    COLUMN_SPECS = _SPECS
    SHED = _SHED
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
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``**_kwargs``: the screen splats it)."""
        selected = swarm_seat_selected if isinstance(swarm_seat_selected, dict) else {}
        self.selected_token = _token(selected.get("token_id"))
        self._as_of = swarm_seat_as_of_hhmm
        self.render_table(swarm_seat_rows)

    def _render_view(self) -> None:
        self._tokens = []
        super()._render_view()
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

    # -- the cells ----------------------------------------------------------

    def build_cells(self, index: int, item) -> dict[str, object] | None:
        if not isinstance(item, dict):
            return None
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

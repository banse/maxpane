"""The swarm bodies' tiered ``DataTable`` panel -- one base under six tables (WP7 hoist).

CAPABILITY, LAUNCHES and SITES (the ``s`` body) and ROSTER, RECORD and
FEEDBACK (the ``a`` body) are all
:class:`~maxpane_dashboard.widgets.panels.TableLeaderboard`\\ s that shed
columns by width tier, carry a slow tier's ``as of`` marker in their title and
tell an unread list (``None``) from a real empty one (``[]``). WP6 wrote the
mechanics once as ``swarm_capability.SwarmTableBase`` and WP6a once more as
``swarm_roster.SeatTableBase``; this module is the one copy both sets of
tables import now (``rules/widgets.md``: a helper two modules need is hoisted,
never re-declared). The name carries ``Base`` because a class name is a CSS
type selector for every subclass; no stylesheet block names it.

What the base adds to ``TableLeaderboard``
--------------------------------------------
* **A width ladder** (``rowfit.Ladder``) over the panel's own ``size.width``
  less :attr:`SwarmTableBase.GUTTER_COLS`, the two cells the table's vertical
  scrollbar costs once its rows overflow -- reserved always, so the width
  requirement is not a function of the height (terminal-layout skill).
* **Columns re-installed on a tier change**, never hidden: a shed column is
  removed from the ``DataTable`` (``clear(columns=True)`` and re-add), because
  the layout sweep reads ``max_scroll_x`` and a zero-width column left behind
  is a hidden column with no marker. The shed is advertised in the title
  through ``rowfit.title_with_hint``, as is a clipped cell the tier did not
  shed (:attr:`_clipped`, set by a subclass's :meth:`build_cells`).
* **One mount.** Textual dispatches ``on_mount`` for every class in the MRO
  (``MessagePump._get_dispatch_methods``), so an explicit ``super().on_mount()``
  ran ``TableLeaderboard.on_mount`` twice and installed every column twice
  (probed 2026-09-21: a 111-cell table with a 222-cell virtual width). The
  base's handler calls no super and defers its repaint past the base's mount.
* **``None`` is not ``[]``**, and the two degraded states have two homes:
  - a table with :attr:`EMPTY_LINE` unset (CAPABILITY, LAUNCHES, SITES) lays
    ``unavailable`` (yellow) or its tier-trimmed ``EMPTY_ROW`` word into the
    first *visible* column wide enough to show it whole -- LAUNCHES' first
    column is ``#`` at 4 cells and a ``DataTable`` would cut the word to
    ``unav`` in silence -- and ``No data`` is painted only when there are no
    rows *and* no footer (the base rule, ``rules/widgets.md``);
  - a table with :attr:`EMPTY_LINE` set (ROSTER, RECORD, FEEDBACK) keeps its
    header, clears its rows and writes the sentence under the table instead
    -- their first column is ``when`` at 5 cells and ``no nodes yet`` would
    render ``no no``; ``EMPTY_ROW`` is the no-op ``()``.
* **A footer line under the table**, not a table row. A ``DataTable`` cannot
  span cells and cuts a long cell with no ellipsis (probed on Textual 8.1.1:
  ``30 skill``); CAPABILITY's summary is 83 cells against a widest cell of
  24. So a summary (:meth:`build_footer`, ``·``-joined, dim) or a degraded
  sentence is one ``Static`` (:attr:`footer_id`, class :attr:`FOOTER_CLASS`)
  beneath the table, clipped once to the panel's width and shown only when it
  has words -- the footer costs the panel one row when it shows, which the
  row sweeps see.

Third-party text
----------------
Every operator- or agent-chosen string a subclass paints goes through
``markup_safety.sanitize_cell`` (flatten, strip bracket runs, clip on
``cell_len``, escape) before it meets the table, and a footer word through
``strip_tags`` into a pre-built ``rich.text.Text`` (a ``Static`` never gets a
markup string). A complete ``[/x]`` run is therefore *removed*, not shown --
``rules/widgets.md``'s sanitiser contract.

Purity: stdlib, ``rich``, ``textual`` and this package's ``widgets/`` modules
only. No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.markup_safety import flatten, strip_tags, visible_len
from maxpane_dashboard.widgets.panels import UNAVAILABLE, TableLeaderboard
from maxpane_dashboard.widgets.surf._fmt import DASH

__all__ = [
    "CELL_PADDING",
    "UNAVAILABLE_ITEM",
    "SwarmTableBase",
    "table_cols",
]

logger = logging.getLogger(__name__)

#: What a ``DataTable`` spends on each column beyond the width asked for --
#: one cell of padding either side, charged for every column it has, the last
#: included (``pool4u_stakers._CELL_PADDING``'s measurement, restated).
CELL_PADDING = 2

#: A poll whose row list could not be read (``None``, or not a list).
UNAVAILABLE_ITEM = object()
#: A real empty read with no footer: paints the tier-trimmed ``EMPTY_ROW``.
_EMPTY_ITEM = object()

#: Between two summary parts laid into one footer line.
_SEP = " · "

#: The ``as of`` marker is ``HH:MM``; a hand-edited cache is third-party input
#: and a longer string is clipped rather than allowed to wrap the title.
_MARKER_COLS = 5


def table_cols(widths) -> int:
    """Rendered width of a ``DataTable`` with exactly these column widths.

    ``rowfit.row_cols`` charges ``GAP`` (2) between cells and a ``DataTable``
    charges :data:`CELL_PADDING` (2) per column including the last, so the
    table costs one more gap than the row -- the ``trailing`` term.
    """
    return rowfit.row_cols(widths, trailing=CELL_PADDING)


class SwarmTableBase(TableLeaderboard):
    """``TableLeaderboard`` plus the swarm tables' width tiers (module docstring).

    A subclass declares :attr:`COLUMN_SPECS` (``(key, label, width)`` in table
    order -- :attr:`COLUMNS` is derived from it for the base's mount),
    :attr:`TIER_COLUMNS` (tier name -> the keys it keeps) and :attr:`LADDER`
    (widest first), implements :meth:`build_cells` (a dict keyed like
    ``COLUMN_SPECS``, or ``None`` to skip the item) and optionally
    :meth:`build_footer` (a summary's parts, total first), :meth:`column_width`
    (one column whose width is not a constant: RECORD's ``detail`` takes the
    spare budget, FEEDBACK's ``tx`` narrows at ``tight``) or the whole
    :meth:`column_plan` (LAUNCHES). ``update_data`` stores through
    :meth:`store`. :attr:`EMPTY_LINE` picks where a degraded state is painted.
    """

    #: ``(key, label, width)`` per column, in table order, every tier's superset.
    COLUMN_SPECS: tuple[tuple[str, str, int], ...] = ()

    #: Tier name -> the column keys that tier keeps, in any order.
    TIER_COLUMNS: dict[str, tuple[str, ...] | frozenset[str]] = {}

    #: The panel's own width tiers, widest first (``rowfit.Ladder``).
    LADDER: rowfit.Ladder = rowfit.Ladder(("full", 0))

    #: The footer sentence for a real empty list (``[]``). ``None`` keeps the
    #: degraded states inside the table (module docstring).
    EMPTY_LINE: str | None = None

    #: The footer sentence for an unread list when :attr:`EMPTY_LINE` is set.
    UNAVAILABLE_LINE: str = "unavailable"

    #: The table's vertical scrollbar, reserved whether or not it is showing.
    GUTTER_COLS = 2

    #: ``PanelBase``'s title ``padding: 0 1``: the room ``title_with_hint`` gets.
    TITLE_PADDING_COLS = 2

    #: The footer ``Static``'s CSS class; its ``padding: 0 1`` lines the text up
    #: with the table's first cell and is the room the footer text gets.
    FOOTER_CLASS = "swarm-footer"
    FOOTER_PADDING_COLS = 2

    #: Geometry the six tables share: the table fills the panel, the footer is
    #: one row that exists only while it has words. A panel's place in the
    #: grid is the stylesheet's.
    DEFAULT_CSS = """
    SwarmTableBase > DataTable {
        height: 1fr;
    }
    SwarmTableBase > .swarm-footer {
        height: 1;
        padding: 0 1;
        display: none;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.COLUMN_SPECS:
            cls.COLUMNS = tuple((label, width) for _key, label, width in cls.COLUMN_SPECS)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict | None = None
        self._tier: str = self.LADDER.steps[0][0]
        #: The keys of the columns currently on the table, in table order.
        self._keys: tuple[str, ...] = tuple(key for key, _l, _w in self.COLUMN_SPECS)
        #: The plan the table was last built with; rebuilt only when it moves.
        self._installed: tuple[tuple[str, str, int], ...] | None = None
        self._widen = False
        #: Set by a subclass's ``build_cells`` when it clipped content the
        #: tier did not shed (LAUNCHES' parked reason, RECORD's detail); the
        #: title hint reads it.
        self._clipped = False

    # -- lifecycle ----------------------------------------------------------

    def compose_body(self) -> ComposeResult:
        yield from super().compose_body()
        yield Static("", id=self.footer_id, classes=self.FOOTER_CLASS)

    @property
    def footer_id(self) -> str:
        return f"{self.TABLE_ID}-footer"

    def on_mount(self) -> None:
        """Repaint a payload stored before mount -- *after* the base's mount.

        No ``super().on_mount()`` (module docstring: the MRO dispatch would run
        ``TableLeaderboard.on_mount`` twice). This handler runs first, the
        base's second; the repaint is deferred past it so its columns are the
        ones replaced.
        """
        self._installed = tuple(self.COLUMN_SPECS)
        if self._payload is not None:
            self.call_after_refresh(self._repaint)

    def on_resize(self, _event=None) -> None:
        if self._payload is not None:
            self._repaint()

    # -- hooks --------------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, str | Text] | None:
        """The cells for one row, keyed like :attr:`COLUMN_SPECS`; ``None`` skips it."""
        raise NotImplementedError

    def build_footer(self, summary) -> tuple[str, ...] | None:
        """The summary's parts (raw, unescaped words), or ``None`` for no footer."""
        return None

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        """The width *key* renders at in *tier*; the spec's constant by default."""
        return width

    def column_plan(self, tier: str, budget: int) -> tuple[tuple[str, str, int], ...]:
        """The columns *tier* keeps, in table order, each at :meth:`column_width`."""
        keep = self.TIER_COLUMNS.get(tier, ())
        return tuple(
            (key, label, self.column_width(key, tier, budget, width))
            for key, label, width in self.COLUMN_SPECS
            if key in keep
        )

    # -- rendering ----------------------------------------------------------

    def store(self, rows, as_of, summary=None) -> None:
        self._payload = {"rows": rows, "as_of": as_of, "summary": summary}
        self._repaint()

    def _budget(self) -> int:
        return max(self.size.width - self.GUTTER_COLS, 0)

    def _repaint(self) -> None:
        try:
            table = self.query_one(f"#{self.TABLE_ID}", DataTable)
        except Exception:
            return  # not composed yet; ``on_mount`` renders the stored payload
        budget = self._budget()
        self._tier = self.LADDER.tier_for(budget)
        plan = self.column_plan(self._tier, budget)
        self._install(table, plan)
        self._keys = tuple(key for key, _l, _w in plan)
        self._widen = bool(budget) and budget < self.LADDER.steps[0][1]
        self._clipped = False

        payload = self._payload or {}
        rows = payload.get("rows")
        if self.EMPTY_LINE is None:
            footer = self._write_footer(self.build_footer(payload.get("summary")))
            if isinstance(rows, list):
                items = rows if rows or footer else [_EMPTY_ITEM]
            else:
                items = [UNAVAILABLE_ITEM]
            if items:
                self.render_table(items)
            else:
                table.clear()  # ``[]`` under a footer: the footer is the fact, no ``No data``
        elif isinstance(rows, list):
            if rows:
                self.render_table(rows)
            else:
                table.clear()  # the sentence is the fact; ``EMPTY_ROW`` is not consulted
            self._write_footer(None if rows else (self.EMPTY_LINE,))
        else:
            # ``None`` is "could not look"; anything else that is not a list
            # is a malformed payload (a hand-edited cache file) and reads the
            # same way -- never as a real empty.
            table.clear()
            self._write_footer((self.UNAVAILABLE_LINE,), style="yellow")
        self._render_title(payload.get("as_of"))

    def _install(self, table: DataTable, plan) -> None:
        if plan == self._installed:
            return
        try:
            table.clear(columns=True)
            for key, label, width in plan:
                table.add_column(label, width=width, key=key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("%s: could not rebuild columns: %s", type(self).__name__, exc)
            return
        self._installed = plan

    def _render_title(self, as_of) -> None:
        base = self.TITLE
        if rowfit.has_marker(as_of):
            base += f" · as of {rowfit.clip(as_of, _MARKER_COLS)}"
        room = max(self.size.width - self.TITLE_PADDING_COLS, 0)
        widen = self._widen or self._clipped
        self.write(".panel-title", Text(rowfit.title_with_hint(base, widen, room)))

    def _write_footer(self, parts, *, style: str = "dim") -> bool:
        """Write the ``·``-joined *parts* under the table; ``False`` when none."""
        words = [strip_tags(flatten(part)) for part in (parts or ())]
        words = [word for word in words if word]
        try:
            footer = self.query_one(f"#{self.footer_id}", Static)
        except Exception:
            return bool(words)
        footer.display = bool(words)
        if words:
            room = max(self.size.width - self.FOOTER_PADDING_COLS, 0)
            footer.update(Text(rowfit.clip(_SEP.join(words), room), style=style))
        return bool(words)

    def _cells(self, by_key: dict) -> tuple:
        return tuple(by_key.get(key, "") for key in self._keys)

    def _degraded_row(self, word: str) -> tuple:
        """*word* (markup) in the first visible column that can show it whole."""
        need = visible_len(word)
        for key, _label, width in self._installed or ():
            if width >= need:
                return self._cells({key: word})
        return self._cells({self._keys[0] if self._keys else None: word})

    def build_row(self, index: int, item) -> tuple | None:
        if item is UNAVAILABLE_ITEM:
            return self._degraded_row(UNAVAILABLE)
        if item is _EMPTY_ITEM:
            word = next((cell for cell in self.EMPTY_ROW if cell and cell != DASH), "")
            return self._degraded_row(word)
        if not isinstance(item, dict):
            return None
        cells = self.build_cells(item)
        if cells is None:
            return None
        return self._cells(cells)

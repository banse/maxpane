"""CAPABILITY: the swarm's skill catalogue, one row per skill (swarm v2, WP6).

Unwired until WP7 swaps the ``s`` body over, exports the class and writes its
stylesheet block; this module is new and imports nothing from the five old
swarm widgets WP7 deletes.

A :class:`~maxpane_dashboard.widgets.panels.TableLeaderboard` with the width
tiers the swarm body's tables all need, so the tier machinery is written once
here as :class:`SwarmTableBase` and imported by ``swarm_launches.py`` and
``swarm_sites.py`` (``widget_wp_common.md``: a helper two WP6 modules need
lives in one of them; the hoist into ``widgets/surf/_swarm_table.py`` is
WP7's, reported).

What the base adds to ``TableLeaderboard``
--------------------------------------------
* **A width ladder** (``rowfit.Ladder``) over the panel's own ``size.width``
  less :attr:`SwarmTableBase.GUTTER_COLS`, the two cells the table's vertical
  scrollbar costs once its rows overflow -- reserved always, so the width
  requirement is not a function of the height (terminal-layout skill).
* **Columns re-installed on a tier change**, never hidden: a shed column is
  removed from the ``DataTable`` (``clear(columns=True)`` and re-add), because
  the layout sweep reads ``max_scroll_x`` and a zero-width column left behind
  is a hidden column with no marker. The tier's shed is advertised in the
  title through ``rowfit.title_with_hint``.
* **Tier-trimmed degraded rows.** ``EMPTY_ROW``/``LOADING_ROW`` stay full-width
  tuples (the base's mount check wants the column count); the empty row and
  the ``unavailable`` row are laid into whichever columns the tier kept, so
  the degraded state cannot raise on a surplus cell at a narrow tier.
* **``None`` is not ``[]``.** A row list that is ``None`` (or not a list at
  all) paints one row whose first cell is ``panels.UNAVAILABLE`` in yellow;
  ``[]`` paints ``EMPTY_ROW`` (``No data``), and only when there is no footer
  -- a footer is a row in its own right (the base rule, ``rules/widgets.md``).
* **A footer line under the table**, not a table row. A ``DataTable`` cannot
  span cells and cuts a long cell with no ellipsis (probed on Textual 8.1.1:
  ``30 skill``); CAPABILITY's summary is 83 cells against a widest cell of
  24. So the summary is one ``Static`` (:attr:`SwarmTableBase.FOOTER_ID`)
  beneath the table, ``·``-joined, clipped once to the panel's width, shown
  only when there is a summary. The base's rule still holds -- ``No data`` is
  painted only when there are no rows *and* no footer -- and the footer
  costs the panel one row, which WP7's row sweep sees.
* **Degraded words land where they can be read.** ``unavailable`` (11 cells)
  and ``No data`` (7) are placed in the first *visible* column wide enough
  for them, at every tier -- LAUNCHES' first column is ``#`` at 4 cells, and a
  ``DataTable`` would cut the word to ``unav`` in silence.

Third-party text
----------------
Skill ids, versions, roles, tiers, judges, checks and every ``requires`` entry
are strings the swarm's operators chose; each goes through
``markup_safety.sanitize_cell`` (flatten, strip bracket runs, clip on
``cell_len``, escape) before it meets the table, and a footer word through
``strip_tags`` into a pre-built ``rich.text.Text`` (a ``Static`` never gets a
markup string). A complete ``[/x]`` run is therefore
*removed*, not shown -- ``rules/widgets.md``'s sanitiser contract, which
wins over a brief's "renders literally" (a lone ``[`` does render literally).

Purity: stdlib, ``rich``, ``textual`` and this package's ``widgets/`` modules
only. No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags, visible_len
from maxpane_dashboard.widgets.panels import LOADING, UNAVAILABLE, TableLeaderboard
from maxpane_dashboard.widgets.surf._fmt import DASH

__all__ = [
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "TIGHT_WIDTH",
    "SurfSwarmCapability",
    "SwarmTableBase",
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

#: Between two summary parts laid into one footer cell.
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
    ``COLUMN_SPECS``) and optionally :meth:`build_footer` (the summary's parts,
    total first) and :meth:`column_plan` (a tier's columns, where a width is
    not a constant). ``update_data`` stores through :meth:`store`.

    The name carries ``Base`` because a class name is a CSS type selector for
    every subclass (``rules/widgets.md``); no stylesheet block names it.
    """

    #: ``(key, label, width)`` per column, in table order, every tier's superset.
    COLUMN_SPECS: tuple[tuple[str, str, int], ...] = ()

    #: Tier name -> the column keys that tier keeps, in any order.
    TIER_COLUMNS: dict[str, tuple[str, ...]] = {}

    #: The panel's own width tiers, widest first (``rowfit.Ladder``).
    LADDER: rowfit.Ladder = rowfit.Ladder(("full", 0))

    #: The table's vertical scrollbar, reserved whether or not it is showing.
    GUTTER_COLS = 2

    #: ``PanelBase``'s title ``padding: 0 1``: the room ``title_with_hint`` gets.
    TITLE_PADDING_COLS = 2

    #: The footer ``Static``'s CSS class; its ``padding: 0 1`` lines the text up
    #: with the table's first cell and is the room the footer text gets.
    FOOTER_CLASS = "swarm-footer"
    FOOTER_PADDING_COLS = 2

    DEFAULT_CSS = """
    SwarmTableBase > .swarm-footer {
        height: 1;
        padding: 0 1;
        display: none;
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
        #: tier did not shed (LAUNCHES' parked reason); the title hint reads it.
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

        No ``super().on_mount()``: Textual dispatches ``on_mount`` for every
        class in the MRO (``MessagePump._get_dispatch_methods``), so the
        explicit call ran ``TableLeaderboard.on_mount`` twice and installed
        every column twice (probed 2026-09-21: a 111-cell table with a
        222-cell virtual width). This handler runs first, the base's second;
        the repaint is deferred past it so its columns are the ones replaced.
        """
        self._installed = tuple(self.COLUMN_SPECS)
        if self._payload is not None:
            self.call_after_refresh(self._repaint)

    def on_resize(self, _event=None) -> None:
        if self._payload is not None:
            self._repaint()

    # -- hooks --------------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, str | Text]:
        """The cells for one row, keyed like :attr:`COLUMN_SPECS`."""
        raise NotImplementedError

    def build_footer(self, summary) -> tuple[str, ...] | None:
        """The summary's parts (raw, unescaped words), or ``None`` for no footer."""
        return None

    def column_plan(self, tier: str, budget: int) -> tuple[tuple[str, str, int], ...]:
        """The columns *tier* keeps, in table order; *budget* for a panel whose
        one elastic column takes the spare width (LAUNCHES)."""
        keep = self.TIER_COLUMNS.get(tier, ())
        return tuple(spec for spec in self.COLUMN_SPECS if spec[0] in keep)

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
        footer = self._render_footer(self.build_footer(payload.get("summary")))
        if isinstance(rows, list):
            items = rows if rows or footer else [_EMPTY_ITEM]
        else:
            items = [UNAVAILABLE_ITEM]
        if items:
            self.render_table(items)
        else:
            table.clear()  # ``[]`` under a footer: the footer is the fact, no ``No data``
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

    def _render_footer(self, parts) -> bool:
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
            footer.update(Text(rowfit.clip(_SEP.join(words), room), style="dim"))
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
        return self._cells(self.build_cells(item))


# -- CAPABILITY -------------------------------------------------------------

# Column budgets, in rendered cells, measured against the committed corpus
# ``tests/fixtures/surf/swarm/v2/skills.json`` (30 skills, 2026-09-21). The
# vocabulary is the operators' and not closed, so a value that outgrows its
# cell is clipped with a visible ``…`` by ``sanitize_cell``, never a reason
# to move a pin.

#: ``skill``: the widest captured id is 24 cells; fits whole.
_SKILL_COLS = 24
#: ``v``: an int version (``2`` today); three cells hold ``999``.
_VERSION_COLS = 3
#: ``role``: ``reference`` (9) is the widest of implement/integrate/reference/
#: review/tests.
_ROLE_COLS = 9
#: ``tier``: one digit or ``--``; the header itself is the widest thing (4).
_TIER_COLS = 4
#: ``judge``: ``verifier-paths`` / ``verifier-rerun`` (14).
_JUDGE_COLS = 14
#: ``checks``: a str ≤ 7 today (``foundry``) or null -> ``--``.
_CHECKS_COLS = 7
#: ``requires``: entries are capability tokens (``network``, ``tool:audio``,
#: ``runtime:codex`` -- 13, the widest) and no skill lists more than one
#: today; ``, ``-joined when one does, clipped visibly then. Never shed: the
#: plan calls this column the point of the panel.
_REQUIRES_COLS = 14

_SPECS = (
    ("skill", "skill", _SKILL_COLS),
    ("version", "v", _VERSION_COLS),
    ("role", "role", _ROLE_COLS),
    ("tier", "tier", _TIER_COLS),
    ("judge", "judge", _JUDGE_COLS),
    ("checks", "checks", _CHECKS_COLS),
    ("requires", "requires", _REQUIRES_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "checks")
_TIGHT = tuple(key for key in _COMPACT if key != "judge")

#: ``full``: all seven columns -- 89 cells. The table's own need; the panel
#: adds :attr:`SwarmTableBase.GUTTER_COLS` for its scrollbar (the catalogue is
#: 30 rows and scrolls in any body-sized slot).
FULL_WIDTH = table_cols(w for k, _l, w in _SPECS)                    # 89
#: ``compact``: ``checks`` shed (the cheapest column that is not the point of
#: the panel) -- 80.
COMPACT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _COMPACT)  # 80
#: ``tight``: ``judge`` shed too; ``requires`` stays at every tier -- 64.
TIGHT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _TIGHT)      # 64


def _requires_cell(value) -> str:
    """``requires`` as ``a, b``; ``--`` for ``[]``/``None``; a str passes as is."""
    if isinstance(value, (list, tuple)):
        parts = [strip_tags(entry) for entry in value]
        joined = ", ".join(part for part in parts if part)
    else:
        joined = strip_tags(value)
    return sanitize_cell(joined, _REQUIRES_COLS) or DASH


class SurfSwarmCapability(SwarmTableBase):
    """CAPABILITY -- ``skill · v · role · tier · judge · checks · requires``."""

    TITLE = "CAPABILITY"
    TABLE_ID = "surf-swarm-capability-table"
    #: The catalogue is the content: every skill, no cap (30 today).
    ROW_CAP = None
    CURSOR_TYPE = "row"

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH)
    )

    LOADING_ROW = (LOADING, "", "", "", "", "", "")
    EMPTY_ROW = ("No data", "", "", "", "", "", "")

    #: Geometry only; the title and its blank row are ``PanelBase``'s, the
    #: panel's place in the grid is WP7's stylesheet.
    DEFAULT_CSS = """
    SurfSwarmCapability > DataTable {
        height: 1fr;
    }
    """

    def update_data(
        self,
        swarm_skill_rows=None,
        swarm_skill_summary=None,
        swarm_scores_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``SWARM_WIDGET_SIGNATURES``)."""
        self.store(swarm_skill_rows, swarm_scores_as_of_hhmm, swarm_skill_summary)

    def build_cells(self, item: dict) -> dict[str, str]:
        return {
            "skill": sanitize_cell(item.get("skill_id"), _SKILL_COLS) or DASH,
            "version": fmt_int(item.get("version")),
            "role": sanitize_cell(item.get("role"), _ROLE_COLS) or DASH,
            "tier": fmt_int(item.get("tier")),
            "judge": sanitize_cell(item.get("judge"), _JUDGE_COLS) or DASH,
            "checks": sanitize_cell(item.get("checks"), _CHECKS_COLS) or DASH,
            "requires": _requires_cell(item.get("requires")),
        }

    def build_footer(self, summary) -> tuple[str, ...] | None:
        """``30 skills · 19 implement · 7 reference · … · 11 requires``."""
        if not isinstance(summary, dict):
            return None
        parts = [f"{fmt_int(summary.get('total'))} skills"]
        by_role = summary.get("by_role")
        if isinstance(by_role, list):
            counted = [
                entry for entry in by_role
                if isinstance(entry, dict) and fmt_int(entry.get("count")) != DASH
            ]
            counted.sort(key=lambda entry: -int(entry.get("count")))
            parts.extend(
                f"{fmt_int(entry.get('count'))} {strip_tags(entry.get('role')) or DASH}"
                for entry in counted
            )
        parts.append(f"{fmt_int(summary.get('requires_count'))} requires")
        return tuple(parts)

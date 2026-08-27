"""The linked-wallet groups (PRD §5.1) — the ``f`` view's first panel.

One row per operator, in the order the analysis adapter hands them::

    1,995 linked  identical 0.45Ξ send ×1,995 · shared funder …  1,811,322  6.8%  44.6×  ⚑

Pattern language only
---------------------

The word for a row here is **linked**: it names what is in the deposit,
transaction and funding data.  ``sybil``, ``cheat``, ``fraud``, ``attack``,
``abuse`` and ``wash`` name an intent this dashboard cannot read, and the
same forbidden-word list that guards the analytics source guards this
panel's composited output.  ``sqrt_subsidy_x`` renders as a bare multiple
(``44.6×``) because it is a property of the curve — it pays ``sqrt(k)`` for
splitting one bankroll across ``k`` wallets — not an accusation.

Confidence is a glyph, never a number
-------------------------------------

``conf`` renders through the **leaderboard's own vocabulary** — ``⚑`` for
``"high"``, ``◌`` for ``"low"``, ``?`` for anything this panel cannot read
(``None`` included) — so one wallet reads the same on both panels.  A raw
``0.87`` on screen is a verdict with a decimal point (PRD §5.1), and the
one cell an unreadable grade must never land in is the empty one, which is
the *clean* rendering.

``None`` is never a zero
------------------------

``operators_count is None`` means the detached B+C sweep has not published
(or could not), and renders :data:`OPERATORS_UNAVAILABLE`.
``operators_count == 0`` is the sweep answering "none linked" — a real,
healthy negative — and renders :data:`OPERATORS_EMPTY`.  Collapsing the two
is the FARM-row defect on the panel that feeds it.

Width behaviour
---------------

==========  ====  ====================================================
Tier        Cost  Columns
==========  ====  ====================================================
full         134  SIZE  EVIDENCE(82)  POINTS  SHARE  SQRT  CONF
no-sqrt      126  SIZE  EVIDENCE(82)  POINTS  SHARE  CONF
no-points    114  SIZE  EVIDENCE(82)  SHARE  CONF
brief         85  SIZE  EVIDENCE(53)  SHARE  CONF
==========  ====  ====================================================

The derived columns shed first — the subsidy multiple is arithmetic on the
size, the points can be read off the leaderboard — and the size, the
evidence and the share never do: they are the finding.  The evidence cell
is the one cell whose worst case (159 joined columns in the committed
slices) no layout can afford, so phrases are dropped **whole, from the
end, behind a visible ``…``** (:func:`_join_reasons`) rather than cut
mid-word by the table in silence.  53 is the widest single reason the
slices hold, so the brief tier still shows one whole phrase.

Primitives only — this module imports nothing from ``data/`` or
``analytics/``.
"""

from __future__ import annotations

from rich.cells import cell_len
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import DASH, as_float, fmt_pct, fmt_points
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    title_with_hint,
    with_optional_suffix,
)
from maxpane_dashboard.widgets.curator.leaderboard import (
    LINK_HIGH,
    LINK_LOW,
    LINK_UNKNOWN,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended, never substituted.
OPERATORS_TITLE = "OPERATORS"

#: The explicit states, tested verbatim and deliberately different: `None`
#: is a sweep that could not answer, `0` is a sweep that answered "none".
OPERATORS_UNAVAILABLE = "analysis unavailable"
OPERATORS_EMPTY = "no linked groups found"

#: Rows rendered.  Six, because the analysis body stacks three panels under
#: one hero and the screen's height budget (ANALYSIS_MIN_HEIGHT) is measured
#: against exactly these caps — grow one only with the screen's sweep open.
MAX_ROWS = 6

#: The size cell, derived from the producer's vocabulary rather than the one
#: captured example: a group is counted in wallets and the board held 15,576
#: contributors at capture time, so five digits with the thousands separator
#: is the bound — one digit of headroom over the widest measured operator
#: (1,995).  ``len("99,999 linked")``.
_SIZE_COLS = len(f"{99_999:,} linked")                                     # 13

#: The evidence cell.  The committed slices join to 159 columns at worst, so
#: this is a **budget with a visible overflow contract** (see
#: :func:`_join_reasons`), not a fit: 82 holds the widest single reason (53,
#: pinned by ``test_the_widest_strings_the_analysis_panels_must_fit``) plus a
#: second phrase, and is what the full tier can afford inside the analysis
#: body at the screen's pinned width.
_REASONS_COLS = 82
#: The brief tier's evidence cell: exactly the widest single reason the
#: slices hold, so one whole phrase always renders.
_REASONS_BRIEF_COLS = 53

#: One order of magnitude over the widest measured operator (4,755,046
#: points), and the same ten columns the cluster table's POINTS cell spends,
#: so the two tables' score columns agree.
_POINTS_COLS = 10

#: ``100.0%`` plus one; the same seven the cluster table spends.
_SHARE_COLS = 7

#: ``sqrt(99,999) ≈ 316.2`` — the subsidy multiple's ceiling under the size
#: bound above renders ``316.2×``, six columns.
_SQRT_COLS = 6

#: One glyph under a four-column header.
_CONF_COLS = 4

_FULL_COLUMNS = (
    ("size", "SIZE", _SIZE_COLS),
    ("reasons", "EVIDENCE", _REASONS_COLS),
    ("points", "POINTS", _POINTS_COLS),
    ("share", "SHARE", _SHARE_COLS),
    ("sqrt", "SQRT", _SQRT_COLS),
    ("conf", "CONF", _CONF_COLS),
)

_TIERS = (
    ("full", 134, _FULL_COLUMNS, ""),
    (
        "no-sqrt",
        126,
        (
            ("size", "SIZE", _SIZE_COLS),
            ("reasons", "EVIDENCE", _REASONS_COLS),
            ("points", "POINTS", _POINTS_COLS),
            ("share", "SHARE", _SHARE_COLS),
            ("conf", "CONF", _CONF_COLS),
        ),
        "‹ widen: sqrt subsidy",
    ),
    (
        "no-points",
        114,
        (
            ("size", "SIZE", _SIZE_COLS),
            ("reasons", "EVIDENCE", _REASONS_COLS),
            ("share", "SHARE", _SHARE_COLS),
            ("conf", "CONF", _CONF_COLS),
        ),
        "‹ widen: sqrt subsidy + POINTS",
    ),
    (
        "brief",
        85,
        (
            ("size", "SIZE", _SIZE_COLS),
            ("reasons", "EVIDENCE", _REASONS_BRIEF_COLS),
            ("share", "SHARE", _SHARE_COLS),
            ("conf", "CONF", _CONF_COLS),
        ),
        "‹ widen: sqrt subsidy + POINTS + evidence",
    ),
)

#: ``conf`` → markup.  ``None`` and every unreadable spelling render the
#: unknown glyph: the empty cell means *clean* on the leaderboard, so it is
#: the one rendering a missing grade must never fall into.
_CONF_GLYPH = {
    "high": f"[yellow]{LINK_HIGH}[/]",
    "low": f"[dim]{LINK_LOW}[/]",
}


def _conf_cell(conf) -> str:
    if isinstance(conf, str) and conf in _CONF_GLYPH:
        return _CONF_GLYPH[conf]
    return f"[dim]{LINK_UNKNOWN}[/]"


def _join_reasons(reasons, width: int) -> str:
    """Join pattern-language phrases into *width* columns, shedding whole
    phrases from the **end** behind a visible ``…``.

    The strongest phrase comes first from the producer, so the drop order is
    weakest-first; a phrase is never cut mid-word unless even the first one
    alone does not fit, and every drop leaves an ellipsis a reader can see.
    Returns :data:`DASH` for anything that is not a non-empty list of
    strings — a malformed payload costs the evidence, never the row.
    """
    if not isinstance(reasons, list):
        return DASH
    phrases = [" ".join(str(r).split()) for r in reasons]
    phrases = [p for p in phrases if p]
    if not phrases:
        return DASH
    kept: list[str] = []
    for phrase in phrases:
        if len(" · ".join(kept + [phrase])) <= width:
            kept.append(phrase)
        else:
            break
    if not kept:
        return phrases[0][: max(width - 1, 1)] + "…"
    if len(kept) < len(phrases):
        joined = " · ".join(kept) + " …"
        if len(joined) <= width:
            return joined
        return " · ".join(kept)[: max(width - 1, 1)] + "…"
    return " · ".join(kept)


def _row_values(row: dict, reasons_width: int) -> dict:
    """One operator row's cells.  Every field degrades on its own."""
    size = row.get("size")
    try:
        size_str = f"{int(size):,} linked"
    except (TypeError, ValueError):
        size_str = f"{DASH} linked"
    share = row.get("points_share_pct")
    subsidy = as_float(row.get("sqrt_subsidy_x"))
    return {
        "size": safe_markup(size_str),
        "reasons": safe_markup(_join_reasons(row.get("reasons"), reasons_width)),
        "points": fmt_points(row.get("points")),
        # None is a division refused, never a zero measured.
        "share": fmt_pct(share) if share is not None else DASH,
        "sqrt": f"{subsidy:.1f}×" if subsidy is not None else DASH,
        "conf": _conf_cell(row.get("conf")),
    }


class CuratorOperators(Vertical):
    """The linked groups, in pattern language, with a verdict-free grade."""

    DEFAULT_CSS = """
    /* One blank row under the title and NONE under the note: this panel
       shares a stacked, height-budgeted body with two siblings, so rows are
       the scarce thing here where the `c` slot has rows to spare. */
    CuratorOperators > .curator-op-title {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorOperators > .curator-op-note {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    CuratorOperators > DataTable {
        height: auto;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._payload: dict = {}
        self._columns: tuple = ()
        self._hint: str = ""
        self._tier: str = "full"

    def compose(self) -> ComposeResult:
        yield Static(OPERATORS_TITLE, classes="curator-op-title", id="curator-op-title")
        yield Static("", classes="curator-op-note", id="curator-op-note")
        yield DataTable(id="curator-op-table", classes="curator-op-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-op-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"size": "[dim]…[/]"}, columns, default=""))

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    # -- layout ------------------------------------------------------------

    def _apply_columns(self, table: DataTable) -> tuple:
        width = table.content_size.width or self.content_size.width
        name, columns, hint = pick_tier(_TIERS, width)
        install_columns(table, columns, self._columns)
        self._columns = columns
        self._hint = hint
        self._tier = name
        return columns

    def _set_title(self) -> None:
        """Title plus the widen marker; the note carries it when it does not fit."""
        width = max(self.content_size.width - 2, 0)
        text, placed = title_with_hint(OPERATORS_TITLE, self._hint, width)
        self.query_one("#curator-op-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    def _set_note(self, text: str) -> None:
        if not getattr(self, "_hint_placed", True):
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-op-note", Static).update(text)

    # -- rendering ---------------------------------------------------------

    def update_data(
        self,
        operator_rows=None,
        operators_count=None,
        flagged_points_share_pct=None,
        analysis_as_of_hhmm=None,
        analysis_version=None,
        **_kwargs,
    ) -> None:
        """Refresh the table and its one-line summary."""
        self._payload = {
            "rows": operator_rows,
            "count": operators_count,
            "share": flagged_points_share_pct,
            "as_of": analysis_as_of_hhmm,
            "version": analysis_version,
            "seen": True,
        }
        self._render_view()

    def _as_of(self, prefix: str = "") -> str:
        """The freshness marker, plus THE LIST's analysis version when it fits.

        ``prefix`` is the plain text already set to render before this
        marker on the same note line -- passed in only so the fit check sees
        the whole line.  The marker is load-bearing and always renders whole
        once ``as_of`` is set; the version is decorative and is what sheds on
        a panel too narrow for both.
        """
        stamp = self._payload.get("as_of")
        if not (isinstance(stamp, str) and stamp.strip()):
            return ""
        marker = f" · as of {safe_markup(stamp.strip())}"
        version = self._payload.get("version")
        if isinstance(version, str) and version.strip():
            width = max(self.content_size.width - 2 - cell_len(prefix), 0)
            suffix = f" · {safe_markup(version.strip())}"
            return with_optional_suffix(marker, suffix, width)
        return marker

    def _summary(self) -> str:
        count = self._payload.get("count")
        share = self._payload.get("share")
        plural = "" if count == 1 else "s"
        text = f"{count:,} linked group{plural}"
        if share is not None:
            text += f" · {fmt_pct(share)} of all points"
        return f"[dim]{text}{self._as_of(text)}[/]"

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-op-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()
        reasons_width = next(
            (w for key, _h, w in columns if key == "reasons"), _REASONS_COLS
        )

        count = self._payload.get("count")
        if not isinstance(count, int) or isinstance(count, bool):
            # The sweep has not published, or could not.  Never a zero.
            self._set_note(
                f"[$warning]⚠ {OPERATORS_UNAVAILABLE}[/]"
                f"{self._as_of(f'⚠ {OPERATORS_UNAVAILABLE}')}"
            )
            table.add_row(*cells({}, columns, default=DASH))
            return
        if count == 0:
            # A real negative: the sweep ran and found no linked groups.
            self._set_note(
                f"[dim]{OPERATORS_EMPTY}{self._as_of(OPERATORS_EMPTY)}[/]"
            )
            return

        try:
            usable = [r for r in list(self._payload["rows"] or []) if isinstance(r, dict)]
        except TypeError:
            usable = []
        if not usable:
            # A count with no rows is a torn payload: say unavailable rather
            # than render a healthy-looking empty table under a real count.
            self._set_note(
                f"[$warning]⚠ {OPERATORS_UNAVAILABLE}[/]"
                f"{self._as_of(f'⚠ {OPERATORS_UNAVAILABLE}')}"
            )
            table.add_row(*cells({}, columns, default=DASH))
            return

        self._set_note(self._summary())
        for row in usable[:MAX_ROWS]:
            try:
                values = _row_values(row, reasons_width)
            except Exception:
                values = {"size": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))

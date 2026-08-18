"""Population segments (PRD §5.2) — the ``f`` view's second panel.

One row per derived band: whale **operators** by combined credit, the
index-1000 early cohort, per-hour join bands, per-multiplier bands::

    largest operators                  6,303   43.2%   16 linked groups · 0.45Ξ–171.99Ξ send shapes

Pattern language only: the labels are the producer's ("largest operators",
"early cohort"), and the same forbidden-word list that guards the analytics
source guards this panel's composited output — a whale here is a size, never
an intent.

``points_share_pct`` is ``None``-honest per row
-----------------------------------------------

Some bands carry a contributor count but no attributable share (the
committed ``degraded_row`` is a per-hour band exactly like that), and a
``0.0%`` there would read "this hour scored nothing" — a measurement nobody
made.  ``None`` renders the package dash.

Width behaviour
---------------

==========  ====  ==============================================
Tier        Cost  Columns
==========  ====  ==============================================
full         111  BAND(33)  WALLETS  SHARE  DETAIL(56)
no-detail     53  BAND(33)  WALLETS  SHARE
minimal       44  BAND(33)  SHARE
==========  ====  ==============================================

The detail is free text and sheds first; the label is the band's identity
and the share is the finding, so neither ever does.  33 and 56 are the
widest label and the widest detail in the committed slices (the 56 lives in
``degraded_row``, *outside* ``rows`` — the envelope lesson), pinned by
``test_the_widest_strings_the_analysis_panels_must_fit``.

Primitives only — this module imports nothing from ``data/`` or
``analytics/``.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from maxpane_dashboard.widgets.curator._fmt import DASH, fmt_pct
from maxpane_dashboard.widgets.curator._table import (
    WIDEN_HINT,
    cells,
    install_columns,
    pick_tier,
    title_with_hint,
)
from maxpane_dashboard.widgets.markup_safety import safe_markup

#: Panel title.  A hint is appended, never substituted.
SEGMENTS_TITLE = "SEGMENTS"

#: The explicit states, tested verbatim: an unreadable analysis and an
#: analysis that has produced no bands are different facts.
SEGMENTS_UNAVAILABLE = "segments unavailable"
SEGMENTS_EMPTY = "no segments yet"

#: Rows rendered.  Eight of the twelve derived bands: the analysis body
#: stacks three panels and the screen's ANALYSIS_MIN_HEIGHT is measured
#: against exactly these caps — grow one only with the screen's sweep open.
MAX_ROWS = 8

#: The widest band label in the committed slices ("early cohort · join
#: index 1–1000", 33 columns).  A longer label ellipsises inside its cell.
_LABEL_COLS = 33

#: Contributor counts are bounded by the board's own population — 15,576 at
#: capture time, so five digits with the separator — but the seven-column
#: header is what actually sets this cell.
_CONTRIB_COLS = len("WALLETS")

#: ``100.0%`` plus one; the same seven the other curator tables spend.
_SHARE_COLS = 7

#: The widest detail string in the committed slices — 56 columns, carried by
#: ``degraded_row``, the one row written by hand *outside* ``rows``.
_DETAIL_COLS = 56

_TIERS = (
    (
        "full",
        111,
        (
            ("label", "BAND", _LABEL_COLS),
            ("contributors", "WALLETS", _CONTRIB_COLS),
            ("share", "SHARE", _SHARE_COLS),
            ("detail", "DETAIL", _DETAIL_COLS),
        ),
        "",
    ),
    (
        "no-detail",
        53,
        (
            ("label", "BAND", _LABEL_COLS),
            ("contributors", "WALLETS", _CONTRIB_COLS),
            ("share", "SHARE", _SHARE_COLS),
        ),
        "‹ widen: detail",
    ),
    (
        "minimal",
        44,
        (
            ("label", "BAND", _LABEL_COLS),
            ("share", "SHARE", _SHARE_COLS),
        ),
        "‹ widen: detail + WALLETS",
    ),
)


def _row_values(row: dict) -> dict:
    """One band's cells.  Every field degrades on its own."""
    label = " ".join(str(row.get("label") or "").split())
    contributors = row.get("contributors")
    try:
        contrib_str = f"{int(contributors):,}"
    except (TypeError, ValueError):
        contrib_str = DASH
    share = row.get("points_share_pct")
    detail = " ".join(str(row.get("detail") or "").split())
    return {
        "label": safe_markup(label) if label else DASH,
        "contributors": contrib_str,
        # None is a share nobody could attribute, never a zero measured.
        "share": fmt_pct(share) if share is not None else DASH,
        "detail": safe_markup(detail) if detail else DASH,
    }


class CuratorSegments(Vertical):
    """The derived bands, in pattern language, with per-row share honesty."""

    DEFAULT_CSS = """
    /* One blank row under the title and NONE under the note: this panel
       shares a stacked, height-budgeted body with two siblings, so rows are
       the scarce thing here. */
    CuratorSegments > .curator-seg-title {
        width: 100%;
        margin: 0 0 1 0;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    CuratorSegments > .curator-seg-note {
        width: 100%;
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    CuratorSegments > DataTable {
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
        yield Static(
            SEGMENTS_TITLE, classes="curator-seg-title", id="curator-seg-title"
        )
        yield Static("", classes="curator-seg-note", id="curator-seg-note")
        yield DataTable(id="curator-seg-table", classes="curator-seg-table")

    def on_mount(self) -> None:
        table = self.query_one("#curator-seg-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        columns = self._apply_columns(table)
        table.add_row(*cells({"label": "[dim]…[/]"}, columns, default=""))

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
        text, placed = title_with_hint(SEGMENTS_TITLE, self._hint, width)
        self.query_one("#curator-seg-title", Static).update(text)
        self._hint_placed = placed or not self._hint

    def _set_note(self, text: str) -> None:
        if not getattr(self, "_hint_placed", True):
            marker = f"[yellow]{WIDEN_HINT}[/]"
            text = f"{marker} {text}" if text else marker
        self.query_one("#curator-seg-note", Static).update(text)

    # -- rendering ---------------------------------------------------------

    def update_data(
        self, segment_rows=None, analysis_as_of_hhmm=None, **_kwargs
    ) -> None:
        """Refresh the table and its one-line summary."""
        self._payload = {
            "rows": segment_rows,
            "as_of": analysis_as_of_hhmm,
            "seen": True,
        }
        self._render_view()

    def _as_of(self) -> str:
        stamp = self._payload.get("as_of")
        if isinstance(stamp, str) and stamp.strip():
            return f" · as of {safe_markup(stamp.strip())}"
        return ""

    def _render_view(self) -> None:
        try:
            table = self.query_one("#curator-seg-table", DataTable)
        except Exception:  # not composed yet
            return
        if not self._payload:
            return

        columns = self._apply_columns(table)
        self._set_title()

        rows = self._payload["rows"]
        if rows is None:
            self._set_note(f"[$warning]⚠ {SEGMENTS_UNAVAILABLE}[/]{self._as_of()}")
            table.add_row(*cells({}, columns, default=DASH))
            return

        try:
            raw = list(rows)
        except TypeError:
            raw = None
        usable = (
            [r for r in raw if isinstance(r, dict)] if raw is not None else []
        )

        if raw is None or (raw and not usable):
            # A torn payload (uniterable, or rows that are not rows) is not a
            # finding: rendered as the empty state it would be a confident
            # "no segments yet" drawn from bytes nobody could read (M2).
            self._set_note(f"[$warning]⚠ {SEGMENTS_UNAVAILABLE}[/]{self._as_of()}")
            table.add_row(*cells({}, columns, default=DASH))
            return

        if not usable:
            # A real negative: the sweep ran and derived no bands.
            self._set_note(f"[dim]{SEGMENTS_EMPTY}{self._as_of()}[/]")
            return

        plural = "" if len(usable) == 1 else "s"
        self._set_note(f"[dim]{len(usable)} band{plural}{self._as_of()}[/]")
        for row in usable[:MAX_ROWS]:
            try:
                values = _row_values(row)
            except Exception:
                values = {"label": f"[dim]{DASH}[/]"}
            table.add_row(*cells(values, columns, default=DASH))

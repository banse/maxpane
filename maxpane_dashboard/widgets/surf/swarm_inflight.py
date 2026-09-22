"""IN FLIGHT: one snapshot row per executing job, in the fold's order.

Rows carry age, template, seat, role/state, objective and the last note column.
The tier ladder sheds role/state, then seat. Objective and note share the
remaining budget: twenty objective cells and twelve note cells at the tier
floor, then each receives half the extra width. Long notes have an ellipsis
and keep the title's widen marker lit even in the full tier. A literal served
ellipsis does not itself mean clipping.

Notes use strip-then-escape sanitization. Existing template/objective/role/state
cells retain their literal Text rendering contract; no markup is parsed for
those fields. Template and objective deliberately avoid sanitize_cell: its
strip_tags step would delete meaningful user text in square brackets. Rich
Text keeps those brackets literal without interpreting them as markup.
None notes render --. The data fold supplies dispatch/failure
precedence and filters executing jobs; this widget performs no data fetch.
Empty snapshots say nothing executing, unread snapshots say unavailable, and
no row survives replacement by a later snapshot.
"""

from __future__ import annotations

import logging

from rich.text import Text
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, fmt_age
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.panels import RichLogFeed

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "LOG_ID",
    "MIN_OBJECTIVE_COLS",
    "TIGHT_WIDTH",
    "TITLE",
    "SurfSwarmInFlight",
]

logger = logging.getLogger(__name__)

TITLE = "IN FLIGHT"
LOG_ID = "surf-swarm-inflight-log"

#: The real negative: a read that found no executing job. ``None`` is the
#: base's ``UNAVAILABLE_LINE`` and never this.
EMPTY_LINE = "[dim]  nothing executing[/]"

_GAP = rowfit.GAP

#: ``fmt_age``: ``45s`` / ``12m`` / ``2h`` / ``3d`` / ``999d`` / ``--`` --
#: four cells at the widest, right-aligned so the units line up.
_AGE_COLS = 4
#: ``template``: the v2 corpus (``tests/fixtures/surf/swarm/v2/``, 100 jobs,
#: 2026-09-21) has ``template`` ≤ 19 chars, ``skill:oracle-assess``-style.
#: Sized to that max so no live template is cut; a longer one clips with ``…``.
_TEMPLATE_COLS = 19
#: ``IDMD #n``: ``IDMD #`` (6) plus the seat token id, ≤ 4 digits in the
#: corpus (``1548``); or ``--`` when the detail route was not read.
_SEAT_COLS = 10
#: ``role·state`` as one cell: corpus roles ``implement`` (9) / ``review`` /
#: ``integrate``, states ``accepted`` (8) / ``failed`` / ``working`` /
#: ``waiting`` -- ``implement·accepted`` is 18. Both vocabularies are open;
#: a longer pair clips with ``…``.
_ROLE_STATE_COLS = 18
#: The narrowest objective still worth reading -- the first clause of a
#: corpus objective ("Assess the oracle feed…"); below it the row would
#: be all chrome. A tier's threshold is where the objective still gets this.
MIN_OBJECTIVE_COLS = 20
#: A readable prefix for the new last column; extra width is shared with objective.
MIN_NOTE_COLS = 12


def _fixed_cols(tier: str) -> int:
    """Columns the fixed cells cost at *tier*, gaps included -- the one
    source both the tier widths and the render-time objective/note budgets use."""
    cells = (_AGE_COLS, _TEMPLATE_COLS)
    if tier == "compact":
        cells = (_AGE_COLS, _TEMPLATE_COLS, _SEAT_COLS)
    elif tier == "full":
        cells = (_AGE_COLS, _TEMPLATE_COLS, _SEAT_COLS, _ROLE_STATE_COLS)
    return rowfit.row_cols(cells)


#: Columns each row layout needs, objective floor included (``row_cols`` sums).
FULL_WIDTH = _fixed_cols("full") + 2 * _GAP + MIN_OBJECTIVE_COLS + MIN_NOTE_COLS        # 93
COMPACT_WIDTH = _fixed_cols("compact") + 2 * _GAP + MIN_OBJECTIVE_COLS + MIN_NOTE_COLS  # 73
#: The floor. ``tight`` is the ladder's last step and always matches, so
#: this number is documentation of what the row costs there, not a gate.
TIGHT_WIDTH = _fixed_cols("tight") + 2 * _GAP + MIN_OBJECTIVE_COLS + MIN_NOTE_COLS      # 59

_LADDER = rowfit.Ladder(
    ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", 0),
)


def _cell(value, width: int) -> str:
    """Flatten and clip a third-party string to *width* cells; ``--`` for none."""
    flat = flatten(value)
    if not flat:
        return DASH
    return rowfit.clip(flat, width)


def _seat_cell(token) -> str:
    """``IDMD #1548`` for an int token; ``--`` for ``None`` or anything else.

    Attribution is a fact about the detail route -- ``None`` means the
    detail was not read. A non-int is not a seat and is not dressed as one.
    """
    if isinstance(token, int) and not isinstance(token, bool):
        return f"IDMD #{token}"
    return DASH


class SurfSwarmInFlight(RichLogFeed):
    """IN FLIGHT -- one row per executing job, newest first, a snapshot."""

    TITLE = TITLE
    LOG_ID = LOG_ID
    SNAPSHOT = True
    WRAP = False
    HIGHLIGHT = False
    MAX_LINES = 200
    EMPTY_LINE = EMPTY_LINE

    #: The body's own geometry only (the base states none); the panel's
    #: place in the grid is ``minimal.tcss``'s. ``scrollbar-size: 1 1`` is the
    #: one cell the width tests charge as chrome beside the padding.
    DEFAULT_CSS = """
    SurfSwarmInFlight > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    #: The title ``Static``'s own ``padding: 0 1`` (``PanelBase``).
    _TITLE_PADDING_COLS = 2

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._payload: dict | None = None
        self._tier = "full"
        self._objective_cols = MIN_OBJECTIVE_COLS
        self._note_cols = MIN_NOTE_COLS
        self._note_clipped = False

    def update_data(
        self,
        swarm_inflight_rows=None,
        swarm_as_of_hhmm=None,
        swarm_network=None,
        **_kwargs,
    ) -> None:
        """Repaint from the manager's flat dict; every kwarg is a contract key.

        ``swarm_network`` is accepted and never painted (module docstring).
        ``**_kwargs`` is mandatory: the screen splats the whole payload.
        """
        rows = swarm_inflight_rows
        if rows is not None:
            try:
                rows = list(rows)
            except TypeError:
                # Not even iterable: the read did not produce a list, which
                # is "could not look", never "nothing executing".
                rows = None
        self._payload = {"rows": rows, "as_of": swarm_as_of_hhmm}
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload is not None:
            self._render_view()

    # -- hooks ----------------------------------------------------------------

    def format_row(self, event) -> Text | None:
        """One fitted line, or ``None`` (logged) for an entry that is no dict."""
        if not isinstance(event, dict):
            logger.warning(
                "%s: skipped a row that is not a dict (%s)",
                type(self).__name__, type(event).__name__,
            )
            return None
        tier = self._tier
        line = Text()
        line.append(f"{fmt_age(event.get('age_s')):>{_AGE_COLS}}", style="dim")
        line.append(" " * _GAP)
        line.append(rowfit.pad(_cell(event.get("template"), _TEMPLATE_COLS), _TEMPLATE_COLS))
        if tier in ("full", "compact"):
            line.append(" " * _GAP)
            line.append(
                rowfit.pad(_seat_cell(event.get("agent_token")), _SEAT_COLS), style="bold",
            )
        if tier == "full":
            role = _cell(event.get("node_role"), _ROLE_STATE_COLS)
            state = _cell(event.get("node_state"), _ROLE_STATE_COLS)
            pair = rowfit.clip(f"{role}·{state}", _ROLE_STATE_COLS)
            line.append(" " * _GAP)
            line.append(rowfit.pad(pair, _ROLE_STATE_COLS), style="cyan")
        if self._objective_cols > 0:
            line.append(" " * _GAP)
            line.append(rowfit.pad(_cell(event.get("objective"), self._objective_cols), self._objective_cols), style="dim")
        note = event.get("note")
        if self._note_cols > 0:
            cell = Text.from_markup(sanitize_cell(note, self._note_cols)) if note else Text(DASH)
            self._note_clipped |= rowfit.cell_len(strip_tags(flatten(note))) > self._note_cols
            line.append(" " * _GAP)
            line.append_text(cell)
        elif note:
            self._note_clipped = True
        return line

    # -- rendering ------------------------------------------------------------

    def _log_width(self, log: RichLog) -> int:
        """Rendered columns available to one line.

        ``scrollable_content_region``, not ``content_size``: ``RichLog``'s
        own CSS is ``overflow-y: scroll`` and the gutter is spent whether or
        not the log overflows (THE FIELD's and ``activity.py``'s measurement).
        """
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - self._TITLE_PADDING_COLS - 1, 0)
        return width

    def _set_title(self, widen: bool) -> None:
        try:
            title = self.query_one(".panel-title", Static)
        except Exception:  # not composed yet
            return
        base = TITLE
        as_of = (self._payload or {}).get("as_of")
        if rowfit.has_marker(as_of):
            base += f" · as of {as_of}"
        room = max(self.content_size.width - self._TITLE_PADDING_COLS, 0)
        title.update(Text(rowfit.title_with_hint(base, widen, room)))

    def _render_view(self) -> None:
        try:
            log = self.query_one(f"#{self.LOG_ID}", RichLog)
        except Exception:  # not composed yet
            return
        rows = (self._payload or {}).get("rows")
        width = self._log_width(log)
        self._tier = _LADDER.tier_for(width)
        free = max(width - _fixed_cols(self._tier) - 2 * _GAP, 0)
        self._note_cols = min(MIN_NOTE_COLS + max(free - MIN_NOTE_COLS - MIN_OBJECTIVE_COLS, 0) // 2, free)
        self._objective_cols = max(free - self._note_cols, 0)
        self._note_clipped = False
        self.render_events(rows)
        # A painted row may shed columns or clip its note. An unavailable or
        # empty snapshot did neither, and a fitting literal ellipsis is not loss.
        self._set_title(bool(rows) and (self._tier != "full" or self._note_clipped))

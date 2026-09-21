"""IN FLIGHT -- the jobs executing right now, one row each (swarm v2, WP5).

A **snapshot** feed on ``panels.RichLogFeed`` (``SNAPSHOT = True``): every
poll is the whole current set, ``[]`` is the real negative ("nothing
executing", :data:`EMPTY_LINE`) and ``None`` is "could not look"
(``panels.UNAVAILABLE_LINE``). No row ever survives a poll -- a job that
finished between two polls is gone from the next frame, not left up as if
still running (``rules/widgets.md``, ``SNAPSHOT``). ``dedupe_key`` is
irrelevant in this mode and is left at the base's default.

Mounted in the ``s`` body since WP7, in the row THE FIELD (``swarm_field.py``,
deleted there) used to hold, beside LAUNCHES; ``widgets/surf/__init__.py``
exports it and ``minimal.tcss`` places it (``4fr`` against LAUNCHES' ``5fr``
-- the ratio, not a ``min-width``, is what holds this panel at its
``compact`` tier at the app's 143-column pin).

Row shape (``data/surf_models.SURF_ROW_KEYS["swarm_inflight_rows"]``,
frozen): ``job_id, template, objective, created_ts, age_s, node_key,
node_role, node_state, agent_token, agent_id, revisions`` -- one row per
executing job with the job's *active* node folded in; ``agent_token`` is
``None`` when the detail route was not read, so attribution is a fact
about the detail route, not about the seat.

The row, and what THE FIELD taught it
-------------------------------------
``age · template · seat · role·state · objective``, columnar in a
``RichLog(wrap=False)`` (``WRAP = False``, ``HIGHLIGHT = False``,
``MAX_LINES = 200`` -- the talismans/ttt reasoning: a wrapped row puts its
objective under its age and the column stops being a column; the repr
highlighter recolours the digits inside ``IDMD #1548``). The **objective is
the last cell and is clipped to whatever budget is left**, with a visible
``…`` -- never wrapped: THE FIELD wrapped its objective into up to four
lines and this panel is the *in-flight* strip, one line a job, where the
objective's first clause is the reader's orientation and the seat and state
are the point. Newest first is the fold's order and is not re-sorted here.

Width tiers on ``rowfit.Ladder``, widest first (the numbers are
``rowfit.row_cols`` sums of the column constants below, each with its
``#:`` fact; a tier is the widest whole-cell layout that still leaves the
objective its :data:`MIN_OBJECTIVE_COLS`):

==========  =====  ==================================================
Tier        Needs  Row
==========  =====  ==================================================
``full``    79     ``age  template  IDMD #n  role·state  objective``
``compact`` 59     ``age  template  IDMD #n  objective``
``tight``   45     ``age  template  objective`` (floor; always reached)
==========  =====  ==================================================

A tier below ``full`` lights ``rowfit.title_with_hint``'s marker in the
title ("the panel names the columns it shed") -- only when rows were
painted: an unavailable or empty feed shed nothing.

Third-party text renders literally, and nothing here parses markup
-------------------------------------------------------------------
``template``, ``objective``, ``node_role`` and ``node_state`` are whatever
the host and the requester typed. Every cell is appended to a
``rich.text.Text`` with ``Text.append`` after ``markup_safety.flatten``
and ``rowfit.clip`` (``cell_len``, never ``len()``); ``Text.append``
parses nothing, so ``[/x]`` renders as the literal four characters and
``[$success]`` cannot raise -- there is no markup step for an escape to
guard, which is the strongest form of the rule. ``sanitize_cell`` was
**not** used on purpose: its ``strip_tags`` step deletes a complete
``[...]`` run, and the plan (WP5) requires a hostile tag in an objective
to **render literally**, which a stripped string cannot do.

``swarm_network`` is accepted and never painted: the row shape carries no
chain, so a title-level word would claim a chain of rows that name none
(THE FIELD's reason, kept). No ``stale`` word either -- that measures the
scores tier's drift, which this live-tier panel does not read.

Purity: stdlib, ``rich``, ``textual``, ``widgets/panels``, ``widgets/fmt``,
``widgets/rowfit``, ``widgets/markup_safety``. No ``data/``, no
``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

import logging

from rich.text import Text
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import DASH, fmt_age
from maxpane_dashboard.widgets.markup_safety import flatten
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


def _fixed_cols(tier: str) -> int:
    """Columns the fixed cells cost at *tier*, gaps included -- the one
    source both the tier widths and the render-time objective budget use."""
    cells = (_AGE_COLS, _TEMPLATE_COLS)
    if tier == "compact":
        cells = (_AGE_COLS, _TEMPLATE_COLS, _SEAT_COLS)
    elif tier == "full":
        cells = (_AGE_COLS, _TEMPLATE_COLS, _SEAT_COLS, _ROLE_STATE_COLS)
    return rowfit.row_cols(cells)


#: Columns each row layout needs, objective floor included (``row_cols`` sums).
FULL_WIDTH = _fixed_cols("full") + _GAP + MIN_OBJECTIVE_COLS        # 79
COMPACT_WIDTH = _fixed_cols("compact") + _GAP + MIN_OBJECTIVE_COLS  # 59
#: The floor. ``tight`` is the ladder's last step and always matches, so
#: this number is documentation of what the row costs there, not a gate.
TIGHT_WIDTH = _fixed_cols("tight") + _GAP + MIN_OBJECTIVE_COLS      # 45

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
            line.append(_cell(event.get("objective"), self._objective_cols), style="dim")
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
        self._objective_cols = max(width - _fixed_cols(self._tier) - _GAP, 0)
        self.render_events(rows)
        # The marker says a column was shed from rows that were painted; an
        # unavailable or empty feed shed nothing and stays unmarked.
        self._set_title(bool(rows) and self._tier != "full")

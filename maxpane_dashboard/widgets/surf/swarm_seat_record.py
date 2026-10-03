"""RECORD: every work attempt in the selected seat's lifetime record.

Owner, 2026-09-23: when/job/node/state/model/took/tok/panel/answer.
Role is hidden; short model names make room for panel evidence and output tokens.

Since 2026-09-22 ``work[]`` lists pending, rejected and failed attempts beside
accepted ones. ``state`` shows the attempt's own status whenever it is not
``accepted`` (a failed attempt on a completed job must not read as a green
``completed``), and the job's state otherwise or under the pre-status shape.
Timestamps (submitted, else accepted) include month/day across midnight.
The job cell links a canonical job id to its IMD explorer page; the node
cell is the node's short word (:data:`_swarm_seat.NODE_TITLES`). Launch and
submission hash are not columns (owner, 2026-09-22: the answer gets the room);
a failed attempt's read answer is red. Answer takes the remaining width and
lights ``‹ widen`` when cut only if there is no popup button. The title has no blank row under it (owner,
2026-09-22, this panel only). The scrollable table starts at forty rows, grows through `more` up to 400
and can filter out completed attempts; the seat state hides stale rows before rendering.

``f`` (2026-10-02, ``docs/surf_record_filter_spec.md``) stores a filter the
screen applies through :meth:`SurfSwarmSeatRecord.set_record_view`: the title
gains a third mode word, ``filtered``, and the footer states the filter, how
many rows match, and how many cannot be judged yet (``not read yet`` /
``unavailable``) -- counted, never shown and never dropped.
"""

from __future__ import annotations


from rich.text import Text
from rich.style import Style
from textual.widgets import DataTable, Static

from maxpane_dashboard.analytics.surf_record_filter import (
    RecordFilter, RecordView, record_filter_choices, record_output_tokens, record_served, record_time,
    record_took_minutes, record_view,
)
from maxpane_dashboard.analytics.surf_swarm_signals import record_state

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import job_text
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, JOB_EXPLORER, mmdd_hhmm, short_model
from maxpane_dashboard.widgets.surf._oracle_answer import _PANEL_COLS, _STATE_COLORS, joined, record_answer, panel_text, can_open_submission, fit_popup_text, tok_text, valid_identity
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES, seat_state_line
from maxpane_dashboard.widgets.surf._swarm_table import CELL_PADDING, SwarmTableBase, table_cols
from maxpane_dashboard.widgets.surf.swarm_record_filter import filter_summary

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "JOB_COLS",
    "NODE_COLS",
    "ANSWER_MIN_COLS",
    "TIGHT_WIDTH",
    "NO_MATCH_LINE",
    "SurfSwarmSeatRecord",
    "seat_footer",
]

EMPTY_LINE = "no work yet"
#: A filtered view with nothing to show, nothing to wait for and nothing older.
NO_MATCH_LINE = "no matching records"
#: The fewest summary cells worth showing before the counts; below it the
#: summary goes and the counts stay whole.
_SUMMARY_MIN_COLS = 8
#: The filtered footer's count words, longest first; it takes the first whose
#: counts fit (F-RF3) -- the words shorten, the figures and ``more`` never go.
#: Worst case (100 / 100 / 100 of a 400-row window, +12,345 older): 69, 61 and
#: 53 cells; the AGENT sweep's 60-column floor leaves the footer 55.
_COUNT_WORDS = (
    ("not read yet", "unavailable", " older"),
    ("not read", "unavail", " older"),
    ("unread", "unavail", ""),
)
#: Right-aligned on the title line where it fits whole; ``i`` is the screen's seat prompt.
SEAT_HINT = "type 'i' to change seat"

#: ``MM-DD HH:MM`` of ``submitted_ts`` (the work entry's ``submittedAt``), else
#: ``accepted_ts``: since 2026-09-22 ``work[]`` also lists pending, rejected
#: and failed attempts, which carry no ``acceptedAt``.
_WHEN_COLS = 11

#: The first eight characters of the job id. The fold's ids are UUIDs
#: (``ad7bebb8-fd1a-4268-b831-1c253a85ae4c``); the whole id is 36 cells and
#: no use on screen, the first group is how the swarm's own pages and this
#: repo's tests name a job. A head slice, never a head-and-tail window (that
#: is an address formatter's shape, ``tests/test_address_rule.py``). The
#: shown group links the whole id's explorer page (``address.job_text``).
JOB_COLS = 8

#: The widest known short word (``oracle``, ``review``; ``build`` 5). An
#: unknown node key is fitted to it with a visible ``…`` (owner, 2026-09-22:
#: the answer gets the cells the 22-cell keys took).
NODE_COLS = 6

#: ``completed`` is 9 -- the only ``jobState`` on the four captured seats; the
#: vocabulary is open and a longer word clips with ``…``.
_STATE_COLS = 9

#: The answer floor, certified with the AGENT body in polish WP6.
#: Above it the column takes every remaining cell.
ANSWER_MIN_COLS = 20

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("job", "job", JOB_COLS),
    ("node", "node", NODE_COLS),
    ("state", "state", _STATE_COLS),
    ("model", "model", 9),
    ("took", "took", 6),
    ("tok", "tok", 6),
    ("panel", "panel", _PANEL_COLS),
    ("answer", "answer", ANSWER_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "tok")
_TIGHT = tuple(key for key in _COMPACT if key not in ("answer", "model", "took"))
_TIERS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}


def _tier_width(keep) -> int:
    return table_cols([w for k, _l, w in _SPECS if k in keep])


#: Width tiers include DataTable cell padding; certified in the screen sweep.
FULL_WIDTH = _tier_width(_ALL)
COMPACT_WIDTH = _tier_width(_COMPACT)
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


def seat_footer(state: object) -> tuple[str, str] | None:
    """Seat-state override as ``(words, style)``; ``None`` keeps the table footer."""
    line = seat_state_line(state)
    if line is not None:
        return line.plain, _line_style(line)
    return None


class SurfSwarmSeatRecord(SwarmTableBase):
    """RECORD -- lifetime work attempts in the source-provided order."""

    TITLE = "RECORD"
    TABLE_ID = "surf-swarm-seat-record-table"
    CURSOR_TYPE = "none"

    #: The one panel title with no blank row under it (owner, 2026-09-22):
    #: the exception to ``PanelBase``'s ``margin: 0 0 1 0``, stated here
    #: where the panel is declared and pinned in the title-blank-row test.
    DEFAULT_CSS = """
    SurfSwarmSeatRecord > .panel-title {
        margin: 0;
    }
    """
    #: Kept at 40 for lifetime rows (plan §9 G); the footer counts the rest.
    ROW_CAP = 40
    MAX_CAP = 400

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = _TIERS
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH),
    )
    EMPTY_LINE = EMPTY_LINE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._answer_cols = ANSWER_MIN_COLS
        self._state: object = None
        self._read: object = None
        self._all_rows = None
        self._open_only = False
        self._spec: RecordFilter | None = None
        self._has_filter = False
        self._view = RecordView((), 0, 0, 0)

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_work_rows=None,
        swarm_seat_state=None,
        swarm_seat_as_of_hhmm=None,
        swarm_seat_read=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``**_kwargs``: the screen splats it)."""
        self._state = swarm_seat_state
        self._read = swarm_seat_read
        self._all_rows = swarm_seat_work_rows if swarm_seat_state == "ok" else None
        self._store_view(swarm_seat_as_of_hhmm)

    def set_record_view(self, cap: int, open_only: bool, spec: RecordFilter | None = None,
                        *, has_filter: bool = False) -> None:
        """Repaint the cached rows; view state is supplied by the screen.

        ``spec`` is the filter in force (the ``filtered`` mode); ``has_filter``
        says one is stored, so the title offers ``filtered`` while ``all`` or
        ``not completed`` shows. An inactive or foreign ``spec`` is no filter.
        """
        if not isinstance(cap, int) or isinstance(cap, bool) or not isinstance(open_only, bool):
            return
        if not isinstance(spec, RecordFilter) or not spec.active:
            spec = None
        has_filter = has_filter is True or spec is not None
        cap = max(40, min(self.MAX_CAP, cap))
        if (self.ROW_CAP, self._open_only, self._spec, self._has_filter) == (cap, open_only, spec, has_filter):
            return
        self.ROW_CAP = cap
        self._open_only = open_only
        self._spec = spec
        self._has_filter = has_filter
        self._store_view((self._payload or {}).get("as_of"))

    def filter_choices(self, spec: RecordFilter | None = None) -> dict[str, tuple[str, ...]]:
        """The seat's own NODE / STATE / MODEL options for the editor, keeping *spec*'s."""
        return record_filter_choices(self._all_rows, spec)

    def _store_view(self, as_of) -> None:
        rows = self._all_rows
        if isinstance(rows, (list, tuple)):
            self._view = record_view(rows, self.ROW_CAP, self._open_only, self._spec)
            rows = list(self._view.rows)
        else:
            self._view = RecordView((), 0, 0, 0)
            rows = None
        self.store(rows, as_of)

    def render_table(self, rows, *, footer=None) -> None:
        table = self.query_one(DataTable)
        position, cursor = table.scroll_offset, table.cursor_coordinate
        super().render_table(rows, footer=footer)
        table.move_cursor(row=cursor.row, column=cursor.column, scroll=False)
        self.call_after_refresh(table.scroll_to, x=position.x, y=position.y, animate=False, force=True)

    def _repaint(self) -> None:
        if not self.is_mounted:
            return
        super()._repaint()
        footer = seat_footer(self._state)
        if footer is not None:
            words, style = footer
            self._write_footer((words,), style=style)
        elif isinstance(self._all_rows, (list, tuple)):
            if self._spec is not None:
                self._show_footer(self._filtered_footer())
                return
            tail = self._older_tail()
            if tail.plain:
                self._show_footer(tail)
            elif self._open_only and not self._view.rows:
                self._write_footer(("no incomplete records",))

    def _older_tail(self, older_word: str = " older") -> Text:
        """``+N older · more`` for base rows past the cap; empty when all fit."""
        text = Text(style="dim")
        older = self._view.older
        if older:
            text.append(f"+{fmt_int(older)}{older_word}")
            if self.ROW_CAP < self.MAX_CAP:
                text.append(" · ").append("more", style=Style(bold=True, meta={"@click": "screen.record_more()"}))
        return text

    def _filtered_footer(self) -> Text:
        """``summary · N match · N not read yet · N unavailable · +N older · more``.

        The summary is clipped first, and dropped below ``_SUMMARY_MIN_COLS``;
        then the counts' words shorten (``_COUNT_WORDS``), never a figure.
        Dim throughout but for ``unavailable``, which keeps the palette's
        plain yellow (spans, not a base style, so the dim does not reach it).
        """
        room = max(self.size.width - self.FOOTER_PADDING_COLS, 0)
        for words in _COUNT_WORDS:
            counts = self._filtered_counts(*words)
            if counts.cell_len <= room:
                break
        summary_room = room - counts.cell_len - len(" · ")
        summary = filter_summary(self._spec)
        if summary and summary_room >= _SUMMARY_MIN_COLS:
            return Text().append(rowfit.clip(summary, summary_room) + " · ", style="dim").append_text(counts)
        return counts

    def _filtered_counts(self, not_read_word: str, unavailable_word: str, older_word: str) -> Text:
        view = self._view
        counts = Text()
        if view.rows or view.not_read or view.unavailable or view.older:
            counts.append(f"{fmt_int(len(view.rows))} match", style="dim")
            if view.not_read:
                counts.append(f" · {fmt_int(view.not_read)} {not_read_word}", style="dim")
            if view.unavailable:
                counts.append(" · ", style="dim").append(f"{fmt_int(view.unavailable)} {unavailable_word}",
                                                         style="yellow")
        else:
            counts.append(NO_MATCH_LINE, style="dim")
        older = self._older_tail(older_word)
        if older.plain:
            counts.append(" · ", style="dim").append_text(older)
        return counts

    def _show_footer(self, text: Text) -> None:
        footer_widget = self.query_one(f"#{self.footer_id}", Static)
        footer_widget.auto_links = False
        footer_widget.display = True
        footer_widget.update(text)

    def _render_title(self, as_of) -> None:
        title = Text("RECORD · ")
        accent = self.app.get_css_variables().get("accent", "cyan")
        filtered = self._spec is not None
        modes = [("all", "all", not self._open_only and not filtered),
                 ("not completed", "open", self._open_only and not filtered)]
        if self._has_filter:
            modes.append(("filtered", "filtered", filtered))
        for index, (word, mode, active) in enumerate(modes):
            if index:
                title.append(" · ")
            title.append(word, style=Style(color=accent if active else None,
                                          bold=active, dim=not active,
                                          meta={"@click": f"screen.record_filter('{mode}')"}))
        if rowfit.has_marker(as_of):
            title.append(f" · as of {rowfit.clip(as_of, 5)}")
        if self._state == "ok" and self._read == "busy":
            title.append(" · ").append("busy", style="yellow")
        room = max(self.size.width - self.TITLE_PADDING_COLS, 0)
        hinted = rowfit.title_with_hint(title.plain, self._widen or self._clipped, room)
        title.append(hinted[len(title.plain):])
        # Right-aligned seat hint (owner, 2026-09-24); shown only where it fits
        # whole after the widen marker, so it never costs the title a line. It
        # ends where the answer column's text ends: the title's text starts one
        # cell right of the table and the last cell keeps one cell of padding.
        gap = room - 2 - title.cell_len - len(SEAT_HINT)
        if room and gap >= 2:
            title.append(" " * gap).append(SEAT_HINT, style="dim")
        self.query_one(".panel-title", Static).auto_links = False
        self.write(".panel-title", title)

    # -- geometry -----------------------------------------------------------

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        if key != "answer":
            return width
        keep = self.TIER_COLUMNS.get(tier, ())
        others = [w for k, _l, w in _SPECS if k != "answer" and k in keep]
        spare = budget - table_cols(others) - CELL_PADDING if budget > 0 else 0
        self._answer_cols = max(ANSWER_MIN_COLS, spare)
        return self._answer_cols

    # -- the cells ----------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, object] | None:
        job_id = item.get("job_id")
        job = job_id[:JOB_COLS] if isinstance(job_id, str) and job_id else DASH
        state = _word(record_state(item))
        color = _STATE_COLORS.get(state)
        state_cell = sanitize_cell(state, _STATE_COLS)
        if color:
            state_cell = f"[{color}]{state_cell}[/]"
        node_key = item.get("node_key")
        title = NODE_TITLES.get(node_key) if isinstance(node_key, str) else None
        answer = self._answer_cell(item)
        if state == "failed" and item.get("answer_state") == "read" and not joined(item):
            # Only a read answer takes the failed colour: the unread words keep
            # their own dim / yellow, which say why there is no answer (F65).
            answer.stylize("red")
        return {
            "when": mmdd_hhmm(record_time(item)),
            "job": job_text(job_id, JOB_COLS, explorer=JOB_EXPLORER) if job != DASH else DASH,
            "node": title.lower() if title else sanitize_cell(_word(node_key), NODE_COLS),
            "state": state_cell,
            "model": self._usage_cell(item, "model", 9),
            "took": self._usage_cell(item, "took_s", 6),
            "panel": self._panel_cell(item),
            "tok": self._usage_cell(item, "output_tokens", 6),
            "answer": answer,
        }

    def _usage_cell(self, item: dict, key: str, width: int) -> str:
        # Metadata belongs to the same successful exact-hash submission read;
        # the rules are the filter's own, so MODEL / TOOK / TOK judge exactly
        # what these cells show (F-RF2).
        if not record_served(item):
            return EMDASH
        value = item.get(key)
        if key == "model":
            value = short_model(value)
        elif key == "output_tokens":
            value = tok_text(record_output_tokens(item))
        elif key == "took_s":
            minutes = record_took_minutes(item)
            if minutes is None:
                return EMDASH
            if minutes >= 60:
                value = f"{minutes // 60}h {minutes % 60:02d}m"
            else:
                value = "<1m" if minutes == 0 else f"{minutes}m"
        return sanitize_cell(value, width) or EMDASH

    def _panel_cell(self, item: dict) -> Text:
        return panel_text(item)

    def _answer_cell(self, item: dict) -> Text:
        if joined(item):
            return record_answer(item, self._answer_cols)
        state = item.get("answer_state")
        style = ""
        if state != "read":
            words = {"not_read": "not read", "not_served": "not served", "no_reply": "no reply"}
            text = words.get(state, "unavailable")
            if state == "not_read" and valid_identity(item.get("job_id"), item.get("submission_hash")):
                text = "loading…"
            style = "dim" if state in words else "yellow"
        else:
            text = strip_tags(item.get("answer"))
        if item.get("panel_state") in ("outvoted", "no_quorum_out"):
            if item.get("panel_answer_type") == "bool":
                answer = item.get("panel_answer_bool")
                figure = ("YES" if answer else "NO") if type(answer) is bool else "unavail"
            else:
                figure = strip_tags(item.get("panel_figure")) or "unavail"
            text = f"panel {figure} · {text}"
        width = self._answer_cols
        eligible = can_open_submission(item)
        rendered, cut, button = fit_popup_text(item, text, width, 'open_submission' if eligible else None,
            style=style)
        if cut and not button:
            self._clipped = True
        return rendered

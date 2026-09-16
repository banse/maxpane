"""THE FIELD: which agent is on what, and what is stuck.

A ``RichLog`` panel on ``widgets/surf/activity.py``'s own shape: a ``Static``
title, a ``Static(" ")`` blank spacer under it, a ``RichLog(wrap=False,
markup=False)`` body.  ``markup=False`` and every row a pre-built
``rich.text.Text`` (never a markup string) are the same decision twice --
this panel's rows carry genuinely third-party text (spec §4/§6.3:
``objective`` and ``dispatch_note`` are "whatever someone typed when they
asked for the work"), and ``Static.update("…[/x]…")``/``RichLog.write("…")``
both defer ``Text.from_markup`` into the message pump, where a parse failure
raises *outside* this widget's own ``try/except`` and takes the app down
(``SurfFeed._row_text`` is the worked example this rule comes from).

Row shape (``data/surf_models.SURF_ROW_KEYS["swarm_field_rows"]``, frozen):
``job_id``, ``template``, ``objective``, ``node_key``, ``role``,
``node_state``, ``agent_token``, ``agent_id``, ``revisions``,
``dispatch_note``, ``moved_ts``, ``age_s``.

Two lines per subtask
----------------------
Spec §5 names six facts for a row -- "agent seat, subtask and role, state,
age, revisions, and the dispatcher's own note" -- and the columns below are
exactly those six, in that order.  ``objective`` is not a seventh column:
it is one fact per *job*, not per subtask, and several subtasks of the same
job repeat it verbatim in the frozen row shape.  Painting it into the note
cell would either waste it on every subtask of a job or crowd out the note
that actually explains a stall, so it gets its own line instead -- a dim
context line, printed once per job (grouped by ``job_id``) and shared by
every subtask row under it.  This is a deliberate reshaping of the flat row
list into job groups for display only; the six *columns* are untouched by
it.

**The reshaping's own ordering, stated precisely (fix round 2).** The
producer hands this widget its rows newest-move-first; grouping them keeps
that promise at two levels rather than one, not at the whole render's:
**groups render in order of their own most-recently-moved subtask, and
subtasks within a group render newest-first too.**  It is *not* a claim
that the flattened sequence is a strict global sort -- keeping one job's
subtasks together outranks strict recency the moment a group has more than
one member, so an older subtask of an already-started group can render
ahead of a different job's newer one.  Three rows at ages 10s, 100s and
200s for jobs A, B, A respectively render ``A(10s), A(200s), B(100s)``:
``A``'s 200s-old subtask is globally older than ``B``'s 100s-old one, but
still renders first, because it belongs to the group that has already
started. This was undisclosed before fix round 2, which corrected a
docstring sentence here that read the render order as a plain restatement
of the producer's own global sort; the render order is not that, and this
paragraph -- plus
``test_groups_order_by_their_own_newest_subtask_and_subtasks_newest_first_within_a_group``
-- is what actually holds now.  :func:`_group_by_job`'s own docstring
carries the same correction and the reason first-seen order is sufficient
to produce it.

Columns, widest first, ``_rowfit``'s own machinery (``clip``/``pad``/
``row_cols``/``tier_for``, shared with ``activity.py`` and
``launchpad_activity.py`` rather than a fourth copy of the same ladder):

==========  =====  ===================================================
Tier        Needs  Row
==========  =====  ===================================================
``full``    117    ``agent  subtask  role  state  age  rev  note``
``compact`` 65     ``agent  subtask  role  state  age  rev``
``minimal`` 47     ``agent  subtask  state  age``
==========  =====  ===================================================

Unlike ``activity.py`` there is no anti-poisoning window here -- none of
these cells is an address -- so nothing is ever *withheld*: the ladder's
last rung (``minimal``) has no threshold and always matches, and a title
marker (:data:`WIDEN_HINT`/:data:`GLYPH_HINT`, ``_pool4``'s own vocabulary)
says what a narrower tier shed.  There is no per-tier custom hint text the
way ``activity.py`` names its shed fields -- the brief's own wording is
"advertising each with ``‹ widen``", one generic marker, not a ladder of
them.

**Not ``_pool4.title_text`` itself.**  That function's fitting logic is
exactly what this panel wants and is reused verbatim below
(:func:`_title_with_hint` restates it rather than importing the private
``_with_hint``, because ``_with_hint`` is not exported and both public
callers of it also print a network word), but its *shape* -- title, network
word, hint -- is not this panel's.  Design §5 is explicit: "The chain word
… goes in the titles of panels that show chain data — JUST SHIPPED, and any
score quoting a transaction — and nowhere else."  THE FIELD shows neither an
address nor a transaction, so ``swarm_network`` is accepted (the screen
splats the whole payload; every widget must survive it) and never painted --
the same "accepted and not rendered" idiom ``pool4u_burn.py``/
``pool4u_signals.py``/``pool4u_depth.py`` already use for
``pool4_as_of_hhmm`` on the ``4`` body.  ``swarm_stale`` rides the same
marker: it prints `` · stale`` immediately after the ``as of`` clock, and
only when both are present -- there is nothing to call stale about a clock
this panel is not showing.

Third-party text, and the no-bracket contract
-----------------------------------------------
``node_key``, ``role``, ``node_state``, ``objective`` and ``dispatch_note``
are every one of them a string this widget did not choose and an external
HTTP host did.  Each passes through ``_pool4.strip_tags`` before it reaches
a cell: flatten embedded whitespace, then drop every complete ``[...]``-
shaped run outright.  Not merely escaped -- an *escaped* ``[/x]`` still
*renders* as the literal text ``[/x]`` once a markup parser unescapes it for
display, so an escape-only defence still paints bracket noise on screen.
Stripping is also the choice that keeps the promise this module's own tests
hold it to: the composited region of a hostile row carries **no literal
``[`` or ``]`` at all**, not merely "no crash" and not merely "the payload
string is still findable as a substring".  Any embedded ``0x…`` address
survives stripping (hex has no brackets) and gets its copy icon through
``widgets/address.address_prose``; a clip reserves :data:`ICON_COLS` ahead
of one only when the cleaned text actually contains one, so a note with no
address is never short-changed two columns it does not need.

``swarm_field_rows`` and the read/empty split
------------------------------------------------
``[]`` is the frozen shape for *both* "nothing in flight" and "not read
yet" (``data/surf_swarm.field_rows`` returns ``[]`` whenever its input is
missing, exactly as much as when a real read found nothing to report), so
the list alone can never carry the distinction -- and that is the whole
reason the marker is the signal rather than a convenience: **``swarm_as_of_
hhmm is None`` means this slot has never been written, and renders
:data:`UNAVAILABLE_LINE` whatever ``swarm_field_rows`` says**, even a
populated list.  Only once a marker is present does an empty list mean
:data:`EMPTY_LINE` -- a real read that found nothing in flight.
``swarm_field_rows is None`` also renders :data:`UNAVAILABLE_LINE`,
independent of the marker, so the widget stays honest if it is ever handed
that sentinel directly. Fix round 1 (2026-09-16) corrected an earlier
version of this widget that keyed off ``swarm_field_rows`` alone
(``None`` -> unavailable, ``[]`` -> empty) -- a resolution that matched a
literal reading of the brief's own first-draft test but made the
unavailable state **unreachable in production**, since the manager never
actually publishes ``None`` for this key: a cold cache or an all-failed
read still rendered the confident, positive claim ``nothing in flight``.
That is exactly the "an unread band is not an absent one" defect
CLAUDE.md's Conventions section names.  "A real marker" means
:func:`_has_marker`'s own check (a non-empty ``str``), not merely
``is not None``: an empty string is not a clock either, and treating it as
one let ``_render_view`` and :meth:`SurfSwarmField._set_title` disagree
about whether the slot had ever been read (fix round 2).

Purity
------
Stdlib, ``rich``, ``textual``, and this package's own ``_fmt``/``_pool4``/
``_rowfit`` primitives, plus ``widgets/address`` for the copy icon.  No
``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, Static

from maxpane_dashboard.widgets.address import ICON_COLS, PROSE_ADDRESS_RE, address_prose
from maxpane_dashboard.widgets.surf import _rowfit
from maxpane_dashboard.widgets.surf._fmt import DASH, fmt_age
from maxpane_dashboard.widgets.surf._pool4 import GLYPH_HINT, WIDEN_HINT, strip_tags

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "MINIMAL_WIDTH",
    "SurfSwarmField",
    "TITLE",
    "UNAVAILABLE_LINE",
]

#: Subtask rows rendered per refresh -- ``activity.py``'s own convention,
#: scaled for a wider real-world row count (up to 62 jobs' worth of nodes).
_MAX_ROWS = 30

TITLE = "THE FIELD"

#: A successful read with nothing unfinished.  Tested verbatim.
EMPTY_LINE = "nothing in flight"

#: The whole-panel degraded state: ``swarm_field_rows is None``.  Tested
#: verbatim.
UNAVAILABLE_LINE = "unavailable"

_GAP = _rowfit.GAP

# -- column budget, in rendered columns --------------------------------
#
# None of these vocabularies is closed the way ``activity.py``'s
# ``wallet_label``/``kind`` are, so these are *measurements*, not producer
# pins: sized to the widest values captured live
# (``tests/fixtures/surf/swarm/job_*.json``, 2026-09-16) -- roles
# ``{implement, review}``, states ``{ready, accepted, waiting, failed}``,
# node keys up to ``build_contract_project`` (23) -- with headroom, and
# never a byte the anti-poisoning kind: a value that grows past its cell is
# cut with a visible ``…`` (:func:`_rowfit.clip`), which is the right
# defence for descriptive text and the wrong one only for the address
# window this panel does not have.

#: ``#`` + up to 5 digits, or :data:`DASH`.
_AGENT_COLS = 6
#: ``node_key``: fits ``build_contract_project`` (23) exactly.
_SUBTASK_COLS = 23
#: ``role``: fits ``implement`` (9) exactly.
_ROLE_COLS = 9
#: ``node_state``: fits ``accepted``/``waiting`` (8/7) with a column spare.
_STATE_COLS = 8
#: ``fmt_age``: ``45s`` / ``12m`` / ``2h`` / ``3d`` / ``999d`` / ``--``.
_AGE_COLS = 4
#: ``revN`` up to two digits, or :data:`DASH`.
_REVISIONS_COLS = 5
#: The narrowest reserve worth calling "the note" -- enough to still carry a
#: real ``dispatchNote`` sentence's own explanation, not just its opener.
#: Measured against the live capture's own note
#: (``"a review needs a contributor who did not author this work…"``, 57
#: cells): the clause that actually explains the stall starts at cell 33.
_MIN_NOTE_COLS = 50


def _fixed_cols(tier: str) -> int:
    """Columns the row's fixed cells cost at *tier*, gaps included.

    The single source both :data:`FULL_WIDTH`/:data:`COMPACT_WIDTH`/
    :data:`MINIMAL_WIDTH` and the render-time note budget derive from, so
    the two cannot drift the way two hand-typed sums would.
    """
    cells = (_AGENT_COLS, _SUBTASK_COLS, _STATE_COLS, _AGE_COLS)
    if tier != "minimal":
        cells = (
            _AGENT_COLS, _SUBTASK_COLS, _ROLE_COLS, _STATE_COLS, _AGE_COLS,
            _REVISIONS_COLS,
        )
    return _rowfit.row_cols(cells)


#: Columns each row layout needs.
COMPACT_WIDTH = _fixed_cols("full")                                  # 65
FULL_WIDTH = COMPACT_WIDTH + _GAP + _MIN_NOTE_COLS                   # 117
MINIMAL_WIDTH = _fixed_cols("minimal")                                # 47


def _tier_for(width: int) -> str:
    """Widest row layout that fits ``width`` rendered columns.

    No floor withheld the way ``activity.py`` withholds a row below its
    address window: ``minimal`` has no threshold of its own and is always
    reached, because there is nothing left in this row shape that a caller
    should refuse to cut.
    """
    return _rowfit.tier_for(
        width, (("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("minimal", 0)),
    )


def _title_with_hint(base: str, widen: bool, budget: int) -> str:
    """Append the longest widen marker that fits *base* within *budget*.

    ``_pool4._with_hint``'s exact fitting rule, restated rather than
    imported: that helper is private, and both of its public callers
    (``title_text``/``market_title_text``) bind the marker to a title that
    also carries a network word, which this panel's title deliberately does
    not (see the module docstring). The two exported constants it uses
    (:data:`WIDEN_HINT`/:data:`GLYPH_HINT`) are the same ones every other
    pool4-era title in this package prints, so the vocabulary stays one
    thing even though the fitter is now two functions.
    """
    if not widen:
        return base
    for candidate in (WIDEN_HINT, GLYPH_HINT):
        if not budget or cell_len(base) + 2 + cell_len(candidate) <= budget:
            return f"{base}  {candidate}"
    return base


def _has_marker(as_of: object) -> bool:
    """True when *as_of* is a real ``as of`` clock, not merely non-``None``.

    Fix round 2: ``_render_view``'s unavailable gate used to check
    ``as_of is None`` alone, which an empty string satisfies as ``False`` --
    so ``swarm_as_of_hhmm=""`` would have been treated as "this slot has
    been read" and let rows or :data:`EMPTY_LINE` render, while
    :meth:`SurfSwarmField._set_title` (which has always checked truthiness,
    not identity, to decide whether to print a clock at all) would still
    show no ``as of`` marker -- a body claiming to have read the swarm under
    a title that shows no time it read it at. Both call sites go through
    this one predicate now, so they cannot disagree again.
    """
    return isinstance(as_of, str) and bool(as_of)


#: State word -> a light colour hint.  Cosmetic only -- every test here
#: measures composited *text*, which carries no colour -- but it costs
#: nothing and helps a reader's eye find a ``failed``/``waiting`` row.
#: Never the load-bearing signal for anything: an unrecognised state (a
#: vocabulary this host has not been observed to use yet) simply gets no
#: colour, never a guess.
_STATE_STYLES = {
    "failed": "red",
    "waiting": "yellow",
    "blocked": "yellow",
    "ready": "cyan",
    "accepted": "green",
    "executing": "cyan",
    "completed": "green",
    "cancelled": "dim",
}


def _agent_cell(token: object) -> str:
    """``#2`` for a held seat; :data:`DASH` for an unheld one.

    ``token is None`` is the frozen "no seat" signal
    (``data/surf_swarm.field_rows``: ``seat.get("tokenId")`` off an empty
    seat dict); an empty string after stripping (a malformed non-``None``
    value) falls back to the same dash rather than painting a bare ``#``.
    """
    if token is None:
        return DASH
    text = strip_tags(token)
    return f"#{text}" if text else DASH


def _row_fields(row: object) -> dict | None:
    """Decompose one subtask row; ``None`` drops a malformed one.

    Every string field is cleaned through ``strip_tags`` here, once, so
    every later step (padding, clipping, prose) works on text that already
    carries no bracket-shaped noise.  ``None`` means "not a usable row" and
    must never reach a pixel -- the same content-before-width split
    ``activity.py._row_fields`` makes.
    """
    if not isinstance(row, dict):
        return None
    try:
        revisions = row.get("revisions")
        rev_text = (
            f"rev{revisions}"
            if isinstance(revisions, int) and not isinstance(revisions, bool)
            else DASH
        )
        raw_state = row.get("node_state")
        state_key = raw_state.strip().lower() if isinstance(raw_state, str) else ""
        job_id = row.get("job_id")
        return {
            "job_id": job_id if isinstance(job_id, str) and job_id else None,
            "objective": strip_tags(row.get("objective")),
            "agent": _agent_cell(row.get("agent_token")),
            "subtask": strip_tags(row.get("node_key")) or DASH,
            "role": strip_tags(row.get("role")) or DASH,
            "state": strip_tags(row.get("node_state")) or DASH,
            "state_key": state_key,
            "age": fmt_age(row.get("age_s")),
            "revisions": rev_text,
            "note": strip_tags(row.get("dispatch_note")),
        }
    except Exception:
        # A single malformed row must never take down the panel.
        return None


def _group_by_job(fields_list: list[dict]) -> list[tuple[str | None, list[dict]]]:
    """Group subtask rows by job, first-seen order.

    The producer already sorts the flat row list newest-move-first
    (``data/surf_swarm.field_rows``), so the first row of a job encountered
    while walking it is that job's own most-recently-moved subtask, and every
    later row of the same job is necessarily older than it -- first-seen
    order therefore gives **both** halves of the ordering the module
    docstring promises (fix round 2) with no second sort needed: groups come
    out ordered by their own newest member (the position of that first
    encounter), and a group's own members stay in the newest-first relative
    order they already had in the flat list, because grouping only removes
    rows from the sequence, it never reorders the ones that remain. What it
    does **not** give is a claim about the *flattened* sequence versus the
    original one -- an older member of an already-started group can render
    ahead of a different job's newer row, which is the module docstring's
    own worked example. A row with no usable ``job_id`` gets its own
    singleton group rather than being folded together with every other
    orphan, so its ``objective`` (if any) still prints once, correctly,
    beside it.
    """
    order: list[object] = []
    groups: dict[object, list[dict]] = {}
    objectives: dict[object, str] = {}
    for index, fields in enumerate(fields_list):
        key = fields["job_id"] if fields["job_id"] is not None else object()
        if key not in groups:
            groups[key] = []
            objectives[key] = fields["objective"]
            order.append(key)
        groups[key].append(fields)
    return [(objectives[key], groups[key]) for key in order]


def _fit_prose(text: str, width: int) -> Text:
    """*text* clipped to *width* cells, with any embedded address's icon.

    The icon's own two columns (:data:`ICON_COLS`) are reserved ahead of a
    clip only when the cleaned text actually contains a full address --
    never unconditionally, which would short a plain sentence two columns
    it does not need.
    """
    if not text or width <= 0:
        return Text("")
    has_address = bool(PROSE_ADDRESS_RE.search(text))
    budget = max(width - ICON_COLS, 0) if has_address else width
    return address_prose(_rowfit.clip(text, budget))


def _header_text(objective: str, width: int) -> Text | None:
    """One job's context line -- its objective, dim, indented two columns.

    ``None`` when there is nothing to say (an empty or unreadable
    objective), so the caller never writes a blank line for it.
    """
    if not objective:
        return None
    line = Text("  ", style="dim")
    line.append_text(_fit_prose(objective, max(width - 2, 0)))
    return line


def _row_text(fields: dict, tier: str, note_width: int) -> Text:
    """One subtask's metadata line at *tier*: agent, subtask, role, state,
    age, revisions, then the note in whatever width is left.

    **Every cell is ``clip``-ed before it is ``pad``-ed, no exception.**
    ``pad`` only ever *adds* trailing spaces (``_rowfit.pad``'s own
    contract), so a cell handed to it without first being clipped and found
    over-length is not narrowed at all -- it sails through at its natural
    width and every column after it starts one or more cells right of the
    row above it. Fix round 2 found exactly this on ``agent``/``age``/
    ``revisions`` (an over-long agent token, ``#123456`` at 7 cells against
    :data:`_AGENT_COLS`'s 6, pushed the whole row over):
    ``test_an_over_long_agent_token_does_not_break_column_alignment`` pins
    it and reddens if the clip is dropped from any one of the three.

    Never raises on well-formed *fields* (the dict :func:`_row_fields`
    produces); a row that fails to decompose never reaches this function at
    all.
    """
    line = Text()
    line.append(
        _rowfit.pad(_rowfit.clip(fields["agent"], _AGENT_COLS), _AGENT_COLS),
        style="bold",
    )
    line.append(" " * _GAP)
    line.append(_rowfit.pad(_rowfit.clip(fields["subtask"], _SUBTASK_COLS), _SUBTASK_COLS))
    if tier != "minimal":
        line.append(" " * _GAP)
        line.append(
            _rowfit.pad(_rowfit.clip(fields["role"], _ROLE_COLS), _ROLE_COLS),
            style="dim",
        )
    line.append(" " * _GAP)
    state_style = _STATE_STYLES.get(fields["state_key"], "")
    line.append(
        _rowfit.pad(_rowfit.clip(fields["state"], _STATE_COLS), _STATE_COLS),
        style=state_style,
    )
    line.append(" " * _GAP)
    line.append(
        _rowfit.pad(_rowfit.clip(fields["age"], _AGE_COLS), _AGE_COLS), style="dim",
    )
    if tier != "minimal":
        line.append(" " * _GAP)
        line.append(
            _rowfit.pad(_rowfit.clip(fields["revisions"], _REVISIONS_COLS), _REVISIONS_COLS),
            style="dim",
        )
    if tier == "full" and note_width > 0 and fields["note"]:
        line.append(" " * _GAP)
        line.append_text(_fit_prose(fields["note"], note_width))
    return line


class SurfSwarmField(Vertical):
    """THE FIELD -- one row per unfinished subtask, grouped by job."""

    DEFAULT_CSS = """
    SurfSwarmField > .surf-field-title {
        width: 100%;
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    SurfSwarmField > RichLog {
        height: 1fr;
        padding: 0 1;
        scrollbar-size: 1 1;
    }
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw payload, not formatted lines, so a resize re-lays it out.
        self._payload: dict = {}

    def compose(self) -> ComposeResult:
        yield Static(TITLE, classes="surf-field-title", id="surf-field-title")
        yield Static(" ", classes="surf-field-spacer")
        yield RichLog(
            id="surf-field-log",
            wrap=False,
            markup=False,
            highlight=False,
            max_lines=400,
        )

    def update_data(
        self,
        swarm_field_rows=None,
        swarm_as_of_hhmm=None,
        swarm_network=None,
        swarm_stale=None,
        **_kwargs,
    ) -> None:
        """Rewrite the log.  Every kwarg spelled after its ``SURF_KEYS`` name.

        ``swarm_network`` is accepted and never painted -- see the module
        docstring for why this panel is not one of the chain-word ones.
        """
        self._payload = {
            "rows": swarm_field_rows,
            "as_of": swarm_as_of_hhmm,
            "stale": swarm_stale,
            "seen": True,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    # -- rendering -----------------------------------------------------

    def _log_width(self, log: RichLog) -> int:
        """Rendered columns available to one line.

        ``scrollable_content_region``, not ``content_size``:
        ``RichLog``'s own ``DEFAULT_CSS`` reserves its scrollbar gutter even
        for a two-line log, exactly the measurement ``activity.py`` and
        ``launchpad_activity.py`` already make.
        """
        width = log.scrollable_content_region.width
        if width <= 0:
            width = max(self.content_size.width - 3, 0)
        return width

    def _set_title(self, widen: bool) -> None:
        try:
            title = self.query_one("#surf-field-title", Static)
        except Exception:  # not composed yet
            return
        base = TITLE
        as_of = self._payload.get("as_of")
        if _has_marker(as_of):
            base += f" · as of {as_of}"
            if self._payload.get("stale"):
                base += " · stale"
        budget = max(self.content_size.width - 2, 0)
        title.update(_title_with_hint(base, widen, budget))

    def _render_view(self) -> None:
        try:
            log = self.query_one("#surf-field-log", RichLog)
        except Exception:  # not composed yet
            return

        log.clear()
        log.auto_scroll = False

        rows_input = self._payload.get("rows")
        as_of = self._payload.get("as_of")
        if not _has_marker(as_of) or rows_input is None:
            # No real ``as of`` marker (``None``, or the same empty string
            # :func:`_has_marker` treats as absent -- fix round 2's ``and
            # as_of``) means this slot has never been written -- unavailable,
            # whatever ``rows`` says, because the fold's own ``[]``-for-both
            # shape (see the module docstring) makes an empty list ambiguous
            # on its own.  ``rows_input is None`` stays checked too, so the
            # widget is still honest if it is ever handed that sentinel
            # directly.
            self._set_title(False)
            log.write(Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"))
            return

        try:
            rows = list(rows_input)[:_MAX_ROWS]
        except TypeError:
            rows = []

        parsed = [f for f in (_row_fields(row) for row in rows) if f is not None]
        if not parsed:
            self._set_title(False)
            log.write(Text(EMPTY_LINE, style="dim"))
            return

        width = self._log_width(log)
        tier = _tier_for(width)
        note_width = (
            max(width - _fixed_cols("full") - _GAP, 0) if tier == "full" else 0
        )
        self._set_title(tier != "full")

        for objective, group in _group_by_job(parsed):
            header = _header_text(objective, width)
            if header is not None:
                log.write(header)
            for fields in group:
                log.write(_row_text(fields, tier, note_width))

        self.call_after_refresh(log.scroll_home, animate=False)

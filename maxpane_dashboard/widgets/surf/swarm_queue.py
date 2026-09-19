"""QUEUE: counts by state across all jobs, then every blocked job's reason.

``pool4u_burn.py``'s shape (Task 8): a ``Vertical`` of two ``Static``s -- a
title with its own blank row under it, and a body joined from a short list of
lines with ``_pool4.join_lines``. Unlike ``pool4u_burn.py`` the body's line
*count* is not fixed (a job can be in any number of states, and up to eight
jobs can be blocked at once -- ``data/surf_swarm.blocked_rows``'s own
``limit=8``), and unlike ``pool4u_burn.py``'s markup-string lines (parsed
through ``_pool4.parse_line``), every line here is built as a pre-built
``rich.text.Text`` directly -- see *"Third-party text"* below for why: state
and blocked-reason are both host-controlled strings, and ``join_lines`` joins
a list of already-built ``Text`` objects regardless of how each one was
constructed, so this keeps the two-``Static`` shape without routing hostile
text through a markup parser at all.

Row shapes (``data/surf_models.SURF_ROW_KEYS``, frozen):
``swarm_queue_rows`` is ``state``, ``count``; ``swarm_blocked_rows`` is
``job_id``, ``template``, ``reason``, ``moved_ts``.

The unread/empty split, and why it is not ``swarm_field.py``'s gate verbatim
------------------------------------------------------------------------------
``data/surf_swarm.queue_rows``/``blocked_rows`` both return ``[]`` for a
missing job list (``jobs`` falsy -- never read, or a cold cache) **and** for a
genuinely empty one, exactly the ambiguity ``swarm_field.py``'s own docstring
names. That module resolves it with one rule: no real ``swarm_as_of_hhmm``
marker (:func:`_has_marker`) means the whole panel is unavailable, full stop,
whatever the rows say.

QUEUE cannot use that rule *unmodified*, because it renders **two**
semi-independent lists off one marker (state counts, and the blocked-job
list) rather than THE FIELD's one homogeneous list, and in production the two
lists are never independently populated -- ``_swarm_keys`` derives both from
the same ``jobs`` read, so a marker-absent, rows-present combination cannot
happen outside a test harness. What is kept from THE FIELD's rule is its
*purpose*: the panel must not tell a cold cache's silence apart from a real
"nothing queued, nothing blocked" read. That purpose is served here by
:func:`_is_unavailable`, which is the marker-absent rule **with an escape
hatch for actual content**: if either list is non-empty, something was
plainly read (a truly cold slot cannot produce a row), so the panel renders
what it was given rather than a message that would contradict the rows sitting
right next to it. The escape hatch is inert in production and exists only so
this module can be tested one list at a time, the way
``tests/widgets/test_surf_swarm_rail.py`` does it, without every call site
threading a marker through for content that already proves itself real.

Below that gate, the two lists degrade independently and honestly: an empty
*queue* section (a marker was seen, or the blocked list carries rows, but no
job states were counted) prints :data:`EMPTY_LINE` rather than nothing, and an
empty *blocked* section prints :data:`NO_BLOCKED_LINE` -- CLAUDE.md's rule
that a real "we looked and found nothing" must never render identically to
"we never looked".

``swarm_queue_depths`` (F6, ``docs/surf_swarm_followups.md``): the pipeline's own
backlog counters
-------------------------------------------------------------------------------
``data/surf_swarm.health_facts`` folds every ``pending*`` key off the live
tier's own ``/health`` read into ``{name: int}`` (``verification``,
``attestation``, ``deployment``, ``delivery``, ``feedback``, ``fuzz``,
``sites``) and publishes ``depths or None`` -- so ``swarm_queue_depths is
None`` means *either* "health was never read" *or* "the payload had no
``pending*`` key at all", while a dict of genuine zeros is truthy and real.
Gating on that truthiness alone (or on a derived total's truthiness -- the
shape ``swarm_jobs_in_flight``/``_blocked`` and ``throughput`` were both
already bitten by, F-C and F10) would render a fully-drained pipeline
identically to a dead read, so this block reuses the **same** instrument
:func:`_is_unavailable` already gates the whole panel with --
:func:`_has_marker` on ``swarm_as_of_hhmm`` -- rather than inventing a second
mechanism keyed off the dict itself. ``health`` and ``jobs`` always land or
fail together within one ``SLOT_SWARM`` write (``SurfManager._pool_swarm``),
so a real marker always means ``queue_depths`` was read; the pending block is
skipped (not a message, just absent) on the one payload shape that cannot
occur in production -- a marker with a non-dict ``queue_depths`` -- rather
than fabricate a line for it.

Rendered as one compact line, :data:`PENDING_LABEL` plus the summed total
(a genuine all-zero backlog prints ``PENDING 0``, never blank and never the
unavailable line) followed by only the *non-zero* named counters, in the
API's own canonical order (:data:`_DEPTH_ORDER`) -- the terminal-layout
skill's "shorten the value, do not raise the pin" rule applied to a block
that could otherwise cost a header plus seven rows: seven full ``name:
count`` lines were measured against this body's own row pin
(``SURF_SWARM_FULL_LAYOUT_ROWS``) and were not the honest trade once the
common case (most counters idle) is this cheap to say in one line instead.

Third-party text, and the no-bracket contract
-----------------------------------------------
``reason`` (``job.blockedReason``) is free text a host process wrote, exactly
the class of string CLAUDE.md's escaping rule and ``swarm_field.py``'s own
module docstring are about: an *escaped* ``[/x]`` still renders as the
literal text ``[/x]`` once a markup parser unescapes it for display, so
stripping (``_pool4.strip_tags``) is used instead of ``safe_markup`` for it,
and for ``state`` -- also host-controlled, per ``data/surf_swarm.queue_rows``'s
own comment that job state is an open, not a closed, vocabulary.

``moved_ts`` is a raw epoch timestamp, not a duration: converting it to an
*age* would need ``time.time()`` at render time, which this module -- like
every pure or render-only module in this repo -- may not call ("Inject the
clock", CLAUDE.md). ``_fmt.hhmm`` is used instead: a pure epoch-to-local-clock
conversion that needs no "now" at all, so the row shows *when* a job moved
rather than a relative age it has no clock to compute.

Purity
------
Stdlib, ``rich``, ``textual``, and this package's own ``_fmt``/``_pool4``/
``rowfit`` primitives. No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm
from maxpane_dashboard.widgets.surf._pool4 import (
    join_lines,
    strip_tags,
)

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "NO_BLOCKED_LINE",
    "PENDING_LABEL",
    "SurfSwarmQueue",
    "TITLE",
    "UNAVAILABLE_LINE",
]

TITLE = "QUEUE"

#: The whole-panel degraded state: no marker and nothing to show either
#: list. Tested verbatim.
UNAVAILABLE_LINE = "unavailable"

#: A real read of the state counts that found nothing to count. Distinct
#: from :data:`UNAVAILABLE_LINE` -- the curator rail bug is a dead group's
#: "unknown" and a genuine "none yet" reading identically, and this module
#: exists to not repeat it.
EMPTY_LINE = "no jobs"

#: A real read of the blocked list that found nothing blocked. Tested
#: verbatim (frozen name).
NO_BLOCKED_LINE = "nothing blocked"

#: F6's own block: the swarm's pipeline backlog (``swarm_queue_depths``).
#: Tested verbatim.
PENDING_LABEL = "PENDING"

#: The seven names ``data/surf_swarm.health_facts`` is documented to fold
#: out of the live ``/health`` read's own ``pending*`` keys, in the order
#: that doc names them -- rendering order, not a producer contract: the
#: dict itself carries whatever order the host's JSON happened to decode
#: in, so without this the line would reorder every poll for no reason. An
#: eighth name the API adds later is not dropped -- :func:`_depth_items`
#: appends anything outside this tuple, sorted, exactly the way
#: ``queue_rows``'s own ``state`` column treats its open vocabulary.
_DEPTH_ORDER = (
    "verification", "attestation", "deployment", "delivery", "feedback",
    "fuzz", "sites",
)

_GAP = rowfit.GAP
_TITLE_ID = "surf-swarm-queue-title"
_BODY_ID = "surf-swarm-queue-body"
_TITLE_CLASS = "surf-swarm-queue-title"

# -- column budget, in rendered columns ---------------------------------
#
# ``state`` is not a closed vocabulary (``data/surf_swarm.queue_rows``'s own
# comment), so this is a measurement against the committed fixtures
# (``tests/fixtures/surf/swarm/``), not a producer pin: the widest captured
# values are ``completed``/``cancelled``/``executing`` at 9 cells -- all of
# them *terminal* states THE FIELD never has to size for, because it only
# ever shows unfinished subtasks. QUEUE counts every job, terminal states
# included, so it needs headroom THE FIELD's own ``_STATE_COLS`` (8) does
# not carry.
_STATE_COLS = 11
#: Up to five digits of count, left-aligned like every other cell in this
#: package.
_COUNT_COLS = 5

#: ``_fmt.hhmm``'s own width: ``HH:MM`` or ``??:??``.
_TIME_COLS = 5
#: The narrowest reason worth printing at all -- the clause that explains a
#: stall, not just its opener. Measured against the widest captured
#: ``blockedReason`` (``"node scaffold_project: runtime_error"``, 37 cells):
#: this floor still shows all of a typical one and clips only the rare
#: longer sentence.
_MIN_REASON_COLS = 20

#: Columns the blocked line's fixed cells (template's own column having been
#: dropped for the rail's width, in favour of the reason it exists to show)
#: cost before the reason gets whatever remains -- the threshold
#: :func:`_tier_for` fits against.
FULL_WIDTH = rowfit.row_cols((_TIME_COLS,)) + _GAP + _MIN_REASON_COLS      # 27
#: Below :data:`FULL_WIDTH` the time column goes and the reason takes the
#: whole remaining budget; there is no floor under *that*, so the fallback
#: tier's own threshold is never consulted (``rowfit.tier_for``'s contract).
COMPACT_WIDTH = 0


_LADDER = rowfit.Ladder(("full", FULL_WIDTH), ("compact", COMPACT_WIDTH))
_tier_for = _LADDER.tier_for


#: The ``as of`` predicate and the network-word-free title fitter, shared by
#: the four swarm panels in ``widgets/rowfit.py`` since Branch 3 (each used to
#: restate them; the reasoning is on the shared definitions), under the names
#: this module's own docstrings and tests use.
_has_marker = rowfit.has_marker
_title_with_hint = rowfit.title_with_hint


def _is_unavailable(as_of: object, queue_rows: object, blocked_rows: object) -> bool:
    """True only when there is truly nothing to show: no marker, no rows.

    See the module docstring's *"The unread/empty split"* section for why
    this is an escape-hatched version of ``swarm_field.py``'s marker-only
    gate rather than a copy of it: in production a marker-absent read can
    never carry rows (both lists are folded from the same ``jobs`` read that
    also produces the marker), so a non-empty list here is always real
    content and must not be hidden behind a message that contradicts it.
    """
    return not _has_marker(as_of) and not queue_rows and not blocked_rows


def _state_line(row: dict) -> Text:
    state = strip_tags(row.get("state")) or DASH
    count = row.get("count")
    count_text = (
        str(count) if isinstance(count, int) and not isinstance(count, bool) else DASH
    )
    line = Text()
    line.append(rowfit.pad(rowfit.clip(state, _STATE_COLS), _STATE_COLS))
    line.append(" " * _GAP)
    line.append(rowfit.pad(count_text, _COUNT_COLS), style="bold")
    return line


def _blocked_line(row: dict, tier: str, reason_width: int) -> Text:
    reason = strip_tags(row.get("reason")) or DASH
    line = Text()
    if tier == "full":
        when = hhmm(row.get("moved_ts"))
        line.append(rowfit.pad(when, _TIME_COLS), style="dim")
        line.append(" " * _GAP)
    line.append(rowfit.clip(reason, max(reason_width, 0)))
    return line


def _depth_items(depths: dict) -> list[tuple[str, int]]:
    """``depths`` as an ordered ``(name, count)`` list; a non-``int`` value
    (including ``bool``, which is an ``int`` subclass) is dropped rather than
    guessed at -- the same defensiveness ``_state_line``'s own count cell
    applies to a row it cannot trust.
    """
    names = list(_DEPTH_ORDER) + sorted(n for n in depths if n not in _DEPTH_ORDER)
    out = []
    for name in names:
        if name not in depths:
            continue
        count = depths.get(name)
        if isinstance(count, int) and not isinstance(count, bool):
            out.append((name, count))
    return out


def _pending_line(depths: dict, budget: int) -> Text:
    """F6's own compact block: the total backlog, then only what is nonzero.

    A genuinely drained pipeline (every counter real, every one ``0``) still
    prints its total -- ``"PENDING 0"``, never blank -- so a zero backlog and
    an unread one cannot look alike; see the module docstring's own F6
    section for why the *caller* gates this on ``swarm_as_of_hhmm`` before
    ever reaching here, rather than this function inventing a second
    unread/read distinction of its own.

    Naming only the nonzero counters (:data:`_DEPTH_ORDER`'s own order) is
    the terminal-layout skill's ``do not raise the pin, shorten the value``
    rule applied here: seven ``name: count`` rows were measured against this
    body's own row pin and cost more than the common case (most counters
    idle) is worth saying every poll. The whole line still clips honestly at
    ``budget`` if a genuinely busy pipeline runs long, the same as every
    other line in this panel.
    """
    items = _depth_items(depths)
    total = sum(count for _, count in items)
    parts = [f"{strip_tags(name) or DASH} {count}" for name, count in items if count > 0]
    text = f"{PENDING_LABEL} {total}"
    if parts:
        text += " · " + " · ".join(parts)
    line = Text()
    line.append(rowfit.clip(text, max(budget, 0)), style="dim")
    return line


def _content_lines(
    queue_rows: object, blocked_rows: object, queue_depths: object,
    as_of: object, budget: int,
) -> tuple[list[Text], str]:
    tier = _tier_for(budget)

    state_lines = [
        _state_line(row) for row in (queue_rows or ()) if isinstance(row, dict)
    ]
    if not state_lines:
        state_lines = [Text(EMPTY_LINE, style="dim")]

    reason_width = budget if tier != "full" else max(budget - _TIME_COLS - _GAP, 0)
    blocked_lines = [
        _blocked_line(row, tier, reason_width)
        for row in (blocked_rows or ())
        if isinstance(row, dict)
    ]
    if not blocked_lines:
        blocked_lines = [Text(NO_BLOCKED_LINE, style="dim")]

    lines = state_lines + [Text("")] + blocked_lines

    # F6: the pending-pipeline block. Gated on the same marker
    # ``_is_unavailable`` already used to decide the whole panel is showing
    # real content at all -- ``health``/``jobs`` always land or fail
    # together in one ``SLOT_SWARM`` write, so a real marker always means
    # ``queue_depths`` was actually read. A non-``dict`` value here despite
    # a real marker is the one shape production cannot produce (an empty
    # ``pending*`` key set folds to ``None`` before this ever runs -- see
    # ``data/surf_swarm.health_facts``), so it is skipped rather than given
    # an invented line.
    if _has_marker(as_of) and isinstance(queue_depths, dict):
        lines += [Text(""), _pending_line(queue_depths, budget)]

    return lines, tier


class SurfSwarmQueue(Vertical):
    """QUEUE -- job counts by state, then every blocked job's reason."""

    DEFAULT_CSS = """
    SurfSwarmQueue {
        height: auto;
    }
    SurfSwarmQueue > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfSwarmQueue > .surf-swarm-queue-title {
        margin: 0 0 1 0;
    }
    """

    #: ``> Static``'s own ``padding: 0 1``: a fit decision compares against
    #: ``self.size.width`` minus two, never ``self.size.width``.
    _TITLE_PADDING_COLS = 2

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # The raw payload, not formatted lines, so a resize re-lays it out.
        self._payload: dict = {}
        self._widen = False

    def compose(self) -> ComposeResult:
        yield Static(Text(TITLE, style="dim"), id=_TITLE_ID, classes=_TITLE_CLASS)
        yield Static(Text(""), id=_BODY_ID)

    def on_resize(self, _event=None) -> None:
        if self._payload:
            self._render_view()

    def update_data(
        self,
        swarm_queue_rows=None,
        swarm_blocked_rows=None,
        swarm_as_of_hhmm=None,
        swarm_queue_depths=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        Every kwarg is spelled after its full ``swarm_`` contract key
        (``data/surf_models.SWARM_KEYS``). ``**_kwargs`` is mandatory: the
        screen splats the whole payload. ``swarm_queue_depths`` is F6
        (``docs/surf_swarm_followups.md``) -- see the module docstring's own
        section on it for the read-vs-zero gate.
        """
        self._payload = {
            "queue": swarm_queue_rows,
            "blocked": swarm_blocked_rows,
            "as_of": swarm_as_of_hhmm,
            "depths": swarm_queue_depths,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        """``TITLE``, plus ``· as of HH:MM`` once a real marker is held.

        F-B: this panel used to serve last-good rows through an outage with
        no clock on screen at all -- ``swarm_as_of_hhmm`` reached
        ``update_data`` and was stored, but only ``_is_unavailable`` ever
        read it. Design §6.2 and CLAUDE.md both require last-good to sit
        behind its own ``as of`` marker, the way THE FIELD's own title does.

        **The live tier's marker, not the scores one.** QUEUE's rows
        (``swarm_queue_rows``/``swarm_blocked_rows``) are folded from
        ``SLOT_SWARM`` in ``_swarm_keys`` -- the same slot this payload's
        ``swarm_as_of_hhmm`` already names -- never from the slower scores
        sweep. ``update_data`` has no ``swarm_scores_as_of_hhmm`` parameter
        at all, so there is no clock here to wire to the wrong tier by
        accident.
        """
        base = TITLE
        as_of = self._payload.get("as_of") if self._payload else None
        if _has_marker(as_of):
            base += f" · as of {as_of}"
        return _title_with_hint(base, self._widen, self._text_budget())

    def _render_view(self) -> None:
        try:
            title = self.query_one(f"#{_TITLE_ID}", Static)
            body = self.query_one(f"#{_BODY_ID}", Static)
        except Exception:  # not composed yet
            return

        def paint(*content: Text) -> None:
            title.update(Text(self._title_text(), style="dim"))
            body.update(join_lines(list(content)))

        if not self._payload:
            self._widen = False
            paint()
            return

        payload = self._payload
        as_of = payload.get("as_of")
        queue_rows = payload.get("queue")
        blocked_rows = payload.get("blocked")

        if _is_unavailable(as_of, queue_rows, blocked_rows):
            self._widen = False
            paint(Text(f"⚠ {UNAVAILABLE_LINE}", style="yellow"))
            return

        budget = self._text_budget()
        queue_depths = payload.get("depths")
        content, tier = _content_lines(queue_rows, blocked_rows, queue_depths, as_of, budget)
        self._widen = tier != "full"
        paint(*content)

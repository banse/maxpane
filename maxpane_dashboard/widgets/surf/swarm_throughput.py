"""THROUGHPUT: accepted per day, median delivery, revision rate, and the
agents who scored the work.

``pool4u_burn.py``'s shape (Task 8), the same as ``swarm_queue.py``: a
``Vertical`` of two ``Static``s -- a title with its own blank row under it,
and a body of pre-built ``rich.text.Text`` lines joined with
``_pool4.join_lines`` (no markup strings, no ``_pool4.parse_line`` -- see
``swarm_queue.py``'s own docstring for why, which applies here too: an agent
token is host-controlled text and gets the same treatment ``swarm_queue.py``
gives a blocked reason).

Two sections, two different honesty problems
----------------------------------------------
This panel answers two different questions off two different reads, and they
degrade differently on purpose:

1. **The three rate numbers** (``accepted_per_day``, ``median_delivery_s``,
   ``revision_rate``) come from ``data/surf_swarm.throughput``, which is
   *already* honest per field: an unread window (``jobs`` falsy) returns a
   dict whose three rate fields are every one of them ``None``, and a read
   window with genuinely nothing accepted returns a real ``0.0`` for
   ``accepted_per_day`` (``round(0 / window_days, 2)``, never skipped). There
   is therefore **no marker-gating needed for these three fields at all**: a
   per-field ``None`` already means "not read" and a per-field number,
   ``0`` included, already means "read". This is the CLAUDE.md rule --
   "a failed read is ``None``, never ``0``" -- already held one layer down,
   so this widget's job is only to keep it visible rather than to enforce it
   again: each of the four labelled rows (the three rates plus the window
   they share) renders :data:`_fmt.DASH` for ``None`` and the real value,
   zero included, otherwise. This is also why these four rows render
   **unconditionally**, with no ``swarm_scores_as_of_hhmm`` gate of their
   own -- gating them on a marker neither test in
   ``tests/widgets/test_surf_swarm_rail.py`` sets would hide the very
   dashes those tests assert are present.

2. **The agent score rows** (``swarm_score_rows``) do *not* carry that same
   guarantee: ``data/surf_swarm.score_rows`` returns ``[]`` for both an
   unread sweep and a read one that scored nothing, the identical ambiguity
   ``swarm_queue.py``'s two lists have. This section is therefore gated the
   way ``swarm_field.py`` gates its one list: no real
   ``swarm_scores_as_of_hhmm`` marker and no rows means unavailable; a marker
   (or non-empty rows, for the same test-harness reason
   ``swarm_queue.py._is_unavailable`` documents) and an empty list means a
   real read found no agents; rows present means rows render.

The chain word is deliberately absent from this title
-------------------------------------------------------
The design note (``docs/superpowers/specs/2026-09-16-surf-swarm-view-design.md``
§5/§6) names "any score quoting a transaction" among the panels that should
carry the chain word in their title. This panel is exactly that panel, and
the tension is recorded rather than resolved by omission: Task 8's own frozen
interface names four consumed keys for this widget --
``swarm_throughput``, ``swarm_score_rows``, ``swarm_scores_as_of_hhmm``,
``swarm_stale`` -- and ``swarm_network`` is not one of them, where the
sibling ``JUST SHIPPED`` panel's own Task 9 brief *does* name it. Read
together, that looks like a deliberate, later narrowing of the design note's
general rule rather than an oversight, so this widget follows the more
specific and more recent instruction and takes no ``swarm_network`` kwarg.
Flagged for the review pass rather than guessed either way.

``last_chain_id`` is accepted as part of the frozen ``swarm_score_rows`` row
shape but is not rendered as a separate word for the same reason: the only
widget-safe (``data/``-free) allowlist mapping a chain id to a name is
``data/surf_swarm.network_of``, which lives in ``data/`` and cannot be
imported here, and the brief's own description of what to render for this
row names only ``last_tx_hash`` (shortened, no copy icon) and, optionally,
``agent_token``.

Purity
------
Stdlib, ``rich``, ``textual``, and this package's own ``_fmt``/``_pool4``/
``_rowfit``/``address`` primitives. No ``data/``, no ``analytics/``, no
clock, no I/O.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Static

from maxpane_dashboard.widgets.address import MIN_SHORT_COLS, short_hex
from maxpane_dashboard.widgets.surf import _rowfit
from maxpane_dashboard.widgets.surf._fmt import DASH, as_float, fmt_age
from maxpane_dashboard.widgets.surf._pool4 import GLYPH_HINT, WIDEN_HINT, join_lines, strip_tags

__all__ = [
    "AGENTS_UNAVAILABLE_LINE",
    "LABEL_COLS",
    "NO_AGENTS_LINE",
    "ROW_LABELS",
    "STALE_WORD",
    "SurfSwarmThroughput",
    "TITLE",
]

TITLE = "THROUGHPUT"

#: Appended to the title whenever the manager says the sweep and the live
#: tier's markers have drifted apart (spec §6). Tested verbatim.
STALE_WORD = "stale"

#: The agent-score section's own degraded states -- mirrors
#: ``swarm_queue.py``'s ``UNAVAILABLE_LINE``/``EMPTY_LINE`` split, scoped to
#: this one section since the rate rows above it never go blank (see the
#: module docstring).
AGENTS_UNAVAILABLE_LINE = "agents unavailable"
NO_AGENTS_LINE = "no agents scored yet"

#: The four labelled rate rows, in render order. A tuple so a test can pin
#: the panel paints exactly these four and in this order.
ROW_LABELS: tuple[str, ...] = ("accepted", "window", "delivered", "revised")

_GAP = _rowfit.GAP
_TITLE_ID = "surf-swarm-throughput-title"
_BODY_ID = "surf-swarm-throughput-body"
_TITLE_CLASS = "surf-swarm-throughput-title"

#: Widest label (``delivered``, 9 cells) plus headroom, so the values line up
#: one column to the right of every label.
LABEL_COLS = 11

#: ``#`` + up to five digits, or :data:`_fmt.DASH` -- ``swarm_field``'s own
#: ``_agent_cell`` window, restated for the same reason every other shared
#: constant in this package is: an import across sibling widgets is a
#: coupling across an ownership seam.
_AGENT_COLS = 6
#: ``mean_score`` at one decimal: ``100.0`` is the widest real value.
_SCORE_COLS = 5
#: ``jobs_scored`` as ``NNNj``.
_JOBS_COLS = 4
#: ``widgets/address.MIN_SHORT_COLS`` -- below this a transaction hash's own
#: shortening window stops being legible, so the column is dropped instead
#: of rendered illegibly small.
_MIN_TX_COLS = MIN_SHORT_COLS


def _has_marker(as_of: object) -> bool:
    """True when *as_of* is a real ``as of`` clock, not merely non-``None``.

    ``swarm_field.py``'s predicate, restated -- see ``swarm_queue.py``'s copy
    of the same docstring note.
    """
    return isinstance(as_of, str) and bool(as_of)


def _title_with_hint(base: str, widen: bool, budget: int) -> str:
    """Append the longest widen marker that fits *base* within *budget*.

    No network word: see the module docstring's *"The chain word is
    deliberately absent"* section.
    """
    if not widen:
        return base
    for candidate in (WIDEN_HINT, GLYPH_HINT):
        if not budget or cell_len(base) + 2 + cell_len(candidate) <= budget:
            return f"{base}  {candidate}"
    return base


def _rate_row(label: str, value: str) -> Text:
    line = Text()
    line.append(_rowfit.pad(label, LABEL_COLS), style="dim")
    line.append(value)
    return line


def _stat_lines(throughput: object) -> list[Text]:
    """The four labelled rows -- unconditional; see the module docstring.

    ``None`` is never rendered as ``0`` here: every value below comes off
    :func:`_fmt.as_float`/an ``int`` check, and a value that is not present
    or not the right type renders :data:`_fmt.DASH`, exactly like a real
    ``0`` renders as ``0``.
    """
    tp = throughput if isinstance(throughput, dict) else {}

    accepted = as_float(tp.get("accepted_per_day"))
    accepted_text = f"{accepted:.2f}/day" if accepted is not None else DASH

    window = tp.get("window_days")
    window_text = (
        f"{window}d"
        if isinstance(window, int) and not isinstance(window, bool)
        else DASH
    )

    delivered_raw = fmt_age(tp.get("median_delivery_s"))
    delivered_text = delivered_raw if delivered_raw == DASH else f"{delivered_raw} median"

    revision = as_float(tp.get("revision_rate"))
    revision_text = f"{revision * 100:.1f}%" if revision is not None else DASH

    return [
        _rate_row(ROW_LABELS[0], accepted_text),
        _rate_row(ROW_LABELS[1], window_text),
        _rate_row(ROW_LABELS[2], delivered_text),
        _rate_row(ROW_LABELS[3], revision_text),
    ]


def _agent_cell(token: object) -> str:
    """``#2`` for a held seat; :data:`_fmt.DASH` for an unheld or malformed one."""
    if token is None:
        return DASH
    text = strip_tags(token)
    return f"#{text}" if text else DASH


def _agent_line(row: dict, tx_width: int) -> Text:
    agent = _agent_cell(row.get("agent_token"))
    mean = row.get("mean_score")
    mean_text = (
        f"{mean:.1f}"
        if isinstance(mean, (int, float)) and not isinstance(mean, bool)
        else DASH
    )
    jobs = row.get("jobs_scored")
    jobs_text = (
        f"{jobs}j" if isinstance(jobs, int) and not isinstance(jobs, bool) else DASH
    )
    tx = row.get("last_tx_hash")
    tx_text = short_hex(tx, tx_width) if isinstance(tx, str) and tx else DASH

    line = Text()
    line.append(_rowfit.pad(_rowfit.clip(agent, _AGENT_COLS), _AGENT_COLS), style="bold")
    line.append(" " * _GAP)
    line.append(_rowfit.pad(_rowfit.clip(mean_text, _SCORE_COLS), _SCORE_COLS))
    line.append(" " * _GAP)
    line.append(
        _rowfit.pad(_rowfit.clip(jobs_text, _JOBS_COLS), _JOBS_COLS), style="dim",
    )
    if tx_width > 0:
        line.append(" " * _GAP)
        line.append(_rowfit.clip(tx_text, tx_width), style="dim")
    return line


def _agents_unavailable(as_of: object, score_rows: object) -> bool:
    """See ``swarm_queue.py``'s ``_is_unavailable`` for the same shape and
    the same test-harness escape hatch."""
    return not _has_marker(as_of) and not score_rows


def _agent_lines(score_rows: object, scores_as_of: object, width: int) -> tuple[list[Text], bool]:
    if _agents_unavailable(scores_as_of, score_rows):
        return [Text(f"⚠ {AGENTS_UNAVAILABLE_LINE}", style="yellow")], False

    rows = [row for row in (score_rows or ()) if isinstance(row, dict)]
    if not rows:
        return [Text(NO_AGENTS_LINE, style="dim")], False

    fixed = _rowfit.row_cols((_AGENT_COLS, _SCORE_COLS, _JOBS_COLS))
    tx_width = max(width - fixed - _GAP, 0)
    show_tx = tx_width >= _MIN_TX_COLS
    lines = [_agent_line(row, tx_width if show_tx else 0) for row in rows]
    return lines, not show_tx


class SurfSwarmThroughput(Vertical):
    """THROUGHPUT -- accepted/day, median delivery, revision rate, agents."""

    DEFAULT_CSS = """
    SurfSwarmThroughput {
        height: auto;
    }
    SurfSwarmThroughput > Static {
        width: 100%;
        padding: 0 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    SurfSwarmThroughput > .surf-swarm-throughput-title {
        margin: 0 0 1 0;
    }
    """

    #: ``> Static``'s own ``padding: 0 1``.
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
        swarm_throughput=None,
        swarm_score_rows=None,
        swarm_scores_as_of_hhmm=None,
        swarm_stale=None,
        **_kwargs,
    ) -> None:
        """Refresh the panel from the manager's flat dict.

        Every kwarg is spelled after its full ``swarm_`` contract key
        (``data/surf_models.SWARM_KEYS``). ``**_kwargs`` is mandatory: the
        screen splats the whole payload.
        """
        self._payload = {
            "throughput": swarm_throughput,
            "score_rows": swarm_score_rows,
            "scores_as_of": swarm_scores_as_of_hhmm,
            "stale": swarm_stale,
            "seen": True,
        }
        self._render_view()

    def _text_budget(self) -> int:
        return max(self.size.width - self._TITLE_PADDING_COLS, 0)

    def _title_text(self) -> str:
        payload = self._payload
        base = TITLE
        as_of = payload.get("scores_as_of")
        if _has_marker(as_of):
            base += f" · as of {as_of}"
        # Unlike ``swarm_field.py``, ``stale`` is not conditioned on the
        # marker's own presence: the given contract test drives it with no
        # marker set at all (``test_the_stale_word_appears_only_when_told``),
        # and in production ``swarm_stale`` is only ever non-``None`` when
        # both markers it compares already exist (``_swarm_scores_keys``),
        # so there is nothing dishonest about surfacing it unconditionally
        # here.
        if payload.get("stale"):
            base += f" · {STALE_WORD}"
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
        budget = self._text_budget()
        stat_lines = _stat_lines(payload.get("throughput"))
        agent_lines, widen = _agent_lines(
            payload.get("score_rows"), payload.get("scores_as_of"), budget,
        )
        self._widen = widen
        paint(*stat_lines, Text(""), *agent_lines)

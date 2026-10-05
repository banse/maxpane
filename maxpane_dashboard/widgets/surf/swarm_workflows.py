"""WORKFLOWS: the swarm's ``/workflows``, one row per workflow (SWARM WORKFLOWS, WP4).

``docs/surf_swarm_workflows_spec.md`` §2 "Widget". A
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase` table that
took CAPABILITY's place on the ``s`` body in WP5 (2026-10-03), exported from
``widgets/surf/__init__.py`` and named in ``SWARM_WIDGET_SIGNATURES``.

Columns ``when · status · contracts · frontend · objective / failure``:

* ``when`` -- ``mmdd_hhmm(created_ts)``, ``--`` when the stamp is unusable;
* ``status`` -- ``sanitize_cell``, coloured on the **raw** word (completed
  green, blocked red, cancelled dim, any other word yellow; a missing status
  is a plain ``--``, not a word);
* ``contracts`` / ``frontend`` -- the job id's head through
  ``address.job_text`` linked on the IMD explorer (``_fmt.JOB_EXPLORER``); a
  workflow with no frontend job is a dim ``—``;
* ``objective / failure`` -- elastic: every spare cell above
  :data:`TEXT_MIN_COLS` (LAUNCHES' ``column_plan`` shape).

The text cell
-------------
A row whose status is not ``completed`` and whose ``failure`` is a non-blank
string shows the failure, in red; every other row shows the objective's
**first sentence** -- flattened, cut after the first ``.`` followed by
whitespace or the end (:func:`first_sentence`; an abbreviation such as
``e.g.`` is cut too, the rule's documented limit), then fitted to the
column on ``cell_len``. The cell is a pre-built ``rich.text.Text``, so the
served words render **literally**: ``sanitize_cell``'s ``strip_tags`` would
delete ``[FAIL: project constructor failed]``, the failure's own words. That
is IN FLIGHT's objective precedent (``swarm_inflight._cell``), and so is the
clip: a text cut with ``…`` does **not** light ``‹ widen`` -- only a shed
column does. ``markup_safety.flatten`` is the one cleaning step, as in IN
FLIGHT (its non-whitespace C0/ESC gap is filed; no private sanitiser here).

An address inside the text: its copy icon, and no link
------------------------------------------------------
CLAUDE.md: every displayed 0x address carries a copy icon, and an unknown
chain gets no link, never a guessed one. A failure can name a contract (the
100-row capture has ``0x000000000000000000000000000000000000c0de`` some 70
cells in), so the text goes through surf's fitted-prose route in
``_icons.py``, the idiom ``_oracle_answer.fit_popup_text`` and ``feed.py``
use: ``mark_addresses`` puts ``NBSP ⧉`` after each whole address in the plain
text, so the fit pays the icon's two cells; ``rowfit.clip`` fits it to the
column; ``keep_units`` keeps an address and its icon whole or drops the unit
whole in front of the ``…`` (never a ``0x`` fragment); ``unmark`` and
``link_prose`` then give each surviving glyph the helper's own copy action
and icon style. ``explorer=None``: a workflow carries no chain id and nothing
joins it to a launch, so the address is copyable and unlinked -- the choice
``rules/surf.md`` records for the SUBMISSION popup. An abbreviated
``0x5167d0...3281`` is not an address and gets nothing.

The SWARM address sweep (``tests/screens/test_address_icons_everywhere.py``)
demands a link for every other surf icon (E7); this one is the named
exception, by address: ``SweepCase.unlinked`` lists the seeded failure
address, and E7 asserts it copies and links nowhere (WP5).

Purity: stdlib, ``rich``, ``textual`` and this package's ``widgets/`` modules.
No ``data/`` (it restates nothing from there: ``ROW_CAP`` is bound to
``surf_models.SWARM_WORKFLOW_LIMIT`` by an agreement test), no
``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

import re

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import job_text
from maxpane_dashboard.widgets.fmt import as_float
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.panels import LOADING
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, JOB_EXPLORER, mmdd_hhmm
from maxpane_dashboard.widgets.surf._icons import fit_prose
from maxpane_dashboard.widgets.surf._swarm_table import (
    CELL_PADDING,
    SwarmTableBase,
    table_cols,
)

__all__ = [
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "TEXT_MIN_COLS",
    "TIGHT_WIDTH",
    "SurfSwarmWorkflows",
    "first_sentence",
]

#: ``when``: ``MM-DD HH:MM`` -- eleven cells, and ``unavailable`` (11) lands
#: here whole when the list could not be read.
_WHEN_COLS = 11
#: ``status``: ``completed`` / ``cancelled`` (9) are the widest served words.
_STATUS_COLS = 9
#: ``contracts``: the header's own nine cells over an eight-cell job-id head.
_CONTRACTS_COLS = 9
#: ``frontend``: the header's eight cells, the same eight-cell head.
_FRONTEND_COLS = 8
#: How much of a job id each job cell shows (a head slice, ``job_text``).
_JOB_HEAD_COLS = 8
#: ``objective / failure``: the elastic column's floor -- the header's own 19
#: cells and one more; it grows to every spare cell (module docstring).
TEXT_MIN_COLS = 20

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("status", "status", _STATUS_COLS),
    ("contracts", "contracts", _CONTRACTS_COLS),
    ("frontend", "frontend", _FRONTEND_COLS),
    ("text", "objective / failure", TEXT_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "frontend")
_TIGHT = tuple(key for key in _COMPACT if key != "when")

# The ladder is the spec's starting proposal, kept as measured: in a harness
# mounting this widget alone under the spec's stylesheet block (``width: 1fr;
# height: 1fr; min-height: 8; padding: 0 1;``) the captured page needs no
# horizontal scroll and shows every kept header whole at each threshold, and
# one cell less drops a tier (``tests/widgets/test_surf_swarm_workflows.py``,
# ``test_each_tier_shows_its_columns_whole_at_its_own_threshold_under_the_spec_css``).
# The panel's outer width is each number plus ``GUTTER_COLS`` (2) plus the
# padding (2). Certified in situ on SWARM by WP5 (2026-10-03,
# ``tests/screens/test_surf_swarm_layout.py``, every payload, both fold
# states): THROUGHPUT holds its 46-cell cap beside it, so the panel gets the
# terminal's width minus 48 and goes full from 119 columns, compact from 109,
# tight below -- each threshold in the layout test's boundary set.

#: ``full``: all five columns, the text at its floor -- 67 cells.
FULL_WIDTH = table_cols(w for _k, _l, w in _SPECS)                      # 67
#: ``compact``: ``frontend`` shed first -- most workflows have none (the
#: capture: 6 of 12), and the contracts job still names the row -- 57.
COMPACT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _COMPACT)  # 57
#: ``tight``: ``when`` shed too; the status and the text say what happened,
#: the row order still says when -- 44.
TIGHT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _TIGHT)      # 44

#: Colour looked up on the **raw** status word; the text beside it is escaped.
_STATUS_COLOURS = {"completed": "green", "blocked": "red", "cancelled": "dim"}
#: Any other non-empty word: a state this table does not know yet.
_OTHER_COLOUR = "yellow"
#: The one status whose failure text is never shown.
_COMPLETED = "completed"

#: A sentence ends at a ``.`` followed by whitespace or the end of the text.
_SENTENCE_END = re.compile(r"\.(?=\s|$)")


def first_sentence(value) -> str:
    """*value* flattened and cut after its first sentence-ending ``.``.

    The whole flattened text when it has no such dot; ``""`` for a
    non-string. Not clipped -- the caller fits it to its column.
    """
    text = flatten(value)
    match = _SENTENCE_END.search(text)
    return text[: match.end()] if match else text


def _when_cell(created_ts) -> str:
    return DASH if as_float(created_ts) is None else mmdd_hhmm(created_ts)


def _status_cell(raw) -> str:
    """Escaped status markup, coloured on the raw word (module docstring)."""
    shown = sanitize_cell(raw, _STATUS_COLS)
    if not shown:
        return DASH
    colour = _STATUS_COLOURS.get(raw, _OTHER_COLOUR)
    return f"[{colour}]{shown}[/]"


def _frontend_cell(job_id) -> Text:
    if job_id is None:
        return Text(EMDASH, style="dim")
    return job_text(job_id, _JOB_HEAD_COLS, explorer=JOB_EXPLORER)


def _text_cell(item: dict, width: int) -> Text:
    """The failure in red while the row is not completed, else the objective;
    each whole address with its copy icon, fitted as one unit (module docstring)."""
    failure = flatten(item.get("failure"))
    if item.get("status") != _COMPLETED and failure:
        raw, style = failure, "red"
    else:
        raw, style = first_sentence(item.get("objective")) or DASH, ""
    return fit_prose(raw, width, style=style)


class SurfSwarmWorkflows(SwarmTableBase):
    """WORKFLOWS -- ``when · status · contracts · frontend · objective / failure``."""

    TITLE = "WORKFLOWS"
    TABLE_ID = "surf-swarm-workflows-table"
    #: Newest twelve: ``surf_models.SWARM_WORKFLOW_LIMIT``, bound by a test.
    ROW_CAP = 12
    CURSOR_TYPE = "row"

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH)
    )

    LOADING_ROW = (LOADING, "", "", "", "")
    #: ``no workflows`` (12 cells) lands in the first column wide enough --
    #: the text column at every tier.
    EMPTY_ROW = ("", "", "", "", "no workflows")

    def update_data(
        self,
        swarm_workflow_rows=None,
        swarm_scores_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict; the footer counts these rows."""
        self.store(swarm_workflow_rows, swarm_scores_as_of_hhmm, swarm_workflow_rows)

    def column_plan(self, tier: str, budget: int) -> tuple[tuple[str, str, int], ...]:
        """The text column takes every spare cell above its floor."""
        keep = self.TIER_COLUMNS[tier]
        fixed = [w for k, _l, w in _SPECS if k in keep and k != "text"]
        spare = budget - table_cols(fixed) - CELL_PADDING
        return tuple(
            (key, label, max(TEXT_MIN_COLS, spare) if key == "text" else width)
            for key, label, width in _SPECS
            if key in keep
        )

    def _text_cols(self) -> int:
        return next((w for k, _l, w in (self._installed or ()) if k == "text"), TEXT_MIN_COLS)

    def build_cells(self, item: dict) -> dict[str, str | Text]:
        return {
            "when": _when_cell(item.get("created_ts")),
            "status": _status_cell(item.get("status")),
            "contracts": job_text(item.get("contracts_job_id"), _JOB_HEAD_COLS,
                                  explorer=JOB_EXPLORER),
            "frontend": _frontend_cell(item.get("frontend_job_id")),
            "text": _text_cell(item, self._text_cols()),
        }

    def build_footer(self, summary) -> tuple[str, ...] | None:
        """``newest 12 · 8 blocked · 4 completed``: the rows shown, by status,
        count descending then word; skip missing statuses. No footer for ``None`` or ``[]``."""
        if not isinstance(summary, list):
            return None
        shown = [row for row in summary[: self.ROW_CAP] if isinstance(row, dict)]
        if not shown:
            return None
        counts: dict[str, int] = {}
        for row in shown:
            word = strip_tags(flatten(row.get("status")))
            if word:
                counts[word] = counts.get(word, 0) + 1
        ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        return (f"newest {len(shown)}", *(f"{count} {word}" for word, count in ordered))

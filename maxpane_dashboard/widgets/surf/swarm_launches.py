"""LAUNCHES: the swarm's ``/launches``, one row per launch (swarm v2, WP6).

Mounted on the ``s`` body since WP7 (beside IN FLIGHT, ``minimal.tcss``);
a new file that imported nothing from the old ``swarm_shipped.py`` WP7
deleted -- its ``TIGHT_ADDR_COLS`` reasoning is restated below, not
imported.

Columns ``# · kind · status · chain · repo · artifacts · parked reason`` on
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase`
(the tier machinery shared by the three WP6 tables; see that module).

The chain word is per row, never in the title
----------------------------------------------
Rows mix chains -- 20 Sepolia and 10 mainnet launches in the corpus -- so
one word in the title would be confidently wrong for a third of the rows
under it (the ruling JUST SHIPPED recorded, 2026-09-16). Each row names its
own chain through ``_swarm_chain.chain_word(chain_id)`` (an allowlist: an
unknown id is the em dash) and links its artifact through
``explorer.for_chain_id(chain_id)`` -- Sepolia rows on ``sepolia.etherscan.io``,
mainnet rows on ``etherscan.io``, an unknown or missing id on nothing, never a
guess. ``swarm_network`` (the live tier's single word) is accepted by
``update_data`` because the frozen signature names it, and is not painted.

One icon per row (R-C)
-----------------------
The corpus has 55 artifact addresses over 30 launches; a column carrying
every one would make LAUNCHES the body's binding panel on icons alone. The
``artifacts`` cell shows the **first** artifact's address through
``address_text`` (copy icon, explorer link) and ``+n`` for the rest, dim;
``--`` for a launch with no artifacts; an artifact whose ``address`` is not a
valid address shows its ``name`` (escaped, no icon, no link).

``parked reason`` is clipped, not wrapped
------------------------------------------
The plan says the reason "wraps". ``DataTable.add_row(height=None)`` can
wrap a cell on Textual 8.1.1, but ``TableLeaderboard.render_table`` adds
every row at height 1, and a 197-character reason (the corpus maximum)
wrapped into a 12-cell column would be seventeen lines on a body whose row
pin is already a worst case over payloads. So the column is **elastic** --
it takes every spare cell above :data:`PARKED_MIN_COLS` -- and a reason it
still cannot show whole is clipped with ``…`` and the title says ``‹ widen``,
which is the brief's instruction and the divergence WP6 reports.

Purity: stdlib, ``rich``, ``textual`` and this package's ``widgets/`` modules.
No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import ICON_COLS, MIN_SHORT_COLS, address_text, is_address
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import sanitize_cell, strip_tags
from maxpane_dashboard.widgets.panels import LOADING
from maxpane_dashboard.widgets.surf._fmt import DASH
from maxpane_dashboard.widgets.surf._swarm_chain import CHAIN_COLS, chain_word
from maxpane_dashboard.widgets.surf._swarm_table import (
    CELL_PADDING,
    SwarmTableBase,
    table_cols,
)

__all__ = [
    "ADDR_COLS",
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "PARKED_MIN_COLS",
    "TIGHT_ADDR_COLS",
    "TIGHT_WIDTH",
    "SurfSwarmLaunches",
]

# Column budgets, in rendered cells, measured against the committed corpus
# ``tests/fixtures/surf/swarm/v2/launches.json`` (30 launches, 2026-09-21).

#: ``#``: ``launch_number`` -- 62 is the highest today; four cells hold 9999.
_NUMBER_COLS = 4
#: ``kind``: ``evm_project`` (11) / ``univ4_hook`` (10), one spare cell.
_KIND_COLS = 12
#: ``status``: ``abandoned`` (9) is the widest of live/abandoned/parked.
_STATUS_COLS = 9
#: ``repo``: ``owner/name`` off ``repo_url``. Corpus names run 50+ cells
#: (``Identity-md/launch-62-build-independently-review-streaming``), so
#: this column always clips with a visible ``…``; 28 keeps the owner and the
#: launch number, which is what identifies the row.
_REPO_COLS = 28
#: The address budget **excluding** the copy icon (``address_text``'s own
#: ``width`` contract): surf's 17-cell anti-poisoning window (``0x`` + 8 hex
#: + ``…`` + 6 hex), the same window JUST SHIPPED rendered at full/compact.
ADDR_COLS = 17
#: The ``tight`` tier's window: ``widgets/address.MIN_SHORT_COLS`` (11, a
#: 4/4 window), the address module's own legibility floor below which
#: ``_window`` clamps back up regardless -- so nothing narrower would render
#: differently. Windowing an address to its narrowest legible form under a
#: tight pin is the repo's established anti-poisoning form (curator's
#: ``short_addr``, JUST SHIPPED's own ``tight`` tier), restated here.
TIGHT_ADDR_COLS = MIN_SHORT_COLS
#: ``+n`` after the first artifact: the corpus tops out at 5 artifacts
#: (`` +4``, 3 cells); one spare cell for a two-digit rest.
_PLUS_COLS = 4
_ARTIFACTS_COLS = ADDR_COLS + ICON_COLS + _PLUS_COLS            # 23
_TIGHT_ARTIFACTS_COLS = TIGHT_ADDR_COLS + ICON_COLS + _PLUS_COLS  # 17
#: ``parked reason``: the elastic column's floor -- the header's own 13 cells
#: (a ``DataTable`` cuts a header like a cell, and at twelve the label read
#: ``parked reaso``), which show the first word or two of a reason
#: (``manifest: to…``); the column grows to every spare cell the panel has
#: above the fixed columns, and a reason it still clips lights the title hint
#: (module docstring).
PARKED_MIN_COLS = len("parked reason")                                    # 13

_SPECS = (
    ("number", "#", _NUMBER_COLS),
    ("kind", "kind", _KIND_COLS),
    ("status", "status", _STATUS_COLS),
    ("chain", "chain", CHAIN_COLS),
    ("repo", "repo", _REPO_COLS),
    ("artifacts", "artifacts", _ARTIFACTS_COLS),
    ("parked", "parked reason", PARKED_MIN_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "kind")
_TIGHT = tuple(key for key in _COMPACT if key != "parked")

#: ``full``: all seven columns with the reason at its floor -- 110 cells.
FULL_WIDTH = table_cols(w for k, _l, w in _SPECS)                      # 110
#: ``compact``: ``kind`` shed (two values, both implied by the artifacts) -- 96.
COMPACT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _COMPACT)  # 96
#: ``tight``: the reason shed too and the address at :data:`TIGHT_ADDR_COLS`
#: -- 75. Never the reverse (reason kept, address narrowed): the reason is
#: free text with a visible clip, the address window is the anti-poisoning
#: form and is spent last.
TIGHT_WIDTH = table_cols(
    (_TIGHT_ARTIFACTS_COLS if k == "artifacts" else w)
    for k, _l, w in _SPECS if k in _TIGHT
)                                                                      # 75

#: Colour looked up on the **raw** status word; the text beside it is escaped.
_STATUS_COLOURS = {"live": "green", "parked": "yellow", "abandoned": "dim"}

#: The one host whose prefix is dropped to ``owner/name`` -- exactly this
#: string, so ``https://github.com.evil.example/…`` keeps its full form.
_GITHUB = "https://github.com/"


def _repo_label(url) -> str:
    if not isinstance(url, str) or not url:
        return DASH
    shown = url[len(_GITHUB):] if url.startswith(_GITHUB) else url
    return sanitize_cell(shown, _REPO_COLS) or DASH


def _artifacts_cell(item: dict, addr_cols: int) -> Text | str:
    """First artifact's address with its icon and link, then ``+n`` (module docstring)."""
    artifacts = item.get("artifacts")
    if not isinstance(artifacts, list) or not artifacts:
        return DASH
    first = artifacts[0]
    explorer = for_chain_id(item.get("chain_id"))
    if isinstance(first, dict) and is_address(first.get("address")):
        cell = address_text(first["address"], width=addr_cols, explorer=explorer)
    elif isinstance(first, dict):
        name = strip_tags(first.get("name")) or DASH
        cell = Text(rowfit.clip(name, addr_cols + ICON_COLS))
    else:
        cell = Text(DASH)
    count = item.get("artifact_count")
    total = count if isinstance(count, int) and not isinstance(count, bool) else len(artifacts)
    if total > 1:
        cell.append(rowfit.clip(f" +{total - 1}", _PLUS_COLS), style="dim")
    return cell


class SurfSwarmLaunches(SwarmTableBase):
    """LAUNCHES -- ``# · kind · status · chain · repo · artifacts · parked reason``."""

    TITLE = "LAUNCHES"
    TABLE_ID = "surf-swarm-launches-table"
    #: Newest twelve; the producer orders them newest first.
    ROW_CAP = 12
    CURSOR_TYPE = "row"

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH)
    )

    LOADING_ROW = (LOADING, "", "", "", "", "", "")
    EMPTY_ROW = ("--", "No data", "", "", "", "", "")

    def update_data(
        self,
        swarm_launch_rows=None,
        swarm_launch_summary=None,
        swarm_scores_as_of_hhmm=None,
        swarm_network=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict. ``swarm_network`` is accepted
        and never painted: the chain word is per row (module docstring)."""
        self.store(swarm_launch_rows, swarm_scores_as_of_hhmm, swarm_launch_summary)

    def column_plan(self, tier: str, budget: int) -> tuple[tuple[str, str, int], ...]:
        """The reason column takes every spare cell; the address narrows at ``tight``."""
        plan = []
        keep = self.TIER_COLUMNS[tier]
        fixed = [w for k, _l, w in _SPECS if k in keep and k != "parked"]
        if tier == "tight":
            fixed = [_TIGHT_ARTIFACTS_COLS if w == _ARTIFACTS_COLS else w for w in fixed]
        spare = budget - table_cols(fixed) - CELL_PADDING
        for key, label, width in _SPECS:
            if key not in keep:
                continue
            if key == "artifacts" and tier == "tight":
                width = _TIGHT_ARTIFACTS_COLS
            elif key == "parked":
                width = max(PARKED_MIN_COLS, spare)
            plan.append((key, label, width))
        return tuple(plan)

    def _parked_cols(self) -> int:
        return next((w for k, _l, w in (self._installed or ()) if k == "parked"), PARKED_MIN_COLS)

    def build_cells(self, item: dict) -> dict[str, str | Text]:
        raw_status = item.get("status")
        status = sanitize_cell(raw_status, _STATUS_COLS) or DASH
        colour = _STATUS_COLOURS.get(raw_status) if isinstance(raw_status, str) else None
        if colour:
            status = f"[{colour}]{status}[/]"

        addr_cols = TIGHT_ADDR_COLS if self._tier == "tight" else ADDR_COLS

        parked_cols = self._parked_cols()
        reason = strip_tags(item.get("parked_reason"))
        if cell_len(reason) > parked_cols and "parked" in self._keys:
            self._clipped = True
        return {
            "number": fmt_int(item.get("launch_number")),
            "kind": sanitize_cell(item.get("kind"), _KIND_COLS) or DASH,
            "status": status,
            "chain": sanitize_cell(chain_word(item.get("chain_id")), CHAIN_COLS),
            "repo": _repo_label(item.get("repo_url")),
            "artifacts": _artifacts_cell(item, addr_cols),
            "parked": sanitize_cell(reason, parked_cols),
        }

    def build_footer(self, summary) -> tuple[str, ...] | None:
        """``30 launches · 19 live · 10 abandoned · 1 parked`` (by_status, count desc)."""
        if not isinstance(summary, dict):
            return None
        by_status = summary.get("by_status")
        counted = [
            entry for entry in (by_status if isinstance(by_status, list) else ())
            if isinstance(entry, dict) and fmt_int(entry.get("count")) != DASH
        ]
        counted.sort(key=lambda entry: -int(entry.get("count")))
        total = sum(int(entry.get("count")) for entry in counted)
        parts = [f"{fmt_int(total)} launches"]
        parts.extend(
            f"{fmt_int(entry.get('count'))} {strip_tags(entry.get('status')) or DASH}"
            for entry in counted
        )
        return tuple(parts)

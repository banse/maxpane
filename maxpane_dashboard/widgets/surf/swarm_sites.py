"""SITES: the swarm's ``/sites`` -- ENS-named, IPFS-pinned deliveries (swarm v2, WP6).

Mounted full-width at the foot of the ``s`` body since WP7
(``minimal.tcss``); a new file that imported nothing from the old
``swarm_shipped.py`` WP7 deleted.

Columns ``label · ens · size · cid · tx`` on
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase`
(the tier machinery the three WP6 tables share; see that module).

The tx links on mainnet, and why that is a measurement
-------------------------------------------------------
A site row carries **no chain field** (``SURF_ROW_KEYS["swarm_site_rows"]``).
The panel binds the package's one explorer declaration, ``_fmt.EXPLORER``
(Etherscan, mainnet), on three facts read off the corpus
``tests/fixtures/surf/swarm/v2/sites.json`` on 2026-09-21: the six rows'
``blockNumber`` values run 25,986,557–26,021,387, which is Ethereum
**mainnet**'s height in 2026-09 (Sepolia is at ~12 M); every ``ensName`` is
``*.site.identitymd.eth``, a name under a mainnet ENS registration; and the
naming transaction is the ENS write, which lives where the name does. If a
site row ever grows a chain id, that is a contract change to file as a
defect and resolve through ``explorer.for_chain_id`` -- never a guess here.

What the panel does not claim
------------------------------
Reachability. PRD §3: SITES shows what was pinned and named -- the label,
the ENS name, the pinned size, the CID window and the naming tx -- and never
whether the site answers. No ``up``/``down`` word appears in it, and a test
asserts none does.

Cells
-----
``label`` is coloured on the raw ``status`` word (``named``/``published``/
``live`` green, ``superseded`` dim, ``failed`` red, anything else plain) and a
``superseded_by`` row appends `` → <label>`` to it. ``failure`` (escaped)
replaces the ``ens`` cell when the row has no ENS name and a failure. ``size``
is ``bytes`` compacted (``2.4M``, ``17.2K``; whole under 1,000 -- bytes are
integers, and ``fmt_compact``'s ``584.0`` would say otherwise). ``cid`` is a
head…tail window built here (:func:`_window_cid`) because a CID is base32,
not hex, and outside ``widgets/address``'s domain. ``tx`` is ``hash_text``
(no icon: a hash is outside the copy rule).

Purity: stdlib, ``rich``, ``textual`` and this package's ``widgets/`` modules.
No ``data/``, no ``analytics/``, no clock, no I/O.
"""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import hash_text
from maxpane_dashboard.widgets.fmt import as_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import safe_markup, sanitize_cell, strip_tags
from maxpane_dashboard.widgets.panels import LOADING
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.surf._fmt import DASH, EXPLORER
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase, table_cols

__all__ = [
    "CID_COLS",
    "COMPACT_WIDTH",
    "FULL_WIDTH",
    "TIGHT_WIDTH",
    "TX_COLS",
    "SurfSwarmSites",
]

# Column budgets, in rendered cells, measured against the committed corpus
# ``tests/fixtures/surf/swarm/v2/sites.json`` (6 sites, 2026-09-21).

#: A site label: 13 is the widest captured (``site-7018907b``).
_LABEL_COLS = 13
#: The label cell: a superseded row is ``<label> → <label>``, two labels and
#: a three-cell arrow. The corpus holds no superseded row (6/6 ``named``), so
#: the second half is the first half's own measurement reused, not a guess at
#: a different vocabulary; a longer pair clips with a visible ``…``.
_LABEL_CELL_COLS = _LABEL_COLS + 3 + _LABEL_COLS                       # 29
#: The ENS suffix every captured name carries.
_ENS_SUFFIX = ".site.identitymd.eth"
#: ``ens``: ``<label>.site.identitymd.eth`` -- 33 at the widest captured
#: label (``site-7018907b.site.identitymd.eth``). The brief budgeted 28 off a
#: ``roll``-shaped name; the corpus's own widest row would have clipped at
#: 28, so the column is sized to the state the data is normally in.
_ENS_COLS = _LABEL_COLS + len(_ENS_SUFFIX)                              # 33
#: ``size``: ``999.9K`` is the widest compact form under a megabyte; the
#: corpus runs 584 B – 2.5 MB.
_SIZE_COLS = 6
#: ``cid``: a 59-character ``bafy…`` CID windowed head…tail; 16 keeps eight
#: cells of head (the multibase prefix and codec) and seven of tail.
CID_COLS = 16
#: ``tx``: surf's 17-cell hash window (``0x`` + 8 + ``…`` + 6).
TX_COLS = 17

_SPECS = (
    ("label", "label", _LABEL_CELL_COLS),
    ("ens", "ens", _ENS_COLS),
    ("size", "size", _SIZE_COLS),
    ("cid", "cid", CID_COLS),
    ("tx", "tx", TX_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "size")
_TIGHT = tuple(key for key in _COMPACT if key != "cid")

#: ``full``: all five columns -- 111 cells.
FULL_WIDTH = table_cols(w for k, _l, w in _SPECS)                      # 111
#: ``compact``: ``size`` shed (the cheapest column; the CID still identifies
#: the pin) -- 103.
COMPACT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _COMPACT)  # 103
#: ``tight``: ``cid`` shed too; the ENS name and the tx stay -- 85.
TIGHT_WIDTH = table_cols(w for k, _l, w in _SPECS if k in _TIGHT)      # 85

#: Colour looked up on the **raw** status word; ``named`` is the corpus's
#: own live state (6/6 rows) and is green beside the brief's ``published``/
#: ``live``; anything unknown renders plain.
_STATUS_COLOURS = {
    "named": "green", "published": "green", "live": "green",
    "superseded": "dim", "failed": "red",
}


def _window_cid(value, width: int) -> str:
    """A CID windowed ``head…tail`` to *width* cells; ``--`` for nothing.

    Not hex, so not ``widgets/address``'s job; measured on ``cell_len`` like
    ``rowfit.clip`` (a CID is third-party text). Bracket runs are stripped
    first; the caller escapes the result.
    """
    text = strip_tags(value)
    if not text:
        return DASH
    if cell_len(text) <= width:
        return text
    if width <= 1:
        return "…"
    budget = width - 1
    tail_cols = budget // 2
    head = rowfit.clip(text, budget - tail_cols + 1)  # clip supplies the ``…``
    tail: list[str] = []
    used = 0
    for char in reversed(text):
        size = cell_len(char)
        if used + size > tail_cols:
            break
        tail.append(char)
        used += size
    return head + "".join(reversed(tail))


def _fmt_bytes(value) -> str:
    size = as_float(value)
    if size is None:
        return DASH
    if size < 1_000:
        return fmt_int(size)
    return fmt_compact(size)


class SurfSwarmSites(SwarmTableBase):
    """SITES -- ``label · ens · size · cid · tx``."""

    TITLE = "SITES"
    TABLE_ID = "surf-swarm-sites-table"
    #: Six sites today; ten is the panel's height budget, not the corpus.
    ROW_CAP = 10
    CURSOR_TYPE = "row"

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH)
    )

    LOADING_ROW = (LOADING, "", "", "", "")
    EMPTY_ROW = ("No data", "", "", "", "")

    def update_data(
        self,
        swarm_site_rows=None,
        swarm_scores_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``SWARM_WIDGET_SIGNATURES``)."""
        self.store(swarm_site_rows, swarm_scores_as_of_hhmm)

    def build_cells(self, item: dict) -> dict[str, str | Text]:
        raw_status = item.get("status")
        label = strip_tags(item.get("label")) or DASH
        successor = strip_tags(item.get("superseded_by"))
        if successor:
            label = f"{label} → {successor}"
        label_cell = sanitize_cell(label, _LABEL_CELL_COLS)
        colour = _STATUS_COLOURS.get(raw_status) if isinstance(raw_status, str) else None
        if colour:
            label_cell = f"[{colour}]{label_cell}[/]"

        ens = sanitize_cell(item.get("ens_name"), _ENS_COLS)
        failure = sanitize_cell(item.get("failure"), _ENS_COLS)
        ens_cell = f"[red]{failure}[/]" if not ens and failure else (ens or DASH)

        return {
            "label": label_cell,
            "ens": ens_cell,
            "size": _fmt_bytes(item.get("bytes")),
            "cid": safe_markup(_window_cid(item.get("cid"), CID_COLS)),
            # Mainnet, by measurement (module docstring); no chain field exists.
            "tx": hash_text(item.get("tx_hash"), TX_COLS, explorer=EXPLORER),
        }

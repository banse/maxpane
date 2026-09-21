"""FEEDBACK -- the selected seat's on-chain ERC-8004 feedback (swarm v2 plan A1, WP6a).

Unwired until WP7 exports the class and mounts it on the AGENT body; this
module only paints the frozen ``swarm_seat_feedback_rows`` shape
(``data/surf_models.SURF_ROW_KEYS``): ``value, node_key, job_id, tx_hash,
chain_id, block_number, sent_ts``. The tiered-table mechanics are
:class:`~maxpane_dashboard.widgets.surf.swarm_roster.SeatTableBase`'s.

Each row links its **own** chain. A review carries a ``chainId`` (the
corpus has 35 on mainnet, one on Sepolia and one ``null``), so the ``tx``
cell is ``widgets.address.hash_text(tx_hash, width,
explorer=for_chain_id(chain_id))``: a mainnet row links Etherscan, a Sepolia
row links Sepolia Etherscan, and ``None`` -- or any id the allowlist does
not name -- links nothing rather than guessing (``rules/widgets.md``). A
hash carries no copy icon (the copy rule is for addresses); the ``chain``
column prints ``_swarm_chain.chain_word`` for the same id, the em dash for
an unknown one.

``block_number`` is **not a column**: the hash is the receipt, and the
block is a click away on the explorer it links. It stays in the frozen row
for the manager's benefit, not the screen's.

``value`` is the review's number as given -- the corpus has ``1`` and
``100`` -- rendered whole when integral and to one decimal otherwise.
``None`` vs ``[]``: a seat with no feedback yet is a real empty
(``no feedback yet``); a sweep that could not run is ``unavailable``.
Every third-party string (node key, job id) goes through
``markup_safety.sanitize_cell``.
"""

from __future__ import annotations

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import MIN_SHORT_COLS, hash_text
from maxpane_dashboard.widgets.explorer import for_chain_id
from maxpane_dashboard.widgets.fmt import as_float, fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, sanitize_cell
from maxpane_dashboard.widgets.surf._fmt import DASH, hhmm
from maxpane_dashboard.widgets.surf._swarm_chain import CHAIN_COLS, chain_word
from maxpane_dashboard.widgets.surf.swarm_roster import SeatTableBase, table_cols
from maxpane_dashboard.widgets.surf.swarm_seat_record import JOB_COLS, NODE_COLS

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "TIGHT_WIDTH",
    "TX_COLS",
    "SurfSwarmSeatFeedback",
]

EMPTY_LINE = "no feedback yet"

#: ``HH:MM`` of ``sent_ts`` (the review's ``sentAt``).
_WHEN_COLS = 5

#: The review value: ``1`` and ``100`` in the corpus; ``100.0`` (5) is the
#: widest one-decimal form a three-digit value takes.
_VALUE_COLS = 6

#: The tx hash window at ``full`` / ``compact``: the same 17 cells surf's
#: other swarm and pool4 panels give a hash (``swarm_shipped.ADDR_COLS``),
#: ``0x`` + 8 hex + ``…`` + 6 hex through ``short_hex``.
TX_COLS = 17

#: At ``tight`` the hash narrows to ``widgets.address.MIN_SHORT_COLS``, the
#: floor under which the window is no longer one.
_TIGHT_TX_COLS = MIN_SHORT_COLS

_SPECS = (
    ("when", "when", _WHEN_COLS),
    ("value", "value", _VALUE_COLS),
    ("node", "node", NODE_COLS),
    ("job", "job", JOB_COLS),
    ("chain", "chain", CHAIN_COLS),
    ("tx", "tx", TX_COLS),
)
_SHED = {
    "compact": frozenset({"job"}),
    "tight": frozenset({"job", "node"}),
}


def _tier_width(shed: frozenset[str], tx_cols: int = TX_COLS) -> int:
    widths = [tx_cols if k == "tx" else w for k, _l, w in _SPECS if k not in shed]
    return table_cols(widths)


#: Every column: 65 cells plus six columns' padding = 77.
FULL_WIDTH = _tier_width(frozenset())
#: Without ``job`` (8 + 2) = 67.
COMPACT_WIDTH = _tier_width(_SHED["compact"])
#: Without ``node`` (22 + 2) too, and the hash at 11 (-6) = 37.
TIGHT_WIDTH = _tier_width(_SHED["tight"], _TIGHT_TX_COLS)


def _value_cell(value: object) -> str:
    v = as_float(value)
    if v is None:
        return DASH
    if v == int(v):
        return fmt_int(int(v))
    return fmt_float(v, ".1f")


class SurfSwarmSeatFeedback(SeatTableBase):
    """FEEDBACK -- one row per on-chain review entry for the selected seat."""

    TITLE = "FEEDBACK"
    TABLE_ID = "surf-swarm-seat-feedback-table"
    CURSOR_TYPE = "none"
    ROW_CAP = 12

    COLUMN_SPECS = _SPECS
    SHED = _SHED
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH),
    )
    EMPTY_LINE = EMPTY_LINE

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_feedback_rows=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``**_kwargs``: the screen splats it)."""
        self._as_of = swarm_seat_as_of_hhmm
        self.render_table(swarm_seat_feedback_rows)

    # -- geometry -----------------------------------------------------------

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        if key == "tx" and tier == "tight":
            return _TIGHT_TX_COLS
        return width

    # -- the cells ----------------------------------------------------------

    def build_cells(self, index: int, item) -> dict[str, object] | None:
        if not isinstance(item, dict):
            return None
        chain_id = item.get("chain_id")
        job_id = item.get("job_id")
        job = job_id[:JOB_COLS] if isinstance(job_id, str) and job_id else DASH
        node = flatten(item.get("node_key")) or DASH
        tx_cols = _TIGHT_TX_COLS if self._tier == "tight" else TX_COLS
        return {
            "when": hhmm(item.get("sent_ts")),
            "value": _value_cell(item.get("value")),
            "node": sanitize_cell(node, NODE_COLS),
            "job": sanitize_cell(job, JOB_COLS),
            "chain": chain_word(chain_id),
            # A ``Text`` cell, never markup: the link lives in a ``Style``.
            "tx": hash_text(item.get("tx_hash"), tx_cols, explorer=for_chain_id(chain_id)),
        }

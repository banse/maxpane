"""FEEDBACK -- the selected seat's scored reviews, lifetime, newest first (plan WP4).

Mounted on the AGENT body (``a``); this module paints the
``swarm_seat_feedback_rows`` shape
(``data/surf_models.SURF_ROW_KEYS["swarm_seat_feedback_rows"]``):
``value, verdict, status, node_key, role, job_id, tx_hash, chain_id,
sent_ts`` -- one row per ``/seats/{tokenId}`` ``reviews[]`` entry
(``docs/surf_agent_seats_spec.md`` §3). A row is read key by key, so a
row missing a key (a hand-edited cache) renders ``--`` in that cell and
never raises. The tiered-table mechanics are
:class:`~maxpane_dashboard.widgets.surf._swarm_table.SwarmTableBase`'s.

A review is ``sent`` (tx + ``sentAt``), ``submitted`` (tx, no ``sentAt``) or
``queued`` (neither). ``when`` is ``HH:MM`` of ``sent_ts``; a review with no
``sent_ts`` shows its status word there instead, dim. ``status`` is its own
column.

Each row links its **own** chain: the ``tx`` cell is
``widgets.address.hash_text(tx_hash, width, explorer=for_chain_id(chain_id))``
-- a mainnet row links Etherscan, a Sepolia row Sepolia Etherscan, and
``None`` or any id the allowlist does not name links nothing rather than
guessing (``rules/widgets.md``). A hash carries no copy icon (the copy rule
is for addresses); ``chain`` prints ``_swarm_chain.chain_word`` for the same
id, the em dash for an unknown one. A **queued** row has no tx cell at all
and no link -- even if a hand-edited cache gave it a hash: a queued review
has not been sent, so a hash on it is not a receipt.

The seat state is read before any row, exactly as RECORD does
(:func:`~maxpane_dashboard.widgets.surf.swarm_seat_record.seat_footer`):
``Loading...`` / ``never paired`` / ``unavailable``; only ``"ok"`` paints
rows, ``[]`` is :data:`EMPTY_LINE`. Past :attr:`SurfSwarmSeatFeedback.ROW_CAP`
the footer names the rows not shown: ``+N older`` (plan §9 G).

``value`` is the review's number as given -- ``1`` on every captured review
-- rendered whole when integral and to one decimal otherwise. Every
third-party string (node key, job id, status word) goes through
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
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase, table_cols
from maxpane_dashboard.widgets.surf.swarm_seat_record import JOB_COLS, NODE_COLS, seat_footer

__all__ = [
    "COMPACT_WIDTH",
    "EMPTY_LINE",
    "FULL_WIDTH",
    "TIGHT_WIDTH",
    "TX_COLS",
    "SurfSwarmSeatFeedback",
]

EMPTY_LINE = "no feedback yet"

#: The status that has no transaction yet: no tx cell, no link.
_QUEUED = "queued"

#: ``when``: ``HH:MM`` of ``sent_ts`` (5), or the status word when there is
#: none -- ``submitted`` (9) is the longest of the three served.
_WHEN_COLS = 9

#: The review value: ``1`` on every captured review; ``100.0`` (5) is the
#: widest one-decimal form a three-digit value takes.
_VALUE_COLS = 6

#: ``status``: ``sent`` / ``submitted`` / ``queued``; ``submitted`` is 9. An
#: unseen word clips with ``…``.
_STATUS_COLS = 9

#: The tx hash window at ``full`` / ``compact``: the same 17 cells surf's
#: other swarm and pool4 panels give a hash (``swarm_launches.ADDR_COLS``),
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
    ("status", "status", _STATUS_COLS),
    ("chain", "chain", CHAIN_COLS),
    ("tx", "tx", TX_COLS),
)
_ALL = tuple(key for key, _l, _w in _SPECS)
_COMPACT = tuple(key for key in _ALL if key != "job")
_TIGHT = tuple(key for key in _COMPACT if key != "node")


def _tier_width(keep, tx_cols: int = TX_COLS) -> int:
    widths = [tx_cols if k == "tx" else w for k, _l, w in _SPECS if k in keep]
    return table_cols(widths)


#: PROVISIONAL tiers (plan WP4), each a :func:`table_cols` sum -- WP6
#: measures them in situ. Every column: 78 cells plus seven columns'
#: padding = 92.
FULL_WIDTH = _tier_width(_ALL)
#: Without ``job`` (8 + 2) = 82.
COMPACT_WIDTH = _tier_width(_COMPACT)
#: Without ``node`` (22 + 2) too, and the hash at 11 (-6) = 52.
TIGHT_WIDTH = _tier_width(_TIGHT, _TIGHT_TX_COLS)


def _value_cell(value: object) -> str:
    v = as_float(value)
    if v is None:
        return DASH
    if v == int(v):
        return fmt_int(int(v))
    return fmt_float(v, ".1f")


class SurfSwarmSeatFeedback(SwarmTableBase):
    """FEEDBACK -- one row per scored review of the selected seat, lifetime."""

    TITLE = "FEEDBACK"
    TABLE_ID = "surf-swarm-seat-feedback-table"
    CURSOR_TYPE = "none"
    #: Kept at 12 for lifetime rows (plan §9 G); the footer counts the rest.
    ROW_CAP = 12

    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(
        ("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH),
    )
    EMPTY_LINE = EMPTY_LINE

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._state: object = None

    # -- the contract -------------------------------------------------------

    def update_data(
        self,
        swarm_seat_feedback_rows=None,
        swarm_seat_state=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Refresh from the manager's flat dict (``**_kwargs``: the screen splats it)."""
        self._state = swarm_seat_state
        rows = swarm_seat_feedback_rows if swarm_seat_state == "ok" else None
        self.store(rows, swarm_seat_as_of_hhmm)

    def _repaint(self) -> None:
        super()._repaint()
        footer = seat_footer(self._state, (self._payload or {}).get("rows"), self.ROW_CAP)
        if footer is not None:
            words, style = footer
            self._write_footer((words,), style=style)

    # -- geometry -----------------------------------------------------------

    def column_width(self, key: str, tier: str, budget: int, width: int) -> int:
        if key == "tx" and tier == "tight":
            return _TIGHT_TX_COLS
        return width

    # -- the cells ----------------------------------------------------------

    def build_cells(self, item: dict) -> dict[str, object] | None:
        chain_id = item.get("chain_id")
        job_id = item.get("job_id")
        job = job_id[:JOB_COLS] if isinstance(job_id, str) and job_id else DASH
        node = flatten(item.get("node_key")) or DASH
        status = flatten(item.get("status"))
        return {
            "when": self._when_cell(item.get("sent_ts"), status),
            "value": _value_cell(item.get("value")),
            "node": sanitize_cell(node, NODE_COLS),
            "job": sanitize_cell(job, JOB_COLS),
            "status": sanitize_cell(status or DASH, _STATUS_COLS),
            "chain": chain_word(chain_id),
            "tx": self._tx_cell(item.get("tx_hash"), chain_id, status),
        }

    @staticmethod
    def _when_cell(sent_ts: object, status: str) -> str:
        """``HH:MM`` of the send; the status word, dim, for a review not sent yet."""
        if sent_ts is not None:
            return hhmm(sent_ts)
        if status:
            return f"[dim]{sanitize_cell(status, _WHEN_COLS)}[/]"
        return DASH

    def _tx_cell(self, tx_hash: object, chain_id: object, status: str):
        # A queued review has no transaction: no cell, no link -- whatever the row says.
        if tx_hash is None or status == _QUEUED:
            return ""
        tx_cols = _TIGHT_TX_COLS if self._tier == "tight" else TX_COLS
        # A ``Text`` cell, never markup: the link lives in a ``Style``.
        return hash_text(tx_hash, tx_cols, explorer=for_chain_id(chain_id))

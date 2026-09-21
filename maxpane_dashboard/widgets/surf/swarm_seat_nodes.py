"""BY NODE: wins / reviewed for each node, not the lifetime attempts denominator.

Every folded node remains in the scrollable table. TEAMMATES is an independent
fitted line, so it never replaces the read-state footer. Third-party strings
use the package's established strip-then-escape sanitizer.
"""
from __future__ import annotations

from rich.text import Text
from textual.widgets import Static
from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import sanitize_cell
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token
from maxpane_dashboard.widgets.surf._swarm_table import SwarmTableBase, table_cols
from maxpane_dashboard.widgets.surf.swarm_seat_record import seat_footer

_SPECS = (("node", "node", 22), ("roles", "roles", 9),
          ("reviewed", "reviewed", 8), ("won", "won", 6),
          ("win", "win", 6), ("chain", "chain", 6))
_ALL = tuple(k for k, _, _ in _SPECS)
_COMPACT = tuple(k for k in _ALL if k != "roles")
_TIGHT = ("node", "reviewed", "won", "win")
FULL_WIDTH = table_cols([w for _, _, w in _SPECS])
COMPACT_WIDTH = table_cols([w for k, _, w in _SPECS if k in _COMPACT])
TIGHT_WIDTH = table_cols([w for k, _, w in _SPECS if k in _TIGHT])

class SurfSwarmSeatNodes(SwarmTableBase):
    TITLE = "BY NODE"
    TABLE_ID = "surf-swarm-seat-nodes-table"
    CURSOR_TYPE = "none"
    ROW_CAP = None
    COLUMN_SPECS = _SPECS
    TIER_COLUMNS = {"full": _ALL, "compact": _COMPACT, "tight": _TIGHT}
    LADDER = rowfit.Ladder(("full", FULL_WIDTH), ("compact", COMPACT_WIDTH), ("tight", TIGHT_WIDTH))
    EMPTY_LINE = "no nodes yet"
    DEFAULT_CSS = """
    SurfSwarmSeatNodes > .swarm-teammates {
        height: 1;
        padding: 0 1;
        text-wrap: nowrap;
    }
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._state = None
        self._teammates = None

    def compose_body(self):
        yield from super().compose_body()
        yield Static("", classes="swarm-teammates")

    def update_data(self, swarm_seat_node_rows=None, swarm_seat_teammates=None,
                    swarm_seat_state=None, swarm_seat_as_of_hhmm=None, **_kwargs):
        self._state = swarm_seat_state
        self._teammates = swarm_seat_teammates if self._state == "ok" else None
        self.store(swarm_seat_node_rows if self._state == "ok" else None, swarm_seat_as_of_hhmm)

    def _repaint(self):
        super()._repaint()
        footer = seat_footer(self._state, (self._payload or {}).get("rows"), None)
        if footer is not None:
            self._write_footer((footer[0],), style=footer[1])
        self.write(".swarm-teammates", Text(self._teammates_line()))

    def _teammates_line(self):
        head = "TEAMMATES  "
        room = max(self.size.width - 2 - rowfit.cell_len(head), 0)
        if not isinstance(self._teammates, list):
            return rowfit.clip(head + "unavailable", self.size.width - 2)
        if not self._teammates:
            return rowfit.clip(head + "none yet", self.size.width - 2)
        parts = [f"#{r['token_id']} ×{r['shared_jobs']}" for r in self._teammates
                 if isinstance(r, dict) and seat_token(r.get("token_id")) is not None
                 and seat_token(r.get("shared_jobs")) is not None]
        for keep in range(len(parts), -1, -1):
            shown = parts[:keep]
            if keep < len(parts):
                shown = shown + [f"+{len(parts)-keep}"]
            line = " · ".join(shown)
            if rowfit.cell_len(line) <= room:
                return head + line
        return rowfit.clip(head + f"+{len(parts)}", self.size.width - 2)

    def build_cells(self, item):
        reviewed, won = item.get("reviewed"), item.get("won")
        roles = " · ".join(item.get("roles") or [])
        return {"node": sanitize_cell(item.get("node_key"), 22),
                "roles": sanitize_cell(roles, 9),
                "reviewed": fmt_int(reviewed), "won": fmt_int(won),
                "win": f"{won/reviewed*100:.1f}%" if reviewed else "—",
                "chain": fmt_int(item.get("onchain"))}

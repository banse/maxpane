"""AGENT card row three: ROLES, the node cards and TEAMMATES.

Replaced the BY NODE table on 2026-09-22 (owner). Nodes keep the fold's order
(reviewed desc); when more exist than :data:`NODE_CARDS`, the last card sums
the rest as ``+N more nodes``. The node rate is accepted / reviewed, never the
lifetime attempts denominator, because per-node attempts are not served.
Teammate tokens are integers with no address icon, so this module renders no
address (``swarm_agent_cards`` holds the row base and the seat row, whose
OWNER card does).
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE
from maxpane_dashboard.widgets.surf._fmt import EMDASH, fmt_win_rate
from maxpane_dashboard.widgets.surf._swarm_seat import seat_token
from maxpane_dashboard.widgets.surf.swarm_agent_cards import (
    SurfSwarmAgentCards,
    count,
    dim_dash,
    gate,
)

__all__ = ["NODE_BOX_IDS", "NODE_CARDS", "SurfSwarmNodeCards"]

#: How many node cards row three holds before the last one sums the rest.
NODE_CARDS = 4

NODE_BOX_IDS = {
    "roles": "surf-swarm-card-roles",
    **{f"node{i}": f"surf-swarm-card-node{i}" for i in range(NODE_CARDS)},
    "teammates": "surf-swarm-card-teammates",
}


class SurfSwarmNodeCards(SurfSwarmAgentCards):
    """Row three: ROLES, the node cards, TEAMMATES."""

    IDS = NODE_BOX_IDS
    BOXES = (
        (NODE_BOX_IDS["roles"], "ROLES"),
        *((NODE_BOX_IDS[f"node{i}"], "NODE") for i in range(NODE_CARDS)),
        (NODE_BOX_IDS["teammates"], "TEAMMATES"),
    )

    def update_data(self, swarm_seat_summary=None, swarm_seat_node_rows=None,
                    swarm_seat_teammates=None, swarm_seat_state=None, **_kwargs) -> None:
        super().update_data(
            swarm_seat_summary=swarm_seat_summary, swarm_seat_node_rows=swarm_seat_node_rows,
            swarm_seat_teammates=swarm_seat_teammates, swarm_seat_state=swarm_seat_state,
        )

    def _paint(self, swarm_seat_summary=None, swarm_seat_node_rows=None,
               swarm_seat_teammates=None, swarm_seat_state=None) -> None:
        state = swarm_seat_state
        blocked = gate(state, first=True)
        summary = swarm_seat_summary if isinstance(swarm_seat_summary, dict) else None
        self.render_box(f"#{NODE_BOX_IDS['roles']}", "ROLES",
                        lambda: blocked if blocked is not None else self._roles_body(summary))
        rows = swarm_seat_node_rows if isinstance(swarm_seat_node_rows, list) else None
        rows = None if rows is None else [r for r in rows if isinstance(r, dict)]
        for i in range(NODE_CARDS):
            key = f"node{i}"
            label, build = self._node_card(i, rows, blocked, state)
            self.render_box(f"#{NODE_BOX_IDS[key]}", label, build)
        mates = swarm_seat_teammates if state == "ok" else None
        self.render_box(f"#{NODE_BOX_IDS['teammates']}", "TEAMMATES",
                        lambda: gate(state, first=False) if blocked is not None else self._teammates_body(mates))

    # -- ROLES --------------------------------------------------------------

    def _roles_body(self, summary) -> str | Text:
        roles = summary.get("roles") if summary is not None else None
        if not isinstance(roles, list):
            return UNAVAILABLE
        parts = [(r.get("role"), count(r.get("count"))) for r in roles if isinstance(r, dict)]
        if not parts:
            return Text("none", style="dim")
        shown = parts if len(parts) <= 3 else parts[:2]
        body = Text()
        for i, (role, n) in enumerate(shown):
            if i:
                body.append("\n")
            n = n or "--"
            body.append(self._fit("roles", role, reserved=rowfit.cell_len(n) + 1) or "--", style="dim")
            body.append(" ").append(n, style="bold")
        if len(parts) > 3:
            body.append("\n").append(f"+{len(parts) - 2} more", style="dim")
        return body

    # -- NODE cards ---------------------------------------------------------

    def _node_card(self, i: int, rows, blocked, state):
        key = f"node{i}"
        if blocked is not None:
            return "NODE", (lambda: gate(state, first=False) or dim_dash())
        if rows is None:
            return "NODE", (lambda: UNAVAILABLE if i == 0 else dim_dash())
        if not rows:
            return "NODE", (lambda: Text("no nodes yet", style="dim") if i == 0 else dim_dash())
        if i >= len(rows):
            return "NODE", dim_dash
        if i == NODE_CARDS - 1 and len(rows) > NODE_CARDS:
            rest = rows[i:]
            label = f"+{len(rest)} more nodes"
            total = {k: sum(v for r in rest if (v := seat_token(r.get(k))) is not None)
                     for k in ("reviewed", "won", "onchain")}
            return label, (lambda: self._node_body(key, total, roles=None))
        row = rows[i]
        label = safe_markup(self._fit(key, row.get("node_key")) or "--")
        return label, (lambda: self._node_body(key, row, roles=row.get("roles") or []))

    def _node_body(self, key: str, row: dict, roles) -> Text:
        reviewed, won = seat_token(row.get("reviewed")), seat_token(row.get("won"))
        body = Text()
        body.append(fmt_int(won) if won is not None else "--", style="bold green" if won else "bold")
        body.append(" of ", style="dim")
        body.append(fmt_int(reviewed) if reviewed is not None else "--", style="bold")
        body.append("\n")
        rate = fmt_win_rate(won / reviewed) if won is not None and reviewed else EMDASH
        body.append(rate, style="bold")
        if roles:
            names = " · ".join(flatten(r) for r in roles)
            reserved = rowfit.cell_len(rate) + 3
            body.append(" · ", style="dim").append(self._fit(key, names, reserved=reserved), style="dim")
        chain = count(row.get("onchain"))
        body.append("\n").append("chain ", style="dim").append(chain or "--", style="bold")
        return body

    # -- TEAMMATES ----------------------------------------------------------

    @staticmethod
    def _teammates_body(mates) -> str | Text:
        if not isinstance(mates, list):
            return UNAVAILABLE
        parts = [(seat_token(r.get("token_id")), seat_token(r.get("shared_jobs")))
                 for r in mates if isinstance(r, dict)]
        parts = [(t, n) for t, n in parts if t is not None and n is not None]
        if not parts:
            return Text("none yet", style="dim")
        shown = parts if len(parts) <= 3 else parts[:2]
        body = Text()
        for i, (token, jobs) in enumerate(shown):
            if i:
                body.append("\n")
            body.append(f"#{token}", style="bold").append(f" ×{fmt_int(jobs)}", style="dim")
        if len(parts) > 3:
            body.append("\n").append(f"+{len(parts) - 2} more", style="dim")
        return body

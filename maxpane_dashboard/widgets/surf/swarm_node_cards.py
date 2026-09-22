"""AGENT card row three: ROLES, the node cards, OTHERS and BOARD.

Replaced the BY NODE table on 2026-09-22 (owner). Nodes keep the fold's order
(reviewed desc). The first :data:`NODE_CARDS` nodes get a card each, titled
with a known key's short word (:data:`NODE_TITLES`); OTHERS always sums every
node after them (owner, 2026-09-22), and reads ``0 of 0`` when the list was
read and there are none. A node card reads ``accepted of attempts`` -- the
hero's ACCEPTED per node. Under the pre-2026-09-22 ``/seats`` shape per-node
attempts were not served (``attempts`` is ``None``) and the card shows the
accepted count with no rate. The roles after a node's rate are shortened
(:data:`ROLE_SHORT`); ROLES keeps the full names. BOARD comes from
``/contributors`` and never borrows seats data. This module renders no address.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, safe_markup
from maxpane_dashboard.widgets.panels import UNAVAILABLE
from maxpane_dashboard.widgets.surf._fmt import EMDASH, fmt_win_rate
from maxpane_dashboard.widgets.surf._swarm_seat import board_body, contrib_body, seat_token
from maxpane_dashboard.widgets.surf.swarm_agent_cards import (
    SurfSwarmAgentCards,
    count,
    dim_dash,
    gate,
)

__all__ = ["NODE_BOX_IDS", "NODE_CARDS", "NODE_TITLES", "ROLE_SHORT", "SurfSwarmNodeCards"]

#: How many nodes get a card of their own; OTHERS sums the rest.
NODE_CARDS = 3

#: Role names shortened after a node card's rate (owner, 2026-09-22). An
#: unknown role keeps its own fitted text.
ROLE_SHORT = {"implement": "impl", "review": "rev"}

#: Card titles for the node keys the swarm serves (owner, 2026-09-22). An
#: unknown key keeps its own fitted, escaped text as its title.
NODE_TITLES = {
    "oracle_assess": "ORACLE",
    "adversarial_review": "REVIEW",
    "build_contract_project": "BUILD",
}

NODE_BOX_IDS = {
    "roles": "surf-swarm-card-roles",
    **{f"node{i}": f"surf-swarm-card-node{i}" for i in range(NODE_CARDS)},
    "others": "surf-swarm-card-others",
    "board": "surf-swarm-card-board",
}


class SurfSwarmNodeCards(SurfSwarmAgentCards):
    """Row three: ROLES, the node cards, OTHERS, BOARD (BOARD under STATUS)."""

    IDS = NODE_BOX_IDS
    BOXES = (
        (NODE_BOX_IDS["roles"], "ROLES"),
        *((NODE_BOX_IDS[f"node{i}"], "NODE") for i in range(NODE_CARDS)),
        (NODE_BOX_IDS["others"], "OTHERS"),
        (NODE_BOX_IDS["board"], "BOARD"),
    )

    def update_data(self, swarm_seat_summary=None, swarm_seat_node_rows=None,
                    swarm_seat_contrib=None, swarm_seat_state=None, **_kwargs) -> None:
        super().update_data(
            swarm_seat_summary=swarm_seat_summary, swarm_seat_node_rows=swarm_seat_node_rows,
            swarm_seat_contrib=swarm_seat_contrib, swarm_seat_state=swarm_seat_state,
        )

    def _paint(self, swarm_seat_summary=None, swarm_seat_node_rows=None,
               swarm_seat_contrib=None, swarm_seat_state=None) -> None:
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
        self.render_box(f"#{NODE_BOX_IDS['others']}", "OTHERS",
                        lambda: self._others_body(rows, blocked, state))
        contrib = swarm_seat_contrib
        self.render_box(f"#{NODE_BOX_IDS['board']}", "BOARD",
                        lambda: contrib_body(contrib, board_body))

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
        row = rows[i]
        node_key = row.get("node_key")
        title = NODE_TITLES.get(node_key) if isinstance(node_key, str) else None
        label = title or safe_markup(self._fit(key, node_key) or "--")
        return label, (lambda: self._node_body(key, row, roles=row.get("roles") or []))

    def _node_body(self, key: str, row: dict, roles) -> Text:
        attempts, accepted = seat_token(row.get("attempts")), seat_token(row.get("accepted"))
        body = Text()
        body.append(fmt_int(accepted) if accepted is not None else "--",
                    style="bold green" if accepted else "bold")
        if attempts is not None:
            body.append(" of ", style="dim").append(fmt_int(attempts), style="bold")
        else:
            body.append(" accepted", style="dim")
        body.append("\n")
        rate = fmt_win_rate(accepted / attempts) if accepted is not None and attempts else EMDASH
        body.append(rate, style="bold")
        if roles:
            names = " · ".join((ROLE_SHORT.get(r) if isinstance(r, str) else None) or flatten(r)
                              for r in roles)
            reserved = rowfit.cell_len(rate) + 3
            body.append(" · ", style="dim").append(self._fit(key, names, reserved=reserved), style="dim")
        chain = count(row.get("onchain"))
        body.append("\n").append("chain ", style="dim").append(chain or "--", style="bold")
        return body

    # -- OTHERS -------------------------------------------------------------

    def _others_body(self, rows, blocked, state) -> str | Text:
        """Every node after the first :data:`NODE_CARDS`, summed; ``0 of 0`` for none."""
        if blocked is not None:
            return gate(state, first=False) or dim_dash()
        if rows is None:
            return dim_dash()
        rest = rows[NODE_CARDS:]
        total = {k: sum(v for r in rest if (v := seat_token(r.get(k))) is not None)
                 for k in ("accepted", "onchain")}
        attempts = [seat_token(r.get("attempts")) for r in rest]
        total["attempts"] = None if None in attempts else sum(attempts)
        return self._node_body("others", total, roles=None)

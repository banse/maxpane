"""AGENT card row three: ROLES, the node cards, OTHERS and BOARD.

Replaced the BY NODE table on 2026-09-22 (owner). Each known node key has a
card of its own, in :data:`NODE_TITLES` order and titled with its short word
whether or not the seat worked it (owner, 2026-09-22); OTHERS sums every node
the table does not name. A card with nothing to show -- the node is absent,
or it has no attempts and nothing accepted -- reads a dim ``—``, OTHERS too
(owner: "when the node values are 0 always show the -"). A node card reads
``accepted of attempts`` -- the
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
from maxpane_dashboard.widgets.sparkline_common import fmt_compact
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE
from maxpane_dashboard.widgets.surf._fmt import EMDASH, fmt_win_rate
from maxpane_dashboard.widgets.surf._swarm_seat import NODE_TITLES, board_body, contrib_body, seat_token
from maxpane_dashboard.widgets.surf.swarm_agent_cards import (
    SurfSwarmAgentCards,
    count,
    dim_dash,
    gate,
)

__all__ = ["NODE_BOX_IDS", "NODE_CARDS", "NODE_TITLES", "ROLE_SHORT", "SurfSwarmNodeCards"]

#: How many nodes get a card of their own -- one per known key, in
#: :data:`NODE_TITLES` order; OTHERS sums every other key.
NODE_CARDS = len(NODE_TITLES)
_CARD_KEYS = tuple(NODE_TITLES)

#: Role names shortened after a node card's rate (owner, 2026-09-22). An
#: unknown role keeps its own fitted text.
ROLE_SHORT = {"implement": "impl", "review": "rev"}

def _whole(value: int) -> str:
    """A count in whole thousands or millions (``10K``, ``2M``): the node
    cards' last short form, for when ``fmt_compact``'s decimal does not fit."""
    if abs(value) < 1_000:
        return fmt_int(value)
    # A thousands count that rounds to 1000K is carried into ``M`` (F66:
    # 999,600 read ``1000K``).
    if abs(round(value / 1_000)) < 1_000:
        return f"{round(value / 1_000)}K"
    return f"{round(value / 1_000_000)}M"


_NUMS = (fmt_int, fmt_compact, _whole)
_UNITS = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}


def _reading(text: str) -> float:
    """The number a shown count reads as: ``100.0K`` and ``100K`` read alike."""
    text = text.replace(",", "")
    return float(text[:-1]) * _UNITS[text[-1]] if text[-1:] in _UNITS else float(text)


def _forms(values: tuple) -> list:
    """:data:`_NUMS` plus, for a pair, one value a decimal finer than the
    other -- the smaller first (``4.6K of 5K``), then the larger
    (``100K of 100.4K``, where ``100.0K of 100K`` would read alike) -- kept
    only while the readings keep the *values*' strict order: no two
    different counts read alike (F66: 4,600 of 5,400 read ``5K of 5K``) and
    none reads the wrong way round (5,460 of 5,480 as ``5.5K of 5K``)."""
    forms = list(_NUMS)
    if len(set(values)) > 1:
        low = min(values)
        forms.append(lambda v: fmt_compact(v) if v == low else _whole(v))
        forms.append(lambda v: _whole(v) if v == low else fmt_compact(v))
    ordered = sorted(set(values))
    return [num for num in forms
            if all(_reading(num(a)) < _reading(num(b)) for a, b in zip(ordered, ordered[1:]))]

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
            build = self._node_card(i, rows, blocked, state)
            self.render_box(f"#{NODE_BOX_IDS[key]}", NODE_TITLES[_CARD_KEYS[i]], build)
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
            return lambda: gate(state, first=False) or dim_dash()
        if rows is None:
            return lambda: UNAVAILABLE if i == 0 else dim_dash()
        if not rows:
            return lambda: Text("no nodes yet", style="dim") if i == 0 else dim_dash()
        row = next((r for r in rows if r.get("node_key") == _CARD_KEYS[i]), None)
        if row is None or self._empty(row):
            return dim_dash
        return lambda: self._node_body(key, row, roles=row.get("roles") or [])

    @staticmethod
    def _empty(row: dict) -> bool:
        """Every count the card shows is zero or unread: the card has nothing
        to say. A node with reviews but no work still has a ``chain`` count,
        and that is not nothing."""
        return not any(seat_token(row.get(k)) for k in ("accepted", "attempts", "onchain"))

    def _num(self, key: str, line, *values):
        """The first of ``fmt_int``, ``fmt_compact`` (``10.0K``) and
        :func:`_whole` (``10K``) whose *line* fits card *key* -- a shorter
        honest number, never a cut one; the last one stands if none fits.
        A form that reads two different *values* as one number, or the wrong
        way round, is not honest and is skipped (:func:`_forms`)."""
        honest = _forms(values)
        for num in honest:
            if rowfit.cell_len(line(num)) <= self._room(key):
                return num
        return honest[-1]

    def _node_body(self, key: str, row: dict, roles) -> Text:
        attempts, accepted = seat_token(row.get("attempts")), seat_token(row.get("accepted"))
        num = self._num(key, lambda n: (n(accepted) if accepted is not None else "--") + (
            f" of {n(attempts)}" if attempts is not None else " accepted"),
            *(v for v in (accepted, attempts) if v is not None))
        body = Text()
        body.append(num(accepted) if accepted is not None else "--",
                    style="bold green" if accepted else "bold")
        if attempts is not None:
            body.append(" of ", style="dim").append(num(attempts), style="bold")
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
        onchain = seat_token(row.get("onchain"))
        chain = None if onchain is None else self._num(key, lambda n: f"chain {n(onchain)}")(onchain)
        body.append("\n").append("chain ", style="dim").append(chain or "--", style="bold")
        return body

    # -- OTHERS -------------------------------------------------------------

    def _others_body(self, rows, blocked, state) -> str | Text:
        """Every node no card names, summed; a dim ``—`` when that is nothing."""
        if blocked is not None:
            return gate(state, first=False) or dim_dash()
        if rows is None:
            return dim_dash()
        rest = [r for r in rows if r.get("node_key") not in _CARD_KEYS]
        total = {k: sum(v for r in rest if (v := seat_token(r.get(k))) is not None)
                 for k in ("accepted", "onchain")}
        attempts = [seat_token(r.get("attempts")) for r in rest]
        total["attempts"] = None if None in attempts else sum(attempts)
        if self._empty(total):
            return dim_dash()
        return self._node_body("others", total, roles=None)

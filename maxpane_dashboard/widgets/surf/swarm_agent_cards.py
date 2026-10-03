"""AGENT seat cards: OWNER, RUNTIME, MODEL, FEEDBACK, COLLAB and NODES.

Third-party text is flattened and fitted to each card with a visible ellipsis.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.analytics.surf_swarm_signals import runtime_semver, runtime_outdated, daemon_differs

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.surf._fmt import (
    ANTI_POISONING_COLS,
    EMDASH,
    fmt_win_rate,
    EXPLORER,
    mmdd_hhmm,
    short_model,
)
from maxpane_dashboard.widgets.surf._swarm_seat import (
    _UNSIZED,
    MeasuredRow,
    NODE_TITLES,
    _num,
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_WORDS,
    count,
    seat_state_line,
    seat_token,
)

__all__ = [
    "SEAT_BOX_IDS",
    "count",
    "dim_dash",
    "gate",
    "SurfSwarmAgentCard",
    "SurfSwarmAgentCards",
    "SurfSwarmSeatCards",
]


SEAT_BOX_IDS = {
    "owner": "surf-swarm-card-owner",
    "runtime": "surf-swarm-card-runtime",
    "feedback": "surf-swarm-card-feedback",
    "model": "surf-swarm-card-model",
    "collab": "surf-swarm-card-collab",
    "nodes": "surf-swarm-card-nodes",
}


def dim_dash() -> Text:
    return Text(EMDASH, style="dim")


def gate(state, first: bool, room: int = _UNSIZED) -> str | Text | None:
    """What a seats-backed card shows instead of its values; ``None`` for ``"ok"``.

    A never-paired seat is a real negative, said once per row (its first
    card) as row 1's SEAT box says it -- the seat number is already there --
    and the other cards show a dash. Pending, busy and a failed read show on
    every card. COLLAB has 14 cells at the AGENT pin: busy uses two existing
    body lines there so both words remain whole.
    """
    if state == "ok":
        return None
    if state == "unknown_seat":
        return Text(NEVER_PAIRED_WORDS, style=NEVER_PAIRED_STYLE) if first else dim_dash()
    line = seat_state_line(state)
    if state == "busy" and line.cell_len > room:
        return Text(line.plain.replace(" · ", " ·\n"), style=line.style)
    return line


class SurfSwarmAgentCard(HeroBoxBase):
    """One card in the AGENT seat row. No geometry here: the stylesheet names this class."""


class SurfSwarmAgentCards(MeasuredRow, HeroRow):
    """Seat-card row mechanics: keep the payload, repaint on resize (:class:`MeasuredRow`).

    Third-party text is fitted to each card's own content width, so a resize
    has to repaint -- after the refresh, when the cards have their new size.
    """

    BOX_CLASS = SurfSwarmAgentCard

    def _fit(self, key: str, value, reserved: int = 0) -> str:
        """Third-party text flattened and cut to what card *key* has left."""
        return rowfit.clip(flatten(value), max(self._room(key) - reserved, 1))


class SurfSwarmSeatCards(SurfSwarmAgentCards):
    """Row two: OWNER, RUNTIME, MODEL, FEEDBACK, COLLAB, NODES (NODES under STATUS)."""

    IDS = SEAT_BOX_IDS
    BOXES = (
        (SEAT_BOX_IDS["owner"], "OWNER"),
        (SEAT_BOX_IDS["runtime"], "RUNTIME"),
        (SEAT_BOX_IDS["model"], "MODEL"),
        (SEAT_BOX_IDS["feedback"], "FEEDBACK"),
        (SEAT_BOX_IDS["collab"], "COLLAB"),
        (SEAT_BOX_IDS["nodes"], "NODES"),
    )

    def update_data(self, swarm_seat_summary=None, swarm_seat_state=None,
                    swarm_seat_teammates=None, swarm_seat_owner_ens=None, swarm_seat_node_rows=None, swarm_runtime_latest=None,
                    swarm_runtime_as_of_hhmm=None, swarm_fleet_daemon=None, **_kwargs) -> None:
        super().update_data(
            swarm_seat_summary=swarm_seat_summary, swarm_seat_state=swarm_seat_state,
            swarm_seat_teammates=swarm_seat_teammates, swarm_seat_owner_ens=swarm_seat_owner_ens,
            swarm_seat_node_rows=swarm_seat_node_rows,
            swarm_runtime_latest=swarm_runtime_latest, swarm_runtime_as_of_hhmm=swarm_runtime_as_of_hhmm,
            swarm_fleet_daemon=swarm_fleet_daemon,
        )

    def _paint(self, swarm_seat_summary=None, swarm_seat_state=None,
               swarm_seat_teammates=None, swarm_seat_owner_ens=None, swarm_seat_node_rows=None,
               swarm_runtime_latest=None, swarm_runtime_as_of_hhmm=None, swarm_fleet_daemon=None) -> None:
        summary, state = swarm_seat_summary, swarm_seat_state
        if self.is_mounted:
            for key in ("runtime", "model", "nodes"):
                self.query_one(f"#{SEAT_BOX_IDS[key]}").tooltip = None
        ens_name = swarm_seat_owner_ens if isinstance(swarm_seat_owner_ens, str) else None
        for key, label, build in (
            ("owner", "OWNER", lambda s: self._owner_body(s, ens_name)),
            ("runtime", "RUNTIME", lambda s: self._runtime_body(
                s, swarm_runtime_latest, swarm_runtime_as_of_hhmm, swarm_fleet_daemon)),
            ("feedback", "FEEDBACK", self._feedback_body),
            ("model", "MODEL", self._model_body),
            ("collab", "COLLAB", lambda s: self._collab_body(s, swarm_seat_teammates)),
        ):
            self.render_box(f"#{SEAT_BOX_IDS[key]}", label,
                            lambda key=key, build=build: self._seat_body(summary, state, key == "owner", build, self._room(key)))
        self.render_box(f"#{SEAT_BOX_IDS['nodes']}", "NODES",
                        lambda: gate(state, first=False, room=self._room("nodes")) or self._nodes_body(swarm_seat_node_rows))

    # -- gates --------------------------------------------------------------

    @staticmethod
    def _seat_body(summary, state, first, build, room=_UNSIZED) -> str | Text:
        blocked = gate(state, first, room)
        if blocked is not None:
            return blocked
        if not isinstance(summary, dict):
            return UNAVAILABLE
        return build(summary)

    # -- seats bodies -------------------------------------------------------

    def _owner_body(self, summary: dict, ens_name: str | None = None) -> Text:
        owner = summary.get("owner")
        # ``address_text`` flattens the label and keeps the icon on the address.
        body = (address_text(owner, label=ens_name, width=ANTI_POISONING_COLS, explorer=EXPLORER)
                if isinstance(owner, str) else Text("unavailable", style="yellow"))
        body.append("\n")
        paired = summary.get("paired_ts")
        if paired is None:
            return body.append("paired unavailable", style="yellow")
        return body.append("paired ", style="dim").append(mmdd_hhmm(paired), style="bold")

    def _runtime_body(self, summary: dict, latest=None, clocks=None, majority=None) -> Text:
        runtime = summary.get("runtime")
        runtime_id, _, version = runtime.partition(" ") if isinstance(runtime, str) else (None, "", None)
        newest = latest.get(runtime_id) if isinstance(latest, dict) else None
        outdated = runtime_outdated(runtime_id, version, newest)
        different = daemon_differs(summary.get("daemon"), majority)
        tooltip = Text()
        if runtime_id not in ("claude", "codex"):
            tooltip.append("runtime not checked")
        elif not isinstance(latest, dict) or runtime_id not in latest:
            tooltip.append("update check pending")
        elif runtime_semver(runtime_id, newest) is None:
            tooltip.append("update check unavailable")
        else:
            package = "claude-code" if runtime_id == "claude" else "codex"
            stamp = clocks.get(runtime_id) if isinstance(clocks, dict) else None
            tooltip.append(f"latest {package} {newest} (npm, as of {flatten(stamp) or 'unavailable'})")
        if isinstance(majority, (tuple, list)) and len(majority) == 3:
            tooltip.append(f"\nfleet daemon {majority[0]} on {majority[1]}/{majority[2]} reporting workers")
        else:
            tooltip.append("\nno fleet majority")
        self.query_one(f"#{SEAT_BOX_IDS['runtime']}").tooltip = tooltip
        body = Text()
        if runtime is None:
            body.append("unavailable", style="yellow")
        elif outdated is True:
            body.append(self._fit("runtime", runtime, reserved=2) + " ↑", style="yellow")
        else:
            body.append(self._fit("runtime", runtime) or "none", style="bold")
        body.append("\n")
        daemon = summary.get("daemon")
        if daemon is None:
            body.append("daemon unavailable", style="yellow")
        elif different is True:
            body.append(self._fit("runtime", "daemon " + daemon, reserved=2) + " ↑", style="yellow")
        else:
            body.append("daemon ", style="dim")
            body.append(self._fit("runtime", daemon, reserved=7) or "not reported")
        body.append("\n")
        devices = count(summary.get("devices"))
        if devices is None:
            return body.append("devices unavailable", style="yellow")
        return body.append(devices, style="bold").append(
            " device" if summary.get("devices") == 1 else " devices", style="dim")

    @staticmethod
    def _feedback_body(summary: dict) -> Text:
        status = summary.get("review_status")
        status = status if isinstance(status, dict) else {}
        body = Text()
        for i, (key, style) in enumerate((("sent", "bold green"), ("submitted", "bold"),
                                          ("queued", "bold yellow"))):
            if i:
                body.append("\n")
            value = count(status.get(key))
            body.append(value if value is not None else "--", style=style if value else "dim")
            body.append(f" {key}", style="dim")
        return body

    def _model_body(self, summary: dict) -> Text:
        """The seat's advertised ``runtimes[].premiumModel`` pairs (F54).

        One pair a line: the short model bold, its effort dim, fitted to the
        card with a visible ``…``. Three or fewer all show; more show two and
        ``+N more`` (NODES' shape), and the tooltip lists every pair raw.
        ``[]`` is served runtimes advertising no model, a real negative;
        ``None`` is no runtimes list served. RECORD's ``model`` column is
        the model a submission actually used, not this.
        """
        pairs = summary.get("models")
        if not isinstance(pairs, list):
            return Text("unavailable", style="yellow")
        pairs = [pair for pair in pairs if isinstance(pair, dict)]
        if not pairs:
            return Text("not advertised", style="dim")
        shown = pairs if len(pairs) <= 3 else pairs[:2]
        body = Text()
        for i, pair in enumerate(shown):
            if i:
                body.append("\n")
            name, effort = short_model(pair.get("model")) or EMDASH, flatten(pair.get("effort"))
            # The effort keeps up to half the card; the model is cut first.
            name = self._fit("model", name, reserved=min(rowfit.cell_len(effort) + 1, self._room("model") // 2)
                             if effort else 0)
            body.append(name, style="bold")
            if effort:
                body.append(" " + self._fit("model", effort, reserved=rowfit.cell_len(name) + 1), style="dim")
        if len(pairs) > 3:
            body.append("\n").append(f"+{len(pairs) - 2} more", style="dim")
        self.query_one(f"#{SEAT_BOX_IDS['model']}").tooltip = self._model_tooltip(pairs)
        return body

    @staticmethod
    def _model_tooltip(pairs) -> Text:
        """Every advertised pair as served, flattened, one a line: ``claude-fable-5-1 · high``."""
        tooltip = Text()
        for i, pair in enumerate(pairs):
            effort = flatten(pair.get("effort"))
            tooltip.append(("\n" if i else "") + flatten(pair.get("model")) + (f" · {effort}" if effort else ""))
        return tooltip

    @staticmethod
    def _collab_body(summary: dict, mates) -> str | Text:
        seats = count(summary.get("collaborators"))
        if seats is None:
            return UNAVAILABLE
        body = Text().append(seats, style="bold").append(
            " seat" if summary.get("collaborators") == 1 else " seats", style="dim")
        return body.append("\n") + SurfSwarmSeatCards._teammates_body(mates)

    @staticmethod
    def _teammates_body(mates) -> str | Text:
        if not isinstance(mates, list):
            return Text("unavailable", style="yellow")
        parts = [(seat_token(r.get("token_id")), seat_token(r.get("shared_jobs")))
                 for r in mates if isinstance(r, dict)]
        parts = [(t, n) for t, n in parts if t is not None and n is not None]
        if not parts:
            return Text("none yet", style="dim")
        shown = sorted(parts, key=lambda p: (-p[1], p[0]))[:2]
        body = Text()
        for i, (token, jobs) in enumerate(shown):
            if i:
                body.append("\n")
            body.append(f"#{token}", style="bold").append(f" ×{fmt_int(jobs)}", style="dim")
        return body


    def _nodes_body(self, rows) -> str | Text:
        if not isinstance(rows, list):
            return UNAVAILABLE
        parts = [r for r in rows if isinstance(r, dict)
                 and any(seat_token(r.get(k)) for k in ("accepted", "attempts"))]
        order = {key: i for i, key in enumerate(NODE_TITLES)}
        parts.sort(key=lambda r: (-(seat_token(r.get("accepted")) or 0),
                                  -(seat_token(r.get("attempts")) or 0),
                                  order.get(r.get("node_key"), len(order)), flatten(r.get("node_key"))))
        if not parts:
            return Text("no nodes yet", style="dim")
        shown = parts if len(parts) <= 3 else parts[:2]
        body = Text()
        for i, row in enumerate(shown):
            if i:
                body.append("\n")
            key = row.get("node_key")
            known = NODE_TITLES.get(key)
            label = known or flatten(key)
            accepted, attempts = seat_token(row.get("accepted")), seat_token(row.get("attempts"))
            rate = fmt_win_rate(accepted / attempts) if accepted is not None and attempts else EMDASH
            if not known:
                exact_count = fmt_int(accepted) if accepted is not None else "--"
                label = self._fit("nodes", key, reserved=rowfit.cell_len(exact_count + rate) + 2)
            num = _num(self._room("nodes"), lambda n: f"{label} {n(accepted) if accepted is not None else '--'} {rate}",
                       *((accepted,) if accepted is not None else ()))
            count_text = num(accepted) if accepted is not None else "--"
            body.append(label, style="dim").append(" ")
            body.append(count_text, style="bold green" if accepted else "bold")
            body.append(" ").append(rate, style="bold")
        if len(parts) > 3:
            body.append("\n").append(f"+{len(parts) - 2} more", style="dim")
            self.query_one(f"#{SEAT_BOX_IDS['nodes']}").tooltip = self._nodes_tooltip(parts)
        return body

    @staticmethod
    def _nodes_tooltip(parts) -> Text:
        """Every node the card's ``+N more`` folds away, exact counts, card order."""
        tooltip = Text()
        for i, row in enumerate(parts):
            key = row.get("node_key")
            accepted, attempts = seat_token(row.get("accepted")), seat_token(row.get("attempts"))
            rate = fmt_win_rate(accepted / attempts) if accepted is not None and attempts else EMDASH
            count = fmt_int(accepted) if accepted is not None else "--"
            if attempts is not None:
                count += f" of {fmt_int(attempts)}"
            tooltip.append(("\n" if i else "") + f"{NODE_TITLES.get(key) or flatten(key)} {count} · {rate}")
        return tooltip

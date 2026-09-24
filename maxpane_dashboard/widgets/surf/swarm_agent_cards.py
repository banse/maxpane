"""AGENT card rows two and three: the shared row base and the seat-details row.

They replaced the SEAT detail panel and the BY NODE table on 2026-09-22 at
the owner's request, with the same values as hero cards. Row 1
(``swarm_agent_hero``) already shows attempts, accepted, accept rate,
reviewed and pending, so these rows leave them out.

* :class:`SurfSwarmSeatCards` -- OWNER, RUNTIME, SCORE, FEEDBACK, COLLAB,
  TEAMMATES, all from ``/seats`` and gated by ``swarm_seat_state``. OWNER shows
  the owner's forward-verified ENS name in place of the address when it has
  one (owner, 2026-09-22); the icon still copies the address. COLLAB moved here
  from the hero and TEAMMATES from row three on 2026-09-22 (owner).
* :class:`~maxpane_dashboard.widgets.surf.swarm_node_cards.SurfSwarmNodeCards`
  (its own module: it renders no address) -- ROLES, the node cards, OTHERS and
  BOARD (``/contributors``).

Third-party text (runtime, daemon, node keys, role names) is flattened and
**fitted to the box's content width with a visible ``…``**. Numbers and fixed
words are never fitted here: if they do not fit, CSS ellipsises them, and the
layout sweep counts that as a clipped line. Card widths belong to the
stylesheet.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.address import address_text
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.surf._fmt import (
    ANTI_POISONING_COLS,
    EMDASH,
    EXPLORER,
    mmdd_hhmm,
)
from maxpane_dashboard.widgets.surf._swarm_seat import (
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_WORDS,
    count,
    seat_state_line,
    seat_token,
)

__all__ = [
    "NO_FEEDBACK_LINE",
    "SEAT_BOX_IDS",
    "count",
    "dim_dash",
    "gate",
    "SurfSwarmAgentCard",
    "SurfSwarmAgentCards",
    "SurfSwarmSeatCards",
]


#: SCORE when the seat has no scored reviews yet: a real zero, not a failure.
NO_FEEDBACK_LINE = "no scores yet"

SEAT_BOX_IDS = {
    "owner": "surf-swarm-card-owner",
    "runtime": "surf-swarm-card-runtime",
    "feedback": "surf-swarm-card-feedback",
    "score": "surf-swarm-card-score",
    "collab": "surf-swarm-card-collab",
    "teammates": "surf-swarm-card-teammates",
}


#: Before the first layout a box has no width; fit nothing rather than guess.
_UNSIZED = 10_000


def dim_dash() -> Text:
    return Text(EMDASH, style="dim")


def gate(state, first: bool) -> str | Text | None:
    """What a seats-backed card shows instead of its values; ``None`` for ``"ok"``.

    A never-paired seat is a real negative, said once per row (its first
    card) as row 1's SEAT box says it -- the seat number is already there --
    and the other cards show a dash. Pending and a failed read show on every
    card, since each card's value is what is missing.
    """
    if state == "ok":
        return None
    if state == "unknown_seat":
        return Text(NEVER_PAIRED_WORDS, style=NEVER_PAIRED_STYLE) if first else dim_dash()
    if state == "pending":
        return seat_state_line(state)
    return UNAVAILABLE


class SurfSwarmAgentCard(HeroBoxBase):
    """One card in AGENT rows two and three. No geometry here: the stylesheet names this class."""


class SurfSwarmAgentCards(HeroRow):
    """Shared behaviour of the two card rows: keep the payload, repaint on resize.

    Third-party text is fitted to each card's own content width, so a resize
    has to repaint -- after the refresh, when the cards have their new size.
    """

    BOX_CLASS = SurfSwarmAgentCard

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data: dict | None = None

    def update_data(self, **kwargs) -> None:
        self._data = kwargs
        self._paint(**kwargs)

    def on_resize(self, _event=None) -> None:
        if self._data is not None:
            self.call_after_refresh(lambda: self._paint(**self._data))

    def _room(self, key: str) -> int:
        """The content width of card *key*; :data:`_UNSIZED` before layout."""
        try:
            width = self.query_one(f"#{self.IDS[key]}", HeroBoxBase).content_size.width
        except Exception:
            return _UNSIZED
        return width if width > 0 else _UNSIZED

    def _fit(self, key: str, value, reserved: int = 0) -> str:
        """Third-party text flattened and cut to what card *key* has left."""
        return rowfit.clip(flatten(value), max(self._room(key) - reserved, 1))

    def _paint(self, **kwargs) -> None:  # pragma: no cover - abstract
        raise NotImplementedError

    IDS: dict[str, str] = {}


class SurfSwarmSeatCards(SurfSwarmAgentCards):
    """Row two: OWNER, RUNTIME, SCORE, FEEDBACK, COLLAB, TEAMMATES (TEAMMATES under STATUS)."""

    IDS = SEAT_BOX_IDS
    BOXES = (
        (SEAT_BOX_IDS["owner"], "OWNER"),
        (SEAT_BOX_IDS["runtime"], "RUNTIME"),
        (SEAT_BOX_IDS["score"], "SCORE"),
        (SEAT_BOX_IDS["feedback"], "FEEDBACK"),
        (SEAT_BOX_IDS["collab"], "COLLAB"),
        (SEAT_BOX_IDS["teammates"], "TEAMMATES"),
    )

    def update_data(self, swarm_seat_summary=None, swarm_seat_state=None,
                    swarm_seat_teammates=None, swarm_seat_owner_ens=None, swarm_seat_node_rows=None, **_kwargs) -> None:
        super().update_data(
            swarm_seat_summary=swarm_seat_summary, swarm_seat_state=swarm_seat_state,
            swarm_seat_teammates=swarm_seat_teammates, swarm_seat_owner_ens=swarm_seat_owner_ens,
        )

    def _paint(self, swarm_seat_summary=None, swarm_seat_state=None,
               swarm_seat_teammates=None, swarm_seat_owner_ens=None) -> None:
        summary, state = swarm_seat_summary, swarm_seat_state
        ens_name = swarm_seat_owner_ens if isinstance(swarm_seat_owner_ens, str) else None
        for key, label, build in (
            ("owner", "OWNER", lambda s: self._owner_body(s, ens_name)),
            ("runtime", "RUNTIME", self._runtime_body),
            ("feedback", "FEEDBACK", self._feedback_body),
            ("score", "SCORE", self._score_body),
            ("collab", "COLLAB", self._collab_body),
        ):
            self.render_box(f"#{SEAT_BOX_IDS[key]}", label,
                            lambda key=key, build=build: self._seat_body(summary, state, key == "owner", build))
        mates = swarm_seat_teammates if state == "ok" else None
        self.render_box(f"#{SEAT_BOX_IDS['teammates']}", "TEAMMATES",
                        lambda: gate(state, first=False) or self._teammates_body(mates))

    # -- gates --------------------------------------------------------------

    @staticmethod
    def _seat_body(summary, state, first, build) -> str | Text:
        blocked = gate(state, first)
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

    def _runtime_body(self, summary: dict) -> Text:
        body = Text()
        runtime = summary.get("runtime")
        if runtime is None:
            body.append("unavailable", style="yellow")
        else:
            body.append(self._fit("runtime", runtime) or "none", style="bold")
        body.append("\n")
        daemon = summary.get("daemon")
        if daemon is None:
            body.append("daemon unavailable", style="yellow")
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

    @staticmethod
    def _score_body(summary: dict) -> Text:
        mean, scored = summary.get("mean_score"), count(summary.get("scored"))
        body = Text()
        if mean is None and summary.get("scored") == 0:
            body.append(NO_FEEDBACK_LINE, style="dim")
        elif isinstance(mean, (int, float)) and not isinstance(mean, bool):
            body.append(fmt_float(mean, ".2f"), style="bold")
            body.append("\non ", style="dim").append(scored or "--", style="bold")
            body.append(" scored", style="dim")
        else:
            body.append("unavailable", style="yellow")
        reviewed, entries = summary.get("reviewed"), summary.get("review_entries")
        if reviewed is not None and entries is not None and reviewed != entries:
            served = count(entries)
            if served is not None:
                body.append("\n").append(served, style="bold").append(" entries", style="dim")
        return body

    @staticmethod
    def _collab_body(summary: dict) -> str | Text:
        seats = count(summary.get("collaborators"))
        if seats is None:
            return UNAVAILABLE
        return Text().append(seats, style="bold").append(
            " seat" if summary.get("collaborators") == 1 else " seats", style="dim")

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

"""AGENT card rows two and three: the shared row base and the seat-details row.

They replaced the SEAT detail panel and the BY NODE table on 2026-09-22 at
the owner's request, with the same values as hero cards. Row 1
(``swarm_agent_hero``) already shows attempts, accepted, accept rate,
reviewed and pending, so these rows leave them out.

* :class:`SurfSwarmSeatCards` -- OWNER, RUNTIME, FEEDBACK, SCORE, BOARD, RANK.
  OWNER, RUNTIME, FEEDBACK and SCORE come from ``/seats`` and are gated by
  ``swarm_seat_state``. BOARD and RANK come from ``/contributors`` under their
  own clock and never borrow seats data.
* :class:`~maxpane_dashboard.widgets.surf.swarm_node_cards.SurfSwarmNodeCards`
  (its own module: it renders no address) -- ROLES, up to :data:`NODE_CARDS` node cards,
  TEAMMATES. Nodes keep the fold's order (reviewed desc); when more exist than
  cards, the last card sums the rest as ``+N more nodes``. The node rate is
  accepted / reviewed, never the lifetime attempts denominator.

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
    source_clock,
)
from maxpane_dashboard.widgets.surf._swarm_seat import (
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_WORDS,
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
    "board": "surf-swarm-card-board",
    "rank": "surf-swarm-card-rank",
}


#: Before the first layout a box has no width; fit nothing rather than guess.
_UNSIZED = 10_000


def count(value) -> str | None:
    number = seat_token(value)
    return None if number is None else fmt_int(number)


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
    """Row two: OWNER, RUNTIME, FEEDBACK, SCORE, BOARD, RANK."""

    IDS = SEAT_BOX_IDS
    BOXES = (
        (SEAT_BOX_IDS["owner"], "OWNER"),
        (SEAT_BOX_IDS["runtime"], "RUNTIME"),
        (SEAT_BOX_IDS["feedback"], "FEEDBACK"),
        (SEAT_BOX_IDS["score"], "SCORE"),
        (SEAT_BOX_IDS["board"], "BOARD"),
        (SEAT_BOX_IDS["rank"], "RANK"),
    )

    def update_data(self, swarm_seat_summary=None, swarm_seat_state=None,
                    swarm_seat_contrib=None, swarm_board_as_of_hhmm=None, **_kwargs) -> None:
        super().update_data(
            swarm_seat_summary=swarm_seat_summary,
            swarm_seat_state=swarm_seat_state, swarm_seat_contrib=swarm_seat_contrib,
            swarm_board_as_of_hhmm=swarm_board_as_of_hhmm,
        )

    def _paint(self, swarm_seat_summary=None,
               swarm_seat_state=None, swarm_seat_contrib=None,
               swarm_board_as_of_hhmm=None) -> None:
        summary, state = swarm_seat_summary, swarm_seat_state
        for key, label, build in (
            ("owner", "OWNER", self._owner_body),
            ("runtime", "RUNTIME", self._runtime_body),
            ("feedback", "FEEDBACK", self._feedback_body),
            ("score", "SCORE", self._score_body),
        ):
            self.render_box(f"#{SEAT_BOX_IDS[key]}", label,
                            lambda key=key, build=build: self._seat_body(summary, state, key == "owner", build))
        contrib = swarm_seat_contrib
        clock = swarm_board_as_of_hhmm
        board_label = "BOARD"
        if isinstance(contrib, dict) and rowfit.has_marker(clock):
            board_label += f" · as of {source_clock(clock)}"
        self.render_box(f"#{SEAT_BOX_IDS['board']}", board_label,
                        lambda: self._contrib_body(contrib, self._board_body))
        self.render_box(f"#{SEAT_BOX_IDS['rank']}", "RANK",
                        lambda: self._contrib_body(contrib, self._rank_body))

    # -- gates --------------------------------------------------------------

    @staticmethod
    def _seat_body(summary, state, first, build) -> str | Text:
        blocked = gate(state, first)
        if blocked is not None:
            return blocked
        if not isinstance(summary, dict):
            return UNAVAILABLE
        return build(summary)

    @staticmethod
    def _contrib_body(contrib, build) -> str | Text:
        if not isinstance(contrib, dict):
            return UNAVAILABLE
        if contrib.get("listed") is not True:
            if contrib.get("listed") is False:
                return Text("not listed", style="dim")
            return UNAVAILABLE
        return build(contrib)

    # -- seats bodies -------------------------------------------------------

    def _owner_body(self, summary: dict) -> Text:
        owner = summary.get("owner")
        body = (address_text(owner, width=ANTI_POISONING_COLS, explorer=EXPLORER)
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

    # -- contributors bodies ------------------------------------------------

    @staticmethod
    def _board_body(contrib: dict) -> Text:
        n = {k: count(contrib.get(k)) or "--" for k in ("attempts", "accepted", "rejected", "pending")}
        return (Text()
                .append(n["accepted"], style="bold green").append(" acc of ", style="dim")
                .append(n["attempts"], style="bold")
                .append("\n").append(n["rejected"], style="bold").append(" rejected", style="dim")
                .append("\n").append(n["pending"], style="bold").append(" pending", style="dim"))

    @staticmethod
    def _rank_body(contrib: dict) -> Text:
        body = Text()
        rank, of = count(contrib.get("rank")), count(contrib.get("ranked_of"))
        if rank is None:
            body.append("unranked", style="dim")
        else:
            body.append(f"#{rank}", style="bold").append(" of ", style="dim").append(of or "--", style="bold")
        turns = count(contrib.get("turns"))
        body.append("\n").append(turns or "--", style="bold").append(" turns", style="dim")
        seconds = contrib.get("wall_clock_s")
        hours = (fmt_float(seconds / 3600, ".1f")
                 if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) else "--")
        return body.append("\n").append(hours, style="bold").append(" h", style="dim")

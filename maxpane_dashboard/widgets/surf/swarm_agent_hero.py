"""AGENT hero: SEAT, ACCEPTED, ACCEPT RATE, REVIEWED, RANK and STATUS.

ACCEPT RATE is lifetime accepted / attempts; a real zero denominator says
``no attempts`` and a missing counter says ``unavailable``. STATUS names the
newest work with its local date -- ``worked`` when the newest attempt is newer
than the newest accepted one, else ``accepted`` (owner, 2026-09-22) -- never the
feedback queue's sent time. An idle worker reads ``● online`` in green. RANK
comes from ``/contributors`` and survives a pending or unavailable seat.
The seats state gates its own statistics; workers remain independent. The selected IDMD token
remains visible while its read is pending or unavailable. Geometry belongs
to the stylesheet; all six titles share one row. Historical contract keys
``win_rate`` and ``last_won_ts`` retain their accepted-work meanings.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, fmt_win_rate, mmdd_hhmm, source_clock
from maxpane_dashboard.widgets.surf._swarm_seat import (
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_WORDS,
    contrib_body,
    rank_body,
    seat_state_line,
    seat_token,
)

__all__ = ["BOX_IDS", "NO_SEAT_LINE", "ONLINE_LINE", "WORKING_GLYPH", "SurfSwarmAgentHero", "SurfSwarmAgentHeroBox"]

#: SEAT when nothing is selected: no roster row, no saved seat.
NO_SEAT_LINE = "no seat selected"

#: Stands for "working" in STATUS's counts (owner, 2026-09-22), beside the
#: pause line's ⏸: one cell where the word took eight with its space.
WORKING_GLYPH = "⚙"

#: STATUS for an idle worker (owner, 2026-09-22): the daemon is up and
#: waiting, which "idle" undersold. Only this part is green.
ONLINE_LINE = "● online"

BOX_IDS = {
    "seat": "surf-swarm-agent-seat",
    "accepted": "surf-swarm-agent-accepted",
    "reviewed": "surf-swarm-agent-reviewed",
    "win_rate": "surf-swarm-agent-win-rate",
    "rank": "surf-swarm-agent-rank",
    "status": "surf-swarm-agent-status",
}

#: How the seat was picked (``sw.choose_seat``): the seat saved in
#: ``~/.maxpane/config.toml``, or the busiest seat.
_SELECTED_BY = {
    "saved": "saved",
    "most_active": "most active",
}


class SurfSwarmAgentHeroBox(HeroBoxBase):
    """One box of the AGENT hero. No geometry here: the stylesheet names this class."""


_count = seat_token


class SurfSwarmAgentHero(HeroRow):
    """Six boxes for one seat -- see the module docstring."""

    BOX_CLASS = SurfSwarmAgentHeroBox
    BOXES = (
        (BOX_IDS["seat"], "SEAT"),
        (BOX_IDS["accepted"], "ACCEPTED"),
        (BOX_IDS["win_rate"], "ACCEPT RATE"),
        (BOX_IDS["reviewed"], "REVIEWED"),
        (BOX_IDS["rank"], "RANK"),
        (BOX_IDS["status"], "STATUS"),
    )

    def update_data(
        self,
        swarm_seat_selected=None,
        swarm_seat_summary=None,
        swarm_seat_state=None,
        swarm_seat_as_of_hhmm=None,
        swarm_seat_live=None,
        swarm_seat_contrib=None,
        **_kwargs,
    ) -> None:
        """Rewrite all six boxes; the state says which kind of missing."""
        selected = swarm_seat_selected
        state = swarm_seat_state
        as_of = swarm_seat_as_of_hhmm if rowfit.has_marker(swarm_seat_as_of_hhmm) else None
        self.render_box(f"#{BOX_IDS['seat']}", "SEAT",
                        lambda: self._seat_body(selected, state))
        for key, label, build in (
            ("accepted", "ACCEPTED", lambda s: self._accepted_body(s, as_of)),
            ("reviewed", "REVIEWED", self._reviewed_body),
            ("win_rate", "ACCEPT RATE", self._win_rate_body),
        ):
            self.render_box(f"#{BOX_IDS[key]}", label,
                            lambda build=build: self._stat_body(swarm_seat_summary, state, build))
        self.render_box(f"#{BOX_IDS['rank']}", "RANK",
                        lambda: contrib_body(swarm_seat_contrib, rank_body))
        self.render_box(f"#{BOX_IDS['status']}", "STATUS",
                        lambda: self._status_body(swarm_seat_summary, state, swarm_seat_live))

    # -- bodies -------------------------------------------------------------

    @staticmethod
    def _seat_body(selected, state) -> str | Text:
        if selected is None:
            return Text(NO_SEAT_LINE, style="dim")
        if not isinstance(selected, dict):
            return UNAVAILABLE
        token = seat_token(selected.get("token_id"))
        body = Text()
        body.append(f"IDMD #{DASH if token is None else token}", style="bold")
        body.append("\n")
        # ``Text.append`` parses nothing: a hostile agent id renders literally.
        body.append("agent ", style="dim")
        body.append(flatten(selected.get("agent_id")) or DASH, style="bold")
        body.append("\n")
        if state == "unknown_seat":
            body.append(NEVER_PAIRED_WORDS, style=NEVER_PAIRED_STYLE)
        else:
            how = selected.get("selected_by")
            body.append(_SELECTED_BY.get(how, flatten(how) or DASH), style="dim")
        return body

    @staticmethod
    def _stat_body(summary, state, build) -> str | Text:
        if state == "unknown_seat":
            return Text(EMDASH, style="dim")
        line = seat_state_line(state)
        if line is not None:
            return line
        if not isinstance(summary, dict):
            return UNAVAILABLE
        return build(summary)

    @staticmethod
    def _accepted_body(summary: dict, as_of=None) -> str | Text:
        accepted = _count(summary.get("accepted"))
        attempts = _count(summary.get("attempts"))
        if accepted is None or attempts is None:
            return UNAVAILABLE
        body = Text()
        body.append(fmt_int(accepted), style="bold green" if accepted else "bold")
        body.append(" of ", style="dim")
        body.append(fmt_int(attempts), style="bold")
        if as_of is not None:
            body.append("\nas of " + source_clock(as_of), style="dim")
        return body

    @staticmethod
    def _reviewed_body(summary: dict) -> str | Text:
        reviewed = _count(summary.get("reviewed"))
        if reviewed is None:
            return UNAVAILABLE
        status = summary.get("review_status")
        status = status if isinstance(status, dict) else {}
        submitted = _count(status.get("submitted"))
        queued = _count(status.get("queued"))
        pending = None if submitted is None or queued is None else submitted + queued
        body = Text()
        body.append(fmt_int(reviewed), style="bold")
        # Two lines, never ``72 · 6 pending`` on one: both are lifetime
        # counters with no ceiling, and one line of two of them is a width
        # that grows with the seat's age -- ``1,202 · 13 pending`` was cut
        # to ``pend…`` at the AGENT pin, where the hero has no ``‹``. On
        # their own lines the widest is ``9,999 pending`` (13 cells).
        body.append("\n")
        # A subset of ``reviewed`` (plan Q-M): the reviews whose score is not
        # on chain yet. ``--`` when the split was not served, never ``0``.
        body.append(fmt_int(pending) if pending is not None else DASH,
                    style="yellow" if pending else "dim")
        body.append(" pending", style="dim")
        return body

    @staticmethod
    def _win_rate_body(summary: dict) -> str | Text:
        """Lifetime accepted / attempts; zero attempts has no rate."""
        if summary.get("attempts") == 0:
            return Text("no attempts", style="dim")
        rate = summary.get("win_rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)):
            return UNAVAILABLE
        return Text().append(fmt_win_rate(rate), style="bold").append("\nof attempts", style="dim")

    @staticmethod
    def _status_body(summary, state, live) -> Text:
        """Worker state and seats acceptance retain independent availability."""
        # The fold distinguishes a known idle worker from unknown pause
        # evidence. `live=True` with zero work alone cannot establish idle.
        live = live if isinstance(live, dict) else {}
        live_state = live.get("live_state")
        active, capacity = _count(live.get("working")), _count(live.get("max_concurrency"))
        counts = f"{WORKING_GLYPH} {fmt_int(active)} of {fmt_int(capacity)}"
        word = counts if live_state == "working" else ONLINE_LINE if live_state == "idle" else (
            live_state if live_state in ("offline", "paused") else "unavailable")
        color = {"working":"green", "idle":"green", "offline":"red", "paused":"red"}.get(live_state, "yellow")
        body = Text().append(word, style=color)
        if live_state in ("idle", "paused") and active is not None and capacity is not None:
            body.append(" · " + counts, style="dim" if live_state == "idle" else color)
        body.append("\n")
        if live.get("paused_until_ts") is not None:
            failures = _count(live.get("failures"))
            body.append(f"⏸ until {hhmm(live['paused_until_ts'])} ×{fmt_int(failures) if failures is not None else DASH}", style="red")
        elif live_state is None and active is not None and capacity is not None:
            body.append(counts, style="dim")
        return body.append("\n").append(SurfSwarmAgentHero._newest_line(summary, state))

    @staticmethod
    def _newest_line(summary, state) -> str:
        """The newest thing the seat did: ``worked`` beats an older ``accepted``."""
        if state != "ok" or not isinstance(summary, dict):
            return "accepted unavailable"
        won, worked = summary.get("last_won_ts"), summary.get("last_worked_ts")
        if worked is not None and (won is None or worked > won):
            return f"worked {mmdd_hhmm(worked)}"
        if summary.get("accepted") == 0:
            return "none accepted yet"
        if won is not None:
            return f"accepted {mmdd_hhmm(won)}"
        return "accepted unavailable"

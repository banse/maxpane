"""AGENT hero: SEAT, ACCEPTED WORK, WORK, REWARDS, RANK and STATUS.

ACCEPTED WORK (box key ``accepted``; WORK traded places with it, F-S6, owner
2026-10-02) includes the lifetime accepted / attempts rate; a real zero denominator says
``no attempts`` and a missing counter says ``unavailable``. STATUS names the
newest work with its local date -- ``worked`` when the newest attempt is newer
than the newest accepted one, else ``accepted`` (owner, 2026-09-22) -- never the
feedback queue's sent time. An idle worker reads ``● online`` and a working one
``● working`` (F-S4), each in green with its counts dim after it. RANK
and acceptance come from one ``/seats/records`` snapshot and survive a pending
or unavailable detail read. WORK retains its independent contributor clock.
REWARDS (F-S5, owner 2026-10-02; it replaced REVIEWED) is the IMD the seat's
owner was paid since ``pairedAt``, split over the owner's seats, then that IMD
at today's price: ``Loading…`` before its read lands, ``unavailable`` after a
failed one, ``0.00 IMD`` for a real zero.
The detail state gates REWARDS; outcomes and workers remain independent. The selected IDMD token
remains visible while its read is pending or unavailable. Geometry belongs
to the stylesheet; all six titles share one row. Historical contract keys
``last_won_ts`` retains its accepted-work meaning for the detail chronology.
"""

from __future__ import annotations

import math

from rich.cells import cell_len
from rich.text import Text

from maxpane_dashboard.widgets.fmt import fmt_int, hhmm
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import LOADING, UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, fmt_win_rate, mmdd_hhmm, source_clock
from maxpane_dashboard.widgets.surf._swarm_seat import (
    _UNSIZED,
    MeasuredRow,
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_WORDS,
    contrib_body,
    outcome_body,
    outcomes_clock,
    rank_body,
    work_body,
    seat_state_line,
    seat_token,
)

__all__ = [
    "BOX_IDS", "NO_SEAT_LINE", "ONLINE_LINE", "WORKING_GLYPH", "WORKING_LINE",
    "SurfSwarmAgentHero", "SurfSwarmAgentHeroBox",
]

#: SEAT when nothing is selected: no roster row, no saved seat.
NO_SEAT_LINE = "no seat selected"

#: Stands for "working" in STATUS's counts (owner, 2026-09-22), beside the
#: pause line's ⏸: one cell where the word took eight with its space.
WORKING_GLYPH = "⚙"

#: STATUS for an idle worker (owner, 2026-09-22): the daemon is up and
#: waiting, which "idle" undersold. Only this part is green.
ONLINE_LINE = "● online"

#: STATUS for a working seat (F-S4, owner 2026-10-02): the same shape as
#: ``ONLINE_LINE``, the word green and the ``⚙`` counts dim after it. Only
#: when the whole line fits STATUS: at the AGENT pin STATUS has 24 cells, and
#: ``● working · ⚙ 99,999 of 99,999`` (the sweep's worst case) needs 30. A line
#: that does not fit drops the word and keeps the green counts whole -- the
#: form STATUS had before -- rather than cutting a number (terminal-layout:
#: shorten the value, do not raise the pin).
WORKING_LINE = "● working"

BOX_IDS = {
    "seat": "surf-swarm-agent-seat",
    "work": "surf-swarm-agent-work",
    "accepted": "surf-swarm-agent-accepted",
    "rewards": "surf-swarm-agent-rewards",
    "rank": "surf-swarm-agent-rank",
    "status": "surf-swarm-agent-status",
}

#: How the seat was picked (``sw.choose_seat``), said only when it is not the
#: seat you saved in ``~/.maxpane/config.toml``: a saved seat is the normal
#: case and SEAT says nothing (owner, 2026-09-22); the busiest seat stands in
#: for no saved one and says so.
_SELECTED_BY = {
    "saved": "",
    "most_active": "most active",
}


class SurfSwarmAgentHeroBox(HeroBoxBase):
    """One box of the AGENT hero. No geometry here: the stylesheet names this class."""


_count = seat_token


def _amount(value) -> str | None:
    """A reward amount, ``None`` when it is not a finite non-negative number.

    Two decimals below 100,000 (``13.87``, ``99,999.99``: 9 cells); above, one
    decimal of K/M/B carried upward (``999.95K`` reads ``1.0M``, never
    ``1000.0K``, the F66 trap), then scientific. A non-zero amount that rounds
    to nothing reads ``<0.01``, never a ``0.00`` it is not.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0:
        return None
    if value > 0 and round(value, 2) == 0:
        return "<0.01"
    if round(value, 2) < 100_000:
        return f"{value:,.2f}"
    for divisor, unit in ((1e3, "K"), (1e6, "M"), (1e9, "B")):
        if round(value / divisor, 1) < 1_000:
            return f"{value / divisor:.1f}{unit}"
    return f"{value:.1e}"


class SurfSwarmAgentHero(MeasuredRow, HeroRow):
    """Six boxes for one seat -- see the module docstring."""

    BOX_CLASS = SurfSwarmAgentHeroBox
    IDS = BOX_IDS
    BOXES = (
        (BOX_IDS["seat"], "SEAT"),
        (BOX_IDS["accepted"], "ACCEPTED WORK"),
        (BOX_IDS["work"], "WORK"),
        (BOX_IDS["rewards"], "REWARDS"),
        (BOX_IDS["rank"], "RANK"),
        (BOX_IDS["status"], "STATUS"),
    )

    def update_data(
        self,
        swarm_seat_selected=None,
        swarm_seat_summary=None,
        swarm_seat_state=None,
        swarm_seat_live=None,
        swarm_seat_contrib=None,
        swarm_seat_rank_delta=None,
        swarm_seat_rewards=None,
        swarm_seat_rewards_state=None,
        swarm_seat_outcome=None,
        swarm_outcomes_source=None,
        swarm_contributors_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Rewrite all six boxes; the state says which kind of missing."""
        super().update_data(
            swarm_seat_selected=swarm_seat_selected, swarm_seat_summary=swarm_seat_summary,
            swarm_seat_state=swarm_seat_state, swarm_seat_live=swarm_seat_live,
            swarm_seat_contrib=swarm_seat_contrib, swarm_seat_rank_delta=swarm_seat_rank_delta,
            swarm_seat_rewards=swarm_seat_rewards, swarm_seat_rewards_state=swarm_seat_rewards_state,
            swarm_seat_outcome=swarm_seat_outcome, swarm_outcomes_source=swarm_outcomes_source,
            swarm_contributors_as_of_hhmm=swarm_contributors_as_of_hhmm,
        )

    def _paint(
        self,
        swarm_seat_selected=None,
        swarm_seat_summary=None,
        swarm_seat_state=None,
        swarm_seat_live=None,
        swarm_seat_contrib=None,
        swarm_seat_rank_delta=None,
        swarm_seat_rewards=None,
        swarm_seat_rewards_state=None,
        swarm_seat_outcome=None,
        swarm_outcomes_source=None,
        swarm_contributors_as_of_hhmm=None,
    ) -> None:
        selected = swarm_seat_selected
        state = swarm_seat_state
        selected_token = seat_token(selected.get("token_id")) if isinstance(selected, dict) else None
        if (not isinstance(swarm_seat_outcome, dict) or selected_token is None
                or seat_token(swarm_seat_outcome.get("token_id")) != selected_token):
            swarm_seat_outcome = None
        self.render_box(f"#{BOX_IDS['seat']}", "SEAT",
                        lambda: self._seat_body(selected, state))
        self.render_box(f"#{BOX_IDS['accepted']}", "ACCEPTED WORK",
                        lambda: outcome_body(swarm_seat_outcome, swarm_outcomes_source,
                                             lambda row: self._accepted_body(row, swarm_outcomes_source)))
        self.render_box(f"#{BOX_IDS['rewards']}", "REWARDS",
                        lambda: self._stat_body(swarm_seat_summary, state,
                            lambda _: self._rewards_body(swarm_seat_rewards, swarm_seat_rewards_state)))
        self.render_box(f"#{BOX_IDS['work']}", "WORK",
                        lambda: contrib_body(swarm_seat_contrib, lambda row:
                            self._timed_work(row, swarm_contributors_as_of_hhmm)))
        self.render_box(f"#{BOX_IDS['rank']}", "RANK",
                        lambda: outcome_body(swarm_seat_outcome, swarm_outcomes_source,
                            lambda row: self._timed_rank(row, swarm_seat_rank_delta, swarm_outcomes_source)))
        self.render_box(f"#{BOX_IDS['status']}", "STATUS",
                        lambda: self._status_body(swarm_seat_summary, state, swarm_seat_live,
                                                  self._room("status")))

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
        # Line 2 is blank, as in STATUS (owner, 2026-09-25); only the rare
        # selection word (never paired, most active) takes it.
        if state == "unknown_seat":
            body.append(NEVER_PAIRED_WORDS, style=NEVER_PAIRED_STYLE)
        else:
            how = selected.get("selected_by")
            word = _SELECTED_BY.get(how) if isinstance(how, str) else None
            body.append(flatten(how) or DASH if word is None else word, style="dim")
        body.append("\n")
        # ``Text.append`` parses nothing: a hostile agent id renders literally.
        body.append("agent ", style="dim")
        body.append(flatten(selected.get("agent_id")) or DASH, style="bold")
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
    def _accepted_body(summary: dict, source=None) -> str | Text:
        accepted = _count(summary.get("accepted"))
        attempts = _count(summary.get("attempts"))
        if accepted is None or attempts is None or accepted > attempts:
            return UNAVAILABLE
        body = Text()
        body.append(fmt_int(accepted), style="bold green" if accepted else "bold")
        body.append(" of ", style="dim")
        body.append(fmt_int(attempts), style="bold")
        rate = SurfSwarmAgentHero._win_rate_body(summary)
        body.append("\n").append(outcomes_clock(source), style="dim").append("\n")
        return body + (Text.from_markup(rate) if isinstance(rate, str) else rate)

    @staticmethod
    def _timed_work(row, clock):
        body = work_body(row)
        lines = body.split("\n")
        return lines[0] + Text("\nread " + source_clock(clock) + "\n", style="dim") + lines[-1]

    @staticmethod
    def _timed_rank(row, delta, source):
        body = rank_body(row, delta)
        lines = body.split("\n")
        return lines[0] + Text("\n" + outcomes_clock(source), style="dim") + (Text("\n") + lines[-1] if len(lines) > 1 else Text())

    @staticmethod
    def _rewards_body(rewards, state) -> str | Text:
        """IMD, a blank row as in STATUS, then that IMD in USD at today's price."""
        if state == "pending":
            return Text.from_markup(LOADING)
        if state != "ok" or not isinstance(rewards, dict):
            return UNAVAILABLE
        imd = _amount(rewards.get("imd"))
        if imd is None:
            return UNAVAILABLE
        body = Text().append(imd, style="bold").append(" IMD", style="dim").append("\n\n")
        usd = _amount(rewards.get("usd"))
        if usd is None:
            return body + Text.from_markup(UNAVAILABLE)
        less = usd.startswith("<")
        return body.append("<$" if less else "$", style="dim").append(usd.lstrip("<"), style="bold")

    @staticmethod
    def _win_rate_body(summary: dict) -> str | Text:
        """Lifetime accepted / attempts; zero attempts has no rate."""
        if summary.get("attempts") == 0:
            return Text("no attempts", style="dim")
        rate = summary.get("accept_rate")
        if isinstance(rate, bool) or not isinstance(rate, (int, float)) or not math.isfinite(rate) or not 0 <= rate <= 1:
            return UNAVAILABLE
        return Text().append(fmt_win_rate(rate), style="bold")

    @staticmethod
    def _status_body(summary, state, live, room: int = _UNSIZED) -> Text:
        """Worker state and seats acceptance retain independent availability."""
        # The fold distinguishes a known idle worker from unknown pause
        # evidence. `live=True` with zero work alone cannot establish idle.
        live = live if isinstance(live, dict) else {}
        live_state = live.get("live_state")
        active, capacity = _count(live.get("working")), _count(live.get("max_concurrency"))
        counts = f"{WORKING_GLYPH} {fmt_int(active)} of {fmt_int(capacity)}"
        # Oracle jobs do not count against maxConcurrency (live #420, 2026-09-26:
        # working 9, maxConcurrency 1), so a count above capacity drops the
        # misleading ``of N`` (owner, 2026-09-26).
        over = active is not None and capacity is not None and active > capacity
        if over:
            counts = f"{WORKING_GLYPH} {fmt_int(active)} working"
        word = {"working": WORKING_LINE, "idle": ONLINE_LINE}.get(live_state) or (
            live_state if live_state in ("offline", "paused") else "unavailable")
        if live_state == "working" and active is not None and capacity is not None:
            # After ``● working`` the over-capacity count drops its own word (F-S4).
            short = f"{WORKING_GLYPH} {fmt_int(active)}" if over else counts
            if cell_len(f"{WORKING_LINE} · {short}") <= room:
                counts = short
            else:
                word = counts       # see WORKING_LINE: the counts stay whole
        color = {"working":"green", "idle":"green", "offline":"red", "paused":"red"}.get(live_state, "yellow")
        body = Text().append(word, style=color)
        if (live_state in ("idle", "paused") or word == WORKING_LINE) and active is not None and capacity is not None:
            body.append(" · " + counts, style=color if live_state == "paused" else "dim")
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

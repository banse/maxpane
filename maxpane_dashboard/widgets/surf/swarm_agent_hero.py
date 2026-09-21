"""The AGENT body's hero: SEAT · ACCEPTED · REVIEWED · SCORE · COLLAB · STATUS.

A third surf hero, swapped in with the AGENT body (``a``, ``MODE_AGENT``)
the way ``SurfSwarmHero`` swaps in with the ``s`` body. Every number here is
the selected seat's **lifetime** record from ``GET /seats/{tokenId}``
(``docs/surf_agent_seats_spec.md`` §3), folded by ``data/surf_swarm
.seat_summary_from_seat`` into ``swarm_seat_summary``; this module only
paints it, on :class:`~maxpane_dashboard.widgets.panels.HeroRow`.

The boxes (spec §3, plan WP3):

* **SEAT** -- ``IDMD #420`` (bold), ``agent 50939`` (dim), how the seat was
  picked (``saved`` / ``selected`` / ``most active``, dim). It names the
  selected seat in **every** state, so a reader watching ``Loading...`` or
  ``unavailable`` in the other five knows which seat that is about. For
  ``unknown_seat`` the third line is ``never paired`` (yellow): the token is
  already on the first line, and ``#12345 never paired`` (19 cells) does not
  fit the ~16-cell box at the AGENT pin.
* **ACCEPTED** ``12 of 74`` -- the submissions a job used, of all attempts.
* **REVIEWED** ``72 · 6 pending`` -- every scored review; *pending* is
  ``submitted + queued``, a **subset** of the 72, never added to it (plan
  Q-M, owner 2026-09-21). Review-accepted is not ``accepted``: the two boxes
  never share a word.
* **SCORE** ``1.00`` over ``(72 scored)``; ``—`` over ``(0 scored)`` when no
  review carried a value -- no score yet is not a score of zero.
* **COLLAB** ``24 seats`` -- the seats this one shared jobs with.
* **STATUS** ``online ●`` / ``offline ○``, ``last HH:MM`` (newest
  ``acceptedAt`` / ``sentAt``), and the seat tier's ``as of HH:MM``, so a
  last-good served after a failed read is never presented as live.

REVISIONS and ACC / REJ left with decision D2: ``/seats`` serves neither.

``swarm_seat_state`` (``widgets/surf/_swarm_seat.py``) decides the five stat
boxes before any number is read: ``"pending"`` → ``Loading...``, ``None``
(or a malformed state) → ``unavailable``, ``"unknown_seat"`` → a dim ``—``
(there is nothing to count for a seat that never paired, and that is not a
failure). Under ``"ok"`` a field the source did not carry is ``None`` and its
box says ``unavailable``; a real zero renders ``0`` (``0 of 0``).

Token ids are integers, not addresses: no copy icon. No clock: STATUS shows
``hhmm`` stamps, never an age.

Geometry
--------
None here (``rules/widgets.md``, ``HeroBoxBase``): ``SurfSwarmAgentHeroBox``
exists so ``minimal.tcss`` can name it, and both swarm heroes follow one
block there (height 7 -- label, blank, three body lines, a solid border).
Six ``1fr`` boxes leave ~16 content cells each at the AGENT pin, which is
why SCORE's count and STATUS's stamps take lines of their own.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, hhmm
from maxpane_dashboard.widgets.surf._swarm_seat import (
    NEVER_PAIRED_STYLE,
    NEVER_PAIRED_WORDS,
    seat_state_line,
    seat_token,
)

__all__ = ["BOX_IDS", "NO_SEAT_LINE", "SurfSwarmAgentHero", "SurfSwarmAgentHeroBox"]

#: SEAT when nothing is selected: no roster row, no saved seat. True whether
#: the roster is empty or was never read -- the ROSTER panel says which.
NO_SEAT_LINE = "no seat selected"

BOX_IDS = {
    "seat": "surf-swarm-agent-seat",
    "accepted": "surf-swarm-agent-accepted",
    "reviewed": "surf-swarm-agent-reviewed",
    "score": "surf-swarm-agent-score",
    "collab": "surf-swarm-agent-collab",
    "status": "surf-swarm-agent-status",
}

#: How the seat was picked (``sw.choose_seat``): the seat saved in
#: ``~/.maxpane/config.toml``, the roster cursor, or the busiest seat.
_SELECTED_BY = {
    "saved": "saved",
    "cursor": "selected",
    "most_active": "most active",
}


class SurfSwarmAgentHeroBox(HeroBoxBase):
    """One box of the AGENT hero. No geometry here: the stylesheet names this class."""


def _count(value: object) -> int | None:
    """A lifetime counter, or ``None``: an ``int``, not a ``bool``, not negative."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


class SurfSwarmAgentHero(HeroRow):
    """Six boxes for one seat -- see the module docstring."""

    BOX_CLASS = SurfSwarmAgentHeroBox
    BOXES = (
        (BOX_IDS["seat"], "SEAT"),
        (BOX_IDS["accepted"], "ACCEPTED"),
        (BOX_IDS["reviewed"], "REVIEWED"),
        (BOX_IDS["score"], "SCORE"),
        (BOX_IDS["collab"], "COLLAB"),
        (BOX_IDS["status"], "STATUS"),
    )

    def update_data(
        self,
        swarm_seat_selected=None,
        swarm_seat_summary=None,
        swarm_seat_state=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Rewrite all six boxes; the state says which kind of missing."""
        selected = swarm_seat_selected
        state = swarm_seat_state
        as_of = swarm_seat_as_of_hhmm if rowfit.has_marker(swarm_seat_as_of_hhmm) else None
        self.render_box(f"#{BOX_IDS['seat']}", "SEAT",
                        lambda: self._seat_body(selected, state))
        for key, label, build in (
            ("accepted", "ACCEPTED", self._accepted_body),
            ("reviewed", "REVIEWED", self._reviewed_body),
            ("score", "SCORE", self._score_body),
            ("collab", "COLLAB", self._collab_body),
            ("status", "STATUS", lambda s: self._status_body(s, as_of)),
        ):
            self.render_box(f"#{BOX_IDS[key]}", label,
                            lambda build=build: self._stat_body(swarm_seat_summary, state, build))

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
    def _accepted_body(summary: dict) -> str | Text:
        accepted = _count(summary.get("accepted"))
        attempts = _count(summary.get("attempts"))
        if accepted is None or attempts is None:
            return UNAVAILABLE
        body = Text()
        body.append(fmt_int(accepted), style="bold green" if accepted else "bold")
        body.append(" of ", style="dim")
        body.append(fmt_int(attempts), style="bold")
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
        body.append(" · ", style="dim")
        # A subset of ``reviewed`` (plan Q-M): the reviews whose score is not
        # on chain yet. ``--`` when the split was not served, never ``0``.
        body.append(fmt_int(pending) if pending is not None else DASH,
                    style="yellow" if pending else "dim")
        body.append(" pending", style="dim")
        return body

    @staticmethod
    def _score_body(summary: dict) -> str | Text:
        scored = _count(summary.get("scored"))
        mean = summary.get("mean_score")
        if scored is None:
            return UNAVAILABLE
        body = Text()
        if mean is None or isinstance(mean, bool):
            body.append(EMDASH, style="dim")
        else:
            body.append(fmt_float(mean, ".2f"), style="bold")
        body.append("\n")
        body.append(f"({fmt_int(scored)} scored)", style="dim")
        return body

    @staticmethod
    def _collab_body(summary: dict) -> str | Text:
        seats = _count(summary.get("collaborators"))
        if seats is None:
            return UNAVAILABLE
        body = Text()
        body.append(fmt_int(seats), style="bold")
        body.append(" seat" if seats == 1 else " seats", style="dim")
        return body

    @staticmethod
    def _status_body(summary: dict, as_of: str | None) -> str | Text:
        online = summary.get("online")
        body = Text()
        if online is True:
            body.append("online ●", style="bold green")
        elif online is False:
            body.append("offline ○", style="dim")
        else:
            body.append_text(Text.from_markup(UNAVAILABLE))
        body.append("\n")
        body.append(f"last {hhmm(summary.get('last_active_ts'))}", style="dim")
        if as_of is not None:
            body.append("\n")
            body.append(f"as of {as_of}", style="dim")
        return body


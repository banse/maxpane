"""The AGENT body's hero: SEAT · NODES · JOBS · ACC / REJ · REVISIONS · SCORE · STATUS.

Swarm v2 plan Amendment A1 (WP6a; on screen since WP7). A third surf hero,
swapped in with the AGENT body (``a``, ``MODE_AGENT``) the way
``SurfSwarmHero`` swaps in with the ``s`` body. This module only paints the
frozen ``swarm_seat_selected`` / ``swarm_seat_summary`` dicts, on
:class:`~maxpane_dashboard.widgets.panels.HeroRow` (``widgets/cattown/
hero.py`` is the idiom): a ``None`` under a marker is a real empty (nothing
selected / nothing to count), a ``None`` with no marker is ``unavailable``,
and a value of the wrong shape lands on ``unavailable`` too (MEDI-38,
never a false degradation). SCORE renders ``— (0 scored)`` when
``mean_score`` is ``None``: no feedback yet is not a score of zero.

Token ids are integers, not addresses: no copy icon. No clock: STATUS shows
``last HH:MM`` through ``hhmm``, never an age.

SEAT is three lines -- ``IDMD #1548`` (bold), ``agent 50971`` (dim) and how
the seat was picked (``saved`` / ``selected`` / ``most active``, dim), or
``#N not seen`` (yellow) when a saved seat is off the roster -- each fifteen
cells or fewer for a real IDMD id. The plan's one-line form ``agent 50971 · most
active`` is 25 cells, and six ``1fr`` boxes at ``__main__
.FULL_LAYOUT_COLUMNS`` (143) leave each about 20 cells of content; a line
that cannot fit at the widest pin the app admits has to be re-cut, not
clipped (terminal-layout skill: *shorten the value before raising the
pin*). ``ACC / REJ`` is the verdicts label for the same reason.

Geometry
--------
None here (``rules/widgets.md``, ``HeroBoxBase``): ``SurfSwarmAgentHeroBox``
exists so ``minimal.tcss`` can name it, and both swarm heroes follow one
block there (height 7 -- label, blank, three body lines, a solid border).
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets import rowfit
from maxpane_dashboard.widgets.fmt import fmt_float, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.surf._fmt import DASH, EMDASH, hhmm

__all__ = ["BOX_IDS", "NO_SEAT_LINE", "SurfSwarmAgentHero", "SurfSwarmAgentHeroBox"]

NO_SEAT_LINE = "no seat seen"

BOX_IDS = {
    "seat": "surf-swarm-agent-seat",
    "nodes": "surf-swarm-agent-nodes",
    "verdicts": "surf-swarm-agent-verdicts",
    "revisions": "surf-swarm-agent-revisions",
    "score": "surf-swarm-agent-score",
    "status": "surf-swarm-agent-status",
}

#: How the seat was picked (``sw.pick_seat``): the seat saved in
#: ``~/.maxpane/config.toml``, the roster cursor, or the busiest seat.
_SELECTED_BY = {
    "saved": "saved",
    "cursor": "selected",
    "most_active": "most active",
}


class SurfSwarmAgentHeroBox(HeroBoxBase):
    """One box of the AGENT hero. No geometry here: the stylesheet names this class."""


#: What a non-dict, non-``None`` payload value becomes: not a fact, a defect.
_MALFORMED = object()


def _dict_or_marker(value: object):
    if value is None or isinstance(value, dict):
        return value
    return _MALFORMED


def _token_word(value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int):
        return DASH
    return str(value)


class SurfSwarmAgentHero(HeroRow):
    """Six boxes for one seat -- see the module docstring."""

    BOX_CLASS = SurfSwarmAgentHeroBox
    BOXES = (
        (BOX_IDS["seat"], "SEAT"),
        (BOX_IDS["nodes"], "NODES · JOBS"),
        (BOX_IDS["verdicts"], "ACC / REJ"),
        (BOX_IDS["revisions"], "REVISIONS"),
        (BOX_IDS["score"], "SCORE"),
        (BOX_IDS["status"], "STATUS"),
    )

    def update_data(
        self,
        swarm_seat_selected=None,
        swarm_seat_summary=None,
        swarm_seat_as_of_hhmm=None,
        **_kwargs,
    ) -> None:
        """Rewrite all six boxes; a missing value says which kind of missing."""
        swept = rowfit.has_marker(swarm_seat_as_of_hhmm)
        # ``None`` is a fact (nothing selected / nothing to count); any other
        # non-dict is a malformed payload and lands on ``unavailable``
        # (MEDI-38), never on the "real empty" wording.
        selected = _dict_or_marker(swarm_seat_selected)
        summary = _dict_or_marker(swarm_seat_summary)
        self.render_box(f"#{BOX_IDS['seat']}", "SEAT",
                        lambda: self._seat_body(selected, swept))
        for key, label, build in (
            ("nodes", "NODES · JOBS", self._nodes_body),
            ("verdicts", "ACC / REJ", self._verdicts_body),
            ("revisions", "REVISIONS", self._revisions_body),
            ("score", "SCORE", self._score_body),
            ("status", "STATUS", self._status_body),
        ):
            self.render_box(f"#{BOX_IDS[key]}", label,
                            lambda build=build: self._summary_body(summary, swept, build))

    # -- bodies -------------------------------------------------------------

    @staticmethod
    def _seat_body(selected, swept: bool) -> str | Text:
        if selected is _MALFORMED or (selected is None and not swept):
            return UNAVAILABLE
        if selected is None:
            return Text(NO_SEAT_LINE, style="dim")
        body = Text()
        body.append(f"IDMD #{_token_word(selected.get('token_id'))}", style="bold")
        body.append("\n")
        # ``Text.append`` parses nothing: a hostile agent id renders literally.
        body.append("agent ", style="dim")
        body.append(flatten(selected.get("agent_id")) or DASH, style="bold")
        body.append("\n")
        how = selected.get("selected_by")
        unseen = selected.get("unseen_token")
        if how == "most_active" and isinstance(unseen, int) and not isinstance(unseen, bool):
            # The busiest seat is standing in for the saved one: name the
            # saved one rather than let "most active" pass as the reader's
            # choice. 16 cells at the AGENT pin -- a five-digit id fits.
            body.append(f"#{unseen} not seen", style="yellow")
        else:
            body.append(_SELECTED_BY.get(how, flatten(how) or DASH), style="dim")
        return body

    @staticmethod
    def _summary_body(summary, swept: bool, build) -> str | Text:
        if summary is _MALFORMED or (summary is None and not swept):
            return UNAVAILABLE
        if summary is None:
            return Text(EMDASH, style="dim")
        return build(summary)

    @staticmethod
    def _nodes_body(summary: dict) -> Text:
        body = Text()
        body.append(fmt_int(summary.get("nodes")), style="bold")
        body.append(" · ", style="dim")
        body.append(fmt_int(summary.get("jobs")), style="bold")
        return body

    @staticmethod
    def _verdicts_body(summary: dict) -> Text:
        accepted = summary.get("accepted")
        rejected = summary.get("rejected")
        body = Text()
        body.append(fmt_int(accepted), style="bold green" if _positive(accepted) else "bold")
        body.append(" / ", style="dim")
        body.append(fmt_int(rejected), style="bold red" if _positive(rejected) else "bold")
        return body

    @staticmethod
    def _revisions_body(summary: dict) -> Text:
        revisions = summary.get("revisions")
        return Text(fmt_int(revisions), style="bold yellow" if _positive(revisions) else "bold")

    @staticmethod
    def _score_body(summary: dict) -> Text:
        mean = summary.get("mean_score")
        scored = fmt_int(summary.get("scored"))
        body = Text()
        if mean is None:
            body.append(EMDASH, style="dim")
        else:
            body.append(fmt_float(mean, ".1f"), style="bold")
        body.append(f" ({scored} scored)", style="dim")
        return body

    @staticmethod
    def _status_body(summary: dict) -> Text:
        body = Text()
        if summary.get("working_now"):
            body.append("working ●", style="bold green")
        else:
            body.append("idle ○", style="dim")
        body.append("\n")
        body.append(f"last {hhmm(summary.get('last_active_ts'))}", style="dim")
        return body


def _positive(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0

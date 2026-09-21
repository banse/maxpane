"""The AGENT body's hero: SEAT · NODES · JOBS · ACCEPTED / REJECTED · REVISIONS · SCORE · STATUS.

Swarm v2 plan Amendment A1 (WP6a). A third surf hero, swapped in with the
AGENT body the way ``SurfSwarmHero`` swaps in with the ``s`` body; unwired
until WP7 exports the class, mounts it and adds ``MODE_AGENT`` to
``_SURF_HERO_MODES``. This module only paints the frozen
``swarm_seat_selected`` / ``swarm_seat_summary`` dicts, on
:class:`~maxpane_dashboard.widgets.panels.HeroRow` (``widgets/cattown/
ct_hero_metrics.py`` is the idiom): every box rewritten on every
``update_data`` inside ``render_box``'s guard (MEDI-38), each body a
pre-built ``rich.text.Text`` so a third-party ``agent_id`` is appended, never
parsed, and renders literally.

Two facts the SEAT box keeps apart. ``selected`` is ``None`` and there is
**no marker**: nothing was swept -- ``unavailable``. ``selected`` is
``None`` **under a marker**: the sweep ran and found no seat --
:data:`NO_SEAT_LINE`, a real empty. The counter boxes read the same
distinction off the summary: ``None`` under a marker is the dim em dash
(nothing to count), ``None`` with no marker is ``unavailable`` (CLAUDE.md:
never a false degradation). SCORE renders ``— (0 scored)`` when
``mean_score`` is ``None``: no feedback yet is not a score of zero.

Token ids are integers, not addresses: no copy icon. No clock: STATUS shows
``last HH:MM`` through ``hhmm``, never an age. The row carries its own
geometry in ``DEFAULT_CSS`` as ``SurfSwarmHero`` does (the ``s`` body's hero
is the sibling idiom); a ``minimal.tcss`` block on ``SurfSwarmAgentHeroBox``
is WP7's to add if the theme wants to restate it.
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

_SELECTED_BY = {
    "env": "from MAXPANE_IMD_SEAT",
    "cursor": "selected",
    "most_active": "most active",
}


class SurfSwarmAgentHeroBox(HeroBoxBase):
    """One box of the AGENT hero; its geometry is the row's ``DEFAULT_CSS`` below."""


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

    #: ``SurfSwarmHero``'s geometry (the ``s`` body's hero, the sibling
    #: idiom) minus its horizontal padding: height 6 holds a label, a blank
    #: and two content lines (SEAT's ``selected_by`` clause, STATUS's ``last
    #: HH:MM``) inside a solid border; vertical padding would clip the second
    #: line in silence (``fwa_hero_metrics.py``'s hazard note). No padding
    #: because six boxes share the row and SEAT's ``IDMD #1548 · agent 50971``
    #: is 24 cells: with a border and a 1-cell margin each box has
    #: ``cols / 6 - 4`` cells of content, 24 at 168 columns. Below that the
    #: line clips with a visible ``…`` -- the row's own pin is WP7's to
    #: measure, and this is the widest fact it must hold.
    DEFAULT_CSS = """
    SurfSwarmAgentHero {
        height: 6;
    }
    SurfSwarmAgentHero > SurfSwarmAgentHeroBox {
        width: 1fr;
        height: 6;
        margin: 0 1;
        border: solid $panel;
        background: $surface;
        content-align: center middle;
        text-align: center;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    BOXES = (
        (BOX_IDS["seat"], "SEAT"),
        (BOX_IDS["nodes"], "NODES · JOBS"),
        (BOX_IDS["verdicts"], "ACCEPTED / REJECTED"),
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
            ("verdicts", "ACCEPTED / REJECTED", self._verdicts_body),
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
        body.append(" · agent ", style="dim")
        body.append(flatten(selected.get("agent_id")) or DASH, style="bold")
        body.append("\n")
        how = selected.get("selected_by")
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

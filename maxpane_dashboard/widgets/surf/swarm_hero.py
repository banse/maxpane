"""SWARM's six summary cards on HeroRow.

AGENTS (online/enrolled), WORKING and ACCEPTED 24h retain their numeric
semantics. LAUNCHES, WORKFLOWS and SITES show a bold total, followed by
whole status/count pairs in descending count order within the measured box.
None is yellow unavailable; empty lists are real zero. SITES shares its
current-site predicate with the table. Breaker, services and health belong
to the screen title. Resizing re-fits whole summary pairs; no I/O or clock.
"""

from __future__ import annotations

from rich.text import Text

from maxpane_dashboard.widgets.fmt import DASH, fmt_int
from maxpane_dashboard.widgets.markup_safety import flatten, safe_markup, sanitize_cell
from maxpane_dashboard.widgets.panels import UNAVAILABLE, HeroBoxBase, HeroRow
from maxpane_dashboard.widgets.rowfit import clip
from ._swarm_summary import launch_counts, row_counts, summary_body

__all__ = [
    "BOX_IDS",
    "SurfSwarmHeroBox",
    "SurfSwarmHero",
]

#: ``(widget id, label)`` per box, in row order (plan §2's hero line).
BOXES: tuple[tuple[str, str], ...] = (
    ("surf-swarm-hero-agents", "AGENTS"),
    ("surf-swarm-hero-working", "WORKING"),
    ("surf-swarm-hero-accepted", "ACCEPTED 24h"),
    ("surf-swarm-hero-launches", "LAUNCHES"),
    ("surf-swarm-hero-workflows", "WORKFLOWS"),
    ("surf-swarm-hero-sites", "SITES"),
)

BOX_IDS: tuple[str, ...] = tuple(box_id for box_id, _label in BOXES)

_VALUE_STYLE = "bold white"


def _int_or_none(value) -> int | None:
    """``fmt_int``'s own acceptance, as a predicate: ``None`` when it would dash."""
    if value is None or isinstance(value, bool):
        return None
    text = fmt_int(value)
    return None if text == DASH else int(value)


def _value(text: str) -> str:
    return f"[{_VALUE_STYLE}]{safe_markup(text)}[/]"


# -- box bodies -----------------------------------------------------------------


def _agents_body(online, enrolled) -> str:
    """``online/enrolled``; ``--`` for a missing half; unavailable for both."""
    o = _int_or_none(online)
    e = _int_or_none(enrolled)
    if o is None and e is None:
        return UNAVAILABLE
    return _value(f"{fmt_int(o)}/{fmt_int(e)}")


def _count_body(value) -> str:
    """One grouped integer; ``0`` is a number; ``None`` is unavailable."""
    if _int_or_none(value) is None:
        return UNAVAILABLE
    return _value(fmt_int(value))


def _working_body(value) -> Text:
    count = _int_or_none(value)
    if count is None:
        return Text.from_markup(UNAVAILABLE)
    if count == 0:
        return Text().append("0", style="bold dim").append(" quiet", style="dim")
    return Text(fmt_int(count), style="bold green")


class SurfSwarmHeroBox(HeroBoxBase):
    """One swarm hero box. No geometry here: the stylesheet names this class."""


class SurfSwarmHero(HeroRow):
    """AGENTS · WORKING · ACCEPTED 24h · QUEUE · BREAKER · SERVICES."""

    BOX_CLASS = SurfSwarmHeroBox
    BOXES = BOXES

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        #: Keep the raw payload so a resize fits whole status pairs to the
        #: box's new width rather than retaining the previous selection.
        self._payload: dict | None = None

    def update_data(
        self,
        swarm_agents_online=None,
        swarm_agents_enrolled=None,
        swarm_working_now=None,
        swarm_accepted_today=None,
        swarm_launch_summary=None,
        swarm_workflow_rows=None,
        swarm_site_rows=None,
        **_kwargs,
    ) -> None:
        """Refresh all six boxes; every box is written on every poll (MEDI-38).

        ``**_kwargs`` is mandatory: the screen splats the whole flat dict.
        """
        self._payload = {
            "online": swarm_agents_online,
            "enrolled": swarm_agents_enrolled,
            "working": swarm_working_now,
            "accepted": swarm_accepted_today,
            "launches": swarm_launch_summary,
            "workflows": swarm_workflow_rows,
            "sites": swarm_site_rows,
        }
        self._render_view()

    def on_resize(self, _event=None) -> None:
        if self._payload is not None:
            self._render_view()

    def _box_width(self, box_id: str) -> int:
        """The box's own content width, measured in situ; ``0`` before layout."""
        try:
            return max(self.query_one(f"#{box_id}", HeroBoxBase).content_size.width, 0)
        except Exception:
            return 0

    def _render_view(self) -> None:
        data = self._payload or {}
        agents, working, accepted, launches, workflows, sites = BOX_IDS
        self.render_box(
            f"#{agents}", "AGENTS",
            lambda: _agents_body(data.get("online"), data.get("enrolled")),
        )
        self.render_box(
            f"#{working}", "WORKING", lambda: _working_body(data.get("working")),
        )
        self.render_box(
            f"#{accepted}", "ACCEPTED 24h", lambda: _count_body(data.get("accepted")),
        )
        for box_id, label, summary in (
            (launches, "LAUNCHES", launch_counts(data.get("launches"))),
            (workflows, "WORKFLOWS", row_counts(data.get("workflows"))),
            (sites, "SITES", row_counts(data.get("sites"), sites=True)),
        ):
            self.render_box(f"#{box_id}", label,
                            lambda s=summary, b=box_id: summary_body(s, self._box_width(b)))

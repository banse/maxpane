"""The approved SWARM rack hero, driven only by projected primitives."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Grid

from maxpane_dashboard.widgets.markup_safety import flatten
from ._fmt import fmt_age
from .news_hero import HeroRecord, NewsHeroCard, _clock, _count, _number


def swarm_records(payload: dict | None) -> tuple[HeroRecord, ...]:
    """Format summaries without turning missing reads into empty collections."""
    payload = payload if isinstance(payload, dict) else {}
    records = []
    for key, title, heading, footer in (
        ("fleet", "FLEET", "STATS", "AGENTS"),
        ("output", "OUTPUT", "24H", "24H"),
        ("workflows", "WORKFLOWS", "STATUS", "JOBS"),
        ("launches", "LAUNCHES", "STATUS", "DEPLOYMENTS"),
        ("workflow", "LATEST WORKFLOW", "OBJECTIVE", "WORKFLOW"),
        ("sites", "SITES", "CURRENT", "ENS"),
    ):
        section = payload.get(key)
        section = section if isinstance(section, dict) else {}
        state = section.get("state")
        state = state if state in ("ok", "stale", "unavailable") else "unavailable"
        available = state != "unavailable"
        fields = dict(key=key, title=title, heading=heading, footer=footer,
                      state=state, read_ts=_number(section.get("read_ts")), accent=state == "ok")
        if key in ("fleet", "output"):
            labels = ("online", "working", "enrolled") if key == "fleet" else ("steps", "jobs", "oracles")
            fields["stats"] = tuple((label, _count(section.get(label)) if available else "--") for label in labels)
            if key == "output":
                raw_points = section.get("points")
                points = tuple(_number(point) for point in raw_points) if isinstance(raw_points, (list, tuple)) else ()
                points_state = section.get("points_state")
                if points_state == "ok" and len(points) >= 2 and None not in points:
                    fields["points"] = points
                elif points_state == "stale":
                    fields["footer"] = "24H stale " + _clock(section.get("points_read_ts"))
                else:
                    fields["footer"] = "24H unavailable"
        elif key in ("workflows", "launches"):
            total = _count(section.get("total")) if available else "--"
            fields["subtitle"] = f"{total} cached"
            statuses = section.get("statuses") if available else None
            if isinstance(statuses, list):
                fields["stats"] = tuple((flatten(row.get("status")) or "unknown", _count(row.get("count")))
                                        for row in statuses[:3] if isinstance(row, dict))
                if not statuses:
                    fields["preview"] = f"No {key} in cache" if total == "0" else "Status unavailable"
            else:
                fields["preview"] = "unavailable"
        elif key == "workflow":
            objective = flatten(section.get("objective")) if available else ""
            age = _number(section.get("age_s")) if available else None
            status = flatten(section.get("status")) if available else ""
            if not available:
                fields["preview"] = "unavailable"
            elif objective:
                fields["preview"] = objective
            else:
                fields["preview"] = "Objective unavailable" if age is not None or status else "No workflows in cache"
            fields["subtitle"] = fmt_age(age) + " ago" if age is not None else ""
            fields["footer"] = status.upper() or footer
            fields["accent"] = state == "ok" and bool(objective)
        else:
            fields["digits"] = _count(section.get("count")) if available else "--"
            fields["subtitle"] = "named sites"
            fields["accent"] = state == "ok" and fields["digits"] != "--"
        records.append(HeroRecord(**fields))
    return tuple(records)


class SurfSwarmRackHero(Grid):
    """Six equal cards above the SWARM body, sharing the news rack renderer."""

    DEFAULT_CSS = """
    SurfSwarmRackHero { width: 1fr; height: 9; grid-size: 6 1; grid-columns: 1fr;
        grid-rows: 9; grid-gutter: 0 1; }
    """

    def compose(self) -> ComposeResult:
        for record in swarm_records(None):
            yield NewsHeroCard(record)

    def update_data(self, *, surf_swarm_hero: dict | None = None, **kwargs):
        for record in swarm_records(surf_swarm_hero):
            self.query_one(f"#hero-{record.key}", NewsHeroCard).set_record(record)

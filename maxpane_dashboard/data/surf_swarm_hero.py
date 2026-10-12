"""Pure six-card SWARM projections of already-read, independently dated data."""
from __future__ import annotations

from maxpane_dashboard.analytics.surf_launch_sites import is_current_site
from maxpane_dashboard.analytics.surf_swarm_signals import count_by
from maxpane_dashboard.analytics.surfboard import count, hourly_points
from maxpane_dashboard.data.surf_news_hero import _metadata, _stamp


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _numbers(metadata: dict, values: dict, fields: dict) -> dict:
    result = dict(metadata, **{key: count(values.get(field)) for key, field in fields.items()})
    if result["state"] == "unavailable" or all(result[key] is None for key in fields):
        result.update(state="unavailable", **dict.fromkeys(fields))
    return result


def _workflows(rows: object, metadata: dict, now: float) -> tuple[dict, dict]:
    summary = dict(metadata, total=None, statuses=None)
    latest = dict(metadata, objective=None, age_s=None, status=None)
    if not isinstance(rows, list) or metadata["state"] == "unavailable":
        return dict(summary, state="unavailable"), dict(latest, state="unavailable")
    populated = bool(rows)
    rows = [row for row in rows if isinstance(row, dict)]
    summary.update(total=len(rows), statuses=count_by((_text(row.get("status")) for row in rows), "status"))
    candidates = [(stamp, _text(row.get("workflow_id")) or "", row)
                  for row in rows if (stamp := _stamp(row.get("created_ts"), now)) is not None]
    if candidates:
        stamp, _, row = max(candidates, key=lambda item: (item[0], item[1]))
        latest.update(objective=_text(row.get("objective")), age_s=now - stamp, status=_text(row.get("status")))
    elif populated:
        latest["state"] = "unavailable"
    return summary, latest


def _launches(summary: object, metadata: dict) -> dict:
    result = dict(metadata, total=None, statuses=None)
    rows = _dict(summary).get("by_status")
    if not isinstance(rows, list) or metadata["state"] == "unavailable":
        return dict(result, state="unavailable")
    counts = {}
    for row in rows:
        if not isinstance(row, dict) or _text(row.get("status")) is None or count(row.get("count")) is None:
            return dict(result, state="unavailable")
        status = row["status"]
        if status in counts:
            return dict(result, state="unavailable")
        counts[status] = row["count"]
    result.update(total=sum(counts.values()), statuses=[dict(status=status, count=value)
                  for status, value in sorted(counts.items(), key=lambda item: (-item[1], item[0]))])
    return result


def project(*, overview: object, hourly: object, workflow_rows: object, workflow_source: dict,
            launch_summary: object, launch_source: dict, site_rows: object, site_source: dict,
            now: float) -> dict:
    """Keep metric clocks separate from hourly history and catalogue clocks."""
    sources = dict(overview=overview, hourly=hourly, workflows=workflow_source,
                   launches=launch_source, sites=site_source)
    metadata = {name: _metadata(sources, name, now) for name in sources}
    values = _dict(_dict(overview).get("payload")).get("overview")
    values = _dict(values)
    fleet = _numbers(metadata["overview"], values,
                     dict(online="agents_online", working="working_now", enrolled="seats_enrolled"))
    output = _numbers(metadata["overview"], values,
                      dict(steps="accepted_24h", jobs="jobs_24h", oracles="oracles_24h"))
    points = hourly_points(_dict(_dict(hourly).get("payload")).get("accepted"))
    history = metadata["hourly"]
    if points is None or history["state"] == "unavailable":
        points, history = None, dict(history, state="unavailable")
    output.update(points=points, points_state=history["state"], points_read_ts=history["read_ts"])
    workflows, latest = _workflows(workflow_rows, metadata["workflows"], now)
    sites = dict(metadata["sites"], count=None)
    if isinstance(site_rows, list) and sites["state"] != "unavailable":
        sites["count"] = sum(is_current_site(row) for row in site_rows)
    else:
        sites["state"] = "unavailable"
    return dict(fleet=fleet, output=output, workflows=workflows,
                launches=_launches(launch_summary, metadata["launches"]), workflow=latest, sites=sites)

"""Persist worker transitions and recorded work; never reset on heartbeats.

Only ``observe`` records an actual /workers attempt. ``project`` is a pure clock
projection, so repainting or switching seats cannot refresh a source or stop.
The activity anchor is the latest observed busy→idle read or own-work submission.
Recorded submissions recover work missed between polls, including before startup.
"""
from __future__ import annotations

import math
from collections.abc import Mapping

from .surf_swarm import coerce_seat_slot, coerce_workers_slot, seat_work_rows


WINDOW_SECONDS = 86400.0
FRESH_SECONDS = 300.0
MAX_SEATS = 4096
_MAX_TOKEN = 2 ** 256 - 1
_SOURCE_FIELDS = {"attempt_ts", "read_ts", "ok", "complete", "seats"}
_POINT_FIELDS = {"state", "known", "stopped_ts", "seen_ts"}


def _stamp(value: object, now: float) -> bool:
    return (type(value) in (int, float) and 0 <= value <= now
            and math.isfinite(value))


def _token(value: object) -> bool:
    return type(value) is int and 0 <= value <= _MAX_TOKEN


def _key(value: object) -> bool:
    return (isinstance(value, str) and 0 < len(value) <= 78
            and value.isascii() and value.isdecimal()
            and str(int(value)) == value and _token(int(value)))


def _bounded(seats: dict) -> dict:
    if len(seats) <= MAX_SEATS:
        return seats
    return dict(sorted(seats.items(), key=lambda pair: (-pair[1]["seen_ts"], int(pair[0])))[:MAX_SEATS])


def coerce(payload: object, *, now: float) -> dict | None:
    """Validate source clocks and each persisted seat; bad points stay unknown."""
    if not _stamp(now, now) or not isinstance(payload, Mapping) or set(payload) != _SOURCE_FIELDS:
        return None
    attempt, read = payload["attempt_ts"], payload["read_ts"]
    if (not _stamp(attempt, now) or type(payload["ok"]) is not bool
            or type(payload["complete"]) is not bool or not isinstance(payload["seats"], Mapping)
            or read is not None and not _stamp(read, attempt)
            or payload["ok"] and read != attempt
            or read is None and (payload["seats"] or payload["complete"])):
        return None
    seats = {}
    complete = payload["complete"]
    for token, point in payload["seats"].items():
        if (not _key(token) or not isinstance(point, Mapping) or set(point) != _POINT_FIELDS
                or point["state"] not in (None, "busy", "idle")
                or type(point["known"]) is not bool
                or point["state"] is None and point["known"]
                or not _stamp(point["seen_ts"], read)
                or point["stopped_ts"] is not None and (
                    point["state"] != "idle" or not _stamp(point["stopped_ts"], read))):
            complete = False
            continue
        seats[token] = dict(point)
    if len(seats) > MAX_SEATS:
        complete = False
    return {"attempt_ts": float(attempt), "read_ts": float(read) if read is not None else None,
            "ok": payload["ok"], "complete": complete, "seats": _bounded(seats)}


def _recorded_work(seat_records: object, now: float) -> dict:
    recorded = {}
    records = coerce_seat_slot(seat_records, now=now) or {"seats": {}}
    for token, record in records["seats"].items():
        worked = max((row["submitted_ts"] for row in seat_work_rows(record["seat"])
                      if _stamp(row["submitted_ts"], min(now, record["read_ts"]))), default=None)
        if worked is not None:
            recorded[int(token)] = worked
    return recorded


def with_records(prior: object, seat_records: object, *, now: float) -> dict | None:
    """Backfill idle anchors without turning a seat read into a workers observation."""
    source = coerce(prior, now=now)
    if source is None or source['read_ts'] is None or not source['ok']:
        return source
    for token, worked in _recorded_work(seat_records, now).items():
        # Work newer than the presence evidence needs the next workers read.
        if worked > source['read_ts']:
            continue
        key = str(token)
        point = source['seats'].get(key)
        if point is None and source['complete']:
            point = dict(state='idle', known=True, stopped_ts=None, seen_ts=source['read_ts'])
        if point is not None and point['known'] and point['state'] == 'idle':
            point['stopped_ts'] = max(worked, point['stopped_ts'] or 0.0)
            source['seats'][key] = point
    return coerce(source, now=now)


def observe(prior: object, workers: object, *, now: float, seat_records: object = None) -> dict:
    """Fold one normalized workers read (None means failure) into seat history.

    ``state`` remembers the last known state through unknown counters. ``known``
    states whether this read actually confirmed it. Positive work on any device
    proves busy; a missing seat proves idle only in a complete successful list.
    ``seen_ts`` bounds the history by most recent presence, including unknowns.
    Cached own-work submissions can advance an idle anchor without an observed
    transition. Acceptance and feedback timestamps never count as execution.
    """
    if not _stamp(now, now):
        raise ValueError("activity observation needs a finite nonnegative clock")
    result = coerce(prior, now=now) or {
        "read_ts": None, "ok": False, "complete": False, "seats": {},
    }
    result["attempt_ts"] = float(now)
    source = coerce_workers_slot(workers)
    result["ok"] = source is not None
    if source is None:
        return result

    recorded = _recorded_work(seat_records, now)
    result["read_ts"] = float(now)
    complete = source["count"] == len(source["workers"]) and not source["malformed_tokens"]
    groups: dict[int, list] = {}
    for row in source["workers"]:
        if not _token(row["token_id"]):
            complete = False
            continue
        groups.setdefault(row["token_id"], []).append(row["working"])
    seats = result["seats"]
    for token in set(groups) | {int(key) for key in seats} | set(recorded):
        key = str(token)
        point = seats.get(key, {"state": None, "known": False, "stopped_ts": None, "seen_ts": now})
        counts = groups.get(token)
        state = None
        if counts is not None:
            point["seen_ts"] = float(now)
            if any(count is not None and count > 0 for count in counts):
                state = "busy"
            elif all(count == 0 for count in counts) and token not in source["malformed_tokens"]:
                state = "idle"
        elif complete:
            state = "idle"
        point["known"] = state is not None
        if state == "busy":
            point["stopped_ts"] = None
        elif state == "idle" and point["state"] == "busy":
            point["stopped_ts"] = float(now)
        if state == "idle" and token in recorded:
            point["stopped_ts"] = max(recorded[token], point["stopped_ts"] or 0.0)
        if state is not None:
            point["state"] = state
        seats[key] = point
    result["complete"] = complete and len(seats) <= MAX_SEATS
    result["seats"] = _bounded(seats)
    return result


def project(payload: object, token: object, *, now: float) -> dict:
    """Return footer facts; stale/failed/unknown reads never display a live bar."""
    result = {"state": "unavailable", "remaining": None, "as_of": None, "stopped_ts": None}
    source = coerce(payload, now=now)
    if source is None or not _token(token):
        return result
    result["as_of"] = source["read_ts"]
    point = source["seats"].get(str(token))
    if point is not None:
        result["stopped_ts"] = point["stopped_ts"]
    if source["read_ts"] is None:
        return result
    if not source["ok"] or now - source["read_ts"] > FRESH_SECONDS:
        result["state"] = "stale"
        return result
    if point is None:
        if source["complete"]:
            result["state"] = "idle"
        return result
    if not point["known"]:
        return result
    result["state"] = point["state"]
    if point["state"] == "busy":
        result["remaining"] = WINDOW_SECONDS
    elif point["stopped_ts"] is not None:
        result["remaining"] = max(0.0, WINDOW_SECONDS - (now - point["stopped_ts"]))
    return result


def meter(observed: dict, live_state: object, *, now: float) -> dict:
    """Shared rack meter: green→orange in 24h, then orange→empty by 72h."""
    state = observed["state"]
    if state == "idle" and live_state == "offline":
        state = "offline"
    result = dict(meter_kind="activity", meter_state=state,
                  numerator=observed["remaining"], denominator=WINDOW_SECONDS)
    if state == "idle" and observed["stopped_ts"] is not None:
        elapsed = now - observed["stopped_ts"]
        if elapsed >= WINDOW_SECONDS:
            result.update(meter_kind="activity-cooldown",
                          numerator=max(0.0, 3 * WINDOW_SECONDS - elapsed), denominator=2 * WINDOW_SECONDS)
    return result


__all__ = ["observe", "with_records", "coerce", "project", "meter"]

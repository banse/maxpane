"""Surf AGENT RECORD's view: the read window, the ``f`` filter, and what it cannot know yet.

``docs/surf_record_filter_spec.md``. The window is the **base** filter -- the
``all`` / ``not completed`` mode plus NODE, STATE and WHEN -- clamped to the
40..400 cap, and it is the one function both the manager (which reads answers,
job details and panels only inside it) and RECORD (which paints it) call. The
read-dependent groups -- MODEL, PANEL, ANSWER, TOOK, TOK -- never decide what is
read, which would be circular: each answers yes, no or *unknown* per row in the
window, and a row nobody has read yet is counted, never shown and never dropped.

Pure: stdlib plus two pure analytics modules (``range_filters`` for the from/to
rules THE LIST uses, ``surf_swarm_signals.record_state``). No clock: WHEN becomes
an absolute ``since_ts`` from the ``now_ts`` the caller injects at apply.
"""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, NamedTuple

from maxpane_dashboard.analytics.range_filters import (
    FilterValidationError,
    check_order,
    parse_number,
)
from maxpane_dashboard.analytics.surf_swarm_signals import count_by, record_state

__all__ = [
    "ANSWER_STATES", "PANEL_STATES", "WHEN_SECONDS", "MATCH", "NO", "NOT_READ", "UNAVAILABLE",
    "RecordFilter", "RecordView", "parse_record_filter", "record_base_match",
    "record_filter_choices", "record_output_tokens", "record_read_match", "record_readable",
    "record_selected", "record_served", "record_time", "record_took_minutes", "record_view",
    "record_window",
]

#: RECORD shows 40 rows, ``more`` grows it by 20, the answers slot retains 400.
_MIN_CAP, _MAX_CAP = 40, 400

#: WHEN's dropdown words; ``any`` is no cutoff. Applied once, at apply time.
WHEN_SECONDS = {"24h": 86_400, "7d": 7 * 86_400, "30d": 30 * 86_400}

#: PANEL's dropdown words -> the ``panel_state`` values
#: (``data/surf_swarm.enrich_panel_rows``) each one matches.
PANEL_STATES = {
    "agreed": ("agreed",),
    "outvoted": ("outvoted",),
    "no_quorum": ("no_quorum_in", "no_quorum_out"),
    "assessing": ("assessing",),
    "blocked": ("blocked",),
    "off_panel": ("off_panel",),
    "unavailable": ("unavailable",),
}

#: ANSWER's dropdown words -> the ``answer_state`` values each one matches.
ANSWER_STATES = {
    "replied": ("read",),
    "no_reply": ("no_reply",),
    "not_served": ("not_served",),
    "unavailable": ("unavailable",),
}

#: One row's verdict under the read-dependent groups.
MATCH, NO, NOT_READ, UNAVAILABLE = "match", "no", "not_read", "unavailable"

#: The rows the seat cycle can read: a canonical lower-case UUID job id and a
#: 64-hex submission hash -- ``data/surf_swarm_client.parse_job_id`` and
#: ``data/surf_swarm._hex64``, restated (analytics may not import ``data/``)
#: and bound to them by ``tests/analytics/test_surf_record_filter.py``.
_JOB_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_HASH = re.compile(r"[0-9a-fA-F]{64}")

#: The submission facts the usage columns show (``answer_state`` read or no_reply).
_SERVED = ("read", "no_reply")
_ORACLE_NODE_KEYS = ("oracle_assess",)
_RANGES = (("took_min", "took_max"), ("tok_min", "tok_max"))


@dataclass(frozen=True)
class RecordFilter:
    """The applied filter: every group ANDs, ticked options inside one group OR."""

    nodes: frozenset[str] = frozenset()
    states: frozenset[str] = frozenset()
    #: The reader's WHEN word, kept for the summary; ``since_ts`` is what filters.
    when: str = "any"
    since_ts: float | None = None
    models: frozenset[str] = frozenset()
    panel: str = "any"
    answer: str = "any"
    #: Minutes, compared against the whole minutes the ``took`` column shows.
    took_min: float | None = None
    took_max: float | None = None
    tok_min: int | None = None
    tok_max: int | None = None

    @property
    def base_active(self) -> bool:
        return bool(self.nodes or self.states or self.since_ts is not None)

    @property
    def reads_active(self) -> bool:
        return bool(self.models or self.panel != "any" or self.answer != "any"
                    or any(v is not None for v in (self.took_min, self.took_max,
                                                   self.tok_min, self.tok_max)))

    @property
    def active(self) -> bool:
        """An empty filter is not an empty result (THE LIST's rule): it is no filter."""
        return self.base_active or self.reads_active


class RecordView(NamedTuple):
    """What RECORD paints: matching rows, base rows past the cap, and the unknowns."""

    rows: tuple[Mapping[str, Any], ...]
    older: int
    not_read: int
    unavailable: int


def _string_set(field: str, raw: object) -> frozenset[str]:
    if isinstance(raw, str):
        raise FilterValidationError(field, f"invalid {field}")
    try:
        items = frozenset(raw if raw is not None else ())
    except TypeError as exc:
        raise FilterValidationError(field, f"invalid {field}") from exc
    if not all(isinstance(item, str) and item for item in items):
        raise FilterValidationError(field, f"invalid {field}")
    return items


def parse_record_filter(values: Mapping[str, object], *, now_ts: float) -> RecordFilter:
    """The editor's primitive values -> a :class:`RecordFilter`, or :class:`FilterValidationError`.

    ``now_ts`` fixes WHEN's cutoff: a stated ``since``, never a window that
    slides while the app is open. Re-applying recomputes it.
    """
    parsed: dict[str, Any] = {
        "took_min": parse_number("took_min", values.get("took_min"), integer=False),
        "took_max": parse_number("took_max", values.get("took_max"), integer=False),
        "tok_min": parse_number("tok_min", values.get("tok_min"), integer=True),
        "tok_max": parse_number("tok_max", values.get("tok_max"), integer=True),
    }
    for field, allowed in (("when", WHEN_SECONDS), ("panel", PANEL_STATES),
                           ("answer", ANSWER_STATES)):
        value = values.get(field, "any")
        if not isinstance(value, str) or (value != "any" and value not in allowed):
            raise FilterValidationError(field, f"invalid {field}")
        parsed[field] = value
    for field in ("nodes", "states", "models"):
        parsed[field] = _string_set(field, values.get(field))
    check_order(parsed, _RANGES)
    when = parsed["when"]
    if when != "any":
        if isinstance(now_ts, bool) or not isinstance(now_ts, (int, float)) or not math.isfinite(now_ts):
            raise FilterValidationError("when", "no clock to anchor when")
        parsed["since_ts"] = now_ts - WHEN_SECONDS[when]
    return RecordFilter(**parsed)


def _finite(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return value


def record_time(row: Mapping[str, Any]) -> float | None:
    """The time RECORD's ``when`` column shows: submitted, else accepted."""
    submitted = row.get("submitted_ts")
    return _finite(submitted if submitted is not None else row.get("accepted_ts"))


def record_served(row: Mapping[str, Any]) -> bool:
    """Whether RECORD's model / took / tok cells show this row's submission facts."""
    return row.get("answer_state") in _SERVED


def record_took_minutes(row: Mapping[str, Any]) -> int | None:
    """The whole minutes RECORD's took cell shows, and TOOK compares."""
    took = _finite(row.get("took_s"))
    return int(took) // 60 if took is not None and took >= 0 else None


def record_output_tokens(row: Mapping[str, Any]) -> int | None:
    """The output tokens RECORD's tok cell shows, and TOK compares: strict ints."""
    tok = row.get("output_tokens")
    return tok if type(tok) is int and tok >= 0 else None


def record_readable(row: Mapping[str, Any]) -> bool:
    """Whether the seat cycle can ever read this row's submission or panel."""
    job, key = row.get("job_id"), row.get("submission_hash")
    return (isinstance(job, str) and _JOB_ID.fullmatch(job) is not None
            and isinstance(key, str) and _HASH.fullmatch(key) is not None)


def record_base_match(row: Mapping[str, Any], spec: RecordFilter | None) -> bool:
    """NODE, STATE and WHEN: known for every row, so they shape the read window."""
    if spec is None:
        return True
    if spec.nodes:
        node = row.get("node_key")
        if not isinstance(node, str) or node not in spec.nodes:
            return False
    if spec.states:
        state = record_state(row)
        if not isinstance(state, str) or state not in spec.states:
            return False
    if spec.since_ts is not None:
        ts = record_time(row)
        if ts is None or ts < spec.since_ts:
            return False
    return True


def _in_range(value: float | None, low, high) -> bool:
    if low is None and high is None:
        return True
    if value is None:
        return False
    return (low is None or value >= low) and (high is None or value <= high)


def _usage_verdicts(row: Mapping[str, Any], spec: RecordFilter, readable: bool) -> list[str]:
    """MODEL, TOOK and TOK: facts of one exact-hash submission read."""
    groups = []
    if spec.models:
        model = row.get("model")
        groups.append(isinstance(model, str) and model in spec.models)
    if spec.took_min is not None or spec.took_max is not None:
        groups.append(_in_range(record_took_minutes(row), spec.took_min, spec.took_max))
    if spec.tok_min is not None or spec.tok_max is not None:
        groups.append(_in_range(record_output_tokens(row), spec.tok_min, spec.tok_max))
    if not groups:
        return []
    state = row.get("answer_state")
    if record_served(row):
        return [MATCH if ok else NO for ok in groups]
    if readable and state == "not_read":
        return [NOT_READ]
    if readable and state == "unavailable":
        return [UNAVAILABLE]
    return [NO]  # not served, or a row no read can ever reach


def _select_verdict(state: object, selected: tuple[str, ...], readable: bool) -> str:
    """One dropdown group: a read state compares; a pending one is unknown unless chosen."""
    if isinstance(state, str) and state in selected:
        return MATCH
    if readable and state == "not_read":
        return NOT_READ
    if readable and state == "unavailable" and "unavailable" not in selected:
        return UNAVAILABLE
    return NO


def record_read_match(row: Mapping[str, Any], spec: RecordFilter | None) -> str:
    """:data:`MATCH`, :data:`NO`, :data:`NOT_READ` or :data:`UNAVAILABLE` for one row.

    Any ``no`` decides; otherwise any unknown makes the row unknown, and
    *not read yet* wins over *unavailable* (it drains as reads land).
    """
    if spec is None or not spec.reads_active:
        return MATCH
    readable = record_readable(row)
    verdicts = _usage_verdicts(row, spec, readable)
    if spec.answer != "any":
        verdicts.append(_select_verdict(row.get("answer_state"), ANSWER_STATES[spec.answer],
                                        readable))
    if spec.panel != "any":
        oracle = row.get("node_key") in _ORACLE_NODE_KEYS
        verdicts.append(_select_verdict(row.get("panel_state"), PANEL_STATES[spec.panel],
                                        readable) if oracle else NO)
    if NO in verdicts:
        return NO
    if NOT_READ in verdicts:
        return NOT_READ
    if UNAVAILABLE in verdicts:
        return UNAVAILABLE
    return MATCH


def _cap(cap: object) -> int:
    if isinstance(cap, bool) or not isinstance(cap, int):
        return _MIN_CAP
    return max(_MIN_CAP, min(_MAX_CAP, cap))


def record_selected(rows: object, open_only: bool,
                    spec: RecordFilter | None = None) -> list[Mapping[str, Any]]:
    """Valid rows in source order, through the mode and the base filter; unclamped."""
    if not isinstance(rows, (list, tuple)):
        return []
    return [row for row in rows if isinstance(row, Mapping)
            and (not open_only or record_state(row) != "completed")
            and record_base_match(row, spec)]


def record_window(rows: object, cap: int, open_only: bool,
                  spec: RecordFilter | None = None) -> list[Mapping[str, Any]]:
    """The read window: filter before windowing, source order, 40..400 rows."""
    return record_selected(rows, open_only, spec)[:_cap(cap)]


def record_view(rows: object, cap: int, open_only: bool,
                spec: RecordFilter | None = None) -> RecordView:
    """What RECORD paints from the window, with the rows it cannot judge yet counted."""
    selected = record_selected(rows, open_only, spec)
    cap = _cap(cap)
    window, older = selected[:cap], max(0, len(selected) - cap)
    shown: list[Mapping[str, Any]] = []
    not_read = unavailable = 0
    for row in window:
        verdict = record_read_match(row, spec)
        if verdict == MATCH:
            shown.append(row)
        elif verdict == NOT_READ:
            not_read += 1
        elif verdict == UNAVAILABLE:
            unavailable += 1
    return RecordView(tuple(shown), older, not_read, unavailable)


def record_filter_choices(rows: object, spec: RecordFilter | None = None) -> dict[str, tuple[str, ...]]:
    """The seat's own NODE / STATE / MODEL options, most frequent first.

    Over every row (the lifetime list, not the window); MODEL only over rows
    whose submission read served one. Anything ``spec`` already selects is
    kept, so a stored choice is always visible and removable.
    """
    valid = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, (list, tuple)) else []

    def strings(values) -> list[str]:
        return [value for value in values if isinstance(value, str) and value]

    def ordered(values, kept) -> tuple[str, ...]:
        found = [item["value"] for item in count_by(strings(values), "value")]
        return tuple(found + sorted(set(kept) - set(found)))

    return {
        "nodes": ordered((row.get("node_key") for row in valid), spec.nodes if spec else ()),
        "states": ordered((record_state(row) for row in valid), spec.states if spec else ()),
        "models": ordered((row.get("model") for row in valid if row.get("answer_state") in _SERVED),
                          spec.models if spec else ()),
    }

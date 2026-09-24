"""Pure rollups for the surf ``s`` SWARM and ``a`` AGENT bodies (swarm v2 plan §1.6).

Stdlib only.  Imports nothing from ``maxpane_dashboard`` -- not ``data/``
(which reaches ``httpx``), not another analytics module -- so the widgets
that import this file cannot reach the network through it
(``tests/widgets/test_surf_widget_contract.py``'s recursive purity walk).
No clock: every ``now_ts`` is injected.  No Textual.

The fold that produces the rows these functions summarise lives in
``data/surf_swarm.py``; this module sees only numbers, strings and the
row dicts it is handed.  A failed read is ``None`` and stays ``None``; a
representable zero is ``0``.
"""
from __future__ import annotations

import math
import statistics
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

__all__ = [
    "completed_within", "count_by", "duration_stats", "launch_summary",
    "seen_since_ts", "skill_summary", "state_rollup", "record_state", "record_selected", "record_window",
]


def _number(value: object) -> float | None:
    """An int or float that is not a bool, else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def duration_stats(durations_s: Sequence[float]) -> dict[str, Any]:
    """``{"dur_median_s", "dur_p90_s", "dur_max_s"}`` over a sample.

    All three are ``None`` under two samples: one duration is a data point,
    not a distribution.  ``p90`` is nearest-rank on the sorted sample
    (``sorted[ceil(0.9 * n) - 1]``), so it is always a value that occurred,
    never an interpolation.
    """
    sample = sorted(v for v in durations_s if _number(v) is not None)
    n = len(sample)
    if n < 2:
        return {"dur_median_s": None, "dur_p90_s": None, "dur_max_s": None}
    rank = max(1, math.ceil(0.9 * n))
    return {
        "dur_median_s": statistics.median(sample),
        "dur_p90_s": sample[rank - 1],
        "dur_max_s": sample[-1],
    }


def count_by(values: Iterable[object], field: str, *,
             keep_none: bool = False) -> list[dict[str, Any]]:
    """``[{<field>: value, "count": n}]``, biggest first, ties by ``str(value)``.

    The generic behind every rollup here: cancel reasons, roles, judges,
    statuses, kinds, chains, rejection codes.  Every distinct value is its
    own bucket -- the vocabulary is open.  ``None`` is a failed read, not a
    value, and is dropped unless ``keep_none`` says otherwise; kept, it
    sorts after every real value of the same count.
    """
    counts: dict[object, int] = {}
    for value in values:
        if value is None and not keep_none:
            continue
        try:
            counts[value] = counts.get(value, 0) + 1
        except TypeError:  # an unhashable value (a list) is not a bucket
            continue
    ordered = sorted(counts.items(),
                     key=lambda kv: (-kv[1], kv[0] is None, str(kv[0])))
    return [{field: value, "count": count} for value, count in ordered]


def state_rollup(states: Iterable[object]) -> list[dict[str, Any]]:
    """``[{"state", "count"}]`` over every non-empty string state.

    Open vocabulary: a state the fold has never seen (``quarantined``) is
    its own bucket, never dropped and never folded into "other".
    """
    return count_by((s for s in states if isinstance(s, str) and s), "state")


def skill_summary(skill_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``{"total", "by_role", "by_judge", "requires_count"}`` off ``swarm_skill_rows``."""
    rows = [r for r in skill_rows if isinstance(r, Mapping)]
    return {
        "total": len(rows),
        "by_role": count_by((r.get("role") for r in rows), "role"),
        "by_judge": count_by((r.get("judge") for r in rows), "judge"),
        "requires_count": sum(1 for r in rows if r.get("requires")),
    }


def launch_summary(launch_rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """``{"by_status", "by_kind", "by_chain"}`` off ``swarm_launch_rows``."""
    rows = [r for r in launch_rows if isinstance(r, Mapping)]
    return {
        "by_status": count_by((r.get("status") for r in rows), "status"),
        "by_kind": count_by((r.get("kind") for r in rows), "kind"),
        "by_chain": count_by((r.get("chain_id") for r in rows), "chain_id"),
    }


def _entries(seen: object) -> list[Mapping[str, Any]]:
    """The seen slot's entries that are mappings; anything else is skipped.

    The slot is persisted to ``~/.maxpane/surf_cache.json`` and read back,
    so it is third-party input: a hand-edited or truncated file must not
    raise here.
    """
    if not isinstance(seen, Mapping):
        return []
    return [e for e in seen.values() if isinstance(e, Mapping)]


def seen_since_ts(seen: object) -> float | None:
    """The oldest ``created_ts`` in the seen slot -- how far back it reaches."""
    stamps = [e.get("created_ts") for e in _entries(seen)]
    numbers = [s for s in stamps if _number(s) is not None]
    return min(numbers) if numbers else None


def completed_within(seen: object, now_ts: float,
                     window_s: float) -> tuple[int | None, float | None]:
    """``(count, seen_since_ts)`` -- completions in the trailing window.

    The count is ``None`` while the slot has not yet observed a whole
    window (``seen_since_ts`` is ``None`` or younger than ``window_s``):
    the honest reading is "accumulating since HH:MM", and it is **never**
    ``0`` in that phase (plan R-A) -- a zero there would claim nothing
    completed when the truth is that nothing was watched.  Once the window
    has been observed, the count is the number of seen entries in state
    ``completed`` whose ``updated_ts`` falls inside it, and a real zero is a
    real zero.
    """
    since = seen_since_ts(seen)
    if since is None or now_ts - since < window_s:
        return None, since
    floor = now_ts - window_s
    count = 0
    for entry in _entries(seen):
        if entry.get("state") != "completed":
            continue
        updated = _number(entry.get("updated_ts"))
        if updated is not None and updated >= floor:
            count += 1
    return count, since


def record_state(row: object) -> str | None:
    """The attempt state, with accepted/pre-status rows taking the job state."""
    if not isinstance(row, Mapping):
        return None
    status = row.get("work_status")
    return row.get("job_state") if status in (None, "accepted") else status


def record_selected(rows: object, open_only: bool) -> list[Mapping[str, Any]]:
    """Valid rows in source order, filtered by the displayed state."""
    if not isinstance(rows, (list, tuple)):
        return []
    return [row for row in rows if isinstance(row, Mapping)
            and (not open_only or record_state(row) != "completed")]


def record_window(rows: object, cap: int, open_only: bool) -> list[Mapping[str, Any]]:
    """Filter before windowing; retain source order within the 40..400 view."""
    return record_selected(rows, open_only)[:max(40, min(400, cap))]

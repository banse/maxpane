"""COST and QUOTA blocks of the PEPEPANE status document (spec §7, §8 COST, §10; contract §C.9) -- pure.

Input: ledger task rows (``SeatLedger.rows()``, SEAT_ROW_KEYS["seat_tasks_rows"] shape, whose token
fields already follow the API-equal formulas of §10) and, optionally, raw session summaries of the
kinds that never become rows (``doctor``/``manual``/``unknown``) so they can be counted as excluded.

Rules carried here:

* tokens, never currency -- there is no price, estimate or dollar field in any output (spec §10);
* doctor and manual runs are excluded from every figure and only counted (spec §10 exclusions);
* a multi-file attempt adds tokens across files but NOT turns (fill3 §2: 73,695 + 1,263 = 74,958
  output, turns 61 != 58 + 8), so an attempt takes the max of its files' turns and is flagged ``xN``;
* buckets are keyed by ``(model, effort, ~tier)`` because tiers changed under us, and a tier change
  must not read as a cost move (spec §8 COST; measurement discipline §10);
* a failed read is ``None``, never ``0`` -- a window with rows but no token data has ``tokens: None``.

No I/O, no clock: ``now`` is always passed in.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import datetime, timezone

DAY_S = 86400
COUNTED_KINDS = frozenset({"code", "research", "fuzz", "task"})  #: ledger row kinds + the summariser's "task"
EXCLUDED_KINDS = ("doctor", "manual")  #: spec §10; "unknown" sessions are counted as manual (non-task runs)
AUTH_STATUSES = (401, 403)
BUCKET_KEYS = ("model", "effort", "tierDerived", "tasks", "turnsP50", "tokens", "wallP50S", "wallP90S", "ttftP50Ms",
               "turn1ContextP50", "maxTurnsHits", "authErrors")  #: == seat_models.SEAT_ROW_KEYS["seat_cost_buckets"]
TOKEN_CLASSES = ("input", "output", "cached", "cacheWrite")


def _epoch(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()
    return None


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def percentile(values: Sequence[float], p: float) -> float | None:
    """Nearest-rank percentile over the non-None numbers of *values*; ``None`` when there are none."""
    clean = sorted(v for v in (_num(x) for x in values) if v is not None)
    if not clean:
        return None
    rank = max(1, math.ceil(p / 100.0 * len(clean)))
    return clean[min(rank, len(clean)) - 1]


def _sum_tokens(items: Sequence[dict | None]) -> dict | None:
    present = [t for t in items if isinstance(t, dict)]
    if not present:
        return None
    return {k: sum(int(_num(t.get(k)) or 0) for t in present) for k in TOKEN_CLASSES}


def tokens_for_attempt(sessions: Sequence[dict]) -> dict:
    """Aggregate the session files of ONE attempt (fill3 §2; spec §5.4 multi-file cwds).

    Tokens are additive across files; turns are NOT summed (the API's 61 is neither 58 + 8 nor
    either file), so the attempt takes the max and ``sessionFiles`` > 1 flags it ``xN``.
    """
    ordered = sorted((s for s in sessions if isinstance(s, dict)), key=lambda s: _epoch(s.get("startedUtc")) or 0.0)
    turns = [int(t) for t in (_num(s.get("turns")) for s in ordered) if t is not None]
    ttft = [t for t in (_num(s.get("ttftMs")) for s in ordered) if t is not None]
    walls = [w for w in (_num(s.get("wallMs")) for s in ordered) if w is not None]
    first_context = next((int(c) for c in (_num(s.get("turn1Context")) for s in ordered) if c is not None), None)
    reached = [s.get("maxTurnsReached") for s in ordered if isinstance(s.get("maxTurnsReached"), bool)]
    errors: list = []
    side: dict | None = None
    for s in ordered:
        errors.extend(e for e in (s.get("apiErrors") or []) if isinstance(e, dict))
        sm = s.get("sideModel")
        if isinstance(sm, dict):
            side = side or {"model": sm.get("model"), "input": 0, "output": 0}
            side["input"] += int(_num(sm.get("input")) or 0)
            side["output"] += int(_num(sm.get("output")) or 0)
    newest = ordered[-1] if ordered else {}
    return {
        "tokens": _sum_tokens([s.get("tokens") for s in ordered]),
        "turns": max(turns) if turns else None,
        "turnsDefinition": next((s.get("turnsDefinition") for s in ordered if s.get("turnsDefinition")), None),
        "sessionFiles": len(ordered),
        "ttftMs": int(min(ttft)) if ttft else None,
        "wallMs": int(sum(walls)) if walls else None,
        "turn1Context": first_context,
        "maxTurnsReached": any(reached) if reached else None,
        "apiErrors": errors,
        "sideModelTokens": side,
        "model": newest.get("model"),
        "effort": newest.get("effort"),
    }


def bucket_key(row: dict) -> tuple[str | None, str | None, str | None]:
    """``(model, effort, tierDerived)`` -- compare only within a bucket (spec §10 measurement discipline)."""
    return (row.get("model"), row.get("effort"), row.get("tierDerived"))


def _row_time(row: dict) -> float | None:
    return _epoch(row.get("acceptedUtc")) or _epoch(row.get("startedUtc"))


def _auth_error(row: dict) -> bool:
    return any(isinstance(e, dict) and e.get("status") in AUTH_STATUSES for e in (row.get("apiErrors") or []))


def _seconds(ms) -> float | None:
    value = _num(ms)
    return None if value is None else value / 1000.0


def _round1(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def _int_or_none(value: float | None) -> int | None:
    return None if value is None else int(value)


def _bucket(key: tuple, rows: list[dict]) -> dict:
    walls = [_seconds(r.get("wallMs")) for r in rows]
    values = {
        "model": key[0], "effort": key[1], "tierDerived": key[2], "tasks": len(rows),
        "turnsP50": _int_or_none(percentile([r.get("turns") for r in rows], 50)),
        "tokens": _sum_tokens([r.get("tokens") for r in rows]),
        "wallP50S": _round1(percentile(walls, 50)), "wallP90S": _round1(percentile(walls, 90)),
        "ttftP50Ms": _int_or_none(percentile([r.get("ttftMs") for r in rows], 50)),
        "turn1ContextP50": _int_or_none(percentile([r.get("turn1Context") for r in rows], 50)),
        "maxTurnsHits": sum(1 for r in rows if r.get("maxTurnsReached") is True),
        "authErrors": sum(1 for r in rows if _auth_error(r)),
    }
    return {k: values[k] for k in BUCKET_KEYS}


def summarise(rows: Sequence[dict], *, window_days: int, now: float, side_model_rows: Sequence[dict] = (),
              sessions: Sequence[dict] = ()) -> dict:
    """The §7 ``cost`` block over the last *window_days* (``series`` is added by the caller).

    *rows*: ledger task rows (any doctor/manual/unknown-kind row is excluded, only counted);
    *sessions*: raw session summaries -- only their ``doctor``/``manual``/``unknown`` kinds are used, as
    excluded counts; *side_model_rows*: extra ``{"model","input","output"}`` side-model figures.
    """
    start = float(now) - window_days * DAY_S
    excluded = {kind: 0 for kind in EXCLUDED_KINDS}
    counted: list[dict] = []
    extra = [s for s in sessions if isinstance(s, dict) and s.get("kind") not in COUNTED_KINDS]
    for row in list(rows) + extra:
        if not isinstance(row, dict):
            continue
        when = _row_time(row)
        if when is None or when < start or when > float(now):
            continue
        kind = row.get("kind")
        if kind in COUNTED_KINDS:
            counted.append(row)
        elif kind == "doctor":
            excluded["doctor"] += 1
        else:
            excluded["manual"] += 1
    groups: dict[tuple, list[dict]] = {}
    for row in counted:
        groups.setdefault(bucket_key(row), []).append(row)
    buckets = [_bucket(key, members) for key, members in groups.items()]
    buckets.sort(key=lambda b: (-b["tasks"], str(b["model"]), str(b["effort"])))
    turns = [int(t) for t in (_num(r.get("turns")) for r in counted) if t is not None]
    side_sources = [r.get("sideModelTokens") for r in counted if isinstance(r.get("sideModelTokens"), dict)]
    side_sources += [s for s in side_model_rows if isinstance(s, dict)]
    side_model = None
    if side_sources:
        names = sorted({str(s.get("model")) for s in side_sources if s.get("model")})
        side_model = {"model": "+".join(names) or None,
                      "input": sum(int(_num(s.get("input")) or 0) for s in side_sources),
                      "output": sum(int(_num(s.get("output")) or 0) for s in side_sources),
                      "tasks": len(side_sources)}
    all_rows = [r for r in rows if isinstance(r, dict)]
    ledger_from = min((r.get("acceptedUtc") for r in all_rows if isinstance(r.get("acceptedUtc"), str)), default=None)
    sessions_from = min((r.get("acceptedUtc") for r in all_rows
                         if isinstance(r.get("acceptedUtc"), str) and isinstance(r.get("tokens"), dict)), default=None)
    return {
        "windowDays": window_days,
        "tasks": len(counted),
        "excluded": excluded,
        "turns": sum(turns) if turns else (0 if not counted else None),
        "tokens": _sum_tokens([r.get("tokens") for r in counted]) if counted else {k: 0 for k in TOKEN_CLASSES},
        "buckets": buckets,
        "sideModel": side_model,
        "depth": {"ledgerFromUtc": ledger_from, "sessionsFromUtc": sessions_from,
                  "expiredRows": sum(1 for r in all_rows if r.get("tokensReason") == "transcript expired"),
                  "skipped": {"oversize": None}},
    }


__all__ = [
    "DAY_S", "COUNTED_KINDS", "EXCLUDED_KINDS", "AUTH_STATUSES", "BUCKET_KEYS", "TOKEN_CLASSES",
    "percentile", "tokens_for_attempt", "bucket_key", "summarise",
]

"""Keyless reads of ``api.imd.fun`` for the PEPEPANE dashboard -- the fallback of spec §6.

Five routes, nothing else: ``/seats/<id>/standing`` (never with ``?queue=0``),
``/seats/<id>?work=N&reviews=0``, ``/jobs/<uuid>/submissions``, ``/services`` and
``/health``.  Every read is a keyless ``GET`` with ``Accept-Encoding: gzip`` and a
20 s timeout over the two-host pool of :mod:`surf_swarm_client`; a 5xx, a timeout
or a transport error is retried **once** (on the other pool host); a 4xx is an
answer about the request and is not retried.  A failed read is ``ApiResult(ok=False)``
with a ``reason`` -- never ``0``, never an empty list.  The body is parsed
tolerantly (control characters stripped, ``strict=False``), every ``summary`` key is
dropped before anything else sees it, and every remaining string passes the
redactor before it leaves this module.  The client remembers the newest good
result per route so a caller can keep rendering ``as of HH:MM`` through a 500.
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from maxpane_dashboard.analytics.seat_redact import strip_controls
from maxpane_dashboard.data.surf_swarm_client import SWARM_API_HOSTS

logger = logging.getLogger(__name__)

Clock = Callable[[], float]
Json = Any

# --- constants (contract §B "data/seat_api.py") ---------------------------------------
API_TIMEOUT_S = 20.0            #: spec §6: 20 s timeout on every read
API_RETRY_ONCE = True           #: spec §6: retry once on 5xx / timeout
RETRY_DELAY_S = 0.25            #: (invented) pause before the one retry; tests inject a no-op sleep
SEAT_WORK_ROWS = 60             #: /seats/<id>?work=60&reviews=0
SEAT_WORK_BACKFILL_ROWS = 1000  #: /seats/<id>?work=1000&reviews=0, install / --backfill-api only
SEAT_WORK_MAX_ROWS = 1000       #: (invented) the docs cap `work`/`reviews` at 0..1000; larger clamps upstream
MAX_REASONS_PER_CYCLE = 2       #: <=2 /jobs/<jobId>/submissions per cycle (surf's SLOT_SWARM_ANSWERS bound)
API_HOSTS = SWARM_API_HOSTS     #: the two-host pool (api.imd.fun -> Railway), imported, never redeclared
MAX_BODY_BYTES = 8 * 1024 * 1024  #: (invented) 13x the largest measured body (/seats/420 613 KB); bigger -> "body too large"
REQUEST_HEADERS: Mapping[str, str] = {"Accept": "application/json", "Accept-Encoding": "gzip"}

#: The plane's FailureReason wire enum (fill1 §4, cli.split.js:23593; docs/imd-api-changelog.md 2026-09-26)
#: plus the contract's `timeout` / `schema_invalid`.  Rendered as the enum word only (spec §6 rule 5);
#: anything else -> REASON_OTHER.
FAILURE_REASONS = (
    "runtime_error", "internal_error", "path_violation", "local_build_failed", "clone_failed",
    "timeout", "cancelled", "schema_invalid",
    "budget_exhausted", "lease_expired", "runtime_unavailable",
)
FAILURE_CLASSES = ("infrastructure", "machine", "unclear")
REASON_OTHER = "other"
WORK_STATUSES = ("accepted", "rejected", "failed", "pending")
COUNTER_KEYS = ("attempts", "accepted", "rejected", "failed", "pending")
WORK_ROW_KEYS = ("jobId", "objective", "jobState", "nodeKey", "role", "status", "submissionHash",
                 "submittedAt", "acceptedAt", "launch")
RUNNING_ROW_KEYS = ("jobId", "objective", "nodeKey", "role", "since")
RECENT_FAILURE_KEYS = ("at", "reason", "nodeKey", "jobId")
QUEUE_KEYS = ("ready", "eligible", "fleetOnline", "blocked", "asOfUtc")
STANDING_KEYS = (
    "working", "running", "consecutiveFailures", "pausedUntil", "lastFailedAt", "breaker", "recentFailures",
    "presenceConnected", "acceptingWork", "heartbeatAgeMs", "presenceStale", "daemonVersion", "maxConcurrency",
    "premiumAdvertised", "agentId", "enrollmentStatus", "devices", "queue", "asOfUtc",
)
SUBMISSION_KEYS = (
    "submissionHash", "hash12", "seatTokenId", "seatAgentId", "deviceKey8", "nodeKey", "role", "attempt",
    "outcome", "accepted", "failureReason", "failureClass", "usage", "createdAt",
)
USAGE_INT_KEYS = ("turns", "inputTokens", "outputTokens", "cachedInputTokens", "wallClockMs")
PLANE_KEYS = ("version", "verifierUp", "verifierLastSeenUtc", "verifierClaims", "awaitingVerdict",
              "connectedDaemons", "activeEnrollments", "computedAt", "asOfUtc")

_HEX64_RE = re.compile(r"[0-9a-f]{64}", re.ASCII)
#: Postgres text ``2026-09-26 03:11:29.985+00`` and ISO ``2026-09-26T03:11:29.985Z`` alike:
#: date, ' ' or 'T', time, optional 1-6 fraction digits, optional Z / +HH / +HHMM / +HH:MM.
_PG_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?\s*(Z|[+-]\d{2}(?::?\d{2})?)?$",
    re.ASCII,
)


@dataclass(frozen=True)
class ApiResult:
    ok: bool
    data: Json | None            # parsed, summary-free, control-stripped, redacted
    status: int | None           # last HTTP status seen (None when no response arrived)
    as_of_utc: str | None        # ISO Z (seconds) of the read; set only when ok
    reason: str | None           # "500 ×2 (retrying)", "timeout ×2 (retrying)", "404", "bad json", "bad seat", ...
    elapsed_s: float | None
    route: str                   # the request path incl. query, e.g. "/seats/7?work=60&reviews=0"


# --- pure helpers ---------------------------------------------------------------------

def parse_json_tolerant(body: bytes | bytearray | str) -> Json:
    """``json.loads(strict=False)`` after :func:`strip_controls` on the text.

    The API is measured to emit raw control characters inside JSON strings (fill1 FACTS);
    ``strict=False`` admits the raw ``\\t``/``\\n`` the strip keeps, the strip removes every other
    C0/C1 byte and turns a bare ESC into ``␛``.  Raises ``ValueError`` on anything that is not JSON.
    """
    if isinstance(body, (bytes, bytearray)):
        text = bytes(body).decode("utf-8-sig", errors="replace")
    elif isinstance(body, str):
        text = body
    else:
        raise TypeError(f"parse_json_tolerant wants bytes or str, not {type(body).__name__}")
    return json.loads(strip_controls(text), strict=False)


def drop_summaries(value: Json) -> Json:
    """A copy of *value* with every ``summary`` key removed, at any depth.

    Spec §6 names ``recentFailures[].summary`` and ``submissions[].summary`` (raw runtime error
    text, once carrying a masked provider key); dropping the key wherever it appears is the
    superset that needs no list of parents.  Nothing is mutated.
    """
    if isinstance(value, Mapping):
        return {k: drop_summaries(v) for k, v in value.items() if k != "summary"}
    if isinstance(value, list):
        return [drop_summaries(v) for v in value]
    return value


def reason_word(value: object) -> str | None:
    """The FailureReason enum word, ``REASON_OTHER`` for anything else, ``None`` for ``None``."""
    if value is None:
        return None
    return value if isinstance(value, str) and value in FAILURE_REASONS else REASON_OTHER


def failure_class_word(value: object) -> str | None:
    """``infrastructure`` | ``machine`` | ``unclear`` (spec §6), ``REASON_OTHER`` otherwise, ``None`` for ``None``."""
    if value is None:
        return None
    return value if isinstance(value, str) and value in FAILURE_CLASSES else REASON_OTHER


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _mapping(value: object) -> Mapping:
    return value if isinstance(value, Mapping) else {}


def _parse_pg_timestamp(text: object) -> float | None:
    """Epoch seconds from Postgres text (``2026-09-26 03:11:29.985+00``) or ISO Z; ``None`` when unusable.

    WP7's public ``analytics.seat_signals.parse_pg_timestamp`` is a verbatim copy of this body
    (contract deviation recorded in WP5.md); the two must stay equal.
    """
    if not isinstance(text, str):
        return None
    match = _PG_TS_RE.match(text.strip())
    if match is None:
        return None
    year, month, day, hour, minute, second, fraction, tz = match.groups()
    micro = int((fraction or "0").ljust(6, "0")[:6])
    offset = timedelta(0)
    if tz and tz != "Z":
        sign = -1 if tz[0] == "-" else 1
        digits = tz[1:].replace(":", "")
        hours = int(digits[:2])
        minutes = int(digits[2:4]) if len(digits) >= 4 else 0
        offset = sign * timedelta(hours=hours, minutes=minutes)
    try:
        stamp = datetime(int(year), int(month), int(day), int(hour), int(minute), int(second), micro,
                         tzinfo=timezone(offset))
    except ValueError:
        return None
    return stamp.timestamp()


def _iso_z(epoch: float, *, millis: bool = True) -> str:
    stamp = datetime.fromtimestamp(epoch, tz=timezone.utc)
    text = stamp.strftime("%Y-%m-%dT%H:%M:%S")
    if millis:
        text += f".{stamp.microsecond // 1000:03d}"
    return text + "Z"


def _normalise_stamp(value: object) -> str | None:
    epoch = _parse_pg_timestamp(value)
    return _iso_z(epoch) if epoch is not None else None


def normalise_work_row(row: Mapping) -> dict:
    """One ``/seats/<id>.work[]`` row with exactly :data:`WORK_ROW_KEYS`.

    ``acceptedAt`` arrives as Postgres text and ``submittedAt`` as ISO Z (spec §6 seats row);
    both leave as ISO Z with milliseconds or ``None``.  ``submissionHash`` is kept whole (the
    ledger joins by ``startswith(hash12)``); a non-string hash is ``None`` so no join ever raises.
    ``status`` outside the four verdict words is ``"unknown"``; missing keys are ``None``, never ``0``.
    """
    src = _mapping(row)
    out: dict[str, Any] = {key: src.get(key) for key in WORK_ROW_KEYS}
    status = out["status"]
    if isinstance(status, str) and status.lower() in WORK_STATUSES:
        out["status"] = status.lower()
    else:
        out["status"] = None if status is None else "unknown"
    digest = out["submissionHash"]
    out["submissionHash"] = digest if isinstance(digest, str) and digest else None
    out["acceptedAt"] = _normalise_stamp(out["acceptedAt"])
    out["submittedAt"] = _normalise_stamp(out["submittedAt"])
    for key in ("jobId", "objective", "jobState", "nodeKey", "role"):
        out[key] = _str_or_none(out[key])
    return out


def validate_counters(seat_body: Mapping) -> bool:
    """``attempts == accepted + rejected + failed + pending``, every counter an ``int`` (not a bool).

    Measured on 417/417 seats (fill5 §3, spec §6 seats row); a body that violates it, or lacks a
    counter, is ``False`` -- the caller renders ``counters inconsistent (api)`` instead of numbers.
    """
    values = {key: _int_or_none(_mapping(seat_body).get(key)) for key in COUNTER_KEYS}
    if any(v is None for v in values.values()):
        return False
    return values["attempts"] == values["accepted"] + values["rejected"] + values["failed"] + values["pending"]


def seat_counters(seat_body: Mapping) -> dict:
    """The five lifetime counters as served plus ``countersInconsistent`` (spec §7 standing block).

    ``countersInconsistent`` is ``True`` when the identity fails on five ints, ``False`` when it
    holds, ``None`` when a counter is missing (nothing to check).  The counters are never
    'repaired' into the sum -- mutation proof 36.
    """
    values = {key: _int_or_none(_mapping(seat_body).get(key)) for key in COUNTER_KEYS}
    if any(v is None for v in values.values()):
        flag: bool | None = None
    else:
        flag = not validate_counters(seat_body)
    return {**values, "countersInconsistent": flag}

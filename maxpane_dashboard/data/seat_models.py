"""Status document schema v2 and the flat ``seat_*`` contract of the PEPEPANE dashboard.

Boundaries: standard library plus ``analytics.seat_redact`` only -- no Textual,
no ``subprocess``, no ``socket``, no ``httpx`` (the WP8 purity walk and
``tests/data/test_seat_models.py::test_seat_models_imports_are_pure`` assert
it).  ``data/seat_manager.py`` builds the document and calls
:func:`fold_status_document`; ``pepepane --once`` prints the document and
runs :func:`validate_status_document` on it, as must any downstream consumer
(The Lineup, MaxPane's SURFBOARD).

Three rules the fold makes load-bearing (spec §7):

* **A failed read is ``None``, never ``0``.**  :func:`empty_document` carries a
  ``None`` at every leaf, and a value whose *source* is not ok folds to
  ``None`` even when the document still carries a number (mutation proof 8):
  the ``sources`` block is mapped **per field** through
  :data:`SEAT_FIELD_SOURCES` and :data:`SEAT_ROW_FIELD_SOURCES`.
* **Every string is redacted, and nothing else.**  The fold runs
  :func:`~maxpane_dashboard.analytics.seat_redact.redact` (control characters
  first) on every string leaf and stops there; the widgets sanitise for Rich
  markup themselves.
* **Identifiers.**  Device public key and wallet are truncated to 8 characters
  at fold time; job/node ids stay whole (they are the ledger's join keys);
  hashes are ``hash12``.  A valid document therefore carries **no** 64-hex
  value anywhere, and :func:`validate_status_document` refuses one wherever it
  appears -- the allowance for ``submissionHash``/``txHash``/``deviceKey``
  exists only for the broker-side projection canary (spec §13).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from maxpane_dashboard.analytics.seat_redact import find_secret_path, redact, redact_tree

__all__ = [
    "LAST_GOOD_SOURCES",
    "MAX_DOCUMENT_BYTES",
    "POLL_INTERVAL_DEFAULT",
    "PRODUCER",
    "Refusal",
    "SCHEMA_VERSION",
    "SEAT_BLOCK_KEYS",
    "SEAT_FIELD_SOURCES",
    "SEAT_KEYS",
    "SEAT_ROW_FIELD_SOURCES",
    "SEAT_ROW_KEYS",
    "SEAT_WIDGET_SIGNATURES",
    "SOURCE_NAMES",
    "SOURCE_TAGS",
    "as_of_hhmm",
    "empty_document",
    "empty_source",
    "fold_status_document",
    "parse_iso",
    "truncate_id",
    "validate_status_document",
]

SCHEMA_VERSION = 2
PRODUCER = "pepepane 0.1.0"
#: A document above this is refused (spec §7 refusal rules).
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
#: (invented) what the flat ``poll_interval`` reads when the document carries
#: no ``pollInterval``: ``pepepane --poll-interval 5`` (spec §4.3), MaxPane's
#: minimum.  ``StatusBar.update_data`` formats it as ``f"{poll_interval}s
#: poll"``, so it must be an int, never ``None``.
POLL_INTERVAL_DEFAULT = 5

SOURCE_NAMES: tuple[str, ...] = (
    "tail", "unit", "broker", "seat", "status", "skills", "sessions", "workstat", "hints", "auth",
    "standing", "seatWork", "reasons", "plane",
)
#: API sources keep their last-good values on ``ok: false`` until ``unavailable``.
LAST_GOOD_SOURCES = frozenset({"standing", "seatWork", "reasons", "plane"})
SOURCE_TAGS = {
    "L": "tail", "H": "broker", "C": "broker", "U": "unit", "S": "sessions",
    "A": "api", "D": "derived", "K": "configured",
}


@dataclass(frozen=True)
class Refusal:
    """Why :func:`validate_status_document` refused a document."""

    code: str    # "wrong_schema" | "with_secret" | "too_large" | "not_an_object"
    detail: str  # e.g. "schemaVersion=1", "canary: hex64 at tasks.rows[3].hash12", "2,301,004 B > 2 MiB"


def empty_source(*, trust: str = "host") -> dict:
    """One ``sources.<name>`` entry with nothing read yet (``ok`` is ``None``, not ``False``)."""
    return {
        "ok": None, "asOfUtc": None, "ageS": None, "reason": None, "trust": trust,
        "failures": 0, "unavailable": False, "watermark": None, "threadAliveAt": None,
    }


def empty_document(*, producer: str = PRODUCER, started_at_utc: str, host: dict) -> dict:
    """Every §7 block present, every leaf ``None`` (never ``0``), every list ``[]``."""
    tokens = {"input": None, "output": None, "cached": None, "cacheWrite": None}
    return {
        "schemaVersion": SCHEMA_VERSION,
        "producer": producer,
        "startedAtUtc": started_at_utc,
        "completedAtUtc": None,
        "host": {
            "kind": host.get("kind"), "unit": host.get("unit"), "container": host.get("container"),
            "runtime": host.get("runtime"), "hostname": host.get("hostname"),
        },
        "sources": {name: empty_source() for name in SOURCE_NAMES},
        "seat": {
            "tokenId": None, "agentId": None, "deviceKeyPublic": None, "wallet": None, "server": None,
            "eligibility": None, "capacity": None, "offers": [], "daemonVersion": None,
            "runtime": {"id": None, "version": None}, "releaseAvailable": None, "buildMismatch": None,
            "skills": {"offered": None, "on": None, "optOut": [], "needsNetwork": None, "rows": []},
            "tools": [], "inference": None, "premiumAdvertised": None, "hints": None,
            "configChangedSinceStart": None,
        },
        "daemon": {
            "state": None, "uptime": None, "work": None, "running": None, "submittedSinceStart": None,
            "lastHeartbeatUtc": None, "heartbeatAgeS": None, "idleBeats": None, "fleetOnline": None,
            "fleetEnrolled": None, "pausedHint": None, "invocationId": None, "lastAdmittedUtc": None,
            "disconnects24h": None, "reconnects24h": None, "consecutiveDisconnectedBeats": None,
        },
        "auth": {"degraded": None, "reasons": [], "sinceUtc": None, "credentialFileMtimeUtc": None},
        "unit": {
            "activeState": None, "subState": None, "mainPid": None, "sinceUtc": None, "restarts": None,
            "bootEnabled": None, "restartPolicy": None, "killMode": None, "stopTimeoutS": None,
            "gracefulStopPossible": None, "memoryCurrentB": None, "memoryPeakB": None, "memoryMaxB": None,
            "cpuQuota": None, "tasksCurrent": None,
        },
        "current": None,
        "queue": None,
        "tasks": {
            "window": {"fromUtc": None, "toUtc": None, "source": None, "rows": None, "gapNote": None,
                       "ledgerSinceUtc": None},
            "rows": [],
        },
        "today": {
            "dayUtc": None, "tasks": None, "stored": None, "notStored": None, "p50S": None, "longestS": None,
            "accepted": None, "rejected": None, "failed": None, "pending": None, "verdictLagP50S": None,
            "verdictsAsOfUtc": None, "divergence": None,
        },
        "cost": {
            "windowDays": None, "tasks": None, "excluded": {"doctor": None, "manual": None}, "turns": None,
            "tokens": dict(tokens), "buckets": [], "sideModel": None,
            "series": {"outputTokensPerDay": [], "tasksPerDay": [], "acceptedPerDay": []},
            "depth": {"ledgerFromUtc": None, "sessionsFromUtc": None, "expiredRows": None,
                      "skipped": {"oversize": None}},
        },
        "quota": {"provider": None, "window": None, "usedPercent": None, "resetsAtUtc": None,
                  "sampledAtUtc": None, "planType": None, "reason": None},
        "standing": {
            "attempts": None, "accepted": None, "rejected": None, "failed": None, "pending": None,
            "countersInconsistent": None, "working": None, "running": [], "consecutiveFailures": None,
            "pausedUntil": None, "breaker": None, "recentFailures": [], "presenceConnected": None,
            "heartbeatAgeMs": None, "asOfUtc": None,
        },
        "plane": {"version": None, "verifierUp": None, "verifierLastSeenUtc": None, "awaitingVerdict": None,
                  "connectedDaemons": None, "asOfUtc": None},
        "machine": {
            "load1": None, "memAvailMiB": None, "diskFreeGiB": None, "workDirs": None, "workBytes": None,
            "abnormalLeaseDirs": None, "outboxFiles": None, "journal": None, "transcriptRetention": None,
            "orphans": [],
        },
        "control": {"brokerReachable": None, "gate": None, "drain": None, "inFlight": None,
                    "restartRequired": None, "lastAudit": []},
    }


def parse_iso(iso_utc: object) -> float | None:
    """``"2026-09-26T03:40:07Z"`` (optionally with fractional seconds or an
    explicit offset) to epoch seconds; ``None`` for anything unusable.  A stamp
    without a zone is read as UTC, as every stamp in the document is."""
    if not isinstance(iso_utc, str):
        return None
    text = iso_utc.strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def as_of_hhmm(iso_utc: str | None) -> str | None:
    """Local ``HH:MM`` of an ISO ``Z`` stamp (every panel's ``as of``); ``None`` when unusable."""
    epoch = parse_iso(iso_utc)
    if epoch is None or epoch <= 0:
        return None
    try:
        local = time.localtime(epoch)
    except (OverflowError, OSError, ValueError):
        return None
    return f"{local.tm_hour:02d}:{local.tm_min:02d}"


def truncate_id(value: object, n: int = 8) -> str | None:
    """The first *n* characters of an identifier (device public key, wallet); ``None`` for nothing."""
    if value is None:
        return None
    try:
        text = str(value).strip()
    except Exception:
        return None
    if not text:
        return None
    return text[:n]


def validate_status_document(doc: object, *, raw_bytes: int | None = None) -> Refusal | None:
    """The §7 refusal rules, in order; ``None`` means the document may be consumed.

    ``raw_bytes`` is the size of the bytes the document was read from; when
    the caller has only the object, the size is measured by serialising it.
    The canary allows **no** 64-hex value anywhere: a valid document truncated
    its device key at fold time.
    """
    if not isinstance(doc, dict):
        return Refusal("not_an_object", f"type={type(doc).__name__}")
    size = raw_bytes
    if size is None:
        try:
            size = len(json.dumps(doc, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8"))
        except (TypeError, ValueError, RecursionError):
            size = None
    if size is not None and size > MAX_DOCUMENT_BYTES:
        return Refusal("too_large", f"{size:,} B > 2 MiB")
    version = doc.get("schemaVersion")
    if version != SCHEMA_VERSION or isinstance(version, bool):
        return Refusal("wrong_schema", f"schemaVersion={version!r}")
    hit = find_secret_path(doc, allowed_hex64_fields=frozenset())
    if hit is not None:
        kind, path = hit
        return Refusal("with_secret", f"canary: {kind} at {path}")
    return None

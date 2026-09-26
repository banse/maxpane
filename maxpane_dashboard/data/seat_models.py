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


# ---------------------------------------------------------------------------
# The flat dict contract
# ---------------------------------------------------------------------------

#: The flat dict has exactly these keys: ``seat_`` + the §7 path in snake_case,
#: dict/list-valued keys carrying their §7 block verbatim (redacted), plus the
#: three keys ``DashboardScreen._do_refresh`` reads for the StatusBar.
SEAT_KEYS: tuple[str, ...] = (
    # ---- meta (D/K) --------------------------------------------------------
    "seat_schema_version", "seat_producer", "seat_started_at_utc", "seat_completed_at_utc",
    "seat_host_kind",            # "systemd" | "docker" | "fixture"
    "seat_host_unit", "seat_host_container", "seat_host_runtime", "seat_hostname",
    "seat_offline",              # bool — the --offline flag (K)
    "seat_sources",              # dict[str, dict] — the §7 sources block, per field
    "seat_as_of_hhmm",           # dict[str, str | None] — source name -> local HH:MM of its asOfUtc (D)
    # ---- seat (C/H/A/K) ----------------------------------------------------
    "seat_token_id", "seat_agent_id", "seat_device_key_public", "seat_wallet", "seat_server",
    "seat_eligibility", "seat_capacity", "seat_offers", "seat_daemon_version",
    "seat_runtime_id", "seat_runtime_version", "seat_release_available", "seat_build_mismatch",
    "seat_skills_offered", "seat_skills_on", "seat_skills_opt_out", "seat_skills_needs_network",
    "seat_skills_rows",          # list[dict] SEAT_ROW_KEYS["seat_skills_rows"] (D over C: `imd skills` parse)
    "seat_tools",                # list[str] tool ids
    "seat_inference",            # dict | None — {"economy": {"codex": {"model","effort"}}, "standard": \u2026, "premium": \u2026}
    "seat_premium_advertised",   # dict | None — {"model","effort"}
    "seat_hints",                # dict | None — {"path","bytes","sha8","mtimeUtc"}
    "seat_config_changed_since_start",
    # ---- daemon (L) --------------------------------------------------------
    "seat_daemon_state", "seat_daemon_uptime", "seat_daemon_work", "seat_daemon_running",
    "seat_daemon_submitted_since_start", "seat_daemon_last_heartbeat_utc", "seat_daemon_heartbeat_age_s",
    "seat_daemon_idle_beats", "seat_daemon_fleet_online", "seat_daemon_fleet_enrolled",
    "seat_daemon_paused_hint",   # dict | None — {"until","failedRuns","reason"} (reason redacted)
    "seat_daemon_invocation_id", "seat_daemon_last_admitted_utc", "seat_daemon_disconnects_24h",
    "seat_daemon_reconnects_24h", "seat_daemon_consecutive_disconnected_beats",
    "seat_daemon_offline",       # bool | None — the two-beat rule (D)
    # ---- auth (D) ----------------------------------------------------------
    "seat_auth_degraded", "seat_auth_reasons", "seat_auth_since_utc", "seat_auth_credential_file_mtime_utc",
    # ---- unit (U) ----------------------------------------------------------
    "seat_unit_active_state", "seat_unit_sub_state", "seat_unit_main_pid", "seat_unit_since_utc",
    "seat_unit_restarts", "seat_unit_boot_enabled", "seat_unit_restart_policy", "seat_unit_kill_mode",
    "seat_unit_stop_timeout_s", "seat_unit_graceful_stop_possible", "seat_unit_memory_current_b",
    "seat_unit_memory_peak_b", "seat_unit_memory_max_b", "seat_unit_cpu_quota", "seat_unit_tasks_current",
    # ---- current / queue (L/A) ---------------------------------------------
    "seat_current",              # dict | None — the §7 current block (None when idle; absent-> None when tail not ok)
    "seat_queue",                # dict | None — {"ready","eligible","fleetOnline","blocked":[{"reason","nodes"}],"asOfUtc"}
    # ---- tasks (L/S/A) -----------------------------------------------------
    "seat_tasks_window",         # dict — {"fromUtc","toUtc","source","rows","gapNote","ledgerSinceUtc"}
    "seat_tasks_rows",           # list[dict] SEAT_ROW_KEYS["seat_tasks_rows"], newest first
    "seat_last_task",            # dict | None — {"nodeId8","storedUtc","hash12","outcome","verdictLagS","acceptedUtc"} (D)
    # ---- today (D) ---------------------------------------------------------
    "seat_today_day_utc", "seat_today_tasks", "seat_today_stored", "seat_today_not_stored",
    "seat_today_p50_s", "seat_today_longest_s", "seat_today_accepted", "seat_today_rejected",
    "seat_today_failed", "seat_today_pending", "seat_today_verdict_lag_p50_s", "seat_today_verdicts_as_of_utc",
    "seat_today_divergence",     # dict | None — {"localStored","planeRowsSubmittedToday","ok"}
    # ---- cost (S/D) --------------------------------------------------------
    "seat_cost_window_days", "seat_cost_tasks",
    "seat_cost_excluded",        # dict — {"doctor": n, "manual": n}
    "seat_cost_turns",
    "seat_cost_tokens",          # dict — {"input","output","cached","cacheWrite"}
    "seat_cost_buckets",         # list[dict] SEAT_ROW_KEYS["seat_cost_buckets"]
    "seat_cost_side_model",      # dict | None — {"model","input","output","tasks"}
    "seat_cost_series",          # dict — {"outputTokensPerDay": [[day, n]\u2026], "tasksPerDay": [\u2026], "acceptedPerDay": [\u2026]}
    "seat_cost_depth",           # dict — {"ledgerFromUtc","sessionsFromUtc","expiredRows","skipped":{"oversize":n}}
    "seat_quota",                # dict — {"provider","window","usedPercent","resetsAtUtc","sampledAtUtc","planType","reason"}
    # ---- standing (A) ------------------------------------------------------
    "seat_standing_attempts", "seat_standing_accepted", "seat_standing_rejected", "seat_standing_failed",
    "seat_standing_pending", "seat_standing_counters_inconsistent", "seat_standing_working",
    "seat_standing_running",     # list[dict] SEAT_ROW_KEYS["seat_standing_running"]
    "seat_standing_consecutive_failures", "seat_standing_paused_until",
    "seat_standing_breaker",     # dict | None — {"failures","cooldownMs"}
    "seat_standing_recent_failures",   # list[dict] SEAT_ROW_KEYS["seat_standing_recent_failures"]
    "seat_standing_presence_connected", "seat_standing_heartbeat_age_ms", "seat_standing_as_of_utc",
    # ---- plane (A) ---------------------------------------------------------
    "seat_plane_version", "seat_plane_verifier_up", "seat_plane_verifier_last_seen_utc",
    "seat_plane_awaiting_verdict", "seat_plane_connected_daemons", "seat_plane_as_of_utc",
    # ---- machine (U/H) -----------------------------------------------------
    "seat_machine_load1", "seat_machine_mem_avail_mib", "seat_machine_disk_free_gib",
    "seat_machine_work_dirs", "seat_machine_work_bytes", "seat_machine_abnormal_lease_dirs", "seat_machine_outbox_files",
    "seat_machine_journal",      # dict | None — VPS {"firstUtc","lastUtc","capNote"} | docker {"driver","rotation","bytes","diesWith"}
    "seat_machine_transcript_retention",   # dict | None
    "seat_machine_orphans",      # list[dict] SEAT_ROW_KEYS["seat_machine_orphans"]
    # ---- control (broker) --------------------------------------------------
    "seat_control_broker_reachable",
    "seat_control_gate",         # dict | None — the §7 control.gate block (plan-time preview)
    "seat_control_drain",        # dict | None
    "seat_control_in_flight",    # dict | None — {"verb","planId","sinceUtc"}
    "seat_control_restart_required",
    "seat_control_last_audit",   # list[dict] SEAT_ROW_KEYS["seat_control_last_audit"]
    # ---- derived for widgets (D) -------------------------------------------
    "seat_hero_state",           # "green" | "amber" | "red" | None
    "seat_hero_reasons",         # list[str]
    "seat_log_lines",            # list[dict] SEAT_ROW_KEYS["seat_log_lines"] — only lines with seq > last seq the widget saw
    "seat_log_seq",              # int — the newest seq in seat_log_lines (widget stores it)
    "seat_log_footer",           # str — e.g. "tail: journalctl -f · cursor age 4 s · grammar 5bfa8261 \u2713"
    "seat_ledger_footer",        # str — window + divergence sentence (§8 LEDGER)
    # ---- status bar (read by DashboardScreen._do_refresh) ------------------
    "last_updated_seconds_ago", "error_count", "poll_interval",
)

#: Every dict in a list-valued key has exactly these keys; a missing one is ``None``.
SEAT_ROW_KEYS: dict[str, tuple[str, ...]] = {
    "seat_tasks_rows": (
        "key", "nodeId8", "nodeId", "jobId", "role", "kind", "acceptedUtc", "submittedUtc", "storedUtc", "hash12",
        "durationS", "agentRan", "preAgentFailure", "cancelled", "leaseClosed", "repair", "resent", "interruptedByRestart",
        "runtime", "model", "effort", "tierDerived", "turns", "turnsDefinition", "tokens", "sideModelTokens",
        "ttftMs", "wallMs", "turn1Context", "maxTurnsReached", "apiErrors", "sessionFiles", "tokensReason",
        "outcome", "outcomeAsOfUtc", "acceptedAtApi", "verdictLagS", "failureReason", "failureClass", "nodeKey", "objective",
        "source", "phases", "lastMessage", "lastMessageUtc", "workDirAbnormal", "maxTurns",
    ),
    "seat_skills_rows": ("id", "on", "needs"),                       # needs: "network" | "tool:<x>" | None
    "seat_cost_buckets": (
        "model", "effort", "tierDerived", "tasks", "turnsP50", "tokens", "wallP50S", "wallP90S", "ttftP50Ms",
        "turn1ContextP50", "maxTurnsHits", "authErrors",
    ),
    "seat_machine_orphans": ("pid", "pgid", "uid", "cgroup", "ageS", "rssB", "cmd", "pgidMembers"),   # pgidMembers: [{"pid","uid","cgroup","cmd"}]
    "seat_standing_running": ("jobId", "objective", "nodeKey", "role", "since"),
    "seat_standing_recent_failures": ("at", "reason", "nodeKey", "jobId"),
    "seat_control_last_audit": ("ts", "seq", "verb", "phase", "planId", "outcome", "verified", "connected"),
    "seat_log_lines": ("seq", "ts", "kind", "text", "invocation", "cursor"),
}

#: (invented) nested dict shapes; a missing key is ``None``.
SEAT_BLOCK_KEYS: dict[str, tuple[str, ...]] = {
    "seat_current": ("nodeId8", "jobId", "role", "kind", "phase", "startedUtc", "elapsedS", "maxTurns", "model",
                     "tierDerived", "lastMessage", "lastMessageUtc", "planeSince", "objective", "nodeKey"),
    "seat_queue": ("ready", "eligible", "fleetOnline", "blocked", "asOfUtc"),
    "seat_control_gate": ("idleBeats", "idleBeatsRequired", "planeRunning", "planeAsOfUtc", "planeMode",
                          "lastLifecycleLine", "lifecycleOpen", "outboxFiles", "unitActive", "safe", "reason"),
    "seat_control_drain": ("armedAtUtc", "idleBeats", "rearmed", "expiresAtUtc"),
    "seat_control_in_flight": ("verb", "planId", "sinceUtc"),
    "seat_quota": ("provider", "window", "usedPercent", "resetsAtUtc", "sampledAtUtc", "planType", "reason"),
}

#: Every ``seat_*`` key -> the ``SOURCE_NAMES`` entry whose ``ok`` gates it, or
#: ``None`` for meta/derived keys that are never gated (spec §7 "sources is
#: load-bearing and mapped per field").  The five lifetime counters and
#: ``countersInconsistent`` come from ``/seats/<id>?work=`` (the ``seatWork``
#: source, spec §7 standing block), not from ``/seats/<id>/standing``.
SEAT_FIELD_SOURCES: dict[str, str | None] = {
    # meta
    "seat_schema_version": None, "seat_producer": None, "seat_started_at_utc": None, "seat_completed_at_utc": None,
    "seat_host_kind": None, "seat_host_unit": None, "seat_host_container": None, "seat_host_runtime": None,
    "seat_hostname": None, "seat_offline": None, "seat_sources": None, "seat_as_of_hhmm": None,
    # seat
    # tokenId C(status) -> K and agentId A(enrollment.agentId) -> K (spec §7): the value carries its own fallback and
    # the manager writes the saved/configured id, so neither is gated (spec §8 `IDMD #7 (saved)`; deviation 4)
    "seat_token_id": None, "seat_agent_id": None, "seat_device_key_public": "seat", "seat_wallet": "seat",
    "seat_server": "seat", "seat_eligibility": "status", "seat_capacity": "status", "seat_offers": "status",
    "seat_daemon_version": "tail", "seat_runtime_id": "status", "seat_runtime_version": "status",
    "seat_release_available": "tail", "seat_build_mismatch": "tail",
    "seat_skills_offered": "skills", "seat_skills_on": "skills", "seat_skills_opt_out": "skills",
    "seat_skills_needs_network": "skills", "seat_skills_rows": "skills",
    "seat_tools": "seat", "seat_inference": "seat", "seat_premium_advertised": "standing", "seat_hints": "hints",
    "seat_config_changed_since_start": None,
    # daemon
    "seat_daemon_state": "tail", "seat_daemon_uptime": "tail", "seat_daemon_work": "tail", "seat_daemon_running": "tail",
    "seat_daemon_submitted_since_start": "tail", "seat_daemon_last_heartbeat_utc": "tail",
    "seat_daemon_heartbeat_age_s": "tail", "seat_daemon_idle_beats": "tail", "seat_daemon_fleet_online": "tail",
    "seat_daemon_fleet_enrolled": "tail", "seat_daemon_paused_hint": "tail", "seat_daemon_invocation_id": "tail",
    "seat_daemon_last_admitted_utc": "tail", "seat_daemon_disconnects_24h": "tail", "seat_daemon_reconnects_24h": "tail",
    "seat_daemon_consecutive_disconnected_beats": "tail", "seat_daemon_offline": None,
    # auth
    "seat_auth_degraded": None, "seat_auth_reasons": None, "seat_auth_since_utc": None,
    "seat_auth_credential_file_mtime_utc": "auth",
    # unit
    "seat_unit_active_state": "unit", "seat_unit_sub_state": "unit", "seat_unit_main_pid": "unit",
    "seat_unit_since_utc": "unit", "seat_unit_restarts": "unit", "seat_unit_boot_enabled": "unit",
    "seat_unit_restart_policy": "unit", "seat_unit_kill_mode": "unit", "seat_unit_stop_timeout_s": "unit",
    "seat_unit_graceful_stop_possible": "unit", "seat_unit_memory_current_b": "unit", "seat_unit_memory_peak_b": "unit",
    "seat_unit_memory_max_b": "unit", "seat_unit_cpu_quota": "unit", "seat_unit_tasks_current": "unit",
    # current / queue
    "seat_current": "tail", "seat_queue": "standing",
    # tasks
    "seat_tasks_window": "tail", "seat_tasks_rows": "tail", "seat_last_task": "tail",
    # today
    "seat_today_day_utc": None, "seat_today_tasks": None, "seat_today_stored": None, "seat_today_not_stored": None,
    "seat_today_p50_s": None, "seat_today_longest_s": None,
    "seat_today_accepted": "seatWork", "seat_today_rejected": "seatWork", "seat_today_failed": "seatWork",
    "seat_today_pending": "seatWork", "seat_today_verdict_lag_p50_s": "seatWork",
    "seat_today_verdicts_as_of_utc": "seatWork", "seat_today_divergence": "seatWork",
    # cost
    "seat_cost_window_days": "sessions", "seat_cost_tasks": "sessions", "seat_cost_excluded": "sessions",
    "seat_cost_turns": "sessions", "seat_cost_tokens": "sessions", "seat_cost_buckets": "sessions",
    "seat_cost_side_model": "sessions", "seat_cost_series": "sessions", "seat_cost_depth": "sessions",
    "seat_quota": "sessions",
    # standing
    "seat_standing_attempts": "seatWork", "seat_standing_accepted": "seatWork", "seat_standing_rejected": "seatWork",
    "seat_standing_failed": "seatWork", "seat_standing_pending": "seatWork",
    "seat_standing_counters_inconsistent": "seatWork",
    "seat_standing_working": "standing", "seat_standing_running": "standing",
    "seat_standing_consecutive_failures": "standing", "seat_standing_paused_until": "standing",
    "seat_standing_breaker": "standing", "seat_standing_recent_failures": "standing",
    "seat_standing_presence_connected": "standing", "seat_standing_heartbeat_age_ms": "standing",
    "seat_standing_as_of_utc": "standing",
    # plane
    "seat_plane_version": "plane", "seat_plane_verifier_up": "plane", "seat_plane_verifier_last_seen_utc": "plane",
    "seat_plane_awaiting_verdict": "plane", "seat_plane_connected_daemons": "plane", "seat_plane_as_of_utc": "plane",
    # machine
    "seat_machine_load1": "unit", "seat_machine_mem_avail_mib": "unit", "seat_machine_disk_free_gib": "unit",
    "seat_machine_work_dirs": "workstat", "seat_machine_work_bytes": "workstat",
    "seat_machine_abnormal_lease_dirs": "workstat", "seat_machine_outbox_files": "workstat",
    "seat_machine_journal": "unit", "seat_machine_transcript_retention": "unit", "seat_machine_orphans": "workstat",
    # control
    "seat_control_broker_reachable": "broker", "seat_control_gate": "broker", "seat_control_drain": "broker",
    "seat_control_in_flight": "broker", "seat_control_restart_required": "broker", "seat_control_last_audit": "broker",
    # derived
    "seat_hero_state": None, "seat_hero_reasons": None, "seat_log_lines": "tail", "seat_log_seq": None,
    "seat_log_footer": None, "seat_ledger_footer": None,
    # status bar
    "last_updated_seconds_ago": None, "error_count": None, "poll_interval": None,
}

#: (invented) row-level gating inside a list-valued key: a row field whose
#: source is not ok folds to ``None`` -- except ``outcome``, whose spec §7
#: word for "API unavailable / offline" is ``"unknown"``.
SEAT_ROW_FIELD_SOURCES: dict[str, dict[str, str]] = {
    "seat_tasks_rows": {
        "outcome": "seatWork", "outcomeAsOfUtc": "seatWork", "acceptedAtApi": "seatWork", "verdictLagS": "seatWork",
        "failureReason": "reasons", "failureClass": "reasons",
    },
}
_ROW_GATED_VALUES: dict[str, object] = {"outcome": "unknown"}

#: The exact ``update_data(**kwargs)`` keyword set of each widget (WP8); the
#: PANELS adapters are ``keys(*SEAT_WIDGET_SIGNATURES["SeatX"])``.
SEAT_WIDGET_SIGNATURES: dict[str, tuple[str, ...]] = {
    "SeatHero": (
        "seat_token_id", "seat_agent_id", "seat_eligibility", "seat_runtime_id", "seat_runtime_version",
        "seat_daemon_version", "seat_release_available", "seat_skills_offered", "seat_skills_on", "seat_capacity",
        "seat_daemon_state", "seat_daemon_uptime", "seat_daemon_work", "seat_daemon_running",
        "seat_daemon_heartbeat_age_s", "seat_daemon_consecutive_disconnected_beats", "seat_daemon_paused_hint",
        "seat_daemon_fleet_online", "seat_daemon_fleet_enrolled", "seat_daemon_last_admitted_utc", "seat_daemon_offline",
        "seat_auth_degraded", "seat_auth_since_utc", "seat_current",
        "seat_today_tasks", "seat_today_stored", "seat_today_not_stored", "seat_today_p50_s", "seat_today_longest_s",
        "seat_today_divergence", "seat_last_task",
        "seat_today_accepted", "seat_today_rejected", "seat_today_failed", "seat_today_pending", "seat_today_verdict_lag_p50_s",
        "seat_standing_attempts", "seat_standing_accepted", "seat_standing_counters_inconsistent", "seat_standing_paused_until",
        "seat_control_broker_reachable", "seat_control_gate", "seat_control_drain", "seat_control_in_flight", "seat_control_last_audit",
        "seat_unit_active_state", "seat_unit_memory_current_b", "seat_unit_memory_peak_b", "seat_unit_memory_max_b",
        "seat_unit_restarts", "seat_unit_boot_enabled", "seat_unit_kill_mode", "seat_unit_stop_timeout_s",
        "seat_unit_graceful_stop_possible",
        "seat_hero_state", "seat_hero_reasons", "seat_sources", "seat_as_of_hhmm", "seat_offline", "seat_host_kind",
    ),
    "SeatNow": (
        "seat_current", "seat_queue", "seat_last_task", "seat_daemon_work", "seat_daemon_state",
        "seat_auth_degraded", "seat_auth_reasons", "seat_auth_credential_file_mtime_utc",
        "seat_standing_running", "seat_sources", "seat_as_of_hhmm", "seat_offline",
    ),
    "SeatLedgerTable": ("seat_tasks_rows", "seat_tasks_window", "seat_ledger_footer", "seat_sources", "seat_as_of_hhmm", "seat_offline"),
    "SeatLog": ("seat_log_lines", "seat_log_seq", "seat_log_footer", "seat_sources"),
    "SeatConfig": (
        "seat_server", "seat_capacity", "seat_offers", "seat_runtime_id", "seat_runtime_version", "seat_daemon_version",
        "seat_release_available", "seat_premium_advertised", "seat_inference", "seat_hints",
        "seat_config_changed_since_start", "seat_skills_rows", "seat_skills_offered", "seat_skills_on", "seat_tools",
        "seat_sources", "seat_as_of_hhmm", "seat_host_kind",
    ),
    "SeatCost": (
        "seat_cost_window_days", "seat_cost_tasks", "seat_cost_excluded", "seat_cost_turns", "seat_cost_tokens",
        "seat_cost_buckets", "seat_cost_side_model", "seat_cost_series", "seat_cost_depth", "seat_quota",
        "seat_host_runtime", "seat_sources", "seat_as_of_hhmm",
    ),
    "SeatMachine": (
        "seat_unit_memory_current_b", "seat_unit_memory_peak_b", "seat_unit_memory_max_b", "seat_unit_cpu_quota",
        "seat_unit_tasks_current", "seat_unit_stop_timeout_s", "seat_unit_kill_mode", "seat_unit_graceful_stop_possible",
        "seat_machine_load1", "seat_machine_mem_avail_mib", "seat_machine_disk_free_gib",
        "seat_machine_work_dirs", "seat_machine_work_bytes", "seat_machine_abnormal_lease_dirs", "seat_machine_outbox_files",
        "seat_machine_journal", "seat_machine_transcript_retention", "seat_machine_orphans",
        "seat_plane_verifier_up", "seat_plane_verifier_last_seen_utc", "seat_plane_awaiting_verdict",
        "seat_plane_connected_daemons", "seat_daemon_fleet_online", "seat_daemon_fleet_enrolled",
        "seat_sources", "seat_as_of_hhmm", "seat_host_kind",
    ),
}

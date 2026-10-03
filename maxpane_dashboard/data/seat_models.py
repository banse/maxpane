"""Status document schema v2 and the flat ``seat_*`` contract of the PEPEPANE dashboard.

Boundaries: standard library plus ``analytics.seat_redact`` and ``analytics.seat_signals`` -- no Textual,
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

from maxpane_dashboard.analytics.seat_redact import find_secret_path
from maxpane_dashboard.analytics.seat_text import sanitize_text as redact, sanitize_tree as redact_tree
from maxpane_dashboard.analytics.seat_signals import hero_state, ledger_footer, log_footer, offline_state

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
    "shape_dashboard_document",
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
#: The daemon build the log grammar is pinned to (== data.seat_log_grammar.GRAMMAR_VERSION; restated so this
#: module keeps its two-import purity rule).  ``tests/data/test_seat_models.py::test_grammar_pin_matches`` binds them.
GRAMMAR_VERSION_PINNED = "0.1.0+5bfa8261"


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
            "configChangedSinceStart": None, "autoUpdate": None, "runtimeWrapper": None,
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
        "currentJobs": [],
        "jobs": [],
        "records": {"rows": [], "window": None},
        "nodes": {"allRows": [], "weekRows": [], "coverage": None},
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
            "outputTokens": None,
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
                    "restartRequired": None, "lastAudit": [], "plan": None, "status": None, "mode": None},
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
    # ---- round 9: six bodies (additive) ------------------------------------
    "seat_current_jobs", "seat_jobs", "seat_records_rows", "seat_records_window",
    "seat_nodes_all_rows", "seat_nodes_week_rows", "seat_nodes_coverage",
    "seat_auto_update", "seat_runtime_wrapper", "seat_output_tokens",
    "seat_control_plan", "seat_control_status", "seat_control_mode",
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

# Round-9 rows expose display facts and ledger keys, never full submission hashes.
SEAT_ROW_KEYS.update({
    "seat_current_jobs": SEAT_BLOCK_KEYS["seat_current"],
    "seat_jobs": (
        "key", "jobId", "nodeId8", "nodeKey", "role", "kind", "acceptedUtc", "storedUtc", "hash12",
        "phase", "elapsedS", "lastMessage", "objective", "reply", "oracleQuestion", "oracleAnswer", "oracleNotes",
        "questionState", "questionReason", "questionAsOfUtc", "replyState", "replyReason", "replyAsOfUtc",
        "textExpired", "template", "paid", "launch", "workflowId", "oracleRequestId", "parentJobId",
        "delivery", "structuralCheck", "panel", "usage", "outcome", "outcomeSource", "verdictLagS", "failureClass", "failureReason",
    ),
    "seat_records_rows": (
        "key", "jobId", "nodeId8", "nodeKey", "role", "kind", "acceptedUtc", "submittedUtc", "storedUtc",
        "hash12", "outcome", "outcomeSource", "jobState", "workStatus", "model", "durationS", "tokens",
        "answerPreview", "answerState", "answerReason", "answerAsOfUtc", "panel", "launch", "paid", "detailRead",
    ),
    "seat_nodes_all_rows": (
        "nodeKey", "role", "attempts", "accepted", "rejected", "failed", "pending", "acceptedPercent",
        "durationP50S", "outputTokensP50", "paid", "launch", "detailsRead", "lastSubmittedUtc",
    ),
})
SEAT_ROW_KEYS["seat_nodes_week_rows"] = SEAT_ROW_KEYS["seat_nodes_all_rows"]
SEAT_BLOCK_KEYS.update({
    "seat_records_window": ("rows", "asOfUtc", "fromUtc", "toUtc", "reason"),
    "seat_nodes_coverage": ("attempts", "covered", "detailsRead", "asOfUtc", "reason"),
    "seat_output_tokens": ("today", "sevenDays", "averagePerDay", "days", "reason"),
    "seat_control_plan": ("planId", "verb", "command", "confirm", "warning", "expiresAtUtc", "forced", "localOnly"),
})

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
    "seat_today_accepted": None, "seat_today_rejected": None, "seat_today_failed": None,
    "seat_today_pending": None, "seat_today_verdict_lag_p50_s": None,
    "seat_today_verdicts_as_of_utc": None, "seat_today_divergence": "seatWork",
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

# Cached round-9 facts remain available behind their stored timestamps. The
# manager owns live currentJobs availability, including its local/API merge.
SEAT_FIELD_SOURCES.update({
    "seat_current_jobs": None, "seat_jobs": None, "seat_records_rows": None, "seat_records_window": None,
    "seat_nodes_all_rows": None, "seat_nodes_week_rows": None, "seat_nodes_coverage": None,
    "seat_auto_update": "unit", "seat_runtime_wrapper": "status", "seat_output_tokens": None,
    "seat_control_plan": None, "seat_control_status": None, "seat_control_mode": None,
})

#: (invented) row-level gating inside a list-valued key: a row field whose
#: source is not ok folds to ``None`` -- except ``outcome``, whose spec §7
#: word for "API unavailable / offline" is ``"unknown"``.
SEAT_ROW_FIELD_SOURCES: dict[str, dict[str, str]] = {
    # Verdicts and reasons are persisted ledger facts with their own timestamps.
    # An API outage gates live fields, never these stored observations (round 9 §8.1).
    "seat_tasks_rows": {},
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
        "seat_current", "seat_queue", "seat_last_task", "seat_daemon_work", "seat_daemon_state", "seat_daemon_running",
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


# Existing signatures grow additively; implementation follows in the widget package.
SEAT_WIDGET_SIGNATURES["SeatHero"] += (
    "seat_nodes_all_rows", "seat_nodes_coverage", "seat_control_restart_required", "seat_config_changed_since_start",
)
SEAT_WIDGET_SIGNATURES["SeatConfig"] += (
    "seat_token_id", "seat_agent_id", "seat_wallet", "seat_device_key_public", "seat_unit_boot_enabled",
    "seat_unit_restart_policy", "seat_auto_update", "seat_runtime_wrapper", "seat_control_restart_required",
)
SEAT_WIDGET_SIGNATURES["SeatLedgerTable"] += ("seat_today_p50_s", "seat_today_longest_s", "seat_today_divergence")
SEAT_WIDGET_SIGNATURES.update({
    "SeatJob": ("seat_current_jobs", "seat_jobs", "seat_sources", "seat_as_of_hhmm", "seat_offline"),
    "SeatOutputTokens": ("seat_cost_series", "seat_cost_tokens", "seat_output_tokens", "seat_sources", "seat_as_of_hhmm"),
    "SeatSkills": ("seat_skills_rows", "seat_skills_offered", "seat_skills_on", "seat_skills_needs_network",
                   "seat_tools", "seat_control_restart_required", "seat_sources", "seat_as_of_hhmm", "seat_host_kind"),
    "SeatRecords": ("seat_records_rows", "seat_records_window", "seat_sources", "seat_as_of_hhmm", "seat_offline"),
    "SeatNodes": ("seat_nodes_all_rows", "seat_nodes_week_rows", "seat_nodes_coverage", "seat_sources", "seat_offline"),
    "SeatGate": ("seat_control_gate", "seat_control_drain", "seat_sources", "seat_as_of_hhmm"),
    "SeatAudit": ("seat_control_last_audit", "seat_control_in_flight", "seat_sources", "seat_as_of_hhmm"),
    "SeatControl": ("seat_control_gate", "seat_control_drain", "seat_control_in_flight", "seat_control_broker_reachable",
                    "seat_unit_boot_enabled", "seat_unit_graceful_stop_possible", "seat_unit_active_state",
                    "seat_host_kind", "seat_machine_orphans", "seat_daemon_version", "seat_release_available",
                    "seat_control_plan", "seat_control_status", "seat_control_mode", "seat_sources"),
})


# ---------------------------------------------------------------------------
# fold_status_document
# ---------------------------------------------------------------------------

_SOURCE_KEYS = tuple(empty_source())
_LAST_TASK_KEYS = ("nodeId8", "storedUtc", "hash12", "outcome", "verdictLagS", "acceptedUtc")


def _dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _clean(value: object, field: str | None = None) -> object:
    """Redact every string leaf; leave ``None``/bool/int/float alone; stringify anything else."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return redact(value, field)
    if isinstance(value, (dict, list, tuple)):
        return redact_tree(value, field=field)
    return redact(value, field)


_DASHBOARD_ROWS = frozenset({"seat_current_jobs", "seat_jobs", "seat_records_rows", "seat_nodes_all_rows", "seat_nodes_week_rows"})
_TOKEN_KEYS = ("input", "output", "cached", "cacheWrite")
_NESTED_KEYS = {
    "tokens": _TOKEN_KEYS,
    "usage": ("model", "turns", "tokens", "wallMs", "wallS"),
    "delivery": ("url", "atUtc"),
    "launch": ("kind", "requested", "workflowId"),
    "structuralCheck": ("status", "evaluation", "detail"),
    "panel": ("state", "agreed", "quorum", "size", "figure", "answerType", "answerBool",
              "memberOk", "memberReason", "chainId", "requestId"),
}
_JOB_TEXT_FIELDS = frozenset({"objective", "reply", "oracleQuestion", "oracleAnswer", "oracleNotes"})


def _dashboard_value(name: str, value: object, *, full_text: bool = False) -> object:
    """Allowlisted objects only; an object in a scalar field becomes unavailable."""
    if name in _NESTED_KEYS:
        if not isinstance(value, dict):
            return None
        return {k: _dashboard_value(k, value.get(k)) for k in _NESTED_KEYS[name]}
    if isinstance(value, str):
        text = redact(value, name)
        if name == "answerPreview":
            text = text.splitlines()[0] if text.splitlines() else ""
        cap = 4096 if full_text else (512 if name in {"detail", "url"} else 160)
        return redact(text, name, cap=cap)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return None


def _dashboard_row(key: str, raw: Mapping[str, Any]) -> dict:
    out = {}
    for name in SEAT_ROW_KEYS[key]:
        value = raw.get(name)
        if name == "launch" and key in {"seat_nodes_all_rows", "seat_nodes_week_rows"}:
            out[name] = value if type(value) is int and value >= 0 else None
        else:
            out[name] = _dashboard_value(name, value, full_text=key == "seat_jobs" and name in _JOB_TEXT_FIELDS)
    return out


def _dashboard_rows(key: str, raw: object) -> list[dict]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [_dashboard_row(key, item) for item in raw if isinstance(item, dict)]


def _dashboard_block(key: str, raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    return {name: _dashboard_value(name, raw.get(name)) for name in SEAT_BLOCK_KEYS[key]}


def shape_dashboard_document(doc: Mapping[str, Any]) -> dict:
    """Shape the additive round-9 blocks before the manager validates its output.

    The manager supplies sanitised ledger facts. This boundary selects each API
    field explicitly and enforces document caps; it does not replace the shared
    third-party-text sanitiser or relax the validator. Existing v2 blocks survive.
    """
    out = dict(doc)
    running = _dashboard_rows("seat_current_jobs", doc.get("currentJobs"))
    running.sort(key=lambda row: parse_iso(row.get("startedUtc")) or 0.0, reverse=True)
    out["currentJobs"] = running
    # Only the running jobs and the newest finished job belong here, never the
    # 400 full replies retained by the ledger. Preserve the supplied job order.
    job_ids = {r["jobId"] for r in running if r.get("jobId") is not None}
    jobs = _dashboard_rows("seat_jobs", doc.get("jobs"))
    last = next((r for r in jobs if r.get("jobId") not in job_ids), None)
    out["jobs"] = [r for r in jobs if r.get("jobId") in job_ids][:len(running)]
    if last is not None:
        out["jobs"].append(last)
    records = _dict(doc.get("records"))
    out["records"] = {"rows": _dashboard_rows("seat_records_rows", records.get("rows"))[:400],
                      "window": _dashboard_block("seat_records_window", records.get("window"))}
    nodes = _dict(doc.get("nodes"))
    out["nodes"] = {"allRows": _dashboard_rows("seat_nodes_all_rows", nodes.get("allRows")),
                    "weekRows": _dashboard_rows("seat_nodes_week_rows", nodes.get("weekRows")),
                    "coverage": _dashboard_block("seat_nodes_coverage", nodes.get("coverage"))}
    seat = dict(_dict(doc.get("seat")))
    for name in ("autoUpdate", "runtimeWrapper"):
        seat[name] = _dashboard_value(name, seat.get(name))
    out["seat"] = seat
    cost = dict(_dict(doc.get("cost")))
    cost["outputTokens"] = _dashboard_block("seat_output_tokens", cost.get("outputTokens"))
    out["cost"] = cost
    control = dict(_dict(doc.get("control")))
    control["plan"] = _dashboard_block("seat_control_plan", control.get("plan"))
    for name in ("status", "mode"):
        control[name] = _dashboard_value(name, control.get(name))
    out["control"] = control
    return out


class _Fold:
    """Per-call state: the sources block, the gating decisions, the row shaper."""

    def __init__(self, sources: Mapping[str, Any]) -> None:
        self.sources = sources

    def gated(self, name: str | None) -> bool:
        """True when a value fed by source *name* must fold to ``None`` (mutation proof 8).

        A source that is ``ok: false`` gates its fields, except an API source
        (:data:`LAST_GOOD_SOURCES`) that is not yet ``unavailable`` -- its
        last-good values stay behind their own ``asOfUtc``.  An absent source
        (``--offline`` removes the API entries) and ``ok: null`` gate nothing:
        the document carries ``None`` there anyway.
        """
        if name is None:
            return False
        source = self.sources.get(name)
        if not isinstance(source, dict) or source.get("ok") is not False:
            return False
        if name in LAST_GOOD_SOURCES and source.get("unavailable") is not True:
            return False
        return True

    def value(self, key: str, raw: object, field: str | None = None) -> object:
        if self.gated(SEAT_FIELD_SOURCES.get(key)):
            return None
        return _clean(raw, field)

    def block(self, key: str, raw: object) -> dict | None:
        if self.gated(SEAT_FIELD_SOURCES.get(key)) or not isinstance(raw, dict):
            return None
        return {name: _clean(raw.get(name), name) for name in SEAT_BLOCK_KEYS[key]}

    def rows(self, key: str, raw: object) -> list[dict] | None:
        if self.gated(SEAT_FIELD_SOURCES.get(key)):
            return None
        if not isinstance(raw, (list, tuple)):
            return []
        return [self.row(key, item) for item in raw if isinstance(item, dict)]

    def row(self, key: str, raw: Mapping[str, Any]) -> dict:
        if key in _DASHBOARD_ROWS:
            return _dashboard_row(key, raw)
        gates = SEAT_ROW_FIELD_SOURCES.get(key, {})
        out: dict = {}
        for name in SEAT_ROW_KEYS[key]:
            if name in gates and self.gated(gates[name]):
                out[name] = _ROW_GATED_VALUES.get(name)
            else:
                out[name] = _clean(raw.get(name), name)
        return out


def fold_status_document(
    doc: dict,
    *,
    now: float | None = None,
    log_lines: Sequence[dict] = (),
    log_seq: int = 0,
) -> dict:
    """The §7 document to the flat dict of exactly :data:`SEAT_KEYS`.

    ``now=None`` makes ``completedAtUtc`` the reference clock, so a fixture
    folds deterministically.  Every value is source-gated (:class:`_Fold`),
    redacted and ``None``-never-``0``.  ``log_lines`` are the tail's
    ``LogLine`` dicts; only those with ``seq > log_seq`` are emitted.  The five
    WP7 keys -- ``seat_hero_state``, ``seat_hero_reasons``,
    ``seat_daemon_offline``, ``seat_log_footer``, ``seat_ledger_footer`` --
    are derived by ``analytics/seat_signals``.
    """
    d = shape_dashboard_document(_dict(doc))
    sources = _dict(d.get("sources"))
    f = _Fold(sources)
    host = _dict(d.get("host"))
    seat = _dict(d.get("seat"))
    runtime = _dict(seat.get("runtime"))
    skills = _dict(seat.get("skills"))
    daemon = _dict(d.get("daemon"))
    auth = _dict(d.get("auth"))
    unit = _dict(d.get("unit"))
    tasks = _dict(d.get("tasks"))
    today = _dict(d.get("today"))
    cost = _dict(d.get("cost"))
    standing = _dict(d.get("standing"))
    plane = _dict(d.get("plane"))
    machine = _dict(d.get("machine"))
    control = _dict(d.get("control"))

    completed_epoch = parse_iso(d.get("completedAtUtc"))
    if now is None:
        last_updated: float = 0.0 if completed_epoch is not None else 999.0
    elif completed_epoch is None:
        last_updated = 999.0
    else:
        last_updated = max(0.0, float(now) - completed_epoch)
    poll = d.get("pollInterval")
    poll_interval = poll if isinstance(poll, int) and not isinstance(poll, bool) and poll > 0 else POLL_INTERVAL_DEFAULT

    flat_sources: dict[str, dict] = {}
    for name in SOURCE_NAMES:
        source = sources.get(name)
        if isinstance(source, dict):
            flat_sources[name] = {k: _clean(source.get(k), k) for k in _SOURCE_KEYS}
    rows = f.rows("seat_tasks_rows", tasks.get("rows"))
    first_row = rows[0] if rows else None
    last_task = None if first_row is None else {k: first_row.get(k) for k in _LAST_TASK_KEYS}
    new_lines = [
        {k: _clean(_dict(line).get(k), k) for k in SEAT_ROW_KEYS["seat_log_lines"]}
        for line in log_lines
        if isinstance(line, dict) and isinstance(line.get("seq"), int) and line["seq"] > log_seq
    ]
    if f.gated("tail"):
        new_lines_out: list[dict] | None = None
    else:
        new_lines_out = new_lines
    newest_seq = max([log_seq] + [line["seq"] for line in new_lines])

    tail_src = _dict(sources.get("tail"))
    window = _dict(tasks.get("window"))
    tail_gated = f.gated("tail")
    # spec §6 rule 4 / mutation proof 8: the hero reads source-gated blocks -- a gated source (tail not ok, unit not ok,
    # standing `unavailable`) contributes none of its stale last-good values. `sources` stays intact (tail-dead / tail-exited
    # detection reads it) and `control.restartRequired` is kept.
    hero_doc = dict(d)
    if f.gated("standing"):
        hero_doc["standing"] = {}
    if tail_gated:
        hero_doc["daemon"] = {}
    if f.gated("unit"):
        hero_doc["unit"] = {}
    hero, hero_reasons = hero_state(hero_doc, now=float(now) if now is not None else (completed_epoch if completed_epoch is not None else 0.0))
    if tail_gated:
        daemon_offline = None
    else:
        daemon_offline = offline_state(
            consecutive_disconnected_beats=daemon.get("consecutiveDisconnectedBeats"),
            presence_connected=None if f.gated("standing") else standing.get("presenceConnected"),
            heartbeat_age_s=daemon.get("heartbeatAgeS"),
        )
    log_foot = log_footer(
        kind=window.get("source") if isinstance(window.get("source"), str) else None,
        cursor_age_s=None if tail_gated else daemon.get("heartbeatAgeS"),
        grammar_version=seat.get("daemonVersion") if isinstance(seat.get("daemonVersion"), str) else None,
        verified_version=GRAMMAR_VERSION_PINNED,
        reason=tail_src.get("reason") if isinstance(tail_src.get("reason"), str) else None,
    )
    ledger_foot = ledger_footer(
        source=None if tail_gated else window.get("source"),
        from_utc=window.get("fromUtc"),
        rows=window.get("rows"),
        ledger_since_utc=window.get("ledgerSinceUtc"),
        gap_note=window.get("gapNote"),
        divergence=None if f.gated("seatWork") else today.get("divergence"),
        tail_reason=tail_src.get("reason") if isinstance(tail_src.get("reason"), str) else None,
        backfill_discarded_utc=window.get("backfillDiscardedUtc") if isinstance(window.get("backfillDiscardedUtc"), str) else None,
    )

    flat: dict[str, Any] = {
        # meta
        "seat_schema_version": _clean(d.get("schemaVersion")),
        "seat_producer": _clean(d.get("producer")),
        "seat_started_at_utc": _clean(d.get("startedAtUtc")),
        "seat_completed_at_utc": _clean(d.get("completedAtUtc")),
        "seat_host_kind": _clean(host.get("kind")),
        "seat_host_unit": _clean(host.get("unit")),
        "seat_host_container": _clean(host.get("container")),
        "seat_host_runtime": _clean(host.get("runtime")),
        "seat_hostname": _clean(host.get("hostname")),
        "seat_offline": not any(name in sources for name in LAST_GOOD_SOURCES),
        "seat_sources": flat_sources,
        "seat_as_of_hhmm": {name: as_of_hhmm(_dict(sources.get(name)).get("asOfUtc")) for name in SOURCE_NAMES},
        # seat
        "seat_token_id": f.value("seat_token_id", seat.get("tokenId")),
        "seat_agent_id": f.value("seat_agent_id", seat.get("agentId")),
        "seat_device_key_public": f.value("seat_device_key_public", truncate_id(seat.get("deviceKeyPublic"))),
        "seat_wallet": f.value("seat_wallet", truncate_id(seat.get("wallet"))),
        "seat_server": f.value("seat_server", seat.get("server")),
        "seat_eligibility": f.value("seat_eligibility", seat.get("eligibility")),
        "seat_capacity": f.value("seat_capacity", seat.get("capacity")),
        "seat_offers": f.value("seat_offers", seat.get("offers")),
        "seat_daemon_version": f.value("seat_daemon_version", seat.get("daemonVersion")),
        "seat_runtime_id": f.value("seat_runtime_id", runtime.get("id")),
        "seat_runtime_version": f.value("seat_runtime_version", runtime.get("version")),
        "seat_release_available": f.value("seat_release_available", seat.get("releaseAvailable")),
        "seat_build_mismatch": f.value("seat_build_mismatch", seat.get("buildMismatch")),
        "seat_skills_offered": f.value("seat_skills_offered", skills.get("offered")),
        "seat_skills_on": f.value("seat_skills_on", skills.get("on")),
        "seat_skills_opt_out": f.value("seat_skills_opt_out", skills.get("optOut")),
        "seat_skills_needs_network": f.value("seat_skills_needs_network", skills.get("needsNetwork")),
        "seat_skills_rows": f.rows("seat_skills_rows", skills.get("rows")),
        "seat_tools": f.value("seat_tools", seat.get("tools")),
        "seat_inference": f.value("seat_inference", seat.get("inference")),
        "seat_premium_advertised": f.value("seat_premium_advertised", seat.get("premiumAdvertised")),
        "seat_hints": f.value("seat_hints", seat.get("hints")),
        "seat_config_changed_since_start": f.value("seat_config_changed_since_start", seat.get("configChangedSinceStart")),
        # daemon
        "seat_daemon_state": f.value("seat_daemon_state", daemon.get("state")),
        "seat_daemon_uptime": f.value("seat_daemon_uptime", daemon.get("uptime")),
        "seat_daemon_work": f.value("seat_daemon_work", daemon.get("work")),
        "seat_daemon_running": f.value("seat_daemon_running", daemon.get("running")),
        "seat_daemon_submitted_since_start": f.value("seat_daemon_submitted_since_start", daemon.get("submittedSinceStart")),
        "seat_daemon_last_heartbeat_utc": f.value("seat_daemon_last_heartbeat_utc", daemon.get("lastHeartbeatUtc")),
        "seat_daemon_heartbeat_age_s": f.value("seat_daemon_heartbeat_age_s", daemon.get("heartbeatAgeS")),
        "seat_daemon_idle_beats": f.value("seat_daemon_idle_beats", daemon.get("idleBeats")),
        "seat_daemon_fleet_online": f.value("seat_daemon_fleet_online", daemon.get("fleetOnline")),
        "seat_daemon_fleet_enrolled": f.value("seat_daemon_fleet_enrolled", daemon.get("fleetEnrolled")),
        "seat_daemon_paused_hint": f.value("seat_daemon_paused_hint", daemon.get("pausedHint")),
        "seat_daemon_invocation_id": f.value("seat_daemon_invocation_id", daemon.get("invocationId")),
        "seat_daemon_last_admitted_utc": f.value("seat_daemon_last_admitted_utc", daemon.get("lastAdmittedUtc")),
        "seat_daemon_disconnects_24h": f.value("seat_daemon_disconnects_24h", daemon.get("disconnects24h")),
        "seat_daemon_reconnects_24h": f.value("seat_daemon_reconnects_24h", daemon.get("reconnects24h")),
        "seat_daemon_consecutive_disconnected_beats": f.value(
            "seat_daemon_consecutive_disconnected_beats", daemon.get("consecutiveDisconnectedBeats")
        ),
        "seat_daemon_offline": daemon_offline,
        # auth
        "seat_auth_degraded": f.value("seat_auth_degraded", auth.get("degraded")),
        "seat_auth_reasons": f.value("seat_auth_reasons", auth.get("reasons")),
        "seat_auth_since_utc": f.value("seat_auth_since_utc", auth.get("sinceUtc")),
        "seat_auth_credential_file_mtime_utc": f.value(
            "seat_auth_credential_file_mtime_utc", auth.get("credentialFileMtimeUtc")
        ),
        # unit
        "seat_unit_active_state": f.value("seat_unit_active_state", unit.get("activeState")),
        "seat_unit_sub_state": f.value("seat_unit_sub_state", unit.get("subState")),
        "seat_unit_main_pid": f.value("seat_unit_main_pid", unit.get("mainPid")),
        "seat_unit_since_utc": f.value("seat_unit_since_utc", unit.get("sinceUtc")),
        "seat_unit_restarts": f.value("seat_unit_restarts", unit.get("restarts")),
        "seat_unit_boot_enabled": f.value("seat_unit_boot_enabled", unit.get("bootEnabled")),
        "seat_unit_restart_policy": f.value("seat_unit_restart_policy", unit.get("restartPolicy")),
        "seat_unit_kill_mode": f.value("seat_unit_kill_mode", unit.get("killMode")),
        "seat_unit_stop_timeout_s": f.value("seat_unit_stop_timeout_s", unit.get("stopTimeoutS")),
        "seat_unit_graceful_stop_possible": f.value("seat_unit_graceful_stop_possible", unit.get("gracefulStopPossible")),
        "seat_unit_memory_current_b": f.value("seat_unit_memory_current_b", unit.get("memoryCurrentB")),
        "seat_unit_memory_peak_b": f.value("seat_unit_memory_peak_b", unit.get("memoryPeakB")),
        "seat_unit_memory_max_b": f.value("seat_unit_memory_max_b", unit.get("memoryMaxB")),
        "seat_unit_cpu_quota": f.value("seat_unit_cpu_quota", unit.get("cpuQuota")),
        "seat_unit_tasks_current": f.value("seat_unit_tasks_current", unit.get("tasksCurrent")),
        # current / queue
        "seat_current": f.block("seat_current", d.get("current")),
        "seat_queue": f.block("seat_queue", d.get("queue")),
        # tasks
        "seat_tasks_window": f.value("seat_tasks_window", tasks.get("window")),
        "seat_tasks_rows": rows,
        "seat_last_task": last_task,
        # today
        "seat_today_day_utc": f.value("seat_today_day_utc", today.get("dayUtc")),
        "seat_today_tasks": f.value("seat_today_tasks", today.get("tasks")),
        "seat_today_stored": f.value("seat_today_stored", today.get("stored")),
        "seat_today_not_stored": f.value("seat_today_not_stored", today.get("notStored")),
        "seat_today_p50_s": f.value("seat_today_p50_s", today.get("p50S")),
        "seat_today_longest_s": f.value("seat_today_longest_s", today.get("longestS")),
        "seat_today_accepted": f.value("seat_today_accepted", today.get("accepted")),
        "seat_today_rejected": f.value("seat_today_rejected", today.get("rejected")),
        "seat_today_failed": f.value("seat_today_failed", today.get("failed")),
        "seat_today_pending": f.value("seat_today_pending", today.get("pending")),
        "seat_today_verdict_lag_p50_s": f.value("seat_today_verdict_lag_p50_s", today.get("verdictLagP50S")),
        "seat_today_verdicts_as_of_utc": f.value("seat_today_verdicts_as_of_utc", today.get("verdictsAsOfUtc")),
        "seat_today_divergence": f.value("seat_today_divergence", today.get("divergence")),
        # cost
        "seat_cost_window_days": f.value("seat_cost_window_days", cost.get("windowDays")),
        "seat_cost_tasks": f.value("seat_cost_tasks", cost.get("tasks")),
        "seat_cost_excluded": f.value("seat_cost_excluded", cost.get("excluded")),
        "seat_cost_turns": f.value("seat_cost_turns", cost.get("turns")),
        "seat_cost_tokens": f.value("seat_cost_tokens", cost.get("tokens")),
        "seat_cost_buckets": f.rows("seat_cost_buckets", cost.get("buckets")),
        "seat_cost_side_model": f.value("seat_cost_side_model", cost.get("sideModel")),
        "seat_cost_series": f.value("seat_cost_series", cost.get("series")),
        "seat_cost_depth": f.value("seat_cost_depth", cost.get("depth")),
        "seat_quota": f.block("seat_quota", d.get("quota")),
        # standing
        "seat_standing_attempts": f.value("seat_standing_attempts", standing.get("attempts")),
        "seat_standing_accepted": f.value("seat_standing_accepted", standing.get("accepted")),
        "seat_standing_rejected": f.value("seat_standing_rejected", standing.get("rejected")),
        "seat_standing_failed": f.value("seat_standing_failed", standing.get("failed")),
        "seat_standing_pending": f.value("seat_standing_pending", standing.get("pending")),
        "seat_standing_counters_inconsistent": f.value(
            "seat_standing_counters_inconsistent", standing.get("countersInconsistent")
        ),
        "seat_standing_working": f.value("seat_standing_working", standing.get("working")),
        "seat_standing_running": f.rows("seat_standing_running", standing.get("running")),
        "seat_standing_consecutive_failures": f.value(
            "seat_standing_consecutive_failures", standing.get("consecutiveFailures")
        ),
        "seat_standing_paused_until": f.value("seat_standing_paused_until", standing.get("pausedUntil")),
        "seat_standing_breaker": f.value("seat_standing_breaker", standing.get("breaker")),
        "seat_standing_recent_failures": f.rows("seat_standing_recent_failures", standing.get("recentFailures")),
        "seat_standing_presence_connected": f.value("seat_standing_presence_connected", standing.get("presenceConnected")),
        "seat_standing_heartbeat_age_ms": f.value("seat_standing_heartbeat_age_ms", standing.get("heartbeatAgeMs")),
        "seat_standing_as_of_utc": f.value("seat_standing_as_of_utc", standing.get("asOfUtc")),
        # plane
        "seat_plane_version": f.value("seat_plane_version", plane.get("version")),
        "seat_plane_verifier_up": f.value("seat_plane_verifier_up", plane.get("verifierUp")),
        "seat_plane_verifier_last_seen_utc": f.value("seat_plane_verifier_last_seen_utc", plane.get("verifierLastSeenUtc")),
        "seat_plane_awaiting_verdict": f.value("seat_plane_awaiting_verdict", plane.get("awaitingVerdict")),
        "seat_plane_connected_daemons": f.value("seat_plane_connected_daemons", plane.get("connectedDaemons")),
        "seat_plane_as_of_utc": f.value("seat_plane_as_of_utc", plane.get("asOfUtc")),
        # machine
        "seat_machine_load1": f.value("seat_machine_load1", machine.get("load1")),
        "seat_machine_mem_avail_mib": f.value("seat_machine_mem_avail_mib", machine.get("memAvailMiB")),
        "seat_machine_disk_free_gib": f.value("seat_machine_disk_free_gib", machine.get("diskFreeGiB")),
        "seat_machine_work_dirs": f.value("seat_machine_work_dirs", machine.get("workDirs")),
        "seat_machine_work_bytes": f.value("seat_machine_work_bytes", machine.get("workBytes")),
        "seat_machine_abnormal_lease_dirs": f.value("seat_machine_abnormal_lease_dirs", machine.get("abnormalLeaseDirs")),
        "seat_machine_outbox_files": f.value("seat_machine_outbox_files", machine.get("outboxFiles")),
        "seat_machine_journal": f.value("seat_machine_journal", machine.get("journal")),
        "seat_machine_transcript_retention": f.value(
            "seat_machine_transcript_retention", machine.get("transcriptRetention")
        ),
        "seat_machine_orphans": f.rows("seat_machine_orphans", machine.get("orphans")),
        # control
        "seat_control_broker_reachable": f.value("seat_control_broker_reachable", control.get("brokerReachable")),
        "seat_control_gate": f.block("seat_control_gate", control.get("gate")),
        "seat_control_drain": f.block("seat_control_drain", control.get("drain")),
        "seat_control_in_flight": f.block("seat_control_in_flight", control.get("inFlight")),
        "seat_control_restart_required": f.value("seat_control_restart_required", control.get("restartRequired")),
        "seat_control_last_audit": f.rows("seat_control_last_audit", control.get("lastAudit")),
        # derived for widgets -- WP7 completes the first two and the footers
        "seat_hero_state": hero,
        "seat_hero_reasons": [redact(r) for r in hero_reasons],
        "seat_log_lines": new_lines_out,
        "seat_log_seq": newest_seq,
        "seat_log_footer": log_foot,
        "seat_ledger_footer": ledger_foot,
        # round 9
        "seat_current_jobs": f.rows("seat_current_jobs", d.get("currentJobs")),
        "seat_jobs": f.rows("seat_jobs", d.get("jobs")),
        "seat_records_rows": f.rows("seat_records_rows", _dict(d.get("records")).get("rows")),
        "seat_records_window": f.block("seat_records_window", _dict(d.get("records")).get("window")),
        "seat_nodes_all_rows": f.rows("seat_nodes_all_rows", _dict(d.get("nodes")).get("allRows")),
        "seat_nodes_week_rows": f.rows("seat_nodes_week_rows", _dict(d.get("nodes")).get("weekRows")),
        "seat_nodes_coverage": f.block("seat_nodes_coverage", _dict(d.get("nodes")).get("coverage")),
        "seat_auto_update": f.value("seat_auto_update", seat.get("autoUpdate")),
        "seat_runtime_wrapper": f.value("seat_runtime_wrapper", seat.get("runtimeWrapper")),
        "seat_output_tokens": f.block("seat_output_tokens", cost.get("outputTokens")),
        "seat_control_plan": f.block("seat_control_plan", control.get("plan")),
        "seat_control_status": f.value("seat_control_status", control.get("status")),
        "seat_control_mode": f.value("seat_control_mode", control.get("mode")),
        # status bar
        "last_updated_seconds_ago": last_updated,
        "error_count": sum(1 for s in sources.values() if isinstance(s, dict) and s.get("ok") is False),
        "poll_interval": poll_interval,
    }
    return {key: flat[key] for key in SEAT_KEYS}

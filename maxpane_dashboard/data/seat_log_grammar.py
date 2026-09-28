"""The daemon's stdout grammar, anchored at its ISO stamp (spec §5.1, Appendix B).

Every daemon line is ``<ISO-8601 ms Z> <text>``. Task-agent prose forges
event-like text (journal line 4876: ``working: … the accepted recipe must
cite …``), so every pattern starts at the stamp and is matched with
``fullmatch`` — never ``search``. Classification uses raw text so control-only objectives cannot
remove lifecycle events; emitted text and every captured field are redacted.

Pinned to daemon build ``GRAMMAR_VERSION``; a line that matches nothing is
``KIND_UNKNOWN`` and goes to the LOG panel only, never into the ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Mapping

from maxpane_dashboard.analytics.seat_redact import redact

GRAMMAR_VERSION = "0.1.0+5bfa8261"

TS = r"^(?P<ts>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z) "
_TS_RE = re.compile(TS, re.ASCII)

# --- Appendix B, verbatim ------------------------------------------------------------------
HEARTBEAT = re.compile(
    TS + r"(?P<state>alive|disconnected) (?P<uptime>\d+m|\d+h\d+m|\d+d\d+h) · "
    r"(?P<work>idle|(?P<running>\d+) tasks? running) · (?P<submitted>\d+) submitted"
    r"(?: · fleet (?P<online>\d+) online, (?P<enrolled>\d+) enrolled)?"
    r"(?: · (?:paused until (?P<until>\d\d:\d\d) after (?P<failed>\d+) failed runs?(?:: (?P<reason>.*?))? — run imd doctor"
    r"|(?P<unregistered>token not registered as an agent — run imd doctor)))?$",
    re.ASCII,
)

ACCEPTED_CODE = re.compile(
    TS + r"accepted (?P<role>implement|tests|review|integrate) (?P<node8>[0-9a-f]{8}) — (?P<paths>.*?) \(max (?P<max_turns>\d+) turns\)$",
    re.ASCII,
)
ACCEPTED_RESEARCH = re.compile(TS + r"accepted question (?P<node8>[0-9a-f]{8})$", re.ASCII)
ACCEPTED_FUZZ = re.compile(
    TS + r"accepted campaign (?P<node8>[0-9a-f]{8}) — (?P<harness>.+?) \((?P<runs>\d+) runs\)$", re.ASCII
)

ACCEPTED_CODE_HEAD = re.compile(
    TS + r"accepted (?P<role>implement|tests|review|integrate) (?P<node8>[0-9a-f]{8}) —(?: (?!.*\(max \d+ turns\)).*)?$",
    re.ASCII,
)
ACCEPTED_FUZZ_HEAD = re.compile(
    TS + r"accepted campaign (?P<node8>[0-9a-f]{8}) —(?: (?!.*\(\d+ runs\)).*)?$", re.ASCII,
)

PHASE = re.compile(
    TS + r"  (?P<phase>preparing|working|checking|bundling|uploading|repairing): (?P<msg>.{0,160})$", re.ASCII
)
MODEL_LINE = re.compile(TS + r"  working: running (?P<rt>claude|codex|acp)(?: on (?P<model>\S+))?$", re.ASCII)
MODEL_REFUSE = re.compile(
    TS + r"  working: (?P<rt>\w+) refused model (?P<model>\S+); running on its default model instead$", re.ASCII
)

SUBMITTED = re.compile(
    TS + r"submitted (?P<role>implement|tests|review|integrate) for (?P<node8>[0-9a-f]{8})$", re.ASCII
)
ANSWERED = re.compile(TS + r"answered (?P<node8>[0-9a-f]{8}) with (?P<citations>\d+) citation\(s\)$", re.ASCII)
FUZZ_OUTCOME = re.compile(
    TS + r"(?:counterexample for (?P<property>.+)|campaign could not run: (?P<detail>.+)|exhausted (?P<runs>\d+) runs, nothing found)$",
    re.ASCII,
)
STORED = re.compile(TS + r"submission stored \((?P<hash12>[0-9a-f]{12})\) — awaiting verdict$", re.ASCII)
CANCELLED = re.compile(
    TS + r"cancelled (?P<lease8>[0-9a-f]{8}): (?P<reason>lease_expired|job_cancelled|superseded|operator)$", re.ASCII
)
SERVER_ERROR = re.compile(
    TS + r"server error \((?P<code>schema_invalid|signature_invalid|unknown_lease|rate_limited|internal)\): (?P<msg>.*)$",
    re.ASCII,
)
RESENDING = re.compile(TS + r"re-sending (?P<n>\d+) unacknowledged result\(s\)$", re.ASCII)
LOCAL_FAIL = re.compile(TS + r"(?P<what>task|question|campaign) failed:(?: (?P<msg>.*))?$", re.ASCII)
RATE_LIMITED = re.compile(TS + r"(?P<msg>.+); pausing new work for five minutes$", re.ASCII)

CONNECTED = re.compile(TS + r"connected to (?P<host>\S+)$", re.ASCII)
ADMITTED = re.compile(TS + r"admitted \(session (?P<session8>[0-9a-f]{8})\)$", re.ASCII)
SERVER_CLOSED = re.compile(
    TS + r"server closed: (?P<reason>not_enrolled|nft_transferred|agent_unregistered|revoked|version_unsupported|duplicate_session|protocol_error|server_shutdown) — (?P<detail>.*)$",
    re.ASCII,
)
RECONNECTING = re.compile(TS + r"reconnecting in (?P<seconds>\d+(?:\.\d+)?)s$", re.ASCII)
WS_RESPONSE = re.compile(TS + r"Unexpected server response: (?P<code>\d{3})$", re.ASCII)
WS_SOCKET = re.compile(
    TS + r"(?P<msg>socket hang up|Client network socket disconnected before secure TLS connection was established)$",
    re.ASCII,
)

RUNTIMES = re.compile(TS + r"runtimes: (?P<list>.+?) \(using (?P<rt>\w+)(?:, as asked)?\)$", re.ASCII)  # restart boundary
PROFILES = re.compile(TS + r"execution profiles: (?P<profiles>.+)$", re.ASCII)
TOOLS_ADV = re.compile(TS + r"tools advertised: (?P<tools>.+)$", re.ASCII)
RELEASE_OK = re.compile(TS + r"release (?P<version>\S+), the latest$", re.ASCII)
RELEASE_AVAIL = re.compile(TS + r"(?P<installed>\S+) installed; (?P<available>\S+) is available; .*$", re.ASCII)
BUILD_SKEW = re.compile(
    TS + r"(?:control plane runs build (?P<plane>\S+); this checkout is (?P<local>\S+).*|build mismatch: (?P<detail>.*))$",
    re.ASCII,
)
SHUTTING_DOWN = re.compile(TS + r"shutting down$", re.ASCII)
UPDATED = re.compile(TS + r"updated (?P<from>\S+) → (?P<to>\S+) \((?P<steps>.*)\)$", re.ASCII)
PAIRED = re.compile(TS + r"paired to token (?P<token>\d+)$", re.ASCII)

# --- kind names = pattern names lower-cased (contract C.5) ---------------------------------
KIND_HEARTBEAT = "heartbeat"
KIND_ACCEPTED_CODE = "accepted_code"
KIND_ACCEPTED_RESEARCH = "accepted_research"
KIND_ACCEPTED_FUZZ = "accepted_fuzz"
KIND_ACCEPTED_CODE_HEAD = "accepted_code_head"
KIND_ACCEPTED_FUZZ_HEAD = "accepted_fuzz_head"
KIND_PHASE = "phase"
KIND_MODEL_LINE = "model_line"
KIND_MODEL_REFUSE = "model_refuse"
KIND_SUBMITTED = "submitted"
KIND_ANSWERED = "answered"
KIND_FUZZ_OUTCOME = "fuzz_outcome"
KIND_STORED = "stored"
KIND_CANCELLED = "cancelled"
KIND_SERVER_ERROR = "server_error"
KIND_RESENDING = "resending"
KIND_LOCAL_FAIL = "local_fail"
KIND_RATE_LIMITED = "rate_limited"
KIND_CONNECTED = "connected"
KIND_ADMITTED = "admitted"
KIND_SERVER_CLOSED = "server_closed"
KIND_RECONNECTING = "reconnecting"
KIND_WS_RESPONSE = "ws_response"
KIND_WS_SOCKET = "ws_socket"
KIND_RUNTIMES = "runtimes"
KIND_PROFILES = "profiles"
KIND_TOOLS_ADV = "tools_adv"
KIND_RELEASE_OK = "release_ok"
KIND_RELEASE_AVAIL = "release_avail"
KIND_BUILD_SKEW = "build_skew"
KIND_SHUTTING_DOWN = "shutting_down"
KIND_UPDATED = "updated"
KIND_PAIRED = "paired"
KIND_UNIT_EVENT = "unit_event"  # systemd's own Started/Stopped/Consumed lines (no daemon stamp)
KIND_UNKNOWN = "unknown"

#: (kind, pattern) in MATCH ORDER. MODEL_LINE and MODEL_REFUSE precede PHASE because
#: ``  working: running codex on gpt-6-luna`` also satisfies PHASE; RATE_LIMITED is last
#: among the stamped patterns because its ``(?P<msg>.+)`` head is the least specific.
PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (KIND_HEARTBEAT, HEARTBEAT),
    (KIND_ACCEPTED_CODE, ACCEPTED_CODE),
    (KIND_ACCEPTED_RESEARCH, ACCEPTED_RESEARCH),
    (KIND_ACCEPTED_FUZZ, ACCEPTED_FUZZ),
    (KIND_ACCEPTED_CODE_HEAD, ACCEPTED_CODE_HEAD),
    (KIND_ACCEPTED_FUZZ_HEAD, ACCEPTED_FUZZ_HEAD),
    (KIND_MODEL_LINE, MODEL_LINE),
    (KIND_MODEL_REFUSE, MODEL_REFUSE),
    (KIND_PHASE, PHASE),
    (KIND_SUBMITTED, SUBMITTED),
    (KIND_ANSWERED, ANSWERED),
    (KIND_FUZZ_OUTCOME, FUZZ_OUTCOME),
    (KIND_STORED, STORED),
    (KIND_CANCELLED, CANCELLED),
    (KIND_SERVER_ERROR, SERVER_ERROR),
    (KIND_RESENDING, RESENDING),
    (KIND_LOCAL_FAIL, LOCAL_FAIL),
    (KIND_CONNECTED, CONNECTED),
    (KIND_ADMITTED, ADMITTED),
    (KIND_SERVER_CLOSED, SERVER_CLOSED),
    (KIND_RECONNECTING, RECONNECTING),
    (KIND_WS_RESPONSE, WS_RESPONSE),
    (KIND_WS_SOCKET, WS_SOCKET),
    (KIND_RUNTIMES, RUNTIMES),
    (KIND_PROFILES, PROFILES),
    (KIND_TOOLS_ADV, TOOLS_ADV),
    (KIND_RELEASE_OK, RELEASE_OK),
    (KIND_RELEASE_AVAIL, RELEASE_AVAIL),
    (KIND_BUILD_SKEW, BUILD_SKEW),
    (KIND_SHUTTING_DOWN, SHUTTING_DOWN),
    (KIND_UPDATED, UPDATED),
    (KIND_PAIRED, PAIRED),
    (KIND_RATE_LIMITED, RATE_LIMITED),
)

ACCEPTED_KINDS = frozenset({KIND_ACCEPTED_CODE, KIND_ACCEPTED_RESEARCH, KIND_ACCEPTED_FUZZ,
                            KIND_ACCEPTED_CODE_HEAD, KIND_ACCEPTED_FUZZ_HEAD})
TERMINAL_KINDS = frozenset({KIND_SUBMITTED, KIND_ANSWERED, KIND_FUZZ_OUTCOME, KIND_STORED, KIND_CANCELLED, KIND_LOCAL_FAIL})
CONNECTION_KINDS = frozenset(
    {KIND_CONNECTED, KIND_ADMITTED, KIND_SERVER_CLOSED, KIND_RECONNECTING, KIND_WS_RESPONSE, KIND_WS_SOCKET}
)
HIGHLIGHT_KINDS = frozenset(
    {KIND_RATE_LIMITED, KIND_BUILD_SKEW, KIND_RELEASE_AVAIL, KIND_LOCAL_FAIL, KIND_RESENDING, KIND_CANCELLED}
)

#: systemd's own lines carry no daemon stamp. Measured in journal7d.txt: 25 lines are
#: ``Started|Stopping|Stopped imd-worker.service - …`` and 16 are prefixed by the unit name
#: (``imd-worker.service: Deactivated successfully.``, ``imd-worker.service: Consumed …``) —
#: the optional ``<unit>.service: `` head is a recorded deviation from contract C.5.
UNIT_EVENT_RE = re.compile(
    r"(?:[\w@.-]+\.service: )?(?P<event>Started|Stopped|Stopping|Consumed|Deactivated|Scheduled restart)\b.*",
    re.ASCII,
)

#: Docker's ``--timestamps`` prefix is RFC3339Nano: 9 fraction digits on 15,882 of 15,882
#: measured lines; Go trims trailing zeros, so 1–9 are accepted. The daemon's own stamp has
#: exactly 3. A first stamp is Docker's when a second stamp follows it or when its fraction
#: is not 3 digits; otherwise the line is a bare daemon line and is returned unchanged.
_DOCKER_PREFIX_RE = re.compile(
    r"^(?P<stamp>\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.(?P<frac>\d{1,9}))?Z) (?P<rest>.*)$", re.ASCII | re.DOTALL
)

@dataclass(frozen=True)
class LogLine:
    ts: str  # the daemon's ISO ms Z stamp as printed; "" for unit events / unstamped unknown lines
    invocation: str | None  # _SYSTEMD_INVOCATION_ID (journald) | None
    text: str  # redacted, control-stripped full line (stamp included)
    kind: str  # KIND_*
    cursor: str | None  # __CURSOR (journald) | None
    fields: Mapping[str, str | None] = field(default_factory=dict)  # named groups of the matching pattern
    seq: int = 0  # monotonic per TailThread / ListLineSource run


def classify(line: str, *, invocation: str | None = None, cursor: str | None = None, seq: int = 0) -> LogLine:
    """Classify raw lines, then redact all emitted text and captures before storage/render."""
    raw = line.rstrip("\r\n")
    text = redact(raw)
    for kind, pattern in PATTERNS:
        match = pattern.fullmatch(raw)
        if match is not None:
            return LogLine(
                ts=match.group("ts"), invocation=invocation, text=text, kind=kind, cursor=cursor,
                fields={key: redact(value) if value is not None else None for key, value in match.groupdict().items()}, seq=seq,
            )
    unit = UNIT_EVENT_RE.fullmatch(text)
    if unit is not None:
        return LogLine(
            ts="", invocation=invocation, text=text, kind=KIND_UNIT_EVENT, cursor=cursor,
            fields={"event": unit.group("event")}, seq=seq,
        )
    stamped = _TS_RE.match(text)
    return LogLine(
        ts=stamped.group("ts") if stamped is not None else "", invocation=invocation, text=text,
        kind=KIND_UNKNOWN, cursor=cursor, fields={}, seq=seq,
    )


def parse_ts(ts: str) -> float | None:
    """Epoch seconds from the daemon's ``YYYY-MM-DDTHH:MM:SS.mmmZ`` stamp; ``None`` when unusable."""
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc).timestamp()
    except (TypeError, ValueError):
        return None


def is_terminal(kind: str) -> bool:
    return kind in TERMINAL_KINDS


def is_accept(kind: str) -> bool:
    return kind in ACCEPTED_KINDS


def strip_docker_prefix(raw: str) -> str:
    """Drop Docker's ``--timestamps`` prefix; the daemon's own stamp remains.

    A Docker line without a daemon stamp (a node crash trace, an npm warning) still loses its
    prefix and then classifies ``unknown``. A journald line — one 3-digit stamp and no second
    stamp — is returned unchanged, so the function is safe to call on either transport.
    """
    match = _DOCKER_PREFIX_RE.match(raw)
    if match is None:
        return raw
    rest = match.group("rest")
    frac = match.group("frac") or ""
    if len(frac) != 3 or _TS_RE.match(rest) is not None:
        return rest
    return raw


__all__ = [
    "GRAMMAR_VERSION", "TS", "HEARTBEAT", "ACCEPTED_CODE", "ACCEPTED_RESEARCH", "ACCEPTED_FUZZ", "PHASE",
    "MODEL_LINE", "MODEL_REFUSE", "SUBMITTED", "ANSWERED", "FUZZ_OUTCOME", "STORED", "CANCELLED", "SERVER_ERROR",
    "RESENDING", "LOCAL_FAIL", "RATE_LIMITED", "CONNECTED", "ADMITTED", "SERVER_CLOSED", "RECONNECTING",
    "WS_RESPONSE", "WS_SOCKET", "RUNTIMES", "PROFILES", "TOOLS_ADV", "RELEASE_OK", "RELEASE_AVAIL", "BUILD_SKEW",
    "SHUTTING_DOWN", "UPDATED", "PAIRED", "PATTERNS", "UNIT_EVENT_RE",
    "ACCEPTED_CODE_HEAD", "ACCEPTED_FUZZ_HEAD", "KIND_ACCEPTED_CODE_HEAD", "KIND_ACCEPTED_FUZZ_HEAD",
    "KIND_HEARTBEAT", "KIND_ACCEPTED_CODE", "KIND_ACCEPTED_RESEARCH", "KIND_ACCEPTED_FUZZ", "KIND_PHASE",
    "KIND_MODEL_LINE", "KIND_MODEL_REFUSE", "KIND_SUBMITTED", "KIND_ANSWERED", "KIND_FUZZ_OUTCOME", "KIND_STORED",
    "KIND_CANCELLED", "KIND_SERVER_ERROR", "KIND_RESENDING", "KIND_LOCAL_FAIL", "KIND_RATE_LIMITED", "KIND_CONNECTED",
    "KIND_ADMITTED", "KIND_SERVER_CLOSED", "KIND_RECONNECTING", "KIND_WS_RESPONSE", "KIND_WS_SOCKET", "KIND_RUNTIMES",
    "KIND_PROFILES", "KIND_TOOLS_ADV", "KIND_RELEASE_OK", "KIND_RELEASE_AVAIL", "KIND_BUILD_SKEW", "KIND_SHUTTING_DOWN",
    "KIND_UPDATED", "KIND_PAIRED", "KIND_UNIT_EVENT", "KIND_UNKNOWN",
    "ACCEPTED_KINDS", "TERMINAL_KINDS", "CONNECTION_KINDS", "HIGHLIGHT_KINDS",
    "LogLine", "classify", "parse_ts", "is_terminal", "is_accept", "strip_docker_prefix",
]

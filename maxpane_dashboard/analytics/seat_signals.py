"""Pure signal rules of the PEPEPANE dashboard (spec §8 hero, §9 staleness, §5.2, §5.5, §6 rules 3–4).

Boundaries: standard library plus ``analytics.seat_redact`` -- no Textual, no
``subprocess``, no ``socket``, no ``httpx`` (``tests/analytics/test_seat_signals.py::test_seat_signals_imports_are_pure``
and the WP8 purity walk assert it).  Every rule takes ``now``; nothing here reads a clock.

The constants are the spec's named thresholds; each ``#:`` block quotes why.
``data/seat_models.fold_status_document`` imports :func:`hero_state`,
:func:`offline_state`, :func:`as_of_hhmm`, :func:`log_footer` and
:func:`ledger_footer` from here; ``data/seat_manager.py`` imports the rest.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Sequence

from maxpane_dashboard.analytics.seat_redact import redact

__all__ = [
    "AGENT_SENTENCE_CAP", "API_UNAVAILABLE_FAILURES", "API_UNAVAILABLE_S", "AUTH_CREDENTIAL_REFRESH_S",
    "AUTH_FAST_FAIL_S", "CONFIG_REWRITE_GRACE_S", "DISCONNECTED_BEATS_RED", "DOCKER_DEFAULT_STOP_TIMEOUT_S",
    "HEARTBEAT_DEAD_S", "HEARTBEAT_STALE_S", "ID_TRUNCATE_CHARS", "IDLE_WINDOW_S", "MAC_GRACEFUL_STOP_TIMEOUT_S",
    "PAUSED_HINT_MAX_AGE_S", "PLANE_PRESENCE_WINDOW_MS", "SOURCE_LIVE_S", "TAIL_DEAD_S", "VPS_GRACEFUL_STOP_TIMEOUT_S",
    "as_of_hhmm", "config_changed_since_start", "counters_consistent", "day_utc", "divergence", "gate_preview",
    "graceful_stop_possible", "hero_state", "iso_z", "ledger_footer", "log_footer", "offline_state",
    "parse_iso", "parse_pg_timestamp", "pausedhint_active", "rollup_today", "short_build", "source_word",
    "staleness", "tail_state", "verdict_lag_s",
]

HEARTBEAT_STALE_S = 90          #: amber; 3 x the daemon's 30 s LIVENESS_MS (spec §8 hero, §9)
HEARTBEAT_DEAD_S = 300          #: red only together with presence.connected == false or 2 disconnected beats (§9)
TAIL_DEAD_S = 45                #: no thread aliveAt for this long -> sources.tail.ok = false, hero red (§9, §18)
DISCONNECTED_BEATS_RED = 2      #: two consecutive `disconnected` heartbeats; a single beat flashes 5-11x/day (§3 B, §6 rule 3)
IDLE_WINDOW_S = 180             #: idle beats count only heartbeats newer than now - 3 min (§9, §11 gate a)
API_UNAVAILABLE_FAILURES = 3    #: `unavailable (reason)` after 3 consecutive failures ... (§6 rule 4)
API_UNAVAILABLE_S = 600         #: ... or 10 min without a good read (§6 rule 4)
CONFIG_REWRITE_GRACE_S = 60     #: the daemon rewrites config.json at every start; mtime measured to the minute (§5.2)
PLANE_PRESENCE_WINDOW_MS = 60000  #: standing.server.presenceWindowMs, the plane's own staleness reference (§18 open 6)
AUTH_FAST_FAIL_S = 40           #: >=2 consecutive rows finished < 40 s with zero tokens trips auth.degraded (§10)
AUTH_CREDENTIAL_REFRESH_S = 3600  #: credential file mtime within the last hour -> `token refreshed HH:MM (not read)` (§10)
AGENT_SENTENCE_CAP = 160        #: the daemon's own slice(160) on `working:` prose (§13)
ID_TRUNCATE_CHARS = 8           #: device public key and wallet shown as 8 chars (§13 identifiers, §16 #13)
SOURCE_LIVE_S = 15              #: (invented) a source read within three poll intervals reads `live`, not `as of HH:MM`
PAUSED_HINT_MAX_AGE_S = 330     #: (invented) the heartbeat's standing suffix refreshes every 5 min (10 ticks) + one 30 s beat (fill1 §5)
VPS_GRACEFUL_STOP_TIMEOUT_S = 30  #: gracefulStopPossible = KillMode == control-group and TimeoutStopSec >= 30 (§5.5)
MAC_GRACEFUL_STOP_TIMEOUT_S = 45  #: gracefulStopPossible = StopTimeout >= 45 or Init (§5.5)
DOCKER_DEFAULT_STOP_TIMEOUT_S = 10  #: HostConfig.StopTimeout null = Docker's 10 s default (fill1 §3)

#: Postgres text ``2026-09-26 03:11:29.985+00`` and ISO ``2026-09-26T03:11:29.985Z`` alike:
#: date, ' ' or 'T', time, optional 1-6 fraction digits, optional Z / +HH / +HHMM / +HH:MM.
_PG_TS_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?\s*(Z|[+-]\d{2}(?::?\d{2})?)?$",
    re.ASCII,
)
#: A fraction longer than six digits (Docker's RFC3339Nano ``State.StartedAt``) is cut to microseconds.
_LONG_FRACTION_RE = re.compile(r"(\.\d{6})\d+")


# ---------------------------------------------------------------------------
# stamps
# ---------------------------------------------------------------------------


def parse_iso(text: object) -> float | None:
    """``"2026-09-26T03:40:07Z"`` (optionally with a fraction of any length or an
    explicit offset) to epoch seconds; ``None`` for anything unusable.  A stamp
    without a zone is read as UTC, as every stamp in the document is."""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value:
        return None
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    value = _LONG_FRACTION_RE.sub(r"\1", value)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.timestamp()
    except (OverflowError, OSError, ValueError):
        return None


def parse_pg_timestamp(text: object) -> float | None:
    """Epoch seconds from Postgres text (``2026-09-26 03:11:29.985+00``) or ISO Z; ``None`` when unusable.

    A verbatim copy of ``data.seat_api._parse_pg_timestamp`` (WP5 deviation 1);
    ``test_parse_pg_timestamp_equals_seat_api_private`` keeps the two equal.
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


def iso_z(epoch: float, *, millis: bool = False) -> str:
    """Epoch seconds to ``YYYY-MM-DDTHH:MM:SSZ`` (``.mmmZ`` with *millis*)."""
    stamp = datetime.fromtimestamp(float(epoch), tz=timezone.utc)
    text = stamp.strftime("%Y-%m-%dT%H:%M:%S")
    if millis:
        text += f".{stamp.microsecond // 1000:03d}"
    return text + "Z"


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


def day_utc(epoch: float) -> str:
    """The UTC calendar day of *epoch* as ``YYYY-MM-DD`` (the ``days`` table key)."""
    return datetime.fromtimestamp(float(epoch), tz=timezone.utc).strftime("%Y-%m-%d")


def short_build(version: object) -> str | None:
    """``0.1.0+5bfa8261`` -> ``5bfa8261``; a version without ``+`` is returned whole; ``None`` for nothing."""
    if not isinstance(version, str) or not version.strip():
        return None
    text = version.strip()
    if "+" in text:
        return text.split("+", 1)[1][:8]
    return text


def _local_mmdd_hhmm(epoch: float) -> str:
    local = time.localtime(epoch)
    return f"{local.tm_mon:02d}-{local.tm_mday:02d} {local.tm_hour:02d}:{local.tm_min:02d}"


# ---------------------------------------------------------------------------
# staleness and lags
# ---------------------------------------------------------------------------


def staleness(as_of_utc: str | None, *, now: float, stale_s: float, dead_s: float) -> str:
    """``"fresh"`` below *stale_s*, ``"stale"`` from *stale_s*, ``"dead"`` from *dead_s*, ``"unknown"`` without a stamp."""
    epoch = parse_iso(as_of_utc)
    if epoch is None:
        return "unknown"
    age = float(now) - epoch
    if age >= dead_s:
        return "dead"
    if age >= stale_s:
        return "stale"
    return "fresh"


def verdict_lag_s(*, stored_utc: str | None, accepted_at_api: str | None) -> int | None:
    """Seconds from the daemon's ``submission stored`` line to the plane's ``acceptedAt`` (Postgres text).

    ``None`` when either stamp is missing or the verdict predates the store (clock skew, never a lag).
    """
    stored = parse_iso(stored_utc)
    accepted = parse_pg_timestamp(accepted_at_api)
    if stored is None or accepted is None:
        return None
    lag = accepted - stored
    if lag < 0:
        return None
    return int(round(lag))

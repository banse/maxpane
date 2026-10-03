"""Runtime-auth-degraded composite rule for the PEPEPANE dashboard (spec §10; contract §C.9) -- pure.

The 2026-09-25 401 wave tripped the plane's breaker in 2 min 42 s (fill1 §6) while the daemon printed
no error line at all: three normal-looking ~30 s cycles, then ``paused until 23:53 after 3 failed runs``
on every heartbeat. So no single signal is enough; ``auth.degraded`` is true, with the matching
reasons, when ANY of these holds (cost §4):

1. the newest heartbeat carries ``paused until HH:MM after N failed runs`` and the pause is still ahead
   (the suffix lingers after the pause -- fill1 §5 -- and never ambers once ``until`` has passed);
2. the newest Claude transcript has ``system api_error`` 401/403 (429 -> ``rate limited``);
3. the newest Codex rollout matches the failure signature -- ``task_complete.last_agent_message in
   ("", None)`` AND (``token_count.info is None`` OR ``task_complete.error`` present). Two research
   files read the same three rollouts differently (cost §4 vs vps §4), so BOTH shapes are accepted;
4. >= 2 consecutive finished ledger rows under 40 s with zero tokens (the six pre-agent failures of
   fill6 §2 trip this too, labelled ``pre-agent failures``);
5. the credential file's mtime changed within the last hour -> ``token refreshed HH:MM (not read)``
   (the file is stat'ed by the broker, never opened).

No I/O, no clock: ``now`` is always passed in. Local HH:MM uses ``time.localtime`` like every as-of.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

AUTH_FAST_FAIL_S = 40  #: >= 2 consecutive rows finished < 40 s with zero tokens trips auth.degraded (spec §10)
AUTH_CREDENTIAL_REFRESH_S = 3600  #: credential mtime within the last hour -> "token refreshed HH:MM (not read)"
PAUSED_HINT_MAX_AGE_S = 330  #: the heartbeat's standing suffix refreshes every 10 ticks = 5 min (+30 s slack), fill1 §5
FAST_FAIL_STREAK = 2  #: ">= 2 consecutive ledger rows" (spec §10)
DAY_S = 86400
AUTH_STATUSES = {401: "api_error 401", 403: "api_error 403"}
RATE_LIMIT_STATUS = 429


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


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hhmm(epoch: float) -> str:
    return time.strftime("%H:%M", time.localtime(epoch))


def codex_failure_signature(*, last_agent_message_empty: bool, token_count_info_missing: bool,
                            task_complete_error_present: bool) -> bool:
    """``last_agent_message in ("", None)`` AND (``info is None`` OR ``error`` present) -- both 401 readings (proof 20)."""
    return bool(last_agent_message_empty) and (bool(token_count_info_missing) or bool(task_complete_error_present))


def pause_hint_active(hint: Mapping | None, *, now: float) -> bool:
    """Whether a heartbeat's ``paused until HH:MM`` suffix still describes the present (fill1 §5).

    ``until`` is UTC on the day the hint was seen (a wrap past midnight is the next day); a hint seen
    more than ``PAUSED_HINT_MAX_AGE_S`` ago is stale; a hint without ``seenUtc`` is dated *now*.
    Same rule as ``seat_signals.pausedhint_active`` (WP7), kept here so this module stays standalone.
    """
    if not isinstance(hint, Mapping):
        return False
    until = hint.get("until")
    if not isinstance(until, str) or not re.fullmatch(r"\d\d:\d\d", until):
        return False
    hour, minute = int(until[:2]), int(until[3:])
    if hour > 23 or minute > 59:
        return False
    seen = _epoch(hint.get("seenUtc"))
    seen = float(now) if seen is None else seen
    if float(now) - seen > PAUSED_HINT_MAX_AGE_S:
        return False
    day = datetime.fromtimestamp(seen, tz=timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    until_epoch = day.timestamp() + hour * 3600 + minute * 60
    if until_epoch < seen - 12 * 3600:
        until_epoch += DAY_S
    return float(now) < until_epoch


def _zero_tokens(row: Mapping) -> bool:
    tokens = row.get("tokens")
    if isinstance(tokens, Mapping):
        return all((tokens.get(k) or 0) == 0 for k in ("input", "output", "cached"))
    return row.get("preAgentFailure") is True  # no session: a pre-agent failure spent nothing by construction


def _fast_fail_streak(rows: Sequence[Mapping]) -> list[Mapping]:
    streak: list[Mapping] = []
    for row in rows:  # newest first
        if not isinstance(row, Mapping):
            break
        duration = row.get("durationS")
        if not streak and duration is None and row.get("submittedUtc") is None:
            continue  # the open row (still running) neither starts nor breaks the streak
        if isinstance(duration, (int, float)) and not isinstance(duration, bool) and duration < AUTH_FAST_FAIL_S and _zero_tokens(row):
            streak.append(row)
            continue
        break
    return streak


def auth_state(*, paused_hint: Mapping | None, newest_transcript: Mapping | None, newest_rollout: Mapping | None,
               recent_rows: Sequence[Mapping], credential_mtime_utc: str | None, now: float) -> dict:
    """``{"degraded", "reasons", "sinceUtc"}`` -- the §7 auth block minus the credential mtime (the caller adds it)."""
    reasons: list[str] = []
    since: list[float] = []

    if pause_hint_active(paused_hint, now=now):
        runs = paused_hint.get("failedRuns")
        reasons.append(f"paused after {runs} failed runs" if isinstance(runs, int) else "paused after failed runs")
        stamp = _epoch(paused_hint.get("seenUtc"))
        since.append(stamp if stamp is not None else float(now))

    if isinstance(newest_transcript, Mapping):
        for error in newest_transcript.get("apiErrors") or []:
            if isinstance(error, Mapping) and error.get("outputFollowed") is True:
                continue
            status = error.get("status") if isinstance(error, Mapping) else None
            word = AUTH_STATUSES.get(status) or ("rate limited" if status == RATE_LIMIT_STATUS else None)
            if word and word not in reasons:
                reasons.append(word)
                stamp = _epoch(error.get("atUtc"))
                if stamp is not None:
                    since.append(stamp)

    if isinstance(newest_rollout, Mapping) and codex_failure_signature(
            last_agent_message_empty=newest_rollout.get("lastAgentMessageEmpty") is True,
            token_count_info_missing=newest_rollout.get("tokenCountInfoMissing") is True,
            task_complete_error_present=newest_rollout.get("taskCompleteErrorPresent") is True):
        reasons.append("codex failure signature")
        stamp = _epoch(newest_rollout.get("endedUtc")) or _epoch(newest_rollout.get("startedUtc"))
        if stamp is not None:
            since.append(stamp)

    streak = _fast_fail_streak(list(recent_rows))
    if len(streak) >= FAST_FAIL_STREAK:
        if all(row.get("preAgentFailure") is True for row in streak):
            reasons.append("pre-agent failures")
        else:
            reasons.append(f"{len(streak)} tasks < {AUTH_FAST_FAIL_S} s with zero tokens")
        stamp = _epoch(streak[-1].get("acceptedUtc"))
        if stamp is not None:
            since.append(stamp)

    mtime = _epoch(credential_mtime_utc)
    if mtime is not None and 0 <= float(now) - mtime <= AUTH_CREDENTIAL_REFRESH_S:
        reasons.append(f"token refreshed {_hhmm(mtime)} (not read)")
        since.append(mtime)

    return {"degraded": bool(reasons), "reasons": reasons, "sinceUtc": _iso(min(since)) if reasons and since else None}


__all__ = [
    "AUTH_FAST_FAIL_S", "AUTH_CREDENTIAL_REFRESH_S", "PAUSED_HINT_MAX_AGE_S", "FAST_FAIL_STREAK", "AUTH_STATUSES",
    "RATE_LIMIT_STATUS", "codex_failure_signature", "pause_hint_active", "auth_state",
]

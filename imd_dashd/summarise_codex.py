"""Codex rollout summariser for the PEPEPANE dashboard (spec §5.4, §10; contract §C.8).

Self-contained on purpose: the broker runs this file as a transient unit on the VPS
(``/usr/bin/python3`` 3.14.4) and it must equally run when piped to ``python3 -``. It
therefore imports only the standard library, nothing from ``imd_dashd`` or
``maxpane_dashboard``, and is Python 3.11 syntax (no ``type`` statements, no nested
same-quote f-strings). It emits metadata only -- model, effort, turns, token classes,
timings, quota, failure flags -- never a prompt, a tool result or an agent message. The
one free-text field it passes on, ``apiErrors[].message``, is redacted by the caller.

API-equal definitions (spec §10; reconciled 40/40 against the control plane, fill3 §3):

* turns = ``event_msg`` ``item_completed`` whose ``item.type`` case-normalises to
  ``agentmessage`` -- never the ``token_usage_record`` count (2.33x over lifetime);
* tokens from the LAST ``token_count.info.total_token_usage``: input = ``input_tokens -
  cached_input_tokens``, cached = ``cached_input_tokens``, output = ``output_tokens``
  (includes reasoning), cacheWrite = ``cache_write_input_tokens`` (always 0 today);
* ttft / wall = ``task_complete.time_to_first_token_ms`` / ``duration_ms``; turn-1
  context = the first ``token_usage_record.usage.input_tokens`` (cached included);
* quota = the newest ``token_count.rate_limits.primary`` + ``plan_type``.

Hostile size (spec §5.4): the files live under the worker uid, so a task can append
arbitrarily large lines. Files over 64 MiB are skipped unopened, lines over 1 MiB are
skipped unparsed and counted, a file gets a 5 s wall clock and a call a budget.
``.jsonl.zst`` rollouts (codex-cli compresses after 7 days) are read through
``compression.zstd`` only when it imports; otherwise they are reported, not read.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import time
from datetime import datetime, timezone

try:  # stdlib only from Python 3.14, and only when built against libzstd (spec §5.4, §18 open 19)
    from compression import zstd as ZSTD
except ImportError:  # Python 3.11 in the container, or a 3.14 build without libzstd
    ZSTD = None

MAX_FILE_BYTES = 64 * 1024 * 1024  #: skip larger files unopened (spec §5.4)
MAX_LINE_BYTES = 1024 * 1024  #: skip longer lines unparsed (spec §5.4)
PER_FILE_WALL_S = 5.0  #: per-file wall clock (spec §5.4)
DEFAULT_BUDGET_S = 40.0  #: per-call budget inside the transient unit's RuntimeMaxSec=60 (contract §B)
CODEX_PLAIN_ROLLOUT_DAYS = 7  #: MIN_ROLLOUT_AGE in codex-cli 0.157.0: older rollouts become .jsonl.zst (fill8 §4)
CODEX_EXCLUDED_CWDS = ("/tmp", "/home/imd-worker")  #: exact manual cwds (fill6 §6: 7 + 2 rollouts)
DOCTOR_PREFIX = "doctor-"  #: `imd doctor` smoke runs: cwd work/doctor-XXXXXX (fill3 §0)
ZSTD_MISSING_REASON = "rollouts > 7 d unreadable (compression.zstd missing)"
STR_CAP = 200  #: every emitted identifier string is capped (a task can write the file)
MESSAGE_CAP = 500  #: apiErrors[].message cap; the caller redacts it
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
STATUS_RE = re.compile(r"\bstatus (\d{3})\b")

SESSION_KEYS = (
    "path", "runtime", "cwd", "slug", "kind", "jobId", "nodeId", "startedUtc", "endedUtc", "mtime", "bytes",
    "model", "effort", "turns", "turnsDefinition", "tokens", "sideModel", "ttftMs", "wallMs", "turn1Context",
    "maxTurnsReached", "maxTurns", "apiErrors", "lastAgentMessageEmpty", "tokenCountInfoMissing",
    "taskCompleteErrorPresent", "quota", "skippedOversize", "error",
)


class _WallClock(Exception):
    """The per-file wall clock ran out."""


class _TooBig(Exception):
    """A stream produced more than MAX_FILE_BYTES (a decompression bomb)."""


def iter_bounded_lines(fh, counts: dict, *, max_line: int = MAX_LINE_BYTES, max_total: int = MAX_FILE_BYTES,
                       deadline: float | None = None, clock=time.monotonic):
    """Yield the complete lines of a binary stream that are at most *max_line* bytes.

    Reads at most ``max_line + 1`` bytes per call, so a multi-hundred-MB line never sits
    in memory; an oversize line is drained in ``max_line`` chunks, counted in
    ``counts["oversize"]`` and never yielded. Raises ``_WallClock`` past *deadline* and
    ``_TooBig`` past *max_total* bytes read.
    """
    total = 0
    while True:
        if deadline is not None and clock() > deadline:
            raise _WallClock()
        chunk = fh.readline(max_line + 1)
        if not chunk:
            return
        total += len(chunk)
        if total > max_total:
            raise _TooBig()
        if len(chunk) > max_line and not chunk.endswith(b"\n"):
            counts["oversize"] = counts.get("oversize", 0) + 1
            while True:
                if deadline is not None and clock() > deadline:
                    raise _WallClock()
                rest = fh.readline(max_line)
                total += len(rest)
                if total > max_total:
                    raise _TooBig()
                if not rest or rest.endswith(b"\n"):
                    break
            continue
        yield chunk


def _loads(raw: bytes) -> dict | None:
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeDecodeError, RecursionError):
        return None
    return obj if isinstance(obj, dict) else None


def _int(value) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _cap(value, cap: int = STR_CAP) -> str | None:
    return value[:cap] if isinstance(value, str) and value else None


def _parse_time(value) -> datetime | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def iso_ms(value) -> str | None:
    """ISO text or epoch seconds -> ``2026-09-26T02:33:41.912Z`` (millisecond precision, UTC)."""
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def iso_s(value) -> str | None:
    """ISO text or epoch seconds -> ``2026-09-28T21:50:11Z`` (second precision, UTC)."""
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def classify_cwd(cwd: str, *, work_root: str) -> tuple[str, str | None, str | None]:
    """``(kind, jobId, nodeId)`` for a rollout's ``session_meta.cwd`` (spec §5.4, §10; fill6 §6).

    ``<work_root>/<jobId>/<nodeId>`` -> task; exactly ``<work_root>`` -> research (answerQuestion
    runs with ``workspace: workRoot``); a basename ``doctor-*`` -> doctor; ``/tmp`` or
    ``/home/imd-worker`` exactly -> manual; anything else -> unknown.
    """
    if not isinstance(cwd, str) or not cwd:
        return ("unknown", None, None)
    path = cwd.rstrip("/") or "/"
    root = work_root.rstrip("/") or "/"
    if path == root:
        return ("research", None, None)
    if os.path.basename(path).startswith(DOCTOR_PREFIX):
        return ("doctor", None, None)
    if path in CODEX_EXCLUDED_CWDS:
        return ("manual", None, None)
    if path.startswith(root + "/"):
        parts = path[len(root) + 1:].split("/")
        if len(parts) == 2 and UUID_RE.fullmatch(parts[0]) and UUID_RE.fullmatch(parts[1]):
            return ("task", parts[0], parts[1])
    return ("unknown", None, None)


def _empty_session(path: str, st: os.stat_result) -> dict:
    session = dict.fromkeys(SESSION_KEYS)
    # a compressed rollout keeps its plain name as identity: codex renames rollout-X.jsonl -> .jsonl.zst after
    # 7 days with a fresh mtime, and the ledger upserts by path -- a second path would double the attempt's tokens
    session.update(path=_cap(path.removesuffix(".zst"), 512), runtime="codex", mtime=st.st_mtime, bytes=st.st_size, kind="unknown",
                   turnsDefinition="agent_messages", apiErrors=[], skippedOversize=0)
    return session


def _quota(rate_limits, ts) -> dict | None:
    if not isinstance(rate_limits, dict):
        return None
    primary = rate_limits.get("primary")
    if not isinstance(primary, dict):
        return None
    used = primary.get("used_percent")
    if isinstance(used, bool) or not isinstance(used, (int, float)):
        return None
    return {
        "usedPercent": float(used),
        "windowMinutes": _int(primary.get("window_minutes")),
        "resetsAtUtc": iso_s(primary.get("resets_at")),
        "planType": _cap(rate_limits.get("plan_type"), 40),
        "sampledAtUtc": iso_s(ts),
    }


def _open(path: str):
    if path.endswith(".zst"):
        return ZSTD.open(path, "rb")
    return open(path, "rb")


def summarise_file(path: str, *, work_root: str, now: float, clock=time.monotonic,
                   wall_s: float = PER_FILE_WALL_S) -> dict | None:
    """One rollout -> a ``SESSION_KEYS`` dict; ``None`` when unreadable, not a regular file,
    over ``MAX_FILE_BYTES`` or a ``.zst`` without ``compression.zstd``.

    *now* is accepted for the contract's signature and deliberately unused: the summary is a
    pure function of the file, so fixture output is deterministic.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
        return None
    if path.endswith(".zst") and ZSTD is None:
        return None
    session = _empty_session(path, st)
    counts = {"oversize": 0}
    cwd = started = ended = meta_ts = model = effort = total_usage = quota = None
    turns = 0
    turn1 = None
    task_complete = None
    task_complete_ts = None
    try:
        with _open(path) as fh:
            for raw in iter_bounded_lines(fh, counts, deadline=clock() + wall_s, clock=clock):
                rec = _loads(raw)
                if rec is None:
                    continue
                ts = rec.get("timestamp")
                if isinstance(ts, str):
                    started = started or ts
                    ended = ts
                kind = rec.get("type")
                payload = rec.get("payload") if isinstance(rec.get("payload"), dict) else {}
                if kind == "session_meta":
                    cwd = cwd or (payload.get("cwd") if isinstance(payload.get("cwd"), str) else None)
                    meta_ts = meta_ts or (payload.get("timestamp") if isinstance(payload.get("timestamp"), str) else None)
                elif kind == "turn_context":
                    model = model or (payload.get("model") if isinstance(payload.get("model"), str) else None)
                    effort = effort or (payload.get("effort") if isinstance(payload.get("effort"), str) else None)
                elif kind == "token_usage_record":
                    usage = payload.get("usage")
                    if turn1 is None and isinstance(usage, dict):
                        turn1 = _int(usage.get("input_tokens"))
                elif kind == "event_msg":
                    event = payload.get("type")
                    if event == "item_completed":
                        item = payload.get("item")
                        item_type = item.get("type") if isinstance(item, dict) else None
                        if isinstance(item_type, str) and item_type.lower().replace("_", "") == "agentmessage":
                            turns += 1
                    elif event == "token_count":
                        info = payload.get("info")
                        if isinstance(info, dict) and isinstance(info.get("total_token_usage"), dict):
                            total_usage = info["total_token_usage"]
                        sample = _quota(payload.get("rate_limits"), ts)
                        if sample is not None:
                            quota = sample
                    elif event == "task_complete":
                        task_complete = payload
                        task_complete_ts = ts
    except _WallClock:
        session["error"] = "per-file wall clock exceeded"
    except _TooBig:
        counts["oversize"] += 1
        session["error"] = "decompressed size > 64 MiB"
    except Exception as exc:  # noqa: BLE001 -- OSError, EOFError, ZstdError: one bad file never kills the call
        session["error"] = "unreadable: " + type(exc).__name__
    kind, job_id, node_id = classify_cwd(cwd, work_root=work_root) if cwd else ("unknown", None, None)
    session.update(cwd=_cap(cwd, 512), kind=kind, jobId=job_id, nodeId=node_id,
                   startedUtc=iso_ms(meta_ts or started), endedUtc=iso_ms(ended),
                   model=_cap(model, 128), effort=_cap(effort, 32), skippedOversize=counts["oversize"], quota=quota)
    if session["error"] is not None:
        return session  # partial parse: classification kept, figures withheld (None, never a partial sum)
    session["turns"] = turns
    session["turn1Context"] = turn1
    session["tokenCountInfoMissing"] = total_usage is None
    if total_usage is not None:
        raw_input = _int(total_usage.get("input_tokens")) or 0
        cached = _int(total_usage.get("cached_input_tokens")) or 0
        session["tokens"] = {
            "input": max(raw_input - cached, 0),
            "output": _int(total_usage.get("output_tokens")) or 0,
            "cached": cached,
            "cacheWrite": _int(total_usage.get("cache_write_input_tokens")) or 0,
        }
    elif task_complete is not None:
        # finished without a usage report: the runtime consumed nothing it reported (API: all zero, cost §4)
        session["tokens"] = {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}
    if task_complete is not None:
        session["ttftMs"] = _int(task_complete.get("time_to_first_token_ms"))
        session["wallMs"] = _int(task_complete.get("duration_ms"))
        session["lastAgentMessageEmpty"] = task_complete.get("last_agent_message") in ("", None)
        error = task_complete.get("error")
        present = error not in (None, "", {}, [])
        session["taskCompleteErrorPresent"] = present
        if present:
            message = error.get("message") if isinstance(error, dict) else error
            message = message if isinstance(message, str) else json.dumps(error)[:MESSAGE_CAP]
            match = STATUS_RE.search(message)
            session["apiErrors"] = [{"status": int(match.group(1)) if match else None,
                                     "message": message[:MESSAGE_CAP], "atUtc": iso_ms(task_complete_ts)}]
    else:
        session["lastAgentMessageEmpty"] = False
        session["taskCompleteErrorPresent"] = False
    return session


def _candidates(root: str) -> list[tuple[float, str, int]]:
    """``(mtime, path, size)`` of every regular ``rollout-*.jsonl[.zst]`` under *root*; symlinks never followed."""
    found = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs.sort()
        for name in sorted(files):
            if not name.startswith("rollout-") or not (name.endswith(".jsonl") or name.endswith(".jsonl.zst")):
                continue
            path = os.path.join(base, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                found.append((st.st_mtime, path, st.st_size))
    found.sort()
    return found


def _drop_twins(pending: list[tuple[float, str, int]]) -> list[tuple[float, str, int]]:
    """A rollout caught mid-compression exists as both ``.jsonl`` and ``.jsonl.zst``: keep one -- the ``.zst``
    when it can be read, else the plain file."""
    names = {path for _, path, _ in pending}
    keep = []
    for entry in pending:
        path = entry[1]
        if path.endswith(".zst") and path.removesuffix(".zst") in names and ZSTD is None:
            continue
        if not path.endswith(".zst") and path + ".zst" in names and ZSTD is not None:
            continue
        keep.append(entry)
    return keep


def summarise_dir(root: str, *, since_mtime: float, work_root: str, budget_s: float = DEFAULT_BUDGET_S, now: float,
                  clock=time.monotonic, wall_s: float = PER_FILE_WALL_S) -> dict:
    """Every rollout with ``mtime > since_mtime``, oldest first, inside *budget_s*.

    Returns ``{"sessions", "skipped": {"oversize"}, "watermarkMtime", "zstdReadable", "reason"}``.
    The watermark advances only over files examined, so a budget stop resumes next call.
    """
    start = clock()
    sessions: list[dict] = []
    oversize = 0
    zstd_skipped = 0
    errors = 0
    watermark = float(since_mtime)
    notes: list[str] = []
    if not os.path.isdir(root):
        return {"sessions": [], "skipped": {"oversize": 0}, "watermarkMtime": watermark,
                "zstdReadable": ZSTD is not None, "reason": "sessions root missing"}
    pending = _drop_twins([c for c in _candidates(root) if c[0] > since_mtime])
    done = 0
    for mtime, path, size in pending:
        if clock() - start > budget_s:
            notes.append(f"budget exhausted after {done} of {len(pending)} files")
            watermark = max(float(since_mtime), min(watermark, mtime - 1e-6))
            break
        done += 1
        watermark = max(watermark, mtime)
        if size > MAX_FILE_BYTES:
            oversize += 1
            continue
        if path.endswith(".zst") and ZSTD is None:
            zstd_skipped += 1
            continue
        session = summarise_file(path, work_root=work_root, now=now, clock=clock, wall_s=wall_s)
        if session is None:
            errors += 1
            continue
        oversize += session.get("skippedOversize") or 0
        if session.get("error"):
            errors += 1
        sessions.append(session)
    if oversize:
        notes.insert(0, f"skipped {oversize} oversize (file > 64 MiB or line > 1 MiB)")
    if zstd_skipped:
        notes.append(f"{ZSTD_MISSING_REASON}: {zstd_skipped} file(s)")
    if errors:
        notes.append(f"{errors} file(s) unreadable or partial")
    return {"sessions": sessions, "skipped": {"oversize": oversize}, "watermarkMtime": watermark,
            "zstdReadable": ZSTD is not None, "reason": "; ".join(notes) or None}


def main(argv: list[str] | None = None) -> int:
    """``--root <sessions dir> --since <mtime> --work-root <path> [--budget 40]`` -> one JSON object on stdout."""
    home = os.path.expanduser("~")
    parser = argparse.ArgumentParser(prog="summarise_codex", add_help=True)
    parser.add_argument("--root", default=os.path.join(home, ".codex", "sessions"))
    parser.add_argument("--since", type=float, default=0.0)
    parser.add_argument("--work-root", default=os.path.join(home, ".identitymd", "work"))
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET_S)
    args = parser.parse_args(argv)
    try:
        result = summarise_dir(args.root, since_mtime=args.since, work_root=args.work_root,
                               budget_s=args.budget, now=time.time())
        code = 0
    except Exception as exc:  # noqa: BLE001 -- the caller always gets one parseable object
        result = {"sessions": [], "skipped": {"oversize": 0}, "watermarkMtime": args.since,
                  "zstdReadable": ZSTD is not None, "reason": "summariser failed: " + type(exc).__name__}
        code = 1
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())

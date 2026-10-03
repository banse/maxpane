"""Claude Code transcript summariser for the PEPEPANE dashboard (spec §5.4, §10; contract §C.8).

Self-contained on purpose: on the Mac the broker pipes this file into the worker container
(``docker exec -i imd-worker timeout -s TERM -k 5 20 python3 -``, container python 3.11.2),
so it imports only the standard library, nothing from ``imd_dashd`` or
``maxpane_dashboard``, and is Python 3.11 syntax. It emits metadata only -- model, effort,
turns, token classes, timings, side-model usage, API-error statuses -- never a prompt, a
tool result or assistant text; the one free-text field it passes on,
``apiErrors[].message``, is redacted by the caller. ``cost-state.totalCostUSD`` and every
``costUSD`` are never read (spec §10 no-currency rule).

API-equal definitions (spec §10; reconciled 40/40, fill3 §2):

* turns = the count of ``type:"user"`` lines (== tool_use blocks + 1 == SDK ``num_turns``);
* tokens summed over DISTINCT ``message.id`` -- Claude Code writes one line per content block
  with identical usage, so per-line summing over-counts 1.5-1.9x (the aidude writer's bug);
  input = ``input_tokens``, output = ``output_tokens``, cached = ``cache_read_input_tokens +
  cache_creation_input_tokens``, cacheWrite = 0 (creation is already inside cached);
* side model = ``cost-state.modelUsage`` keys starting ``claude-haiku-4-5``: SDK side calls,
  absent from the API usage -- reported separately, never added;
* turn-1 context = the first assistant ``cache_creation + cache_read + input_tokens``.

Slug exclusions are EXACT matches, never prefixes (spec §5.4): a prefix match on
``-home-imd`` would also swallow ``-home-imd--identitymd-work``, the slug a research task
uses on the Mac.

Hostile size (spec §5.4): files over 64 MiB are skipped unopened, lines over 1 MiB are
skipped unparsed and counted, each file has a 5 s wall clock and each call a budget.
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

MAX_FILE_BYTES = 64 * 1024 * 1024  #: skip larger files unopened (spec §5.4)
MAX_LINE_BYTES = 1024 * 1024  #: skip longer lines unparsed (spec §5.4)
PER_FILE_WALL_S = 5.0  #: per-file wall clock (spec §5.4)
DEFAULT_BUDGET_S = 15.0  #: per-call budget inside the in-container `timeout ... 20` (spec §4.2)
CLAUDE_CLEANUP_DAYS = 30  #: cleanupPeriodDays default: older transcripts are swept (fill8 §4)
CLAUDE_EXCLUDED_SLUGS = frozenset({"-home-imd", "-tmp", "-tmp-probe-ws", "-tmp-probe-ws2", "-tmp-probe-ws3"})  #: EXACT
CLAUDE_DOCTOR_SLUG_PREFIX = "-home-imd--identitymd-work-doctor-"  #: `imd doctor` smoke runs (fill6 §3)
CLAUDE_RESEARCH_SLUG = "-home-imd--identitymd-work"  #: cwd = work root; exact; NOT excluded (mutation proof 35)
CLAUDE_TASK_SLUG_PREFIX = "-home-imd--identitymd-work-"  #: + <jobId 36>-<nodeId 36>
SIDE_MODEL_PREFIX = "claude-haiku-4-5"  #: SDK side calls in cost-state.modelUsage (fill3 §2)
SYNTHETIC_MODEL = "<synthetic>"  #: client-side error messages, not a model
STR_CAP = 200
MESSAGE_CAP = 500
MAX_API_ERRORS = 20  #: a task can append lines; the list stays bounded
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SYNTHETIC_STATUS_RE = re.compile(r"API Error: (\d{3})")

SESSION_KEYS = (
    "path", "runtime", "cwd", "slug", "kind", "jobId", "nodeId", "startedUtc", "endedUtc", "mtime", "bytes",
    "model", "effort", "turns", "turnsDefinition", "tokens", "sideModel", "ttftMs", "wallMs", "turn1Context",
    "maxTurnsReached", "maxTurns", "apiErrors", "lastAgentMessageEmpty", "tokenCountInfoMissing",
    "taskCompleteErrorPresent", "quota", "skippedOversize", "error",
)


def classify_slug(slug: str, *, home_slug: str = "-home-imd") -> str:
    """``task | research | doctor | manual | unknown`` for a ``~/.claude/projects/<slug>`` dir name.

    Exclusions are exact (``CLAUDE_EXCLUDED_SLUGS``); the research slug is exact and counts;
    doctor is the ``-home-imd--identitymd-work-doctor-*`` pattern (spec §5.4, §10).
    """
    if not isinstance(slug, str) or not slug:
        return "unknown"
    if slug in (CLAUDE_EXCLUDED_SLUGS - {"-home-imd"}) or slug == home_slug:
        return "manual"
    if slug == home_slug + "--identitymd-work":
        return "research"
    doctor_prefix = home_slug + "--identitymd-work-doctor-"
    if slug.startswith(doctor_prefix) and len(slug) > len(doctor_prefix):
        return "doctor"
    if parse_task_slug(slug, home_slug=home_slug) is not None:
        return "task"
    return "unknown"


def parse_task_slug(slug: str, *, home_slug: str = "-home-imd") -> tuple[str, str] | None:
    """``-home-imd--identitymd-work-<jobId>-<nodeId>`` -> ``(jobId, nodeId)``.

    Both ids are 36-char UUIDs that themselves contain ``-``, so the split is by length.
    """
    prefix = home_slug + "--identitymd-work-"
    if not isinstance(slug, str) or not slug.startswith(prefix):
        return None
    rest = slug[len(prefix):]
    if len(rest) != 73 or rest[36] != "-":
        return None
    job, node = rest[:36], rest[37:]
    if UUID_RE.fullmatch(job) and UUID_RE.fullmatch(node):
        return (job, node)
    return None


class _WallClock(Exception):
    """The per-file wall clock ran out."""


class _TooBig(Exception):
    """More than MAX_FILE_BYTES were read from one file."""


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
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)
    return None


def iso_ms(value) -> str | None:
    """ISO text -> ``2026-09-26T01:10:02.150Z`` (millisecond precision, UTC)."""
    parsed = _parse_time(value)
    if parsed is None:
        return None
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _status_of(value) -> int | None:
    status = _int(value)
    return status if status is not None and 100 <= status <= 599 else None


def summarise_file(path: str, *, now: float, clock=time.monotonic, wall_s: float = PER_FILE_WALL_S,
                   home_slug: str = "-home-imd") -> dict | None:
    """One transcript -> a ``SESSION_KEYS`` dict; ``None`` when unreadable, not a regular file or over 64 MiB.

    *now* is accepted for the contract's signature and deliberately unused: the summary is a
    pure function of the file, so fixture output is deterministic.
    """
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode) or st.st_size > MAX_FILE_BYTES:
        return None
    slug = os.path.basename(os.path.dirname(path))
    kind = classify_slug(slug, home_slug=home_slug)
    ids = parse_task_slug(slug, home_slug=home_slug) if kind == "task" else None
    session = dict.fromkeys(SESSION_KEYS)
    session.update(path=_cap(path, 512), runtime="claude", slug=_cap(slug, 256), kind=kind,
                   jobId=ids[0] if ids else None, nodeId=ids[1] if ids else None,
                   mtime=st.st_mtime, bytes=st.st_size, turnsDefinition="user_lines", apiErrors=[], skippedOversize=0)
    counts = {"oversize": 0}
    started = ended = cwd = effort = cost_state = None
    user_lines = 0
    usage_by_id: dict = {}
    model_counts: dict = {}
    first_context = None
    max_turns: list[int] = []
    api_errors: list[dict] = []
    line_no = 0
    try:
        with open(path, "rb") as fh:
            for raw in iter_bounded_lines(fh, counts, deadline=clock() + wall_s, clock=clock):
                line_no += 1
                rec = _loads(raw)
                if rec is None:
                    continue
                ts = rec.get("timestamp")
                if isinstance(ts, str):
                    started = started or ts
                    ended = ts
                if cwd is None and isinstance(rec.get("cwd"), str):
                    cwd = rec["cwd"]
                kind_of_line = rec.get("type")
                if kind_of_line == "user":
                    user_lines += 1
                elif kind_of_line == "assistant":
                    message = rec.get("message") if isinstance(rec.get("message"), dict) else {}
                    model = message.get("model")
                    if model == SYNTHETIC_MODEL:
                        for block in message.get("content") or []:
                            text = block.get("text") if isinstance(block, dict) else None
                            match = SYNTHETIC_STATUS_RE.search(text) if isinstance(text, str) else None
                            if match and len(api_errors) < MAX_API_ERRORS:
                                api_errors.append({"status": int(match.group(1)), "message": text[:MESSAGE_CAP],
                                                   "atUtc": iso_ms(ts), "outputFollowed": False})
                        continue
                    usage = message.get("usage")
                    if not isinstance(usage, dict):
                        continue
                    if (_int(usage.get("output_tokens")) or 0) > 0:
                        for error in api_errors:
                            error["outputFollowed"] = True
                    key = message.get("id") or rec.get("requestId") or f"line-{line_no}"
                    if key in usage_by_id:
                        continue  # one line per content block, identical usage: count each message once
                    usage_by_id[key] = usage
                    if isinstance(model, str):
                        model_counts[model] = model_counts.get(model, 0) + 1
                    if effort is None and isinstance(rec.get("effort"), str):
                        effort = rec["effort"]
                    if first_context is None:
                        first_context = sum(_int(usage.get(k)) or 0 for k in
                                            ("cache_creation_input_tokens", "cache_read_input_tokens", "input_tokens"))
                elif kind_of_line == "attachment":
                    attachment = rec.get("attachment") if isinstance(rec.get("attachment"), dict) else {}
                    if attachment.get("type") == "max_turns_reached":
                        value = _int(attachment.get("maxTurns"))
                        max_turns.append(value if value is not None else 0)
                elif kind_of_line == "system" and rec.get("subtype") == "api_error":
                    error = rec.get("error") if isinstance(rec.get("error"), dict) else {}
                    status = _status_of(error.get("status"))
                    if status is None:
                        status = _status_of(rec.get("status"))
                    text = error.get("formatted") or error.get("message") or rec.get("content")
                    if len(api_errors) < MAX_API_ERRORS:
                        api_errors.append({"status": status, "message": text[:MESSAGE_CAP] if isinstance(text, str) else None,
                                           "atUtc": iso_ms(ts), "outputFollowed": False})
                elif kind_of_line == "cost-state":
                    cost_state = rec
    except _WallClock:
        session["error"] = "per-file wall clock exceeded"
    except _TooBig:
        counts["oversize"] += 1
        session["error"] = "file grew past 64 MiB while read"
    except Exception as exc:  # noqa: BLE001 -- one bad file never kills the call
        session["error"] = "unreadable: " + type(exc).__name__
    session.update(cwd=_cap(cwd, 512), startedUtc=iso_ms(started), endedUtc=iso_ms(ended),
                   skippedOversize=counts["oversize"], apiErrors=api_errors)
    if session["error"] is not None:
        return session  # partial parse: classification kept, figures withheld
    if model_counts:
        best = max(model_counts.values())
        session["model"] = _cap(next(m for m, n in model_counts.items() if n == best), 128)
    session["effort"] = _cap(effort, 32)
    session["turns"] = user_lines
    session["turn1Context"] = first_context
    if usage_by_id:
        usages = list(usage_by_id.values())
        session["tokens"] = {
            "input": sum(_int(u.get("input_tokens")) or 0 for u in usages),
            "output": sum(_int(u.get("output_tokens")) or 0 for u in usages),
            "cached": sum((_int(u.get("cache_read_input_tokens")) or 0) + (_int(u.get("cache_creation_input_tokens")) or 0)
                          for u in usages),
            "cacheWrite": 0,
        }
    elif cost_state is not None:
        session["tokens"] = {"input": 0, "output": 0, "cached": 0, "cacheWrite": 0}
    if cost_state is not None:
        usage_map = cost_state.get("modelUsage") if isinstance(cost_state.get("modelUsage"), dict) else {}
        side_keys = sorted(k for k in usage_map if isinstance(k, str) and k.startswith(SIDE_MODEL_PREFIX))
        if side_keys:
            session["sideModel"] = {
                "model": _cap(side_keys[0], 128),
                "input": sum(_int((usage_map[k] or {}).get("inputTokens")) or 0 for k in side_keys),
                "output": sum(_int((usage_map[k] or {}).get("outputTokens")) or 0 for k in side_keys),
            }
        session["wallMs"] = _int(cost_state.get("totalDuration"))
    if session["wallMs"] is None:
        first, last = _parse_time(started), _parse_time(ended)
        if first is not None and last is not None:
            session["wallMs"] = int(round((last - first).total_seconds() * 1000))
    session["maxTurnsReached"] = bool(max_turns)
    session["maxTurns"] = max(max_turns) if max_turns else None
    return session


def _candidates(root: str) -> list[tuple[float, str, int]]:
    """``(mtime, path, size)`` of every regular ``<root>/<slug>/*.jsonl``; symlinks never followed."""
    found = []
    try:
        slugs = sorted(os.scandir(root), key=lambda e: e.name)
    except OSError:
        return found
    for entry in slugs:
        if not entry.is_dir(follow_symlinks=False):
            continue
        try:
            names = sorted(os.listdir(entry.path))
        except OSError:
            continue
        for name in names:
            if not name.endswith(".jsonl"):
                continue
            path = os.path.join(entry.path, name)
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if stat.S_ISREG(st.st_mode):
                found.append((st.st_mtime, path, st.st_size))
    found.sort()
    return found


def summarise_dir(root: str, *, since_mtime: float, budget_s: float = DEFAULT_BUDGET_S, now: float,
                  clock=time.monotonic, wall_s: float = PER_FILE_WALL_S) -> dict:
    """Every transcript with ``mtime > since_mtime``, oldest first, inside *budget_s*.

    Returns ``{"sessions", "skipped": {"oversize"}, "watermarkMtime", "zstdReadable": None, "reason"}``.
    The watermark advances only over files examined, so a budget stop resumes next call.
    """
    start = clock()
    sessions: list[dict] = []
    oversize = 0
    errors = 0
    watermark = float(since_mtime)
    notes: list[str] = []
    if not os.path.isdir(root):
        return {"sessions": [], "skipped": {"oversize": 0}, "watermarkMtime": watermark,
                "zstdReadable": None, "reason": "projects root missing"}
    pending = [c for c in _candidates(root) if c[0] > since_mtime]
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
        normal_root = os.path.normpath(root)
        home = os.path.dirname(os.path.dirname(normal_root))
        home_slug = re.sub(r"[^A-Za-z0-9-]", "-", home) if normal_root.endswith("/.claude/projects") else "-home-imd"
        session = summarise_file(path, now=now, clock=clock, wall_s=wall_s, home_slug=home_slug)
        if session is None:
            errors += 1
            continue
        oversize += session.get("skippedOversize") or 0
        if session.get("error"):
            errors += 1
        sessions.append(session)
    if oversize:
        notes.insert(0, f"skipped {oversize} oversize (file > 64 MiB or line > 1 MiB)")
    if errors:
        notes.append(f"{errors} file(s) unreadable or partial")
    return {"sessions": sessions, "skipped": {"oversize": oversize}, "watermarkMtime": watermark,
            "zstdReadable": None, "reason": "; ".join(notes) or None}


def main(argv: list[str] | None = None) -> int:
    """``--root /home/imd/.claude/projects --since <mtime> [--budget 15]`` -> one JSON object on stdout."""
    parser = argparse.ArgumentParser(prog="summarise_claude", add_help=True)
    parser.add_argument("--root", default=os.path.join(os.path.expanduser("~"), ".claude", "projects"))
    parser.add_argument("--since", type=float, default=0.0)
    parser.add_argument("--budget", type=float, default=DEFAULT_BUDGET_S)
    args = parser.parse_args(argv)
    try:
        result = summarise_dir(args.root, since_mtime=args.since, budget_s=args.budget, now=time.time())
        code = 0
    except Exception as exc:  # noqa: BLE001 -- the caller always gets one parseable object
        result = {"sessions": [], "skipped": {"oversize": 0}, "watermarkMtime": args.since,
                  "zstdReadable": None, "reason": "summariser failed: " + type(exc).__name__}
        code = 1
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")) + "\n")
    return code


if __name__ == "__main__":
    sys.exit(main())

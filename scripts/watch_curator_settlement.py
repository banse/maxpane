#!/usr/bin/env python3
"""Unattended crossing watcher for the WhitelistCurator captures.

Run it from launchd/cron once an hour, a few minutes before ``HH:58:47``; it
waits for the crossing itself, sweeps it, and keeps only what is worth keeping.
One shot per invocation -- no daemon, nothing to leave running, and a machine
that was asleep simply misses that hour rather than falling behind forever.

    python3 scripts/watch_curator_settlement.py            # next crossing
    python3 scripts/watch_curator_settlement.py --once     # same, explicit

Why it exists: **capture C, the settlement transition, is one-shot and
unrepeatable.**  ``isSettled()`` is derived, so it flips with no transaction and
no log -- there is nothing to go back and read afterwards.  Both halves are
wanted (the last bundle reading false and the first reading true), which is why
this keeps the bundle *before* the flip as well.

Sweeps every hour crossing densely into a scratch directory, then keeps only the
bundles that are worth committing:

  A  a QUIET crossing  - currentHourTotal() == 0 while lastActiveHour() still
                         names the previous hour. The one state the busy grace
                         hours never produced.
  C  the settlement    - isSettled() flips 0 -> 1. It can only flip at a
                         crossing, so hunting crossings catches it by
                         construction. Both halves are kept: the last bundle
                         reading false and the first reading true.
  named windows        - post-grace (19:58:47Z) and the first judged hour's
                         completion (20:58:47Z) are kept whatever they show,
                         because a negative observation at a named instant is
                         still evidence.

Everything else is discarded, so 19 hours of hunting costs a few dozen kilobytes
in the repo rather than a few hundred megabytes.
"""

from __future__ import annotations


import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

#: The checkout this script lives in, found from the script itself so a
#: scheduled run does not depend on anyone's working directory.
REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts/capture_curator_state.py"
KEEP = REPO / "tests/fixtures/curator/captures/live"
_ARGS = [a for a in sys.argv[1:] if not a.startswith("-")]
SCRATCH = Path(_ARGS[0] if _ARGS else "/tmp/curator_watch")
LOG = SCRATCH / "watch.log"

LAUNCH = 1786910327
HOUR = 3600
#: One crossing per run by default: launchd supplies the schedule, so this
#: process never needs to outlive the sweep it was started for.
ONE_SHOT = True

SEL_HOUR_TOTAL = "0x78f251f3"
SEL_LAST_ACTIVE = "0xa8a036f1"
SEL_CURRENT_HOUR = "0x020e185d"
SEL_SETTLED = "0x3270bb5b"
SEL_EARLY_BPS = "0xd8631b3d"

NAMED = {
    LAUNCH + 24 * HOUR: "post-grace",       # 2026-08-17 19:58:47Z, earlyBps hits 10000
    LAUNCH + 25 * HOUR: "first-judged",     # 2026-08-17 20:58:47Z, earliest settlement
}


def note(msg: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    line = f"{stamp} {msg}"
    print(line, flush=True)
    with LOG.open("a") as fh:
        fh.write(line + "\n")


def words(bundle: dict, selector: str) -> list[int] | None:
    entry = (bundle.get("state") or {}).get(selector) or {}
    raw = entry.get("result")
    if not isinstance(raw, str) or not raw.startswith("0x"):
        return None
    body = raw[2:]
    if not body:
        return None
    return [int(body[i:i + 64], 16) for i in range(0, len(body), 64)]


def classify(bundle: dict) -> tuple[bool, bool]:
    """(is_quiet_crossing, is_settled) — either one makes a bundle worth keeping."""
    total = words(bundle, SEL_HOUR_TOTAL)
    last = words(bundle, SEL_LAST_ACTIVE)
    cur = words(bundle, SEL_CURRENT_HOUR)
    settled = words(bundle, SEL_SETTLED)
    quiet = bool(
        total and last and cur
        and total[0] == 0
        and last[0] < cur[0]
        and len(last) > 1 and last[1] != 0
    )
    return quiet, bool(settled and settled[0] == 1)


def sweep(label: str, repeat: int, every: int) -> list[Path]:
    out = SCRATCH / f"{label}_{int(time.time())}"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable, str(SCRIPT),
        "--label", label,
        "--start-at", "boundary",
        "--every", str(every),
        "--repeat", str(repeat),
        "--no-logs", "--no-blockscout",
        "--out-dir", str(out),
    ]
    try:
        subprocess.run(cmd, cwd=REPO, timeout=repeat * every + 4200, capture_output=True)
    except subprocess.TimeoutExpired:
        note(f"sweep {label}: timed out, keeping whatever landed")
    return sorted(p for p in out.glob("*.json"))


def main() -> None:
    SCRATCH.mkdir(parents=True, exist_ok=True)
    KEEP.mkdir(parents=True, exist_ok=True)
    note("watcher up")

    settled_seen = False
    while True:
        now = int(time.time())
        nxt = LAUNCH + ((now - LAUNCH) // HOUR + 1) * HOUR
        named = NAMED.get(nxt)
        label = named or "hour-boundary"
        note(f"waiting for crossing at {time.strftime('%H:%M:%SZ', time.gmtime(nxt))} ({label})")

        bundles = sweep(label, repeat=40, every=5)
        if not bundles:
            note(f"{label}: no bundles came back")
            continue

        kept, prev = [], None
        for path in bundles:
            try:
                data = json.loads(path.read_text())
            except Exception as exc:
                note(f"unreadable bundle {path.name}: {exc}")
                continue
            quiet, settled = classify(data)
            if quiet:
                kept.append(path)
                note(f"*** QUIET CROSSING (capture A) in {path.name}")
            if settled and not settled_seen:
                settled_seen = True
                if prev:
                    kept.append(prev)  # the last bundle still reading false
                kept.append(path)
                note(f"*** SETTLED (capture C) in {path.name} — both halves kept")
            prev = path

        if named:
            # A named window is kept whatever it showed: the first, the middle and the last.
            kept.extend([bundles[0], bundles[len(bundles) // 2], bundles[-1]])
            note(f"{label}: named window, keeping 3 of {len(bundles)} bundles")

        for path in dict.fromkeys(kept):
            target = KEEP / path.name
            if not target.exists():
                shutil.copy2(path, target)
                note(f"kept -> {target.name}")

        if not kept:
            note(f"{label}: {len(bundles)} bundles, nothing worth keeping (busy crossing)")
        for path in bundles:
            if path not in kept:
                path.unlink(missing_ok=True)

        if settled_seen:
            note("settlement captured — both halves are on disk")

        if ONE_SHOT:
            note("watcher done (one crossing per run)")
            return


if __name__ == "__main__":
    main()

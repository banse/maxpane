"""Metadata-only, complete container process identities for orphan signal rechecks.

Standalone so the fixed source can travel over stdin to a timeout-wrapped Python
child. No command lines, environment, credentials, or task file bodies are read.
A disappearing or unreadable row makes the snapshot unavailable; callers retry.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import time


def snapshot(root: Path = Path('/proc'), *, now: float | None = None, clk_tck: int | None = None) -> list[dict]:
    now = time.time() if now is None else now
    clk_tck = os.sysconf('SC_CLK_TCK') if clk_tck is None else clk_tck
    btime = next(float(line.split()[1]) for line in (root / 'stat').read_text().splitlines() if line.startswith('btime '))
    rows = []
    for base in sorted(root.iterdir()):
        if not base.name.isdigit():
            continue
        before = (base / 'stat').read_text().rsplit(')', 1)[-1].split()
        status = (base / 'status').read_text().splitlines()
        uid = int(next(line.split()[1] for line in status if line.startswith('Uid:')))
        cgroup = (base / 'cgroup').read_text().strip()
        after = (base / 'stat').read_text().rsplit(')', 1)[-1].split()
        ppid, pgid, start = int(before[1]), int(before[2]), int(before[19])
        if not cgroup or (ppid, pgid, start) != (int(after[1]), int(after[2]), int(after[19])):
            raise ValueError('process changed during snapshot')
        rows.append({'pid': int(base.name), 'ppid': ppid, 'pgid': pgid, 'uid': uid, 'cgroup': cgroup,
                     'start_ticks': start, 'age_s': max(0, now - btime - start / clk_tck)})
    return rows


if __name__ == '__main__':
    try:
        print(json.dumps(snapshot(), separators=(',', ':')))
    except (OSError, ValueError, IndexError, StopIteration):
        raise SystemExit(1) from None

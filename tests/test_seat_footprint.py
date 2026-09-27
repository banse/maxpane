"""Spec §1 #6, §12.1 "Footprint budget": the lean ``pepepane`` entrypoint's cold peak is asserted ≤ 160 MiB.

``ps rss`` is not a footprint on a memory-pressured Mac (fill7 §4: it swung 9.7 → 169 MiB in one idle
run); ``footprint -p`` (dirty + compressed) is. The measurement runs on macOS, including CI on the Mac, with a read-only libproc fallback
when the attachment tool is missing or denied; it is **skipped** elsewhere. Parser and fallback
seams are tested everywhere. The 142 MiB the research measured was the full ``MaxPaneApp`` with 14 managers on a
cold HOME; a ``SeatManager``-only entrypoint had never been measured until this test.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "pty_footprint2.py"
HEALTHY = REPO / "tests" / "fixtures" / "seat" / "healthy"


def _module():
    spec = importlib.util.spec_from_file_location("pty_footprint2", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_budget_and_the_parsers():
    mod = _module()
    assert mod.FOOTPRINT_CI_MAX_MIB == 160
    args = mod.parse_args(["180", "50", "seat", "--seconds", "30", "--max-mib", "160", "--", "python", "-m", "x"])
    assert (args.cols, args.rows, args.label, args.seconds, args.max_mib, args.cmd) == (180, 50, "seat", 30, 160.0, ["python", "-m", "x"])
    assert mod.parse_footprint_output("pepepane [123]: 64-bit    Footprint: 1649 KB (16384 bytes per page)") == pytest.approx(1649 / 1024, abs=0.01)
    assert mod.parse_footprint_output("phys_footprint: 123.4 MB") == pytest.approx(123.4)
    assert mod.parse_footprint_output("Footprint: 1.5 GB") == pytest.approx(1536.0)
    assert mod.parse_footprint_output("nothing here") is None
    assert mod.parse_pss_kib("Rss: 1000 kB\nPss: 2048 kB\n") == 2048


@pytest.mark.skipif(sys.platform != "darwin", reason="needs macOS physical-footprint sampling (run in CI on the Mac)")
@pytest.mark.skipif(not HEALTHY.is_dir(), reason="WP7's healthy fixture case is not committed yet")
def test_cold_footprint_of_the_lean_entrypoint_is_under_the_ci_budget(tmp_path):
    # spec §12.1: CI asserts ≤160 MiB via scripts/pty_footprint2.py against the lean entrypoint on a cold temp HOME
    env = dict(os.environ, HOME=str(tmp_path), PYTHONDONTWRITEBYTECODE="1", TERM="xterm-256color")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "180", "50", "seat", "--seconds", "40", "--max-mib", "160", "--",
         str(Path(sys.executable).with_name("pepepane")), "--host", "fixture", "--fixture", str(HEALTHY), "--offline", "--poll-interval", "5"],
        capture_output=True, text=True, timeout=240, env=env, cwd=str(REPO),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    match = re.search(r"peak phys_footprint=([0-9.]+) MiB", proc.stdout)
    assert match, proc.stdout
    assert 0 < float(match.group(1)) <= 160.0, proc.stdout
    assert "marker 'PEPEPANE': seen" in proc.stdout, "the screen rendered"
    print(proc.stdout)


def test_failed_footprint_attach_switches_permanently_to_libproc(monkeypatch):
    mod = _module()
    monkeypatch.setattr(mod.sys, "platform", "darwin")
    calls = []

    def denied(*args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args[0], 1, "", "attach denied")

    monkeypatch.setattr(mod.subprocess, "run", denied)
    monkeypatch.setattr(mod, "libproc_footprint_mib", lambda pid: 52.5)
    assert mod.footprint_mib(123) == 52.5
    assert mod.footprint_mib(123) == 52.5
    assert len(calls) == 1, "a denied attach must never be retried"


def test_libproc_reads_positive_peak_from_the_v4_struct(monkeypatch):
    import ctypes
    mod = _module()

    class ReadUsage:
        def __call__(self, pid, flavor, buffer):
            assert (pid, flavor) == (123, 4)
            info = ctypes.cast(buffer, ctypes.POINTER(mod.RusageInfoV4)).contents
            info.ri_phys_footprint = 40 * 1024**2
            info.ri_lifetime_max_phys_footprint = 64 * 1024**2
            return 0

    class Lib:
        proc_pid_rusage = ReadUsage()

    monkeypatch.setattr(mod.ctypes, "CDLL", lambda *args, **kwargs: Lib())
    assert ctypes.sizeof(mod.RusageInfoV4) == 296
    assert mod.libproc_footprint_mib(123) == 64


def test_driver_fails_without_a_positive_sample(monkeypatch, capsys):
    import itertools
    mod = _module()
    monkeypatch.setattr(mod.pty, "fork", lambda: (123, 4))
    monkeypatch.setattr(mod.fcntl, "ioctl", lambda *args: None)
    monkeypatch.setattr(mod.select, "select", lambda *args: ([], [], []))
    monkeypatch.setattr(mod.time, "time", lambda: next(clock))
    monkeypatch.setattr(mod.os, "write", lambda fd, data: len(data))
    monkeypatch.setattr(mod.os, "waitpid", lambda *args: (123, 0))
    monkeypatch.setattr(mod, "footprint_mib", lambda pid: None)
    clock = itertools.count(0, 10)
    assert mod.main(["180", "50", "fake", "--seconds", "1", "--max-mib", "160", "--", "fixture"]) == 1
    assert "no positive footprint sample" in capsys.readouterr().out

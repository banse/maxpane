#!/usr/bin/env python3
"""Drive a Textual app in a pty unattended and sample its footprint (spec §12.1; fill7 REUSABLE).

Usage: ``pty_footprint2.py COLS ROWS LABEL [--seconds N] [--max-mib N] -- CMD [ARGS...]``

Adapted from the research driver that measured MaxPane at 142 MiB (fill7 §4 run D): the same
``pty.fork`` + ``TIOCSWINSZ`` shape, the same ``footprint -p`` sampling (dirty + compressed;
``ps rss`` is not a footprint under memory pressure), a Linux fallback on ``/proc/<pid>/smaps_rollup``
``Pss``. The key script is the seat's: no splash and no menu to dismiss, so it waits, then presses
``c`` (CONTROL), ``escape``, ``l`` (tall log), ``h`` (heartbeats), and ``q``. Prints one sample per
10 s and ``[LABEL] peak phys_footprint=<n> MiB``; exits 1 when ``--max-mib`` is set and the peak is
above it, or no positive sample exists -- the CI assertion (``tests/test_seat_footprint.py``).
"""

from __future__ import annotations

import argparse
import ctypes
import fcntl
import os
import pty
import re
import select
import struct
import subprocess
import sys
import termios
import time

#: Spec §12.1: the CI ceiling for the lean entrypoint's cold peak (the 256M slice is 1.6× this).
FOOTPRINT_CI_MAX_MIB = 160

_UNITS = {"KB": 1 / 1024, "MB": 1.0, "GB": 1024.0}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="pty_footprint2.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("cols", type=int)
    parser.add_argument("rows", type=int)
    parser.add_argument("label")
    parser.add_argument("--seconds", type=int, default=60, help="how long to hold the app open after the key script (default 60)")
    parser.add_argument("--max-mib", type=float, default=None, help="exit 1 when the peak is above this")
    # The command is split off at the first ``--`` BEFORE argparse runs: an ``argparse.REMAINDER`` positional after
    # the three positionals would swallow every option given after them (``--seconds 30`` would land in the command).
    argv = list(argv)
    if "--" not in argv:
        parser.error("give the command after --")
    cut = argv.index("--")
    args = parser.parse_args(argv[:cut])
    args.cmd = argv[cut + 1:]
    if not args.cmd:
        parser.error("give the command after --")
    return args


def parse_footprint_output(text: str) -> float | None:
    """MiB from ``footprint -p`` output; both the macOS 26 header form and the older ``phys_footprint:`` line."""
    match = re.search(r"Footprint:\s*([0-9.,]+)\s*([KMG]B)", text) or re.search(r"phys_footprint:\s*([0-9.,]+)\s*([KMG]B)", text)
    if not match:
        return None
    return float(match.group(1).replace(",", ".")) * _UNITS[match.group(2)]


def parse_pss_kib(text: str) -> int | None:
    """``Pss:`` KiB from ``/proc/<pid>/smaps_rollup`` (the Linux fallback; cgroup memory.current is the VPS's own number)."""
    match = re.search(r"^Pss:\s+(\d+)\s+kB", text, flags=re.M)
    return int(match.group(1)) if match else None


# Darwin SDK sys/resource.h, rusage_info_v4: 16-byte UUID plus 35 uint64 fields.
# This read-only libproc call works when footprint cannot obtain an attach port.
class RusageInfoV4(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16)] + [
        (name, ctypes.c_uint64) for name in (
            'ri_user_time',
            'ri_system_time',
            'ri_pkg_idle_wkups',
            'ri_interrupt_wkups',
            'ri_pageins',
            'ri_wired_size',
            'ri_resident_size',
            'ri_phys_footprint',
            'ri_proc_start_abstime',
            'ri_proc_exit_abstime',
            'ri_child_user_time',
            'ri_child_system_time',
            'ri_child_pkg_idle_wkups',
            'ri_child_interrupt_wkups',
            'ri_child_pageins',
            'ri_child_elapsed_abstime',
            'ri_diskio_bytesread',
            'ri_diskio_byteswritten',
            'ri_cpu_time_qos_default',
            'ri_cpu_time_qos_maintenance',
            'ri_cpu_time_qos_background',
            'ri_cpu_time_qos_utility',
            'ri_cpu_time_qos_legacy',
            'ri_cpu_time_qos_user_initiated',
            'ri_cpu_time_qos_user_interactive',
            'ri_billed_system_time',
            'ri_serviced_system_time',
            'ri_logical_writes',
            'ri_lifetime_max_phys_footprint',
            'ri_instructions',
            'ri_cycles',
            'ri_billed_energy',
            'ri_serviced_energy',
            'ri_interval_max_phys_footprint',
            'ri_runnable_time',
        )
    ]


def libproc_footprint_mib(pid: int) -> float | None:
    try:
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        read_usage = lib.proc_pid_rusage
        read_usage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p]
        read_usage.restype = ctypes.c_int
        usage = RusageInfoV4()
        if read_usage(pid, 4, ctypes.byref(usage)) != 0:
            return None
        peak = max(usage.ri_phys_footprint, usage.ri_lifetime_max_phys_footprint)
        return peak / (1024 * 1024) if peak > 0 else None
    except (OSError, AttributeError):
        return None


_FOOTPRINT_AVAILABLE = True


def footprint_mib(pid: int) -> float | None:
    global _FOOTPRINT_AVAILABLE
    if sys.platform == "darwin":
        if _FOOTPRINT_AVAILABLE:
            try:
                result = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True, timeout=20)
                value = parse_footprint_output(result.stdout) if result.returncode == 0 else None
            except (OSError, subprocess.SubprocessError):
                value = None
            if value is not None and value > 0:
                return value
            _FOOTPRINT_AVAILABLE = False
            print("footprint attach unavailable; using libproc proc_pid_rusage v4", flush=True)
        return libproc_footprint_mib(pid)
    try:
        with open(f"/proc/{pid}/smaps_rollup", encoding="utf-8") as handle:
            kib = parse_pss_kib(handle.read())
    except OSError:
        return None
    return kib / 1024 if kib is not None else None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    pid, fd = pty.fork()
    if pid == 0:  # the child: the app
        os.environ["TERM"] = "xterm-256color"
        os.environ["COLORTERM"] = "truecolor"
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        os.execvp(args.cmd[0], args.cmd)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", args.rows, args.cols, 0, 0))
    t0 = time.time()
    screen = b""

    def elapsed() -> str:
        return f"{time.time() - t0:6.1f}s"

    def drain(seconds: float) -> bool:
        nonlocal screen
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([fd], [], [], 0.2)
            if fd in ready:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    return False
                if not data:
                    return False
                screen = (screen + data)[-200000:]
        return True

    peak = 0.0

    def sample(tag: str) -> None:
        nonlocal peak
        value = footprint_mib(pid)
        if value is None or value <= 0:
            print(f"[{args.label}] {elapsed()} {tag:14s} footprint unavailable", flush=True)
            return
        peak = max(peak, value)
        print(f"[{args.label}] {elapsed()} {tag:14s} phys_footprint={value:.1f} MiB", flush=True)

    def send(keys: str, why: str) -> None:
        os.write(fd, keys.encode())
        print(f"[{args.label}] {elapsed()} sent {keys!r} ({why})", flush=True)

    print(f"[{args.label}] pty {args.cols}x{args.rows} cmd={' '.join(args.cmd)}", flush=True)
    drain(8)
    sample("start")
    send("c", "CONTROL modal")
    drain(3)
    sample("control")
    send("\x1b", "close the modal")
    drain(2)
    send("l", "tall log")
    drain(2)
    send("h", "hide heartbeats")
    for i in range(max(1, args.seconds // 10)):
        drain(10)
        sample(f"seat+{(i + 1) * 10}s")
    send("q", "quit")
    end = time.time() + 20
    exited = False
    while time.time() < end:
        wpid, status = os.waitpid(pid, os.WNOHANG)
        if wpid == pid:
            exited = True
            print(f"[{args.label}] {elapsed()} exited status={status}", flush=True)
            break
        drain(0.5)
    if not exited:
        print(f"[{args.label}] {elapsed()} did not exit in 20 s -> SIGTERM", flush=True)
        os.kill(pid, 15)
        time.sleep(2)
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass
    print(f"[{args.label}] peak phys_footprint={peak:.1f} MiB", flush=True)
    text = screen.decode("utf-8", "replace")
    for marker in ("PEPEPANE", "IDMD #", "as of", "CONTROL", "LEDGER"):
        print(f"[{args.label}] marker {marker!r}: {'seen' if marker in text else 'not seen'}", flush=True)
    if peak <= 0:
        print(f"[{args.label}] FAIL no positive footprint sample", flush=True)
        return 1
    if args.max_mib is not None and peak > args.max_mib:
        print(f"[{args.label}] FAIL peak {peak:.1f} MiB > {args.max_mib:.0f} MiB", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

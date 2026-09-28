"""A scripted host for ``Broker`` tests: journal, systemctl, children -- all through the one ``Runner`` seam.

``Journal`` renders ``journalctl -o json`` output, adding a cursor only when requested, from ``(epoch, message)`` pairs so the
broker's gate, cursors and verify watch run against controllable lines. ``make_broker`` wires a
``RecordingRunner`` whose default script answers every read the broker performs at construction
and during a plan/apply/verify cycle; tests override entries by prefix.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from imd_dashd import imd_dashd as broker_mod
from imd_dashd.audit import Audit
from imd_dashd.imd_dashd import Broker
from tests.broker._recorder import RecordingRunner

NOW = 1_790_000_000.0
DASH_UID = 1001
WORKER_UID = 1000
PYTHON = "python3"
IP_DENY = "169.254.0.0/16 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 fc00::/7 fe80::/10 192.0.2.10 192.0.2.11"
PUBLIC_KEY = "72b617d4a1c3e5f70918273645b6c7d8e9f0a1b2c3d4e5f60718293a4b5c6d7e"
PRIVATE_KEY = "9f8e7d6c5b4a39281706f5e4d3c2b1a0f9e8d7c6b5a4938271605f4e3d2c1b0a"


def stamp(epoch: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(epoch)) + f".{int(round((epoch % 1) * 1000)) % 1000:03d}Z"


def hb(epoch: float, work: str = "idle", state: str = "alive") -> tuple[float, str]:
    return epoch, f"{stamp(epoch)} {state} 14h42m · {work} · 77 submitted · fleet 406 online, 417 enrolled"


def msg(epoch: float, text: str) -> tuple[float, str]:
    return epoch, f"{stamp(epoch)} {text}"


def idle_window(now: float, beats: int = 9) -> list[tuple[float, str]]:
    """``beats`` idle heartbeats 30 s apart, newest 11 s old, preceded by a terminal lifecycle line."""
    lines = [msg(now - 20 * 60 - 17, "submitted implement for 0c1f9727")]
    lines += [hb(now - 11 - 30 * i) for i in range(beats - 1, -1, -1)]
    return lines


class Journal:
    """Filter full fields first; systemd v259 emits large MESSAGEs as null without --all."""

    def __init__(self, lines: list[tuple[float, str]] | None = None) -> None:
        self.lines: list[tuple[float, str]] = sorted(lines or [], key=lambda item: item[0])

    def add(self, *lines: tuple[float, str]) -> None:
        self.lines = sorted(self.lines + list(lines), key=lambda item: item[0])

    @staticmethod
    def cursor(index: int) -> str:
        return f"s=deadbeef;i={index}"

    def render(self, selected: list[tuple[int, tuple[float, str]]], *, show_cursor: bool = True, all_fields: bool = False) -> bytes:
        out = []
        for index, (epoch, message) in selected:
            out.append(json.dumps({"MESSAGE": message if all_fields or len(message.encode("utf-8")) < 4088 else None, "__REALTIME_TIMESTAMP": str(int(epoch * 1_000_000)),
                                   "__CURSOR": self.cursor(index), "_SYSTEMD_INVOCATION_ID": "inv0001"}))
        last = selected[-1][0] if selected else len(self.lines) - 1
        if show_cursor:
            out.append(f"-- cursor: {self.cursor(max(last, -1))}")
        return ("\n".join(out) + ("\n" if out else "")).encode()

    def __call__(self, argv: list[str], kw: dict) -> subprocess.CompletedProcess:
        indexed = list(enumerate(self.lines))
        if "--grep" in argv:
            import re
            pattern = re.compile(argv[argv.index("--grep") + 1])
            selected = [(i, ln) for i, ln in indexed if pattern.search(ln[1])][-int(argv[argv.index("--lines") + 1]):]
            if not selected:
                return subprocess.CompletedProcess(argv, 1, self.render([], show_cursor="--show-cursor" in argv), b"")
        elif "--after-cursor" in argv:
            cursor = argv[argv.index("--after-cursor") + 1]
            after = int(cursor.rsplit("=", 1)[1])
            selected = [(i, ln) for i, ln in indexed if i > after]
        else:
            since = argv[argv.index("--since") + 1]          # "-600s"
            seconds = float(since.strip("-s"))
            now = self.now()
            selected = [(i, ln) for i, ln in indexed if ln[0] >= now - seconds]
        return subprocess.CompletedProcess(argv, 0, self.render(selected, show_cursor="--show-cursor" in argv, all_fields="--all" in argv), b"")

    now = staticmethod(lambda: NOW)


def standing_child(running: int, at: float) -> subprocess.CompletedProcess:
    body = json.dumps({"running_count": running, "at": stamp(at)}).encode() + b"\n"
    return subprocess.CompletedProcess([], 0, body, b"")


def projection_child(payload: dict, rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, json.dumps(payload).encode() + b"\n", b"")


def transient(out: str, rc: int = 0) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], rc, out.encode(), b"")


class Clock:
    def __init__(self, start: float = NOW) -> None:
        self.t = start

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> float:
        self.t += seconds
        return self.t


def default_script(journal: Journal, clock: Clock) -> dict:
    journal.now = clock
    broker_dir = broker_mod.BROKER_DIR
    return {
        ("systemctl", "show", "imd-worker.service", "-p", "IPAddressDeny", "--value"): (0, IP_DENY + "\n"),
        ("systemctl", "show", "imd-worker.service", "-p", "KillMode"): (0, "KillMode=control-group\nTimeoutStopUSec=30s\n"),
        ("systemctl", "is-active", "imd-worker.service"): (0, "active\n"),
        ("systemctl", "is-enabled", "imd-worker.service"): (0, "disabled\n"),
        ("journalctl",): journal,
        ("ls", "-1A"): (0, ""),
        (PYTHON, "-I", os.path.join(broker_dir, "gate.py")): lambda argv, kw: standing_child(0, clock() - 0.4),
        ("systemd-run",): lambda argv, kw: transient(PUBLIC_KEY + "\n") if argv[-1] == "whoami" else transient("ok\n"),
    }


def make_broker(tmp_path: Path, *, journal: Journal | None = None, clock: Clock | None = None, script: dict | None = None,
                seat: int | None = 7, proc_root: str | None = None, allowed_uid: int = DASH_UID) -> tuple[Broker, RecordingRunner, Journal, Clock, Audit]:
    clock = clock or Clock()
    journal = journal or Journal(idle_window(clock()))
    runner = RecordingRunner(default_script(journal, clock))
    runner.script.update(script or {})
    audit = Audit(tmp_path / "audit.jsonl", now=clock)
    broker = Broker(run=runner, peer_uid_of=lambda conn: DASH_UID, allowed_uid=allowed_uid, audit=audit, now=clock, monotonic=clock, seat=seat,
                    worker_home="/home/imd-worker", proc_root=proc_root or str(tmp_path / "proc"), python=PYTHON)
    return broker, runner, journal, clock, audit


def call(broker: Broker, verb: str, args: dict | None = None, *, peer_uid: int = DASH_UID) -> dict:
    return broker.handle({"v": 1, "verb": verb, "args": dict(args or {})}, peer_uid=peer_uid)


def audit_lines(audit: Audit) -> list[dict]:
    return [json.loads(ln) for ln in audit.path.read_text().splitlines()]


def write_fake_proc(root: Path, spec: dict) -> None:
    """Materialise ``procs_orphan.json`` as a /proc tree: stat (btime), <pid>/{stat,status,cgroup,cmdline}."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "stat").write_text(f"cpu  1 2 3 4\nbtime {spec['btime']}\n")
    for proc in spec["procs"]:
        pdir = root / str(proc["pid"])
        pdir.mkdir(exist_ok=True)
        comm = proc["cmd"].split()[0].rsplit("/", 1)[-1][:15]
        fields = [str(proc["pid"]), f"({comm})", "S", str(proc["ppid"]), str(proc["pgid"]), str(proc["pgid"]), "0", "-1", "4194560",
                  "0", "0", "0", "0", "0", "0", "0", "0", "20", "0", "1", "0", str(proc["start_ticks"]), "0", str(proc["rss_pages"])]
        (pdir / "stat").write_text(" ".join(fields) + " 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0\n")
        (pdir / "status").write_text(f"Name:\t{comm}\nUid:\t{proc['uid']}\t{proc['uid']}\t{proc['uid']}\t{proc['uid']}\nPPid:\t{proc['ppid']}\n")
        (pdir / "cgroup").write_text(f"0::/{proc['cgroup']}\n")
        (pdir / "cmdline").write_bytes(proc["cmd"].encode().replace(b" ", b"\x00") + b"\x00")

"""Seat #3 uses Claude and uid 1001; production startup must resolve that uid."""
from types import SimpleNamespace
import subprocess

import pytest

from imd_dashd import imd_dashd as mod
from tests.broker._harness import call, make_broker


def test_claude_hints_fallback_uses_dot_claude(tmp_path):
    path = "/home/imd-worker/.claude/CLAUDE.md"
    broker, runner, *_ = make_broker(tmp_path, script={
        ("stat", "-c"): lambda argv, kw: subprocess.CompletedProcess(
            argv, 0 if argv[-1] == path else 1, b"5953 1790000000\n", b""),
        ("sha256sum", path): (0, "abcdef12  CLAUDE.md\n"),
    })
    reply = call(broker, "hints-stat")
    assert reply["data"]["path"] == path
    assert reply["data"]["bytes"] == 5953
    assert [a[-1] for a in runner.argvs("stat")] == ["/home/imd-worker/.codex/AGENTS.md", path]


@pytest.mark.parametrize("override, expected", [(None, 1001), (1000, 1000)])
def test_main_resolves_worker_uid_by_name_or_explicit_override(tmp_path, monkeypatch, override, expected):
    import pwd
    resolved = []
    def lookup(name):
        resolved.append(name)
        return SimpleNamespace(pw_uid={"imd-dash": 1002, "imd-worker": 1001}[name])
    monkeypatch.setattr(pwd, "getpwnam", lookup)
    captured = {}
    class Broker:
        def __init__(self, **kw):
            captured.update(kw)
        def serve_forever(self, listener):
            pass
        def shutdown(self):
            pass
    monkeypatch.setattr(mod, "Broker", Broker)
    monkeypatch.setattr(mod, "listener_from_systemd", lambda: object())
    monkeypatch.setattr(mod.signal, "signal", lambda *args: None)
    args = ["--audit", str(tmp_path / "audit")]
    if override is not None:
        args += ["--worker-uid", str(override)]
    assert mod.main(args) == 0
    assert captured["worker_uid"] == expected
    assert resolved == (["imd-dash", "imd-worker"] if override is None else ["imd-dash"])
    rows = [{"pid": uid, "ppid": 0, "pgid": uid, "uid": uid, "cgroup": "user.slice",
             "age_s": 7200, "rss_b": 4096, "cmd": "claude"} for uid in (1000, 1001)]
    assert [p["uid"] for p in mod.select_orphans(rows, worker_uid=captured["worker_uid"])] == [expected]


def test_broker_version_identifies_fix8():
    import imd_dashd
    assert mod.VERSION == "imd-dashd 0.1.4"
    assert imd_dashd.__version__ == "0.1.4"

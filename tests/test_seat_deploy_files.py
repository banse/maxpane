"""The VPS deploy tree agrees with the broker it deploys (spec §12.1, §14, §15; contract §C.18).

Unit files, drop-ins, the sshd block, the installer, the probe, the hash-pinned lock, the
MANIFEST and the seat docs are read as text and bound to the constants the broker package
exports, so a path, user, mode or interpreter cannot drift between ``deploy/vps/`` and
``imd_dashd/`` without a red test. Nothing here touches a host: ``bash -n`` parses the
scripts, ``install.sh --dry-run`` and ``probe_seat_host.sh --list`` only print.

The deploy literal ``/opt/imd-dash/broker/imd_dashd`` (contract §B ``BROKER_DIR``) is
restated here rather than imported: the broker resolves its own directory at runtime so the
same files import under pytest and under ``python3 -I`` on the VPS (contract §C.11), and the
unit file must name the deployed path, never the checkout's.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tomllib
from pathlib import Path

import pytest

from imd_dashd.child_unit import CHILD_ENV, TRANSIENT_PROPERTIES, UNIT_PREFIX, WORKER_GROUP, WORKER_USER
from imd_dashd.imd_dashd import AUDIT_PATH, SOCKET_PATH, VERSION

#: Reads repo source or docs rather than exercising code (CLAUDE.md "Tests").
pytestmark = pytest.mark.guard

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "deploy" / "vps"
PYPROJECT = REPO / "pyproject.toml"

DASH_USER = "imd-dash"                                  #: spec §12.1 Users
WORKER_UNIT = "imd-worker.service"
DEPLOY_BROKER_ROOT = "/opt/imd-dash/broker"             #: contract §B BROKER_ROOT (root 0755)
DEPLOY_BROKER_DIR = DEPLOY_BROKER_ROOT + "/imd_dashd"   #: contract §B BROKER_DIR -- restated, see the module docstring
BROKER_PYTHON = "/usr/bin/python3"                      #: spec §12.1: the broker runs on the system interpreter, never the venv

SOCKET_UNIT = DEPLOY / "imd-dashd.socket"
SERVICE_UNIT = DEPLOY / "imd-dashd.service"

#: Spec §12.1 imd-dashd.service: the hardening the root broker carries. RestrictNamespaces /
#: PrivateDevices / ProtectSystem=strict apply to the broker and its stdlib children only;
#: every runtime-executing child is a transient unit outside this service (spec §4.1b).
SERVICE_HARDENING = {
    "NoNewPrivileges": "yes",
    "ProtectSystem": "strict",
    "PrivateTmp": "yes",
    "PrivateDevices": "yes",
    "ProtectKernelTunables": "yes",
    "ProtectKernelModules": "yes",
    "ProtectControlGroups": "yes",
    "RestrictNamespaces": "yes",
    "RestrictRealtime": "yes",
    "LockPersonality": "yes",
    "SystemCallArchitectures": "native",
}
#: Spec §12.1: 128M, not 64M and not 256M -- the broker idles at ~20 MiB and its in-process
#: children are a stdlib projection and an urllib read; node/codex children live in 512M
#: transient units.
SERVICE_BUDGET = {"MemoryMax": "128M", "CPUQuota": "50%", "TasksMax": "64", "TimeoutStopSec": "15"}
CAPABILITY_BOUNDING_SET = "CAP_SETUID CAP_SETGID CAP_KILL CAP_DAC_READ_SEARCH CAP_DAC_OVERRIDE CAP_CHOWN CAP_FOWNER"
#: Spec §12.1 notes: no ReadWritePaths (the broker writes only under LogsDirectory); no
#: IPAddressDeny / RestrictAddressFamilies (the gate's urllib standing read needs api.imd.fun).
FORBIDDEN_SERVICE_KEYS = ("ReadWritePaths", "IPAddressDeny", "IPAddressAllow", "RestrictAddressFamilies")


def _unit(path: Path) -> dict[str, list[tuple[str, str]]]:
    """Parse a systemd unit / drop-in into ``{section: [(key, value), ...]}``, duplicates kept in order."""
    sections: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, [])
            continue
        assert current is not None, f"{path.name}: directive before any [Section]: {raw!r}"
        key, sep, value = line.partition("=")
        assert sep, f"{path.name}: not a key=value line: {raw!r}"
        sections[current].append((key.strip(), value.strip()))
    return sections


def _values(section: list[tuple[str, str]], key: str) -> list[str]:
    return [value for name, value in section if name == key]


def _one(section: list[tuple[str, str]], key: str) -> str:
    found = _values(section, key)
    assert len(found) == 1, f"expected exactly one {key}=, found {found}"
    return found[0]


def _none(section: list[tuple[str, str]], key: str) -> None:
    assert _values(section, key) == [], f"{key}= must not appear, found {_values(section, key)}"


# --- Task 9.1: the broker units ------------------------------------------------------------------


def test_socket_directory_mode_is_0755_and_socket_mode_0660():
    """Spec §12.1 imd-dashd.socket: DirectoryMode is 0755, not 0750. systemd creates the parent
    directory root:root with DirectoryMode and applies SocketUser/SocketGroup to the socket node
    only (systemd.socket(5)); at 0750 imd-dash could not traverse /run/imd-dash and every
    connect() would fail EACCES -- the whole control path dead until the install-day probe.
    Mutation: DirectoryMode=0750 -> red; SocketMode=0666 -> red; ListenStream elsewhere -> red."""
    unit = _unit(SOCKET_UNIT)
    sock = unit["Socket"]
    assert _one(sock, "ListenStream") == SOCKET_PATH, "the socket path is the broker's SOCKET_PATH"
    assert _one(sock, "SocketUser") == "root"
    assert _one(sock, "SocketGroup") == DASH_USER
    assert _one(sock, "SocketMode") == "0660"
    assert _one(sock, "DirectoryMode") == "0755"
    assert _one(sock, "Accept") == "no", "one broker process serves every connection (SO_PEERCRED per accept)"
    assert _one(sock, "RemoveOnStop") == "yes"
    assert _one(unit["Install"], "WantedBy") == "sockets.target"
    assert _one(unit["Unit"], "Description").startswith("IMD seat dashboard broker")


def test_service_execstart_is_python_isolated_at_broker_dir():
    """Contract §C.11 (contract decision): the package directory is copied verbatim to
    BROKER_DIR, and ExecStart is ``/usr/bin/python3 -I /opt/imd-dash/broker/imd_dashd/imd_dashd.py``
    -- the spec's ``/opt/imd-dash/broker/imd_dashd.py`` spelling is superseded. ``-I`` keeps the
    script directory off sys.path (the module inserts its parent itself). Mutation: drop ``-I``
    -> red; the spec's old path -> red; the venv interpreter -> red."""
    service = _unit(SERVICE_UNIT)
    exec_start = _one(service["Service"], "ExecStart").split()
    assert exec_start == [BROKER_PYTHON, "-I", DEPLOY_BROKER_DIR + "/imd_dashd.py"]
    script = Path(exec_start[2])
    assert script.name == "imd_dashd.py" and script.parent.name == "imd_dashd"
    assert (REPO / "imd_dashd" / script.name).is_file(), "the deployed script exists in the checkout"
    assert _one(service["Unit"], "Requires") == "imd-dashd.socket"
    assert _one(service["Service"], "Type") == "simple"
    assert _one(service["Service"], "User") == "root"
    assert _one(service["Service"], "Group") == "root"
    assert _one(service["Service"], "Environment") == "PYTHONDONTWRITEBYTECODE=1"
    assert "Install" not in service, "socket-activated: the service is never enabled on its own"


def test_service_has_no_readwritepaths_and_no_ipaddresspaths():
    """Spec §12.1 notes: no ReadWritePaths in v1 (the broker writes only under LogsDirectory;
    ``imd skills add|remove`` runs as a transient unit with the worker's own BindPaths), and no
    IPAddressDeny / RestrictAddressFamilies (the gate's urllib standing read needs api.imd.fun;
    approach C's IPAddressDeny=any broke its own read verbs). InaccessiblePaths hides only
    /home/imd-dash: /run/dbus and /run/systemd/private must stay connectable for systemctl and
    systemd-run. Mutation: add ReadWritePaths=/home/imd-worker -> red; IPAddressDeny=any -> red."""
    svc = _unit(SERVICE_UNIT)["Service"]
    for key in FORBIDDEN_SERVICE_KEYS:
        _none(svc, key)
    assert _values(svc, "InaccessiblePaths") == ["-/home/imd-dash"]
    assert "/run/dbus" not in " ".join(_values(svc, "InaccessiblePaths"))


def test_service_hardening_budget_and_logs_directory():
    """Spec §12.1 imd-dashd.service: the hardening list, the 128M/50%/64 budget, the bounding set,
    and LogsDirectory=imd-dash (0700) -- which is where AUDIT_PATH lives. Mutation: MemoryMax=256M
    -> red; drop RestrictNamespaces -> red; LogsDirectoryMode=0755 -> red."""
    svc = _unit(SERVICE_UNIT)["Service"]
    for key, value in SERVICE_HARDENING.items():
        assert _one(svc, key) == value, key
    for key, value in SERVICE_BUDGET.items():
        assert _one(svc, key) == value, key
    assert _one(svc, "CapabilityBoundingSet") == CAPABILITY_BOUNDING_SET
    assert _one(svc, "AmbientCapabilities") == "", "no ambient capabilities: root drops via setresuid in Popen(user=)"
    audit = Path(AUDIT_PATH)
    assert audit.parent.parent == Path("/var/log"), "LogsDirectory= is relative to /var/log"
    assert _one(svc, "LogsDirectory") == audit.parent.name == "imd-dash"
    assert _one(svc, "LogsDirectoryMode") == "0700"


# --- Task 9.2: the drop-ins -----------------------------------------------------------------------

WORKER_DROPIN = DEPLOY / "20-hide-dash.conf"
SLICE_DROPIN = DEPLOY / "50-pepepane.conf"
SSHD_DROPIN = DEPLOY / "10-imd-dash.sshd.conf"


def test_worker_dropin_hides_every_dash_path_and_proc():
    """Spec §12.1 / §16 #4: the worker unit hides the socket dir, the dash home and the audit dir
    from tasks (which read the filesystem root as imd-worker, vps §2) and gets ProtectProc=invisible.
    The same three paths are InaccessiblePaths on every transient child (contract §C.11
    TRANSIENT_PROPERTIES), so the two postures cannot drift. Each path carries the ``-`` prefix
    (ignore if missing) because the drop-in must not fail the worker on a host where the dash
    is not installed. Mutation: drop /var/log/imd-dash -> red; ProtectProc=default -> red."""
    svc = _unit(WORKER_DROPIN)["Service"]
    hidden = _one(svc, "InaccessiblePaths").split()
    assert hidden == ["-/run/imd-dash", "-/home/imd-dash", "-/var/log/imd-dash"]
    assert hidden[0] == "-" + str(Path(SOCKET_PATH).parent)
    assert hidden[1] == "-/home/" + DASH_USER
    assert hidden[2] == "-" + str(Path(AUDIT_PATH).parent)
    child_hidden = {p.split("=", 1)[1] for p in TRANSIENT_PROPERTIES if p.startswith("InaccessiblePaths=")}
    assert {h.lstrip("-") for h in hidden} <= child_hidden, "the transient children hide what the worker hides"
    assert _one(svc, "ProtectProc") == "invisible"
    assert list(_unit(WORKER_DROPIN)) == ["Service"], "a drop-in: one [Service] section, nothing else"


def test_slice_dropin_fences_the_tui_at_256m_and_half_a_cpu():
    """Spec §12.1 footprint fence: logind puts every process of the imd-dash login into
    user-<uid>.slice, so a forge spike kills the TUI's slice, not the worker's. 256M is 1.8x the
    measured 142 MiB cold peak of the full app (fill7 §4) and above the 160 MiB CI assertion on the
    lean entrypoint. Mutation: MemoryMax=128M -> red; a [Service] section -> red."""
    unit = _unit(SLICE_DROPIN)
    assert list(unit) == ["Slice"]
    assert _one(unit["Slice"], "MemoryMax") == "256M"
    assert _one(unit["Slice"], "CPUQuota") == "50%"


def test_sshd_match_block_denies_forwarding_for_imd_dash():
    """Spec §12.1 sshd: the account that holds the daily key gets no TCP/agent/X11 forwarding
    (closes the ``ssh -L`` path safety §4 warns about; the global is AllowTcpForwarding yes) and
    keeps PermitTTY for the TUI. The Match block must name exactly imd-dash and nothing else.
    Mutation: AllowTcpForwarding yes -> red; a second Match block -> red."""
    lines = [ln.strip() for ln in SSHD_DROPIN.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert lines[0] == f"Match User {DASH_USER}"
    directives = dict(ln.split(None, 1) for ln in lines[1:])
    assert directives == {
        "AllowTcpForwarding": "no",
        "X11Forwarding": "no",
        "AllowAgentForwarding": "no",
        "PermitTTY": "yes",
    }
    assert sum(ln.startswith("Match") for ln in lines) == 1


# --- Task 9.3: install.sh ---------------------------------------------------------------------------

INSTALL_SH = DEPLOY / "install.sh"
STRICT_MODE = "set -euo pipefail"
STEP_TITLES = (                                   #: spec §12.1 "Install sequence" 1..8, as install.sh prints them
    "== step 1:", "== step 2:", "== step 3:", "== step 4:", "== step 5:", "== step 6:", "== step 7:", "== step 8:",
)


def _bash_n(path: Path) -> None:
    """``bash -n`` parses the script (macOS ships bash 3.2, so the scripts stay 3.2-compatible)."""
    proc = subprocess.run(["bash", "-n", str(path)], capture_output=True, text=True, timeout=20)
    assert proc.returncode == 0, proc.stderr


def _run_bash(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run a deploy script in a minimal environment; nothing here may touch the host (dry-run / list only)."""
    return subprocess.run(["bash", *args], capture_output=True, text=True, timeout=60,
                          env={"PATH": "/usr/bin:/bin", "HOME": "/nonexistent", "LC_ALL": "C", **(env or {})})


def test_install_sh_is_bash_strict_and_symlinks_usr_local_bin_pepepane():
    """Spec §12.1 PATH: ``ssh host cmd`` runs a non-interactive bash whose skel .bashrc returns before
    any user additions, so the venv goes on PATH through a root-owned symlink in /usr/local/bin, never
    a .bashrc line. Bash strict mode + the hash-pinned offline install are the other two lines that
    must never disappear. Mutation: drop ``--require-hashes`` -> red; ``ln -s`` into ~/.local/bin -> red."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "#!/usr/bin/env bash"
    assert STRICT_MODE in [ln.strip() for ln in lines[:12]], "strict mode in the header, before any command"
    assert INSTALL_SH.stat().st_mode & 0o111, "install.sh is executable"
    assert re.search(r'ln -sfn "\$VENV/bin/pepepane" /usr/local/bin/pepepane', text)
    assert 'VENV="$PREFIX/venv"' in text and 'PREFIX=/opt/imd-dash' in text
    assert "--no-index" in text and "--require-hashes" in text and "--only-binary=:all:" in text
    assert re.search(r'(?m)^run "\$VENV/bin/python" -m pip install .*--require-hashes -r "\$LOCK"$', text)
    assert "sha256sum -c" in text
    assert "useradd -m -s /bin/bash -G systemd-journal" in text
    assert "chmod 0700" in text
    _bash_n(INSTALL_SH)


def test_install_sh_dry_run_prints_the_eight_steps_in_order(tmp_path):
    """Spec §12.1 install sequence 1..8: ``--dry-run`` prints every command it would run, runs none,
    needs neither root nor Linux, and keeps the step order. Mutation: swap steps 5 and 6 -> red;
    let dry-run execute ``ln`` -> the ``[dry-run]`` prefix disappears -> red."""
    key = tmp_path / "imd-dash.pub"
    key.write_text("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIExampleKeyForTheGuard imd-dash@probe\n")
    proc = _run_bash(str(INSTALL_SH), "--dry-run", "--route", "a", "--authorized-keys", str(key))
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    positions = [out.index(title) for title in STEP_TITLES]
    assert positions == sorted(positions), "steps print in spec order"
    assert "[dry-run] apt-get install -y --no-install-recommends python3.14-venv" in out
    assert "[dry-run] useradd -m -s /bin/bash -G systemd-journal imd-dash" in out
    assert "[dry-run] chmod 0700 /home/imd-dash" in out
    assert f"[dry-run] install -m 0600 -o imd-dash -g imd-dash {key} /home/imd-dash/.ssh/authorized_keys" in out
    assert "--require-hashes -r /opt/imd-dash/requirements.lock" in out
    assert "[dry-run] ln -sfn /opt/imd-dash/venv/bin/pepepane /usr/local/bin/pepepane" in out
    assert "[dry-run] systemctl enable --now imd-dashd.socket" in out
    assert "[dry-run] sshd -t" in out and "[dry-run] systemctl reload ssh" in out
    assert "20-hide-dash.conf" in out and "--worker-dropin" in out, "step 7 names the flag it is waiting for"
    assert "probe_seat_host.sh" in out, "step 8 prints the probe command"
    assert "\n  + " not in out, "nothing was executed in dry-run mode"


def test_install_sh_never_restarts_stops_or_starts_the_worker():
    """Spec §12.1 step 7 and §11: the drop-in takes effect at a DRAINED restart issued through the
    broker's gate; the installer has no gate and therefore no restart. Mutation: add
    ``run systemctl restart imd-worker.service`` -> red."""
    text = INSTALL_SH.read_text(encoding="utf-8")
    for verb in ("systemctl restart", "systemctl stop", "systemctl start", "systemctl kill"):
        assert verb not in text, verb
    assert "systemctl enable --now imd-dashd.socket" in text, "the one unit the installer starts is the socket"


def test_install_sh_refuses_bad_routes_and_route_b_without_the_pip_wheel(tmp_path):
    """Spec §16 #2: routes are a (apt python3.14-venv) or b (venv --without-pip + pip wheel bootstrap,
    fill7 §3); b without ``--pip-wheel`` cannot bootstrap pip and must say so instead of running
    ``python3 -m venv`` (which fails on the VPS: no ensurepip). Mutation: default the pip wheel -> red."""
    bad = _run_bash(str(INSTALL_SH), "--dry-run", "--route", "c")
    assert bad.returncode == 1 and "--route must be a or b" in bad.stderr
    no_wheel = _run_bash(str(INSTALL_SH), "--dry-run", "--route", "b")
    assert no_wheel.returncode == 1 and "--pip-wheel" in no_wheel.stderr
    wheel = tmp_path / "pip-26.2.1-py3-none-any.whl"
    wheel.write_bytes(b"PK\x05\x06" + b"\0" * 18)
    ok = _run_bash(str(INSTALL_SH), "--dry-run", "--route", "b", "--pip-wheel", str(wheel))
    assert ok.returncode == 0, ok.stderr
    assert "[dry-run] python3 -m venv --without-pip /opt/imd-dash/venv" in ok.stdout
    assert f"{wheel}/pip install --no-index {wheel}" in ok.stdout
    usage = _run_bash(str(INSTALL_SH), "--dry-run", "--bogus")
    assert usage.returncode == 1 and "unknown argument" in usage.stderr


def test_install_sh_gives_the_broker_its_seat():
    """Spec §11 gate step (b): at every apply the broker re-reads ``GET /seats/<id>/standing`` itself
    (``standing_age_s <= 2``); §1 criterion 4 and the drain fire condition need that plane half. The root
    broker learns <id> only from ``--seat`` (WP6 ``main``: default ``None`` -> ``_standing_url_for_seat()``
    is ``None`` -> every gate is ``local-only`` and a drain re-arms until ``drain_expired``). The
    MANIFEST-pinned unit stays the contract's verbatim text, so install.sh writes the seat into a drop-in
    that resets and re-states ExecStart, before the socket is enabled. Mutation: drop the drop-in -> red;
    render ``--seat`` without its value -> red; skip the empty ``ExecStart=`` reset -> red (systemd refuses
    a second ExecStart= for Type=simple)."""
    proc = _run_bash(str(INSTALL_SH), "--dry-run", "--seat", "7")
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "/etc/systemd/system/imd-dashd.service.d/10-seat.conf" in out
    rendered = [ln[6:] for ln in out.splitlines() if ln.startswith("    > ")]
    assert "[Service]" in rendered
    starts = [ln for ln in rendered if ln.startswith("ExecStart=")]
    assert starts == ["ExecStart=", f"ExecStart={BROKER_PYTHON} -I {DEPLOY_BROKER_DIR}/imd_dashd.py --seat 7"]
    step5 = out[out.index("== step 5:"):out.index("== step 6:")]
    dropin_at = step5.index("[dry-run] install -m 0644 <the 10-seat.conf above>")
    assert dropin_at < step5.index("[dry-run] systemctl daemon-reload") < step5.index("[dry-run] systemctl enable --now imd-dashd.socket")
    assert "--seat" not in SERVICE_UNIT.read_text(encoding="utf-8"), "the unit file itself stays the contract text (Task 9.1)"


# --- Task 9.4: probe_seat_host.sh + docs/seat_install_probe.md ---------------------------------------------

PROBE_SH = DEPLOY / "probe_seat_host.sh"
PROBE_DOC = REPO / "docs" / "seat_install_probe.md"
#: Spec §14 "Only on the VPS": every item, as a substring one of the probe's titles must carry, in order.
PROBE_TITLES_MUST_MENTION = (
    ("connect", DASH_USER, "succeeds"),
    ("connect", WORKER_USER, "fails"),
    ("journalctl", "read count"),
    ("--after-cursor", "stale"),
    ("journalctl", "lifecycle", "--grep", "no-match"),
    ("systemctl show",),
    ("cgroup",),
    ("compression.zstd",),
    ("pepepane --once --offline",),
    ("ping",),
    ("seat projection", "whoami"),
    ("status", "memory.peak"),
    ("doctor", "memory.peak"),
    ("plan restart", "never applied"),
    ("sha256sum -c", "MANIFEST"),
    ("ls /home/imd-dash", "must fail"),
    ("sshd -T", "allowtcpforwarding"),
    ("user-<uid>.slice", "MemoryMax"),
    ("HISTORY", "sysstat"),
    ("drained restart", "by hand"),
)


def _probe_titles() -> list[str]:
    proc = _run_bash(str(PROBE_SH), "--list")
    assert proc.returncode == 0, proc.stderr
    titles = []
    for line in proc.stdout.splitlines():
        m = re.fullmatch(r"(\d+)\. (.+)", line)
        assert m, f"--list prints numbered titles only: {line!r}"
        assert int(m.group(1)) == len(titles) + 1, "numbered 1..N without gaps"
        titles.append(m.group(2))
    return titles


def test_probe_lists_the_two_connect_checks_first():
    """Spec §14: 'first two lines -- connect(/run/imd-dash/broker.sock) as imd-dash succeeds, as
    imd-worker fails' -- the pair that proves DirectoryMode=0755 + SocketMode=0660 + the worker
    drop-in at once. The socket path in the titles is the broker's SOCKET_PATH. Mutation: move the
    journalctl count above the connect checks -> red; drop the imd-worker negative -> red."""
    titles = _probe_titles()
    assert all(word in titles[0] for word in PROBE_TITLES_MUST_MENTION[0]), titles[0]
    assert all(word in titles[1] for word in PROBE_TITLES_MUST_MENTION[1]), titles[1]
    assert SOCKET_PATH in titles[0] and SOCKET_PATH in titles[1]
    _bash_n(PROBE_SH)
    assert PROBE_SH.read_text(encoding="utf-8").splitlines()[0] == "#!/usr/bin/env bash"
    assert STRICT_MODE in PROBE_SH.read_text(encoding="utf-8")


def test_probe_covers_every_only_on_the_vps_item_in_order():
    """Spec §14 'Only on the VPS', §5.1 (stale cursor), §5.4 (compression.zstd), §5.5 (HISTORY),
    §4.1b (child memory.peak), §12.1 (MANIFEST, sshd, slice): every item is a section, in the spec's
    order, and the script never applies a restart. Mutation: delete the HISTORY section -> red;
    add ``"verb":"apply"`` with a restart plan -> red."""
    titles = _probe_titles()
    assert len(titles) == len(PROBE_TITLES_MUST_MENTION), titles
    for title, words in zip(titles, PROBE_TITLES_MUST_MENTION):
        assert all(word in title for word in words), (title, words)
    text = PROBE_SH.read_text(encoding="utf-8")
    assert UNIT_PREFIX + "status-*" in text and UNIT_PREFIX + "doctor-*" in text, "child memory.peak via the transient unit glob"
    assert "--skip-doctor" in text
    assert text.count('"verb":"apply"') == 1, "exactly one apply (doctor); plan restart is never applied"
    assert '"verb":"restart"' in text
    assert "s=00000000000000000000000000000000" in text, "the deliberately stale cursor"
    assert "import compression.zstd" in text
    assert "sed -E 's/[0-9a-fA-F]{32,}/<hex>/g'" in text, "every reply is scrubbed of hex >= 32 before it is printed"
    assert "$" not in " ".join(titles), "titles are prose: they land in docs/seat_install_probe.md"


def test_probe_placeholder_doc_lists_the_probe_sections():
    """Spec §14 / §16 #17: docs/seat_install_probe.md is a placeholder until the owner runs the probe
    once; its numbered list (or, once pasted, its ``## N.`` headings) is the probe's own list, so the
    doc cannot describe a probe that no longer exists. Mutation: renumber a section -> red."""
    text = PROBE_DOC.read_text(encoding="utf-8")
    assert text.startswith("# PEPEPANE install probe")
    found = []
    for line in text.splitlines():
        m = re.fullmatch(r"(?:## )?(\d+)\. (.+)", line.strip())
        if m:
            found.append(m.group(2).strip())
    assert found == _probe_titles()
    if "placeholder" in text.lower():
        assert "not yet run" in text.lower(), "a placeholder says so in its first paragraph"


def test_probe_redacts_all_code_blocks_with_the_broker_redactor():
    """Synthetic hostile journal text must be scrubbed before a probe report emits it."""
    import sys
    text = PROBE_SH.read_text()
    assert "code_block() { printf '~~~\\n'; scrub; printf '~~~\\n'; }" in text
    match = re.search(r"# BEGIN PROBE_REDACTOR\n(.*?)\n# END PROBE_REDACTOR", text, re.S)
    assert match, "the probe must reuse the installed stdlib redactor"
    code = match.group(1).replace('"/opt/imd-dash/broker"', repr(str(REPO)))
    hostile = "sk-ant-example0000 Bearer examplecredential0000 " + "a" * 64 + "\x1b]52;c;AAAA\x07\u202e\n"
    proc = subprocess.run([sys.executable, "-I", "-c", code], input=hostile,
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    assert "example0000" not in proc.stdout and "examplecredential0000" not in proc.stdout
    assert "a" * 64 not in proc.stdout and "\x1b" not in proc.stdout and "\u202e" not in proc.stdout
    assert "sk-ant-[redacted]" in proc.stdout and "Bearer [redacted]" in proc.stdout
    from imd_dashd.redact import redact
    from maxpane_dashboard.data.seat_manager import SeatManager
    currency = "runtime estimate " + chr(36) + "0.07\n"
    sample = subprocess.run([sys.executable, "-I", "-c", code], input=currency, capture_output=True, text=True, timeout=10)
    assert sample.returncode == 0
    assert sample.stdout == SeatManager._no_currency(redact(currency))


def test_probe_socket_read_budget_covers_synchronous_broker_reads():
    text = PROBE_SH.read_text()
    assert "from imd_dashd.child_unit import RUNTIME_MAX_S, SUBPROCESS_BELT_S" in text
    assert "s.settimeout(max(RUNTIME_MAX_S.values()) + SUBPROCESS_BELT_S + 5)" in text


# --- Task 9.5: build_wheels.sh + requirements.lock ------------------------------------------------------------

BUILD_WHEELS_SH = REPO / "scripts" / "build_wheels.sh"
LOCK = DEPLOY / "requirements.lock"
HASH_RE = re.compile(r"--hash=sha256:[0-9a-f]{64}")


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _lock_requirements(text: str) -> dict[str, tuple[str, list[str]]]:
    """``name -> (version, hashes)`` from a pip requirements file with backslash continuations.

    Every logical line must be ``name==version`` followed only by ``--hash=sha256:…`` tokens: no URLs,
    no editables, no index options -- the VPS install is ``--no-index`` and hash-checked (spec §12.1)."""
    logical: list[str] = []
    buf = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        logical.append((buf + line).strip())
        buf = ""
    assert not buf, "dangling continuation at end of file"
    out: dict[str, tuple[str, list[str]]] = {}
    for entry in logical:
        parts = entry.split()
        m = re.fullmatch(r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9.+!-]+)", parts[0])
        assert m, f"not a ``name==version`` requirement: {entry!r}"
        hashes = [p for p in parts[1:] if p.startswith("--hash=")]
        others = [p for p in parts[1:] if not p.startswith("--hash=")]
        assert not others, f"unexpected tokens after {parts[0]}: {others}"
        name = m.group(1).lower().replace("_", "-")
        assert name not in out, f"duplicate requirement {name}"
        out[name] = (m.group(2), hashes)
    return out


def test_requirements_lock_pins_match_pyproject_seat_group():
    """Spec §12.1 Pins / §15: the lock and the ``seat`` group name the same four versions, the closure
    carries the fork's own wheel (``maxpane==<project version>``) and its upstream dependency
    ``sybilkit``, and the only binary wheel's project is present. Mutation: bump rich to 15.0.1 in the
    lock alone -> red; drop the maxpane block -> red."""
    project = _project()["project"]
    lock = _lock_requirements(LOCK.read_text(encoding="utf-8"))
    for spec in project["optional-dependencies"]["seat"]:
        name, version = spec.split("==")
        assert lock[name.lower()][0] == version, spec
    assert lock["maxpane"][0] == project["version"], "the fork wheel is pinned to the checkout's version"
    assert "sybilkit" in lock and "pydantic-core" in lock
    assert len(lock) >= 20, f"the closure is ~20 wheels + maxpane (fill7 §2 counted 22 before the 3.14 markers); found {len(lock)}"


def test_every_lock_line_has_a_hash():
    """Spec §12.1: ``pip install --require-hashes`` refuses an install where any requirement lacks a
    hash -- and a constraints file alone would pin versions, not bytes (fill7 §3). Every requirement
    carries at least one sha256, and the file has no index or URL lines (offline install).
    Mutation: strip one ``--hash`` -> red; add ``--extra-index-url`` -> red."""
    text = LOCK.read_text(encoding="utf-8")
    lock = _lock_requirements(text)
    for name, (version, hashes) in lock.items():
        assert hashes, f"{name}=={version} has no --hash"
        for h in hashes:
            assert HASH_RE.fullmatch(h), f"{name}: malformed {h}"
    for forbidden in ("--index-url", "--extra-index-url", "--find-links", " @ ", "git+", "http://", "https://", "-e "):
        assert forbidden not in "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith("#")), forbidden


def test_build_wheels_script_emits_the_lock_the_manifest_and_ignores_the_wheels():
    """Spec §12.1 install route (a): the closure is resolved and hash-pinned on the Mac
    (``uv pip compile --generate-hashes``), the wheels are downloaded for the VPS's interpreter and
    platform, the fork wheel is built from the checkout, and the MANIFEST covers the tree; wheels are
    never committed. Mutation: drop ``--generate-hashes`` -> red; remove deploy/vps/.gitignore -> red."""
    text = BUILD_WHEELS_SH.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "#!/usr/bin/env bash" and STRICT_MODE in text
    assert BUILD_WHEELS_SH.stat().st_mode & 0o111
    for needle in ("uv pip compile", "--generate-hashes", "--python-version", "--python-platform", "--extra seat",
                   "pip download", "--only-binary=:all:", "--no-deps", "uv build", "--wheel",
                   "requirements.lock", "MANIFEST.sha256", "--manifest-only", "seat-deploy-"):
        assert needle in text, needle
    _bash_n(BUILD_WHEELS_SH)
    ignore = (DEPLOY / ".gitignore").read_text(encoding="utf-8").split()
    assert "wheels/" in ignore


# --- Task 9.6: MANIFEST.sha256 + VERIFY.md ---------------------------------------------------------------------

MANIFEST = DEPLOY / "MANIFEST.sha256"
VERIFY_MD = DEPLOY / "VERIFY.md"
MANIFEST_LINE = re.compile(r"([0-9a-f]{64})  (\S.*)")
#: Contract §C.18 + deviation #5: every deploy/vps file the installer copies or feeds to pip.
MANIFEST_DEPLOY_FILES = (
    "deploy/vps/imd-dashd.socket", "deploy/vps/imd-dashd.service", "deploy/vps/20-hide-dash.conf",
    "deploy/vps/50-pepepane.conf", "deploy/vps/10-imd-dash.sshd.conf", "deploy/vps/install.sh",
    "deploy/vps/probe_seat_host.sh", "deploy/vps/requirements.lock",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict[str, str]:
    """``path -> sha256`` from MANIFEST.sha256; every line is ``<hex64><two spaces><path>``."""
    out: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        m = MANIFEST_LINE.fullmatch(line)
        assert m, f"not a sha256sum line: {line!r}"
        assert m.group(2) not in out, f"duplicate manifest path {m.group(2)}"
        out[m.group(2)] = m.group(1)
    return out


def test_manifest_names_every_imd_dashd_file_and_the_fork_wheel():
    """Spec §12.1 / contract §C.18: the MANIFEST covers the whole tree the installer touches -- every
    ``imd_dashd/*.py`` (as deployed under BROKER_DIR), the units and drop-ins, both scripts, the lock,
    and exactly one fork wheel at the checkout's version -- and never lists itself. Mutation: delete the
    ``imd_dashd/gate.py`` line -> red; rename the wheel line to 0.9.2 -> red."""
    manifest = _manifest()
    on_disk = {f"imd_dashd/{p.name}" for p in (REPO / "imd_dashd").glob("*.py")}
    listed = {p for p in manifest if p.startswith("imd_dashd/")}
    assert listed == on_disk, f"missing {on_disk - listed}, stale {listed - on_disk}"
    for path in MANIFEST_DEPLOY_FILES:
        assert path in manifest, path
    version = _project()["project"]["version"]
    wheels = [p for p in manifest if p.startswith("deploy/vps/wheels/")]
    assert wheels == [f"deploy/vps/wheels/maxpane-{version}-py3-none-any.whl"]
    assert "deploy/vps/MANIFEST.sha256" not in manifest
    assert set(manifest) == on_disk | set(MANIFEST_DEPLOY_FILES) | set(wheels), "nothing else is listed"


def test_manifest_hashes_match_the_committed_files():
    """The guard the WP title promises: the unit files, the installer, the probe, the lock and the
    broker sources AGREE with the MANIFEST byte for byte. Any edit to one of them without
    ``scripts/build_wheels.sh --out deploy/vps --manifest-only`` reddens this. The wheel is the one
    entry not on disk in a clean checkout; its hash is bound to the lock below."""
    for path, digest in _manifest().items():
        if path.startswith("deploy/vps/wheels/"):
            continue
        assert _sha256(REPO / path) == digest, f"{path} changed since the MANIFEST was generated"


def test_manifest_wheel_hash_equals_the_lock_hash():
    """Deviation #6: the fork wheel is in the lock (so ``--require-hashes`` can install it) and in the
    MANIFEST (so ``sha256sum -c`` covers it); both were written by one run of build_wheels.sh and must
    carry the same sha256. Mutation: rebuild the lock alone -> red."""
    manifest = _manifest()
    wheel_hash = next(digest for path, digest in manifest.items() if path.startswith("deploy/vps/wheels/"))
    version, hashes = _lock_requirements(LOCK.read_text(encoding="utf-8"))["maxpane"]
    assert hashes == [f"--hash=sha256:{wheel_hash}"]
    assert version == _project()["project"]["version"]


def test_verify_md_explains_the_check_and_what_it_does_not_prove():
    """Contract §C.18: VERIFY.md = how to check the MANIFEST and what the checksum does not prove
    (transfer integrity, not authorship -- the same limit as the daemon's unsigned SHA256SUMS)."""
    text = VERIFY_MD.read_text(encoding="utf-8")
    for needle in ("sha256sum -c", "--require-hashes", "--manifest-only", "does not prove", "unsigned",
                   "authorship", "deploy/vps/wheels/", "/opt/imd-dash/MANIFEST.sha256", "probe_seat_host.sh"):
        assert needle in text, needle


# --- Task 9.7: docs/seat_status_schema_v2.md -------------------------------------------------------------------

from maxpane_dashboard.data.seat_models import PRODUCER, SCHEMA_VERSION, SOURCE_NAMES, empty_document  # noqa: E402

SCHEMA_DOC = REPO / "docs" / "seat_status_schema_v2.md"
#: fill4 §3: the 13 top-level keys of the aidude mode-B writer's v1 document (`jq keys`).
V1_TOP_LEVEL = ("schemaVersion", "generatedAtUtc", "seat", "daemon", "host", "container", "fleet", "current",
                "tasks", "reputation", "cost", "standing", "sources")
#: Spec §10: the one sentence allowed to carry a ``$`` in the seat docs (Task 9.9's guard).
NO_CURRENCY_SENTENCE = "no `$` figure in any panel, document field or code path"


def test_schema_doc_maps_every_v1_key_and_names_every_v2_block():
    """Spec §7 'Versioning vs aidude schema v1': v2 is a new contract, and the mapping table is what
    The Lineup and the aidude writer adopt. Every v2 top-level block (derived from
    ``empty_document``), every source name, every v1 top-level key (as the first cell of a mapping
    row), the three refusal codes and the no-currency sentence are in the document. Mutation: drop
    the ``reputation`` row -> red; rename a source -> red."""
    text = SCHEMA_DOC.read_text(encoding="utf-8")
    assert f"`schemaVersion: {SCHEMA_VERSION}`" in text and f"`{PRODUCER}`" in text
    doc = empty_document(started_at_utc="2026-09-26T00:00:00Z",
                         host={"kind": "systemd", "unit": WORKER_UNIT, "container": None, "runtime": "codex", "hostname": "ubuntu"})
    for block in doc:
        assert f"`{block}`" in text, f"v2 block {block} is not described"
    for name in SOURCE_NAMES:
        assert f"`{name}`" in text, f"source {name} is not described"
    for key in V1_TOP_LEVEL:
        assert re.search(rf"^\| `{re.escape(key)}[`.\[]", text, re.M), f"no mapping row starts with v1 `{key}`"
    for code in ("wrong_schema", "with_secret", "too_large", "not_an_object"):
        assert f"`{code}`" in text, code
    assert NO_CURRENCY_SENTENCE in text


# --- Task 9.8: docs/seat_install.md + deploy/mac/README.md + the pepepane.toml keys --------------------------------

from maxpane_dashboard.seat_cli import DEFAULT_CONFIG, ENV, HOSTS  # noqa: E402

INSTALL_DOC = REPO / "docs" / "seat_install.md"
MAC_README = REPO / "deploy" / "mac" / "README.md"


def test_install_sh_writes_pepepane_toml_with_seat_cli_env_keys():
    """Spec §12.1 'Runtime configuration for the TUI': install.sh writes /home/imd-dash/.config/pepepane.toml
    with exactly the keys seat_cli reads (CLI > PEPEPANE_* env > file > config.get_seat() > defaults),
    host=systemd, the worker unit, the broker's SOCKET_PATH, seat and agent -- configuration, never a
    secret. Mutation: write ``token = 7`` instead of ``seat = 7`` -> red; write the broker path with a
    typo -> red."""
    proc = _run_bash(str(INSTALL_SH), "--dry-run", "--seat", "7", "--agent", "51075")
    assert proc.returncode == 0, proc.stderr
    rendered = [ln[6:] for ln in proc.stdout.splitlines() if ln.startswith("    | ")]
    cfg = tomllib.loads("\n".join(rendered) + "\n")["pepepane"]
    assert set(cfg) == {"host", "unit", "broker", "seat", "agent"}
    assert set(cfg) <= set(ENV), f"every key written is one seat_cli reads: {set(cfg) - set(ENV)}"
    assert cfg["host"] == "systemd" and cfg["host"] in HOSTS
    assert cfg["unit"] == WORKER_UNIT
    assert cfg["broker"] == SOCKET_PATH
    assert cfg["seat"] == 7 and cfg["agent"] == 51075
    assert DEFAULT_CONFIG.name == "pepepane.toml" and DEFAULT_CONFIG.parent.name == ".config"
    assert f"/home/{DASH_USER}/.config/pepepane.toml" in proc.stdout
    for line in rendered:
        assert "sk-" not in line and "eyJ" not in line, "never a secret"


def test_seat_install_doc_names_the_sequence_the_child_env_and_the_broker_version():
    """Spec §12.1: the runbook the owner follows names the build, the staging tarball, the dry run, the
    eight steps (a table row per step), the owner-step flag (`--worker-dropin` at an idle gap) and the `--route b` fallback to the decided route a, the probe, the daily ssh path, the
    verbatim child environment (§4.1a), the budgets and the broker version ``ping`` returns."""
    text = INSTALL_DOC.read_text(encoding="utf-8")
    for needle in ("scripts/build_wheels.sh --out deploy/vps", "seat-deploy-", "install.sh --dry-run", "--authorized-keys",
                   "--worker-dropin", "--route b", "probe_seat_host.sh", "--require-hashes", "/usr/local/bin/pepepane",
                   f"ssh -t {DASH_USER}@", "pepepane --once --offline", "docs/seat_install_probe.md", "deploy/vps/VERIFY.md",
                   VERSION, "MemoryMax=256M", "MemoryMax=128M", "MemoryMax=512M", "systemd-journal", "sockets.target",
                   "Restart=always", "boot: disabled"):
        assert needle in text, needle
    for n in range(1, 9):
        assert re.search(rf"^\| {n} \| ", text, re.M), f"no table row for step {n}"
    for key, value in CHILD_ENV.items():
        assert f"`{key}={value}`" in text, f"the child env line {key}={value} is quoted"


def test_mac_readme_matches_the_parity_design():
    """Spec §12.2 / §4.2: the Mac runs the same entrypoint with an in-process LocalDockerBroker, into
    .venv-seat from the pepepane checkout; every CLI-fed value is container-reported; --force stays
    off in v1 even after the §16 #8 recreate (enabling it is follow-up item 13); nothing new is
    mounted; the aidude launchd jobs keep running."""
    text = MAC_README.read_text(encoding="utf-8")
    for needle in ("--host docker --container imd-worker", ".venv-seat", "uv pip install", "'.[seat]'", "pepepane",
                   "LocalDockerBroker", "seat_audit.jsonl", "--stop-timeout 45 --init", "(container)", "--once",
                   "--offline", "timeout=25", "timeout -s TERM", "--host fixture", "worker-page", "worker-notify",
                   "imd-npm", "#18"):
        assert needle in text, needle
    assert "docker.sock" not in text, "nothing mounts the Docker socket"


# --- Task 9.9: follow-ups, the spec/plan copies, the banners, the no-currency doc guard -----------------------------

FOLLOWUPS = REPO / "docs" / "seat_followups.md"
LOCAL_PRD = REPO / "docs" / "pepepane_PRD.md"
LOCAL_PLAN = REPO / "docs" / "pepepane_plan.md"
BANNER_PREFIX = "> **Overridden by `pepepane` (2026-09-26).**"
#: Spec §15: the untracked lineage docs get a dated banner as line 1 and nothing else changes.
OLD_DOCS = {
    "docs/seat_PRD.md": "# SEAT — a dashboard for the IdentityMD worker running on this machine",
    "docs/seat_implementation_plan.md": "# SEAT — implementation plan",
}
#: Deviation #4: the documents this WP writes; the verbatim spec/plan copies are exempt by name.
NO_CURRENCY_DOCS = (
    "docs/seat_status_schema_v2.md", "docs/seat_install.md", "docs/seat_install_probe.md",
    "docs/seat_followups.md", "deploy/mac/README.md", "deploy/vps/VERIFY.md",
)
DOLLAR_FIGURE = re.compile(r"\$\s?\d")
FOLLOWUP_MUST_MENTION = (
    "listPriceUsdEstimate", "cost-state", "docs/imd-api-changelog.md", "§3", "mode-B writer", "message.id", "AgentMessage",
    "dev asks", "do not send", "imd pause", "imd status --json", "signed releases", "§16 #7", "§16 #9", "§16 #12",
    "§16 #17", "§16 #18", "seat_install_probe.md", "uv.lock", "compileall", "tier set", "capacity set", "promotion",
    "thread_turns", "ssh-keygen -Y sign", "seat_PRD.md", "requirements.lock", "MANIFEST.sha256", "six-surface",
)


def _prose_and_code(text: str) -> tuple[list[str], list[str]]:
    """Split a Markdown document into prose lines and fenced-code lines (``` or ~~~ fences)."""
    prose: list[str] = []
    code: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if fence is None and (stripped.startswith("```") or stripped.startswith("~~~")):
            fence = stripped[:3]
            continue
        if fence is not None and stripped.startswith(fence):
            fence = None
            continue
        (code if fence is not None else prose).append(line)
    assert fence is None, "unterminated code fence"
    return prose, code


def test_no_dollar_sign_in_docs_seat_files_except_the_no_currency_rule_sentence():
    """Spec §10 no-currency rule, applied to the fork's own documents: in prose a ``$`` may appear only
    on the line that states the rule (exactly one ``$``); inside fenced shell blocks ``$(``, ``${`` and
    ``$var`` are shell, but a ``$`` followed by a digit is a dollar figure and fails. Mutation: write
    'costs $0.07 per doctor run' into docs/seat_install.md -> red; put ``"price": "$1"`` in a JSON
    example -> red."""
    for rel in NO_CURRENCY_DOCS:
        prose, code = _prose_and_code((REPO / rel).read_text(encoding="utf-8"))
        for line in prose:
            if "$" in line:
                assert NO_CURRENCY_SENTENCE in line and line.count("$") == 1, f"{rel}: {line!r}"
        for line in code:
            assert not DOLLAR_FIGURE.search(line), f"{rel}: a dollar figure inside a code block: {line!r}"


def test_followups_carry_every_parked_item():
    """Spec §10, §6 rule 6, §17, §16, §18, §15: everything this fork parks is written down in one place
    (CLAUDE.md 'Follow-ups': file it, do it as Tier 0 when its file is next touched)."""
    text = FOLLOWUPS.read_text(encoding="utf-8")
    for needle in FOLLOWUP_MUST_MENTION:
        assert needle in text, needle
    assert text.count(NO_CURRENCY_SENTENCE) == 1


def test_pepepane_prd_and_plan_are_the_spec_and_the_plan_with_an_adaptation_header():
    """Spec §15: docs/pepepane_PRD.md is 'this spec, adapted' -- the spec verbatim under a header that
    names the contract decisions superseding its spellings; docs/pepepane_plan.md is the companion
    plan. Mutation: drop the ExecStart correction from the header -> red; copy only §1-§8 -> red."""
    prd = LOCAL_PRD.read_text(encoding="utf-8")
    assert prd.startswith("# PEPEPANE — local dashboard and control panel for an IdentityMD worker (pepepane PRD)")
    assert "> **Adapted copy (2026-09-26).**" in prd
    header = prd.partition("\n---\n\n")[0]
    assert f"ExecStart={BROKER_PYTHON} -I {DEPLOY_BROKER_DIR}/imd_dashd.py" in header
    assert "specific `sk-ant-` before generic `sk-`" in header
    assert "plain yellow `pending`" in header and "never infer a suffix" in header
    assert "# PEPEPANE — a local dashboard and control panel for an IdentityMD worker (MaxPane fork) — design spec" in prd
    for heading in ("## 11. Control panel", "## 12. Privilege and installation", "## 14. Testing strategy",
                    "## 16. Owner decisions required", "## Appendix B"):
        assert heading in prd, heading
    assert len(prd) > 150_000, "the whole spec, not an excerpt"
    plan = LOCAL_PLAN.read_text(encoding="utf-8")
    assert plan.startswith("# PEPEPANE dashboard (MaxPane fork) Implementation Plan — pepepane copy")
    for marker in ("## Global Constraints", "## WP9: Deploy, install, probe, docs", "### Task 9.1", "## F. Mutation proofs"):
        assert marker in plan, marker


def test_old_seat_docs_carry_the_overridden_banner_and_nothing_else_changed():
    """Spec §15: 'a dated overridden-by-pepepane banner, not edits' -- line 1 is the banner, line 2
    blank, line 3 the original heading. Skips when the untracked files are absent (deviation #3)."""
    for rel, heading in OLD_DOCS.items():
        path = REPO / rel
        if not path.exists():
            pytest.skip(f"{rel} is untracked upstream and absent in this checkout")
        lines = path.read_text(encoding="utf-8").splitlines()
        assert lines[0].startswith(BANNER_PREFIX), rel
        assert "docs/pepepane_PRD.md" in lines[0] and "docs/pepepane_plan.md" in lines[0]
        assert lines[1] == "" and lines[2] == heading, f"{rel}: the original heading follows the banner unchanged"


DOCUMENT_BODY_HASHES = {'docs/pepepane_PRD.md': 'b4015c901f0f3671e577aa3afa161bd9cc131940dbea46c653774c381fca4a6b', 'docs/pepepane_plan.md': '5af1cfde16d6a12328592a0aa492878f591e9f15d0c04dd09b801bec2fd37e8b', 'docs/seat_PRD.md': 'ee4384d2ea486992af9e8e94a920444d9e6c648df63fbbf3ae0bb307f3cdd511', 'docs/seat_implementation_plan.md': '2a62dfe5ebd99d2cbe0b96ebd8f808a856a446a67ed9c22038b12443ff5e2689'}

def test_historical_document_bodies_remain_byte_identical():
    for rel, expected in DOCUMENT_BODY_HASHES.items():
        raw = (REPO / rel).read_bytes()
        body = raw.partition(b"\n---\n\n")[2] if "pepepane_" in rel else raw.split(b"\n\n", 1)[1]
        assert hashlib.sha256(body).hexdigest() == expected, rel


# --- Task 9.10: CHANGELOG.md + docs/decisions.md ----------------------------------------------------------------

CHANGELOG = REPO / "CHANGELOG.md"
DECISIONS = REPO / "docs" / "decisions.md"
CHANGELOG_HEADING = "## pepepane (unreleased) — 2026-09-26"
#: One distinctive prefix per WP9 bullet in docs/decisions.md (each exactly once, after the pepepane anchor).
WP9_DECISION_PHRASES = (
    "**2026-09-26 (WP9)** — `deploy/vps/MANIFEST.sha256` lists repo-relative paths",
    "**2026-09-26 (WP9)** — The fork wheel enters `requirements.lock`",
    "**2026-09-26 (WP9)** — `install.sh` installs the worker drop-in only with `--worker-dropin`",
    "**2026-09-26 (WP9)** — `probe_seat_host.sh` issues `plan restart` and never `apply`",
    "**2026-09-26 (WP9)** — The no-currency guard over the seat docs",
    "**2026-09-26 (WP9)** — `docs/seat_PRD.md` and `docs/seat_implementation_plan.md`",
    "**2026-09-26 (WP9)** — The deploy guard restates `/opt/imd-dash/broker/imd_dashd`",
    "**2026-09-26 (WP9)** — `CHANGELOG.md` gains its `## pepepane (unreleased) — 2026-09-26` section at the end",
)


def test_changelog_and_decisions_have_the_dated_entries():
    """Contract §A.3 / spec §15 'Shared surfaces': one dated pepepane changelog section, appended
    after the release history (deviation #2), naming what the branch adds; and the WP9 decisions in
    docs/decisions.md, each once, inside the pepepane block. Mutation: delete a bullet -> red; move
    the changelog section above ## v0.9.3 -> red."""
    changelog = CHANGELOG.read_text(encoding="utf-8")
    assert changelog.count(CHANGELOG_HEADING) == 1
    release_headings = [m.start() for m in re.finditer(r"^## v\d", changelog, re.M)]
    assert release_headings, "the upstream release history is still there"
    assert changelog.index(CHANGELOG_HEADING) > max(release_headings), "appended after the release history"
    section = changelog[changelog.index(CHANGELOG_HEADING):]
    for needle in ("pepepane", "PEPEPANE", "imd_dashd", "deploy/vps/", "docs/seat_status_schema_v2.md", "docs/seat_followups.md",
                   "textual 8.2.8", "read-only", "tokens, never dollars", "plan → apply → verify"):
        assert needle in section, needle
    decisions = DECISIONS.read_text(encoding="utf-8")
    anchor = decisions.index("**2026-09-26 (pepepane)**")
    for phrase in WP9_DECISION_PHRASES:
        assert decisions.count(phrase) == 1, f"missing or duplicated decision: {phrase}"
        assert decisions.index(phrase) > anchor, f"decision outside the pepepane block: {phrase}"


@pytest.mark.parametrize("latest", ["heartbeat", "terminal", "older-heartbeat"])
def test_lifecycle_probe_uses_the_installed_broker_argv_and_records_no_match(monkeypatch, capsys, latest):
    from imd_dashd.imd_dashd import lifecycle_journal_argv
    text = PROBE_SH.read_text()
    body = text.split("# BEGIN LIFECYCLE_PROBE\n", 1)[1].split("# END LIFECYCLE_PROBE", 1)[0]
    assert 'sys.path.insert(0, "/opt/imd-dash/broker")' in body
    assert "from imd_dashd.imd_dashd import lifecycle_journal_argv" in body
    assert "ACCEPTED_RE.pattern" not in body and "TERMINAL_RE.pattern" not in body
    older = "2026-09-27T10:00:00.000Z accepted question deadbeef"
    terminal = "2026-09-27T10:01:00.000Z question failed: executor threw"
    heartbeat = "2026-09-27T10:02:00.000Z alive 2m · idle · 0 submitted"
    baseline_rows = [older, terminal, heartbeat]
    if latest == "terminal": baseline_rows = [older, terminal]
    if latest == "older-heartbeat": baseline_rows[-1] = heartbeat.replace("10:02", "10:00")
    records = lambda messages: "\n".join(json.dumps({"MESSAGE": message, "_HOSTNAME": "private-host", "_CMDLINE": "private-argv", "__CURSOR": "private-cursor"}) for message in messages)
    calls = []
    def fake(argv, **kwargs):
        calls.append(argv)
        assert kwargs["timeout"] == 12
        if "--grep" not in argv:
            return subprocess.CompletedProcess(argv, 0, records(baseline_rows), "")
        if argv[argv.index("--grep") + 1] == "(?!)":
            return subprocess.CompletedProcess(argv, 1, "", "")
        assert argv == lifecycle_journal_argv()
        return subprocess.CompletedProcess(argv, 0, records([terminal]), "")
    monkeypatch.setattr(subprocess, "run", fake)
    exec(compile(body, "<synthetic lifecycle probe>", "exec"), {})
    output = capsys.readouterr().out
    if latest == "heartbeat":
        assert "filter-before-limit: PASS" in output
    else:
        assert "filter-before-limit: inconclusive (newest entry is not a heartbeat)" in output
        assert "filter-before-limit: PASS" not in output
    assert "newest entry heartbeat: " + str(latest != "terminal") in output
    assert "grep/pcre2: PASS" in output
    assert "no-match exit status: 1" in output
    assert "no-match acceptance: PASS" in output and "no-match stderr:" in output
    assert calls[0] == lifecycle_journal_argv()[:lifecycle_journal_argv().index("--grep")] + ["--lines", "10000"]
    assert len(calls) == 3
    assert "private-host" not in output and "private-argv" not in output and "private-cursor" not in output

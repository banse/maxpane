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

"""Interpreter preflight, exercised without root or any host mutation."""
from pathlib import Path
import os
import re
import subprocess

import pytest

INSTALL = Path(__file__).resolve().parents[1] / "deploy/vps/install.sh"


def _function(name):
    found = re.search(r"^" + name + r"\(\).*?^\}", INSTALL.read_text(), re.M | re.S)
    assert found, name
    return found.group()


def _versions(tmp_path, *, absolute="3.12", path="3.12", venv=None, dry=False, seam=""):
    root = tmp_path / "venv"
    if venv is not None:
        (root / "bin").mkdir(parents=True)
        python = root / "bin/python"
        python.write_text("#!/bin/sh\nexit 99\n")
        python.chmod(0o755)
    script = '''
SUPPORTED_PYTHONS=(3.12 3.14)
die() { printf '%s\\n' "$*" >&2; exit 1; }
warn() { printf '%s\\n' "$*" >&2; }
python_minor() {
  case "$1" in /usr/bin/python3) printf '%s' "$ABS_VERSION" ;;
    python3) printf '%s' "$PATH_VERSION" ;;
    *) printf '%s' "$VENV_VERSION" ;; esac
}
'''
    script += _function("check_python_versions") + '\ncheck_python_versions\nprintf "%s\\n" "$VENV_PACKAGE"'
    env = {**os.environ, "VENV": str(root), "DRY_RUN": str(int(dry)), "DRY_RUN_PYTHON_VERSION": seam,
           "ABS_VERSION": absolute, "PATH_VERSION": path, "VENV_VERSION": venv or ""}
    return subprocess.run(["/bin/bash", "-c", script], env=env, text=True, capture_output=True, timeout=5)


@pytest.mark.parametrize("version", ["3.12", "3.14"])
def test_installer_accepts_matching_supported_interpreters(tmp_path, version):
    done = _versions(tmp_path, absolute=version, path=version, venv=version)
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == f"python{version}-venv"


@pytest.mark.parametrize("changes, message", [({"absolute": "3.13"}, "supported"),
    ({"path": "3.14"}, "PATH"), ({"venv": "3.14"}, "venv")])
def test_real_preflight_refuses_unsupported_or_mismatched_python(tmp_path, changes, message):
    done = _versions(tmp_path, **changes)
    assert done.returncode != 0
    assert message in done.stderr


def test_native_unsupported_dry_run_warns_and_prints_placeholder(tmp_path):
    done = _versions(tmp_path, absolute="3.9", dry=True)
    assert done.returncode == 0, done.stderr
    assert "3.9" in done.stderr and "3.12" in done.stderr and "3.14" in done.stderr
    assert done.stdout.strip() == "python3.<minor>-venv"


def test_dry_run_seam_uses_remote_version_but_is_refused_for_real_runs(tmp_path):
    done = _versions(tmp_path, absolute="3.9", dry=True, seam="3.14")
    assert done.returncode == 0, done.stderr
    assert done.stdout.strip() == "python3.14-venv"
    done = subprocess.run(["/bin/bash", str(INSTALL), "--dry-run-python-version", "3.12"],
                          text=True, capture_output=True, timeout=5)
    assert done.returncode != 0
    assert "requires --dry-run" in done.stderr


@pytest.mark.parametrize("present", [False, True])
def test_preflight_checks_host_abi_before_installing(tmp_path, present):
    (tmp_path / "wheels").mkdir()
    if present:
        (tmp_path / "wheels/pydantic_core-2.46.5-cp312-cp312-manylinux_2_17_x86_64.whl").write_bytes(b"fixture")
    script = 'die() { printf "%s\\n" "$*" >&2; exit 1; }; warn() { :; }; DRY_RUN=0; PY_VERSION=3.12\n'
    script += _function("check_staged_abi") + '\nHERE="$1"; check_staged_abi'
    done = subprocess.run(["/bin/bash", "-c", script, "bash", str(tmp_path)], text=True, capture_output=True, timeout=5)
    assert (done.returncode == 0) is present
    if not present:
        assert "cp312" in done.stderr and "re-stage" in done.stderr


def test_apt_is_noninteractive_and_suspends_needrestart():
    text = INSTALL.read_text()
    assert 'NEEDRESTART_SUSPEND=1 DEBIAN_FRONTEND=noninteractive run apt-get install -y --no-install-recommends "$VENV_PACKAGE"' in text
    assert 'dpkg -s "$VENV_PACKAGE"' in text

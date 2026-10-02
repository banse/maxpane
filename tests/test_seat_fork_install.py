"""Offline installer regressions: synthetic wheels and extracted read-only shell helpers."""
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import re
import subprocess
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy/vps"


def _render(lock):
    text = (DEPLOY / "install.sh").read_text()
    match = re.search(r"^render_fork_lock\(\).*?^\}", text, re.M | re.S)
    assert match, "installer must validate the fork-only requirement"
    return subprocess.run(["bash", "-c", match.group() + '\nrender_fork_lock "$1"', "bash", str(lock)],
                          text=True, capture_output=True, timeout=5)


@pytest.mark.parametrize("body", ["", "# comment only\n", "maxpane==0.9.3\n",
    "maxpane==0.9.3 --hash=sha256:" + "a" * 64 + "\nmaxpane==0.9.3 --hash=sha256:" + "b" * 64,
    "maxpane==0.9.3 --hash=sha256:abc", "other==1 --hash=sha256:" + "a" * 64])
def test_fork_cut_refuses_empty_multiple_or_unhashed_entries(tmp_path, body):
    lock = tmp_path / "requirements.lock"
    lock.write_text("# pepepane fork wheel, built by scripts/build_wheels.sh\n" + body)
    assert _render(lock).returncode != 0


def test_fork_cut_requires_marker_and_preserves_exact_hash(tmp_path):
    lock = tmp_path / "requirements.lock"
    entry = "maxpane==0.9.3 --hash=sha256:" + "a" * 64
    lock.write_text(entry)
    assert _render(lock).returncode != 0
    lock.write_text("other==1\n# pepepane fork wheel, built by scripts/build_wheels.sh\n" + entry)
    done = _render(lock)
    assert done.returncode == 0
    assert done.stdout.replace("\\", "").split() == entry.split()


def test_dry_run_reinstalls_fork_before_full_lock_and_checks_installed_bytes():
    done = subprocess.run(["bash", str(DEPLOY / "install.sh"), "--dry-run"],
                          text=True, capture_output=True, timeout=10)
    assert done.returncode == 0, done.stderr
    lines = done.stdout.splitlines()
    forced = next(i for i, line in enumerate(lines) if "[dry-run]" in line and "--force-reinstall --no-deps" in line)
    full = next(i for i, line in enumerate(lines) if "[dry-run]" in line and "--require-hashes -r /opt/imd-dash/requirements.lock" in line)
    assert forced < full
    assert "--require-hashes" in lines[forced] and " -r " in lines[forced]
    assert any("maxpane==0.9.3" in line and not line.startswith("    > ") for line in lines)
    assert "--hash=sha256:" in done.stdout
    check = next(i for i, line in enumerate(lines) if "[dry-run]" in line and " -I " in line and "check_fork_wheel.py" in line)
    assert full < check
    assert not any("mktemp" in line for line in lines)
    assert 'pgrep -u "$DASH_USER" -f /opt/imd-dash/venv/bin/pepepane' in (DEPLOY / "install.sh").read_text()
    assert '"$PREFIX/venv/bin/python" -I "$HERE/check_fork_wheel.py" "$PREFIX/wheels"' in (DEPLOY / "probe_seat_host.sh").read_text()


def _checker():
    spec = importlib.util.spec_from_file_location("check_fork_wheel", DEPLOY / "check_fork_wheel.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check_fork_wheel


def _wheel(tmp_path, *, empty=False):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    purelib = tmp_path / "purelib"
    purelib.mkdir()
    name = "maxpane_dashboard/checked.py"
    record = "maxpane-0.9.3.dist-info/RECORD"
    data = b"new fork bytes\n"
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).decode().rstrip("=")
    rows = [] if empty else [(name, "sha256=" + digest, str(len(data)))]
    rows.append((record, "", ""))
    csv_text = io.StringIO()
    csv.writer(csv_text).writerows(rows)
    wheel = wheels / "maxpane-0.9.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(name, data)
        archive.writestr(record, csv_text.getvalue())
    installed = purelib / name
    installed.parent.mkdir()
    installed.write_bytes(data)
    # A copied RECORD must not make corrupted installed bytes pass.
    (purelib / record).parent.mkdir()
    (purelib / record).write_text(csv_text.getvalue())
    return wheels, purelib, installed


@pytest.mark.parametrize("fault", ["mismatch", "missing", "empty"])
def test_post_install_check_hashes_installed_bytes_and_fails_closed(tmp_path, fault):
    wheels, purelib, installed = _wheel(tmp_path, empty=fault == "empty")
    if fault == "mismatch":
        installed.write_bytes(b"old fork bytes")
    elif fault == "missing":
        installed.unlink()
    check = _checker()
    with pytest.raises((ValueError, OSError)):
        check(wheels, purelib)


def test_post_install_check_reports_count_and_short_wheel_identity(tmp_path):
    wheels, purelib, _ = _wheel(tmp_path)
    (purelib / "unrelated.pyc").write_bytes(b"pip-generated files do not matter")
    result = _checker()(wheels, purelib)
    assert "1" in result and "matched" in result
    prefix = hashlib.sha256(next(wheels.glob("*.whl")).read_bytes()).hexdigest()[:10]
    assert prefix in result and not re.search(r"[a-f0-9]{32,}", result)

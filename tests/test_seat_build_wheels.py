"""Exercise the real build shell with offline resolver and download stand-ins."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

import pytest

REPO = Path(__file__).resolve().parents[1]


def _build(tmp_path, *, drift=False, upgrade=False, custom_out=False, diverge=False, missing_abi=False, bad_hash=False):
    repo = tmp_path / "checkout"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    shutil.copyfile(REPO / "scripts/build_wheels.sh", scripts / "build_wheels.sh")
    (repo / "pyproject.toml").write_text('[project]\nversion = "0.9.3"\n')
    broker = repo / "imd_dashd"
    broker.mkdir()
    (broker / "__init__.py").write_text("# synthetic broker\n")
    deploy = repo / "deploy/vps"
    deploy.mkdir(parents=True)
    original = (REPO / "deploy/vps/requirements.lock").read_text()
    hashes = "".join("    --hash=sha256:" + hashlib.sha256(("synthetic " + abi).encode()).hexdigest() + " \\\n" for abi in ("cp312", "cp314"))
    original = original.replace("pydantic-core==2.46.5 \\\n", "pydantic-core==2.46.5 \\\n" + hashes)
    (deploy / "requirements.lock").write_text(original)
    out = repo / "other-output" if custom_out else deploy
    out.mkdir(exist_ok=True)
    if custom_out:
        (out / "requirements.lock").write_text("wrong-output-seed==1\n")
    for name in ("imd-dashd.socket", "imd-dashd.service", "20-hide-dash.conf",
                 "50-pepepane.conf", "10-imd-dash.sshd.conf", "install.sh", "probe_seat_host.sh", "check_fork_wheel.py"):
        (out / name).write_text("# synthetic deployment file\n")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    uv = bindir / "uv"
    uv.write_text(f"#!{sys.executable}\n" + '''
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
if args[:2] == ["pip", "compile"]:
    output = Path(args[args.index("-o") + 1])
    seed = output.read_text() if output.exists() else ""
    with open(os.environ["COMPILE_LOG"], "a") as log:
        log.write(json.dumps({"seed": seed, "cwd": os.getcwd(), "args": args}) + "\\n")
    text = Path(os.environ["REFERENCE_LOCK"]).read_text().split("# pepepane fork wheel", 1)[0]
    if os.environ["DRIFT"] == "1" or (os.environ["DIVERGE"] == "1" and args[args.index("--python-version") + 1] == "3.12"):
        text = text.replace("platformdirs==4.12.1", "platformdirs==4.12.2")
    output.write_text(text.rstrip() + "\\n")
elif args[0] == "build":
    dest = Path(args[args.index("--out-dir") + 1])
    (dest / "maxpane-0.9.3-py3-none-any.whl").write_bytes(b"synthetic wheel")
else:
    raise AssertionError(args)
''')
    uv.chmod(0o755)
    python = bindir / "build-python"
    python.write_text(f"#!{sys.executable}\n" + '''
import os, sys
from pathlib import Path
if sys.argv[1:4] == ["-m", "pip", "download"]:
    args = sys.argv[1:]
    abi = args[args.index("--abi") + 1]
    with open(os.environ["DOWNLOAD_LOG"], "a") as log:
        log.write(abi + "\\n")
    dest = Path(args[args.index("-d") + 1])
    if not (os.environ["MISSING_ABI"] == "1" and abi == "cp312"):
        (dest / ("pydantic_core-2.46.5-" + abi + "-" + abi + "-manylinux_2_17_x86_64.whl")).write_bytes(("synthetic " + abi).encode())
    if os.environ["BAD_HASH"] == "1":
        (dest / "unlocked-1-py3-none-any.whl").write_bytes(b"not in lock")
else:
    os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
''')
    python.chmod(0o755)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    temp = tmp_path / "temp"
    temp.mkdir()
    env = {**os.environ, "PATH": f"{bindir}:/usr/bin:/bin", "PYTHON": str(python),
           "TMPDIR": str(temp), "COMPILE_LOG": str(tmp_path / "compile.json"),
           "DOWNLOAD_LOG": str(tmp_path / "download.txt"),
           "REFERENCE_LOCK": str(deploy / "requirements.lock"), "DRIFT": str(int(drift)),
           "DIVERGE": str(int(diverge)), "MISSING_ABI": str(int(missing_abi)), "BAD_HASH": str(int(bad_hash))}
    args = ["bash", str(scripts / "build_wheels.sh"), "--out", str(out)]
    if upgrade:
        args.append("--upgrade")
    result = subprocess.run(args, cwd=elsewhere, env=env, capture_output=True, text=True, timeout=20)
    return result, repo, out, original


@pytest.mark.parametrize("custom_out", [False, True])
def test_build_refuses_resolver_version_drift_before_downloading(tmp_path, custom_out):
    result, repo, _, original = _build(tmp_path, drift=True, custom_out=custom_out)
    assert result.returncode != 0, result.stdout
    assert "third-party versions changed" in result.stderr
    assert not (tmp_path / "download.txt").exists()
    _assert_compiles(tmp_path, repo, original)


def test_build_seeds_the_canonical_lock_and_keeps_versions(tmp_path):
    result, repo, out, original = _build(tmp_path)
    assert result.returncode == 0, result.stderr
    _assert_compiles(tmp_path, repo, original)
    assert (tmp_path / "download.txt").read_text().splitlines() == ["cp312", "cp314"]
    assert (out / "requirements.lock").read_text().split("# pepepane fork wheel", 1)[0] == original.split("# pepepane fork wheel", 1)[0]


def test_explicit_upgrade_skips_seed_and_version_check(tmp_path):
    result, repo, out, _ = _build(tmp_path, drift=True, upgrade=True)
    assert result.returncode == 0, result.stderr
    _assert_compiles(tmp_path, repo, "")
    assert "platformdirs==4.12.2" in (out / "requirements.lock").read_text()
    assert (tmp_path / "download.txt").exists()


def test_deploy_archive_uses_neutral_owner_headers(tmp_path):
    result, repo, _, _ = _build(tmp_path)
    assert result.returncode == 0, result.stderr
    with tarfile.open(next((repo / "dist").glob("seat-deploy-*.tar.gz"))) as archive:
        entries = archive.getmembers()
    assert entries
    assert all(item.uid == item.gid == 0 for item in entries)
    assert all(item.uname in ("", "root") and item.gname in ("", "root") for item in entries)


def _assert_compiles(tmp_path, repo, original):
    calls = [json.loads(line) for line in (tmp_path / "compile.json").read_text().splitlines()]
    assert [call["args"][call["args"].index("--python-version") + 1] for call in calls] == ["3.12", "3.14"]
    assert len({call["args"][call["args"].index("-o") + 1] for call in calls}) == 2
    for call in calls:
        assert call["seed"] == original.split("# pepepane fork wheel", 1)[0]
        assert call["cwd"] == str(repo)
        assert "-c" not in call["args"]
        assert not Path(call["args"][call["args"].index("-o") + 1]).exists()


@pytest.mark.parametrize("upgrade", [False, True])
def test_build_refuses_different_interpreter_closures(tmp_path, upgrade):
    result, _, _, _ = _build(tmp_path, diverge=True, upgrade=upgrade)
    assert result.returncode != 0
    assert "interpreter closures differ" in result.stderr
    assert "third-party versions changed" not in result.stderr
    assert not (tmp_path / "download.txt").exists()


@pytest.mark.parametrize("failure, message", [("missing_abi", "cp312"), ("bad_hash", "wheel hash absent from lock")])
def test_archive_guard_refuses_missing_abi_or_unlocked_wheel(tmp_path, failure, message):
    result, repo, _, _ = _build(tmp_path, **{failure: True})
    assert result.returncode != 0
    assert message in result.stderr
    assert not list((repo / "dist").glob("*.tar.gz"))

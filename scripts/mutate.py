"""Mutation proof: apply a mutant, run the named tests, restore the file byte for byte.

Usage (from the repo root)::

    .venv/bin/python scripts/mutate.py \\
        --file maxpane_dashboard/widgets/surf/hero.py --old 'if seen:' --new 'if not seen:' \\
        --expect tests/widgets/test_surf_hero.py::test_x -- tests/widgets/test_surf_hero.py -k seen

    .venv/bin/python scripts/mutate.py --mutants mutants.json -- tests/widgets/test_surf_hero.py

``mutants.json`` is a list of ``{"name", "file", "old", "new", "expect": [node ids]}``.
Everything after ``--`` is handed to pytest. Each mutant must match its file exactly once
(``replace(old, new, 1)`` would otherwise hit the first of several identical blocks); the
original bytes stay in memory and are written back in a ``finally`` and on SIGINT/SIGTERM,
then compared. A mutant is

* ``KILLED`` -- the tests went red, and every ``expect`` node id is among the failures;
* ``WRONG TEST`` -- red, but not the test the proof is about (check WHICH test reddened);
* ``SURVIVED`` -- green: the tests cannot see this change;
* ``ERROR`` -- collection or usage error, which is suspect rather than a kill.

The unmutated baseline runs first and must be green. pytest runs with an isolated ``HOME``,
no bytecode and no cache, so a mutant never leaves a ``.pyc`` or a cache file behind.
Exit status 0 only when every mutant is ``KILLED``.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET  # pytest's own JUnit file, written a moment ago
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


@dataclass
class Mutant:
    name: str
    file: Path
    old: str
    new: str
    expect: list[str] = field(default_factory=list)


@dataclass
class Outcome:
    verdict: str
    failed: list[str]
    detail: str = ""


def run_pytest(pytest_args: list[str], python: str, root: Path = REPO) -> tuple[int, list[str]]:
    """Run pytest once; return its exit code and the failing node ids from its JUnit XML."""
    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "junit.xml"
        env = dict(os.environ, HOME=tmp, PYTHONDONTWRITEBYTECODE="1")
        cmd = [python, "-m", "pytest", "-p", "no:cacheprovider", "-q",
               f"--junitxml={xml_path}", *pytest_args]
        proc = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
        failed = _failures(xml_path, root) if xml_path.exists() else []
    return proc.returncode, failed


def _failures(xml_path: Path, root: Path) -> list[str]:
    out = []
    for case in ET.parse(xml_path).getroot().iter("testcase"):
        if case.find("failure") is None and case.find("error") is None:
            continue
        module = case.get("classname", "")
        parts = module.split(".")
        # classname is "tests.widgets.test_x" or "tests.widgets.test_x.TestClass".
        path_parts, cls = parts, None
        while path_parts and not (root / Path(*path_parts)).with_suffix(".py").exists():
            cls = path_parts[-1] if cls is None else f"{path_parts[-1]}::{cls}"
            path_parts = path_parts[:-1]
        path = str(Path(*path_parts).with_suffix(".py")) if path_parts else module
        out.append("::".join(p for p in (path, cls, case.get("name", "")) if p))
    return out


def apply_and_run(m: Mutant, pytest_args: list[str], python: str, root: Path = REPO) -> Outcome:
    path = m.file if m.file.is_absolute() else root / m.file
    orig = path.read_bytes()
    text = orig.decode("utf-8")
    count = text.count(m.old)
    if count != 1:
        return Outcome("ERROR", [], f"`old` occurs {count} times in {m.file}, need exactly 1")

    def restore(*_sig) -> None:
        path.write_bytes(orig)
        if _sig:
            sys.exit(130)

    previous = {s: signal.signal(s, restore) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        path.write_bytes(text.replace(m.old, m.new, 1).encode("utf-8"))
        code, failed = run_pytest(pytest_args, python, root)
    finally:
        restore()
        for s, h in previous.items():
            signal.signal(s, h)
    if path.read_bytes() != orig:
        raise SystemExit(f"RESTORE FAILED for {m.file} -- inspect it now")

    if code == 0:
        return Outcome("SURVIVED", [])
    if code != 1 or not failed:
        return Outcome("ERROR", failed, f"pytest exit {code} (collection or usage error)")
    missing = [e for e in m.expect if e not in failed]
    if missing:
        return Outcome("WRONG TEST", failed, f"expected red but green: {', '.join(missing)}")
    return Outcome("KILLED", failed)


def load_mutants(args: argparse.Namespace) -> list[Mutant]:
    if args.mutants:
        raw = json.loads(Path(args.mutants).read_text(encoding="utf-8"))
        return [Mutant(r.get("name") or f"m{i}", Path(r["file"]), r["old"], r["new"],
                       list(r.get("expect", []))) for i, r in enumerate(raw, 1)]
    if not (args.file and args.old is not None and args.new is not None):
        raise SystemExit("give --mutants FILE, or --file, --old and --new")
    return [Mutant(args.name or "m1", Path(args.file), args.old, args.new, list(args.expect))]


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if "--" not in argv:
        raise SystemExit("pass the pytest selection after `--`")
    split = argv.index("--")
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--mutants")
    parser.add_argument("--file")
    parser.add_argument("--old")
    parser.add_argument("--new")
    parser.add_argument("--name")
    parser.add_argument("--expect", action="append", default=[])
    parser.add_argument("--python", default=str(REPO / ".venv/bin/python"))
    parser.add_argument("--root", default=str(REPO), help="where pytest runs and paths resolve")
    args = parser.parse_args(argv[:split])
    pytest_args = argv[split + 1:]
    mutants = load_mutants(args)
    root = Path(args.root)

    code, failed = run_pytest(pytest_args, args.python, root)
    if code != 0:
        print(f"BASELINE NOT GREEN (pytest exit {code}): {failed or 'see pytest output'}")
        return 2

    results = [(m, apply_and_run(m, pytest_args, args.python, root)) for m in mutants]
    for m, o in results:
        print(f"{o.verdict:<10} {m.name}  ({m.file})")
        for node in o.failed:
            print(f"           red: {node}")
        if o.detail:
            print(f"           {o.detail}")
    return 0 if all(o.verdict == "KILLED" for _, o in results) else 1


if __name__ == "__main__":
    sys.exit(main())

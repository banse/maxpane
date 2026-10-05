"""``scripts/mutate.py`` -- the mutation-proof harness.

Each case builds a two-test project in ``tmp_path`` and runs the real script against it with
this interpreter, so the subprocess pytest, the JUnit parse and the restore are all exercised.
The script is loaded from its path: ``scripts/`` is not a package and nothing imports it.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "mutate.py"


def _load():
    spec = importlib.util.spec_from_file_location("mutate_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve their module through sys.modules
    spec.loader.exec_module(module)
    return module


mutate = _load()

MOD = "def f():\n    return 1  # one\n\n\ndef g():\n    return 2\n"
TESTS = "from mod import f, g\n\n\ndef test_f():\n    assert f() == 1\n\n\ndef test_g():\n    assert g() == 2\n"


def _project(tmp_path: Path) -> Path:
    (tmp_path / "mod.py").write_text(MOD, encoding="utf-8")
    (tmp_path / "test_mod.py").write_text(TESTS, encoding="utf-8")
    return tmp_path


def _run(root: Path, *flags: str) -> int:
    return mutate.main([*flags, "--root", str(root), "--python", sys.executable, "--", "test_mod.py"])


def test_a_killed_mutant_names_the_test_that_reddened_and_the_file_comes_back(tmp_path, capsys):
    root = _project(tmp_path)
    code = _run(root, "--file", "mod.py", "--old", "return 1", "--new", "return 7",
                "--expect", "test_mod.py::test_f")
    out = capsys.readouterr().out
    assert code == 0, out
    assert out.startswith("KILLED"), out
    assert "red: test_mod.py::test_f" in out and "test_g" not in out, out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD


def test_red_on_the_wrong_test_is_not_a_kill(tmp_path, capsys):
    root = _project(tmp_path)
    code = _run(root, "--file", "mod.py", "--old", "return 1", "--new", "return 7",
                "--expect", "test_mod.py::test_g")
    out = capsys.readouterr().out
    assert code == 1 and out.startswith("WRONG TEST"), out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD


def test_a_change_no_test_sees_survives(tmp_path, capsys):
    root = _project(tmp_path)
    code = _run(root, "--file", "mod.py", "--old", "# one", "--new", "# two")
    out = capsys.readouterr().out
    assert code == 1 and out.startswith("SURVIVED"), out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD


def test_an_old_text_that_is_not_unique_is_refused_untouched(tmp_path, capsys):
    root = _project(tmp_path)
    code = _run(root, "--file", "mod.py", "--old", "return", "--new", "raise")
    out = capsys.readouterr().out
    assert code == 1 and out.startswith("ERROR") and "occurs 2 times" in out, out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD


def test_a_mutant_that_breaks_collection_is_an_error_not_a_kill(tmp_path, capsys):
    root = _project(tmp_path)
    code = _run(root, "--file", "mod.py", "--old", "def g():", "--new", "def g(:")
    out = capsys.readouterr().out
    assert code == 1 and out.startswith("ERROR"), out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD


def test_a_red_baseline_stops_before_any_mutant(tmp_path, capsys):
    root = _project(tmp_path)
    (root / "test_mod.py").write_text(TESTS.replace("== 2", "== 3"), encoding="utf-8")
    code = _run(root, "--file", "mod.py", "--old", "return 1", "--new", "return 7")
    out = capsys.readouterr().out
    assert code == 2 and out.startswith("BASELINE NOT GREEN"), out
    assert "test_mod.py::test_g" in out, out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD


def test_a_mutants_file_runs_each_in_turn(tmp_path, capsys):
    root = _project(tmp_path)
    spec = tmp_path / "mutants.json"
    spec.write_text(json.dumps([
        {"name": "f-off", "file": "mod.py", "old": "return 1", "new": "return 0",
         "expect": ["test_mod.py::test_f"]},
        {"name": "g-off", "file": "mod.py", "old": "return 2", "new": "return 0",
         "expect": ["test_mod.py::test_g"]},
    ]), encoding="utf-8")
    code = _run(root, "--mutants", str(spec))
    out = capsys.readouterr().out
    assert code == 0, out
    assert [line.split()[:2] for line in out.splitlines() if not line.startswith(" ")] == [
        ["KILLED", "f-off"], ["KILLED", "g-off"]], out
    assert (root / "mod.py").read_text(encoding="utf-8") == MOD

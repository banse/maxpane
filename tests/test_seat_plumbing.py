"""pepepane plumbing on the shared surfaces (spec §15 "Shared surfaces"; contract §A.3).

Guards over ``pyproject.toml`` and ``tests/conftest.py``: the ``pepepane`` console
script, the ``seat`` optional-dependency group with the measured pins, the opt-in
``host`` marker, the untouched ``dependencies`` block, and the autouse fixture that
deletes ``PEPEPANE_*`` before every test.
"""

from __future__ import annotations

import importlib.metadata
import tomllib
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"

#: Spec §12.1 "Pins" / contract §A.3: the exact versions the PEPEPANE layout was measured on.
SEAT_PINS = {"textual": "8.2.8", "rich": "15.0.0", "httpx": "0.28.1", "pydantic": "2.13.5"}

#: Contract §A.4: the existing block is never edited by the fork.
UPSTREAM_DEPENDENCIES = ["textual>=0.80", "httpx>=0.27", "pydantic>=2.0", "sybilkit>=0.1.0"]

HOST_MARKER = "host: opt-in tests that run journalctl/docker on the real host; never in CI"


def _project() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


@pytest.mark.guard
def test_pyproject_declares_the_pepepane_script():
    """Spec §15 "Lean entrypoint": ``pepepane = maxpane_dashboard.seat_cli:main``."""
    scripts = _project()["project"]["scripts"]
    assert scripts["pepepane"] == "maxpane_dashboard.seat_cli:main"
    assert scripts["maxpane"] == "maxpane_dashboard.__main__:main", "the upstream script is untouched"


@pytest.mark.guard
def test_pyproject_seat_group_pins_the_measured_versions():
    """Spec §12.1 Pins: ``[project.optional-dependencies] seat`` is exactly the four ``==`` pins."""
    group = _project()["project"]["optional-dependencies"]["seat"]
    assert group == [f"{name}=={version}" for name, version in SEAT_PINS.items()]


@pytest.mark.guard
def test_pyproject_leaves_the_upstream_dependencies_block_alone():
    """Contract §A.4: the fork never edits ``dependencies``; the pins live only in the ``seat`` group."""
    assert _project()["project"]["dependencies"] == UPSTREAM_DEPENDENCIES


@pytest.mark.guard
def test_pyproject_registers_the_host_marker():
    """Spec §14 Rules: the journalctl/docker sources run only under an opt-in ``host`` marker."""
    markers = _project()["tool"]["pytest"]["ini_options"]["markers"]
    assert markers[-1] == HOST_MARKER, "appended at the end of the list (append-only surface)"
    assert [m for m in markers if m.startswith("host:")] == [HOST_MARKER]


@pytest.mark.guard
def test_the_repo_venv_carries_the_seat_pins():
    """Spec §15: the surf 545-case sweep is re-run on every Textual bump -- so the venv the
    suite runs in must be the pinned one, or a green layout sweep proves nothing."""
    installed = {name: importlib.metadata.version(name) for name in SEAT_PINS}
    assert installed == SEAT_PINS

"""pepepane plumbing on the shared surfaces (spec §15 "Shared surfaces"; contract §A.3).

Guards over ``pyproject.toml`` and ``tests/conftest.py``: the ``pepepane`` console
script, the ``seat`` optional-dependency group with the measured pins, the opt-in
``host`` marker, the untouched ``dependencies`` block, and the autouse fixture that
deletes ``PEPEPANE_*`` before every test.
"""

from __future__ import annotations

import importlib.metadata
import os
import tomllib
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"
CONFTEST = REPO / "tests" / "conftest.py"

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


def test_pepepane_env_is_deleted_before_every_test(pytester, monkeypatch):
    """Spec §14 Rules / contract §A.3: ``tests/conftest.py`` deletes every ``PEPEPANE_*``
    variable through an autouse fixture. Run the real conftest in an isolated session
    with two variables set; the inner test must see none. Mutation: remove
    ``_no_pepepane_env`` from ``tests/conftest.py`` -> the inner run fails -> red."""
    monkeypatch.setenv("PEPEPANE_HOST", "docker")
    monkeypatch.setenv("PEPEPANE_BROKER", "/run/imd-dash/broker.sock")
    pytester.makeconftest(CONFTEST.read_text(encoding="utf-8"))
    pytester.makepyfile(test_inner="""
        import os

        def test_no_pepepane_variable_reaches_a_test():
            assert [k for k in os.environ if k.startswith("PEPEPANE_")] == []
    """)
    result = pytester.runpytest("-p", "no:cacheprovider", "-q")
    result.assert_outcomes(passed=1)
    # The outer session's variables are untouched: the fixture deletes per test and restores.
    assert os.environ["PEPEPANE_HOST"] == "docker"


DECISIONS = REPO / "docs" / "decisions.md"

#: One distinctive phrase per dated §15 / contract entry WP0 appends (spec §15 "Shared surfaces").
SEAT_DECISION_PHRASES = (
    "**2026-09-26 — PEPEPANE-CTRL**",
    "No six-surface registration for PEPEPANE",
    "`subprocess` and `socket` are allowed in `data/seat_tail.py` and",
    "drained on the poll tick inside `SeatManager.fetch_and_compute()`",
    "docker subprocesses on the Mac exist only as one long-lived `docker logs -f --tail 200",
    "QUOTA moved to COST, WORK merged into LIVE, GATE and TODAY added",
    "textual pinned to 8.2.8",
    "Seat per-day series live in `seat_ledger.sqlite`'s `days` table",
    "Seat CSS lives only in `SeatScreen.DEFAULT_CSS`",
    "run as `systemd-run` transient units",
    "`apply` returns when the command exits; verification is the separate `verify` read verb",
    "No currency anywhere in v1",
    "`widgets/surf/_swarm_table.py` → `widgets/swarm_table.py`",
    "`BROKER_DIR = /opt/imd-dash/broker/imd_dashd`",
    "`-p BindReadOnlyPaths=/opt/imd-dash/broker`",
    "(contract deviation, WP0)",
    "**2026-09-27 (Codex build)**",
    "**2026-09-27 (execution deviation, WP0)**",
    "**2026-09-27 (owner correction, spec §13)**",
    "(contract decision, WP2) — a local `task failed:` line appends the pseudo-phase `failed`",
    "(contract decision, WP2) — the seat ledger adds `sessions_skipped_oversize`",
)


@pytest.mark.guard
def test_decisions_record_the_pepepane_entries():
    """Spec §15 "Shared surfaces": every dated 2026-09-26 decision is in ``docs/decisions.md``,
    appended after the last upstream entry (append-only, at the file's end). Mutation: delete one
    entry -> red; move the block to the top -> red."""
    text = DECISIONS.read_text(encoding="utf-8")
    anchor = text.index("**2026-09-26 (pepepane)**")
    assert anchor > text.index("- **Standing**"), "the pepepane block is appended after the upstream entries"
    for phrase in SEAT_DECISION_PHRASES:
        assert text.count(phrase) == 1, f"missing or duplicated decision: {phrase}"
        assert text.index(phrase) > anchor, f"decision outside the pepepane block: {phrase}"

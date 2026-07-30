"""Path guards for the one-shot Cat Town ABI scripts.

``scripts/extract_cattown_abis.py`` and ``scripts/validate_cattown_abis.py``
are imported by nothing, so nothing caught them still pointing at the
pre-rename ``dashboard/abis/cattown`` directory: the validator reported
0/6 "ABI file not found" and exited 1 regardless of the real ABIs, and the
extractor created a dead untracked tree and called it success.

These tests import the modules by file path and assert only on their
directory constants and the vendored ABI files. No network, no ``main()``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "scripts"
VENDORED = ROOT / "maxpane_dashboard" / "abis" / "cattown"


def _load(name: str) -> ModuleType:
    """Import a script from scripts/ without making it importable elsewhere."""
    path = SCRIPTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_cattown_scripts_{name}", path)
    assert spec and spec.loader, path
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules.pop(f"_cattown_scripts_{name}", None)
    return module


@pytest.fixture(scope="module")
def extract_mod() -> ModuleType:
    return _load("extract_cattown_abis")


@pytest.fixture(scope="module")
def validate_mod() -> ModuleType:
    return _load("validate_cattown_abis")


class TestValidatorPaths:
    def test_abi_dir_is_the_vendored_directory(self, validate_mod):
        assert validate_mod.ABI_DIR == VENDORED
        assert validate_mod.ABI_DIR.is_dir()

    def test_every_configured_abi_file_exists_and_parses(self, validate_mod):
        """The validator's 6 contracts all resolve to real ABI arrays.

        This is the assertion that would have failed before the path fix --
        the run reported 0/6 PASS for exactly this reason.
        """
        for name, info in validate_mod.CONTRACTS.items():
            abi_path = validate_mod.ABI_DIR / info["abi_file"]
            assert abi_path.exists(), f"{name}: missing {abi_path}"
            abi = json.loads(abi_path.read_text())
            assert isinstance(abi, list) and abi, f"{name}: ABI is not a non-empty array"


class TestExtractorPaths:
    def test_output_dir_is_staging_not_the_package(self, extract_mod):
        """The scraper must never write into the shipped package.

        Labelling in the extractor is heuristic and it dumps unlabelled
        candidates alongside the labelled ones; aiming that at the vendored
        directory would overwrite curated ABIs and ship scrape output in the
        wheel (pyproject includes all of maxpane_dashboard/).
        """
        package_dir = ROOT / "maxpane_dashboard"
        assert not extract_mod.ABI_DIR.is_relative_to(package_dir)
        assert extract_mod.ABI_DIR.is_relative_to(ROOT)

    def test_copy_target_points_at_the_vendored_directory(self, extract_mod):
        assert extract_mod.VENDORED_ABI_DIR == VENDORED

    def test_import_creates_no_directories(self, extract_mod):
        """mkdir belongs in main(), not at import time."""
        assert not extract_mod.ABI_DIR.exists() or extract_mod.ABI_DIR.is_dir()
        # Re-importing must not be what creates it.
        before = extract_mod.ABI_DIR.exists()
        _load("extract_cattown_abis")
        assert extract_mod.ABI_DIR.exists() == before

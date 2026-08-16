"""Fact pins for the WhitelistCurator captures, and the vendored ABI's provenance.

Every number a later curator work package hardcodes is asserted here, once,
against the committed payload it came from.  A re-capture that moves one of them
fails in this file — the file that owns the fact — instead of drifting silently
through six work packages.

Nothing here touches the network: the whole suite reads committed bytes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.curator_fixtures import CAPTURES, capture, capture_text

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PKG = _REPO_ROOT / "maxpane_dashboard"
_VENDORED_ABI = _PKG / "abis" / "curator" / "whitelist_curator.json"


def _extract_abi_in_memory(name: str = "contract.json") -> list[dict]:
    """The extraction ``scripts/vendor_curator_abi.py`` performs, re-run here.

    Deliberately *not* an import of the script: ``scripts/`` is absent from a
    pipx install and nothing under test may depend on it.  Six lines duplicated
    is the price of the guarantee.
    """
    return capture(name)["abi"]


def test_the_two_abi_captures_agree() -> None:
    """Two agents saved the same Blockscout endpoint. Divergence means one is stale."""
    assert _extract_abi_in_memory("contract.json") == _extract_abi_in_memory(
        "wc_abi.json"
    )


def test_the_vendored_abi_matches_the_capture() -> None:
    """A hand-edit of the vendored artifact fails here.

    The committed bytes must be exactly what the extraction produces from the
    capture, formatting included, so the artifact stays a pure function of the
    provenance.
    """
    expected = json.dumps(_extract_abi_in_memory(), indent=2) + "\n"
    assert _VENDORED_ABI.read_text(encoding="utf-8") == expected


def test_the_vendored_abi_declares_every_event_the_source_declares() -> None:
    """Set equality against ``source.sol`` — this is what catches a truncated save."""
    src = capture_text("source.sol")
    declared = set(re.findall(r"^\s*event\s+(\w+)\s*\(", src, re.MULTILINE))
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    assert declared == {e["name"] for e in abi if e["type"] == "event"}
    assert declared == {
        "Launched",
        "Deposited",
        "FirstDeposit",
        "HourSaved",
        "Settled",
        "Rescued",
    }


def test_the_vendored_abi_declares_every_error_the_source_declares() -> None:
    """Ten custom errors. A missing one is a revert the client cannot name."""
    src = capture_text("source.sol")
    declared = set(re.findall(r"^\s*error\s+(\w+)\s*\(", src, re.MULTILINE))
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    assert declared == {e["name"] for e in abi if e["type"] == "error"}
    assert len(declared) == 10


def test_the_vendored_abi_holds_every_view_the_dashboard_reads() -> None:
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    names = {e["name"] for e in abi if e["type"] == "function"}
    required = {
        "contributors",
        "totalVolume",
        "totalContributors",
        "totalTxCount",
        "POINTS_PER_ETH",
        "launchTime",
        "hourlyThreshold",
        "gracePeriod",
        "hourDuration",
        "minDeposit",
        "minEscalation",
        "creditCap",
        "firstJudgedHour",
        "deployer",
        "isSettled",
        "currentHour",
        "currentHourTotal",
        "ethNeededThisHour",
        "timeLeftInHour",
        "lastActiveHour",
        "earlyMultiplierBps",
        "stats",
        "pointsOf",
        "weightOf",
        "contributedBy",
        "txCountOf",
        "requiredNext",
        "firstHourOf",
        "previewPoints",
    }
    assert required <= names, sorted(required - names)


def test_the_vendored_abi_carries_no_state_changing_call_the_dashboard_could_make() -> (
    None
):
    """Read-only by hard constraint.

    ``deposit()``, ``settle()`` and ``rescue()`` exist on chain and are in the
    ABI — that is correct, the ABI is the contract's.  What must never exist is
    a curator module that encodes one; WP7's guardrail scan owns that.  This
    test records the three names so the scan has a list to work from.
    """
    abi = json.loads(_VENDORED_ABI.read_text(encoding="utf-8"))
    mutating = {
        e["name"]
        for e in abi
        if e["type"] == "function"
        and e.get("stateMutability") not in ("view", "pure")
    }
    assert mutating == {"deposit", "settle", "rescue"}


def test_nothing_under_maxpane_dashboard_imports_scripts() -> None:
    """``scripts/`` is a dev tool; a pipx install ships without it."""
    offenders = []
    for path in sorted(_PKG.rglob("*.py")):
        code = path.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+scripts\b", code, re.MULTILINE):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert not offenders, offenders


def test_the_vendored_abi_is_not_fetched_at_runtime() -> None:
    """No curator module may name a Blockscout smart-contracts URL."""
    for path in sorted(_PKG.rglob("curator*.py")):
        code = path.read_text(encoding="utf-8")
        assert "smart-contracts" not in code, path.name

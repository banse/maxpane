"""Keccak-256 must be Ethereum's hash, not SHA-3.

This module exists only to make ENS ``namehash`` possible, and a namehash built
on the wrong permutation is the worst kind of wrong: internally consistent,
plausible-looking, and resolving nothing.  The two functions differ *only* in a
padding byte (``0x01`` vs ``0x06``), so the mistake is invisible by inspection
and total in effect.

The strongest check here is not the published vectors -- it is that this
implementation independently reproduces all 209 selectors and event topics
already vendored under ``abis/``.  Those were captured from chain by a
different route entirely, so agreement means the hash and the vendored tables
confirm each other.  Nothing verified those tables before.

No network: every input is a literal or a committed ABI file.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from maxpane_dashboard.data.keccak import keccak256, keccak256_hex, keccak256_text

_ABI_DIR = Path(__file__).resolve().parents[2] / "maxpane_dashboard" / "abis" / "fwa"


# ---------------------------------------------------------------------------
# published vectors
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "data,expected",
    [
        (b"", "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"),
        (b"abc", "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45"),
        (
            b"testing",
            "5f16f4c7f149ac4f9510d9cf8cf384038ad348b3bcdc01915f95de12df9d1b02",
        ),
    ],
)
def test_official_vectors(data, expected) -> None:
    assert keccak256(data).hex() == expected


def test_this_is_not_sha3() -> None:
    """The whole trap, stated as a test.

    ``hashlib.sha3_256`` is available, has the same name shape and the same
    output length.  Substituting it would break every ENS lookup while raising
    nothing.
    """
    assert keccak256(b"") != hashlib.sha3_256(b"").digest()
    assert keccak256(b"abc") != hashlib.sha3_256(b"abc").digest()


def test_rate_boundary_inputs() -> None:
    """Lengths either side of the 136-byte rate exercise the padding branches."""
    for size in (0, 1, 135, 136, 137, 272, 273):
        assert len(keccak256(b"\xa5" * size)) == 32


def test_hex_helper_matches_digest() -> None:
    assert keccak256_hex(b"abc") == "0x" + keccak256(b"abc").hex()


def test_rejects_str() -> None:
    """A ``str`` would hash its repr under a permissive implementation."""
    with pytest.raises(TypeError):
        keccak256("abc")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# cross-check against everything this repo already vendored
# ---------------------------------------------------------------------------


def test_reproduces_every_vendored_selector() -> None:
    """All 167 vendored function selectors recompute from their signatures."""
    selectors = json.loads((_ABI_DIR / "selectors.json").read_text())
    assert len(selectors) > 100, "fixture shrank -- this test lost its teeth"

    mismatched = {
        sig: (want, keccak256_hex(sig.encode())[:10])
        for sig, want in selectors.items()
        if keccak256_hex(sig.encode())[:10] != want.lower()
    }
    assert not mismatched, f"selector disagreement: {mismatched}"


def test_reproduces_every_vendored_event_topic() -> None:
    """All 42 vendored topic0 hashes recompute from their signatures."""
    topics = json.loads((_ABI_DIR / "topics.json").read_text())
    assert len(topics) > 20, "fixture shrank -- this test lost its teeth"

    mismatched = {
        name: (entry["topic0"], keccak256_hex(entry["signature"].encode()))
        for name, entry in topics.items()
        if entry.get("signature")
        and entry.get("topic0")
        and keccak256_hex(entry["signature"].encode()) != entry["topic0"].lower()
    }
    assert not mismatched, f"topic disagreement: {mismatched}"


@pytest.mark.parametrize(
    "signature,selector",
    [
        ("transfer(address,uint256)", "a9059cbb"),
        ("balanceOf(address)", "70a08231"),
        ("name()", "06fdde03"),
        ("resolver(bytes32)", "0178b8bf"),
        ("addr(bytes32)", "3b3b57de"),
        ("name(bytes32)", "691f3431"),
    ],
)
def test_well_known_selectors(signature, selector) -> None:
    """Selectors any Ethereum developer can check by eye, including ENS's."""
    assert keccak256_text(signature).hex()[:8] == selector

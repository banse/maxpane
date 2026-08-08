"""The surf capture set — the one source material, and the facts it pins.

Every surf work package derives its test data from ``tests/fixtures/surf/captures/``:
real keyless payloads (Blockscout REST v2, GeckoTerminal, DexScreener) fetched on
2026-08-08.  Two things are asserted here and nowhere else:

1.  The captures are committed, readable, keyless and read-only.
2.  Every number a later work package hardcodes is recomputed *from the capture* —
    the burn total, the poisoning rows, the holder disagreement, the parity spread,
    the nonce ladder.  A re-capture that moves one of them fails here, once.

WP0 commits no fixture file.  Each consuming work package owns a subdirectory of
``tests/fixtures/surf/`` (``client/``, ``signals/``, …); the root-directory guard
below is what keeps those from colliding with each other's globs.

No network: this module reads files only.
"""

from __future__ import annotations

import json

from tests.surf_fixtures import CAPTURES, SURF_FIXTURES


def test_captures_are_committed_and_readable() -> None:
    names = {p.name for p in CAPTURES.iterdir()}
    assert "README.md" in names, "the capture set must document its own provenance"
    json_files = sorted(CAPTURES.glob("*.json"))
    assert len(json_files) == 29
    for path in json_files:
        assert json.loads(path.read_text(encoding="utf-8")) is not None, path.name


def test_the_fixtures_root_holds_directories_only() -> None:
    """Ownership rule: WP0 owns ``captures/`` and every other work package owns its
    own subdirectory.  A loose ``*.json`` at the root is a file with no owner, and
    it is how one WP's slice lands in another WP's glob and turns its suite red in
    a file it may not edit."""
    loose = sorted(p.name for p in SURF_FIXTURES.iterdir() if p.is_file())
    assert loose == [], f"put these in a per-work-package subdirectory: {loose}"


def test_no_capture_carries_an_api_key() -> None:
    """Hard constraint: every source is keyless.  A captured URL with a key in it
    would mean the payload cannot be re-fetched by someone who installed the app."""
    for path in sorted(CAPTURES.iterdir()):
        text = path.read_text(encoding="utf-8", errors="replace").lower()
        for banned in ("api_key=", "apikey=", "x-api-key", "authorization:"):
            assert banned not in text, f"{path.name} contains {banned}"

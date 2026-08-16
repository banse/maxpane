"""Shared access to the curator capture set.

``tests/fixtures/curator/captures/`` holds the real keyless payloads captured on
2026-08-16, plus whatever timed bundles WP1 has landed under ``captures/live/``.
Every curator work package slices its own test data out of them, so this module
is the one reader and four suites (``tests/data``, ``tests/analytics``,
``tests/widgets``, ``tests/screens``) do not hand-roll four.

It exposes **only** the raw-capture reader.  There is no envelope helper here
because WP0 commits no derived fixture for one to open; a work package that
commits slices under ``tests/fixtures/curator/<its-dir>/`` and wants a shared
reader adds it *here*, next to :func:`capture` — never by copying this file.

The captures are **read-only**.  Nothing regenerates them; a test that rewrote
one would turn the provenance into whatever made the suite green that afternoon.

Shapes you will trip over (all verified against the committed bytes, and each
contradicting something a planning document says — see
``tests/data/test_curator_captures.py``, which pins the truth):

* ``tenderly_logs.json`` is the **full JSON-RPC envelope**, not a bare list.
  The 377 log rows are ``capture("tenderly_logs.json")["result"]``.
* Those rows **do** carry ``blockTimestamp``, and Blockscout's log items carry
  ``block_timestamp``.  The plan's H14 assumed neither did.
* ``batch.json`` / ``results.json`` are bare lists of 21 JSON-RPC requests and
  21 responses, correlated by ``id`` — never by list position.
* ``bs_page_*.json`` are Blockscout pages: ``{"items": [...], "next_page_params"}``.
* ``hour_boundary_h1_h2.json`` is ``{"meta", "views", "samples"}`` where
  ``views`` maps request id → selector → Solidity signature and each sample is
  ``{"captured_at", "response": [...21 results...]}``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: ``tests/fixtures/curator`` — the root each work package takes a subdirectory
#: of.  It holds **directories only**; a loose file here is a file with no owner
#: (``test_the_fixtures_root_holds_directories_only`` enforces it).
CURATOR_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "curator"

#: The committed 2026-08-16 research payloads.  WP0 owns these.
CAPTURES = CURATOR_FIXTURES / "captures"

#: WP1's timed bundles.  Grows at unpredictable moments while other work
#: packages build, which is exactly why WP0's guard is a *named required set*
#: and never a file count.
LIVE = CAPTURES / "live"


def capture(name: str) -> Any:
    """One raw capture body, exactly as the keyless API served it.

    ``.json`` files are parsed; anything else (``source.sol``, ``README.md``)
    should be read with :func:`capture_text`.
    """
    with open(CAPTURES / name, encoding="utf-8") as fh:
        return json.load(fh)


def capture_text(name: str) -> str:
    """A raw capture as text — for ``source.sol``, the only signature authority."""
    return (CAPTURES / name).read_text(encoding="utf-8")


def live_bundles() -> list[Path]:
    """WP1's timed bundles, sorted.  **Empty is normal** and never a failure.

    Before WP1's first timed run there are none; during the build there may be
    any number.  No test may assert a count here.
    """
    if not LIVE.is_dir():
        return []
    return sorted(p for p in LIVE.glob("*.json") if p.is_file())

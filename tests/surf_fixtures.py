"""Shared access to the surf capture set.

``tests/fixtures/surf/captures/`` holds the real keyless payloads captured on
2026-08-08; every surf work package slices its own test data out of them.  This
module is the one reader of the captures, so four test suites (``tests/data``,
``tests/analytics``, ``tests/widgets``, ``tests/screens``) do not hand-roll four.

It exposes **only** the raw-capture reader.  There is no envelope helper here
because WP0 commits no fixture file for one to open, and a helper with no caller
is exactly the defect that deleted nine tasks from this plan.  A work package that
commits slices under ``tests/fixtures/surf/<its-dir>/`` and wants a shared reader
adds it *here*, next to ``capture()`` — never by copying this file.

The captures are **read-only**.  Nothing regenerates them; a test that rewrote one
would turn the provenance into whatever made the suite green that afternoon.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

#: ``tests/fixtures/surf`` — the root each work package takes a subdirectory of.
SURF_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "surf"

#: The committed 2026-08-08 payloads.
CAPTURES = SURF_FIXTURES / "captures"


def capture(name: str) -> Any:
    """One raw capture body, exactly as the keyless API served it."""
    with open(CAPTURES / name, encoding="utf-8") as fh:
        return json.load(fh)

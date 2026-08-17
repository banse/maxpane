"""Shared access to the curator **sybil-analysis** fixture slices.

``tests/fixtures/curator/sybil/`` holds the payloads the linked-wallet build
measures against.  It is a sibling of ``tests/fixtures/curator/captures/`` and
is read by exactly this module, for the reason ``tests/curator_fixtures.py``
gives: four suites (``tests/data``, ``tests/widgets``, ``tests/screens`` and
whatever WP3's adapter suite becomes) need the same bytes, and four hand-rolled
readers is four places for a path to go stale.

Nothing here opens a socket, and nothing here writes.  The slices are committed
artifacts; a test that regenerated one would turn the provenance into whatever
made the suite green that afternoon.

What is in here, and what it is for
-----------------------------------
``labeled_subset.json``
    The benchmark subset (PRD §3.5/§8): the 16 audited operators' sampled
    members and the 60 controls, each with its deposit rows, its join index,
    its transaction fingerprint and its funder — enough to run a whole
    ``detect()`` offline.  **Byte-identical** to
    ``sybilkit/tests/fixtures/labeled_subset.json``; both distributions gate on
    the same evidence, and ``test_curator_sybil_data.py`` pins that they agree.

``operator_row_worst.json`` · ``segment_rows_worst.json`` ·
``clean_list_rows_worst.json``
    The **worst-case** analysis payloads WP4 and WP5 size their layouts
    against, frozen before WP3's adapter exists.  Worst-case rather than a toy
    row on purpose: CLAUDE.md's IMD/FP-peg lesson is that a width measured
    against a narrow state is a width that is wrong in the state the data is
    normally in.  The widest real operator is 1 995 wallets holding 6.81% of
    all points at a 44.6× sqrt subsidy, and that is the row the columns have to
    fit.

Every one of the three carries the literal marker
``SYNTHETIC — calibrated from docs/curator_sybil_data/, re-point at a live
analysis bundle`` in its ``synthetic`` field, so ``rg "SYNTHETIC —"`` remains
the whole checklist.  ``labeled_subset.json`` does **not** carry it: every byte
of it is real measured data, joined rather than invented.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tests.curator_fixtures import CURATOR_FIXTURES

#: ``tests/fixtures/curator/sybil`` — this work package's own subdirectory of
#: the curator fixtures root.  One directory per work package is what stops one
#: package's slice landing in another package's glob.
SYBIL = CURATOR_FIXTURES / "sybil"

#: The worst-case row payloads, in the order the analysis view renders their
#: panels: OPERATORS, SEGMENTS, CLEANED LIST.
WORST_CASE = (
    "operator_row_worst.json",
    "segment_rows_worst.json",
    "clean_list_rows_worst.json",
)

#: The literal every synthetic slice carries, and the string the ledger greps
#: for.  Imported rather than retyped by the tests that check it.
SYNTHETIC_MARKER = (
    "SYNTHETIC — calibrated from docs/curator_sybil_data/, "
    "re-point at a live analysis bundle"
)


def load(name: str) -> Any:
    """One committed slice, parsed."""
    with open(SYBIL / name, encoding="utf-8") as fh:
        return json.load(fh)


def slices() -> list[Path]:
    """Every committed slice, **sorted**.

    Sorted because an unsorted ``iterdir()`` makes a test's failure message
    depend on the filesystem's mood, and because a later work package will add
    its own slices here — a stable order is what keeps a diff readable.
    """
    if not SYBIL.is_dir():
        return []
    return sorted(p for p in SYBIL.glob("*.json") if p.is_file())


def labeled_subset() -> dict:
    """The benchmark subset — the same bytes ``sybilkit`` gates on."""
    return load("labeled_subset.json")


def worst_case_rows(name: str) -> list[dict]:
    """The ``rows`` list of one worst-case slice.

    The slices are envelopes (``synthetic``/``note``/``row_keys``/``rows``)
    rather than bare lists, because a bare list has nowhere to carry its own
    provenance — and a fixture whose provenance lives only in a README is a
    fixture whose provenance is one rename from gone.
    """
    return load(name)["rows"]

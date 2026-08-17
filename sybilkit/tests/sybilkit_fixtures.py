"""Shared access to ``sybilkit``'s committed fixtures.

The mirror of ``tests/curator_sybil_fixtures.py`` on the maxpane side: same
function names, same shapes, so a reader who knows one knows the other and the
two distributions gate on the same evidence rather than on two convenient
subsets of it.

Nothing here opens a socket.  ``sybilkit`` is keyless and its suite is
offline — every external payload is a file in ``tests/fixtures/``.

What is in here
---------------
``labeled_subset.json``
    The benchmark subset (PRD §3.5): the 16 audited operators' sampled members
    (160 addresses) and 60 controls, each carrying its deposit rows, its 1-based
    join index, its transaction fingerprint and its funder — plus, per address,
    whether that funder is a member of its own cluster.  Self-contained: enough
    to build a :class:`sybilkit.Dataset` and run ``detect()`` end to end with no
    network and no maxpane.  **Byte-identical** to
    ``tests/fixtures/curator/sybil/labeled_subset.json`` in the maxpane repo.

``deposits.json.gz`` · ``first_deposits.json.gz``
    The **full population** — 22 319 deposits across 15 576 contributors, as
    swept on 2026-08-17.  Committed gzipped and read in memory; there is no
    uncompressed copy in the tree.  They are here so the curator preset's
    segment statistics can be asserted against the real distribution rather
    than against a sample of it, and because the population is what makes a
    precision floor mean anything.

    They are **test data**.  Wheels do not ship ``tests/`` — see
    ``pyproject.toml``'s ``[tool.hatch.build.targets.wheel] packages`` — so the
    3 MB stays out of the distribution a user installs.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parent / "fixtures"

#: The two full-population datasets, gzipped.  Named so a test can iterate them
#: without hardcoding either name twice.
POPULATION = ("deposits.json.gz", "first_deposits.json.gz")


def load(name: str) -> Any:
    """One committed fixture, parsed.  ``.gz`` files are decompressed in memory.

    Never writes an uncompressed copy beside the archive: a decompressed
    ``deposits.json`` is 12 MB of untracked file that the next ``git status``
    reads as a change nobody made.
    """
    path = FIXTURES / name
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def slices() -> list[Path]:
    """Every committed fixture, **sorted** — ``.json`` and ``.json.gz`` alike."""
    if not FIXTURES.is_dir():
        return []
    return sorted(
        p for p in FIXTURES.iterdir() if p.is_file() and p.suffix in (".json", ".gz")
    )


def labeled_subset() -> dict:
    """The benchmark subset — the same bytes the maxpane side gates on."""
    return load("labeled_subset.json")

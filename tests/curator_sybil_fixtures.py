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

Read the **envelope**, not just ``rows``
----------------------------------------
Each worst-case slice is an envelope, and two of the payloads a width sweep
needs live *outside* ``rows``: ``operator_row_worst``'s ``worst`` (the row the
brief names) and ``segment_rows_worst``'s ``degraded_row`` (the ``None``-share
case — and, at 56 columns, the widest ``detail`` string in the set).  A sweep
driven by :func:`worst_case_rows` alone measures neither.  Use
:func:`worst_case_envelope` for the whole slice, :func:`row_payloads` for every
row-shaped payload in it, and :func:`rendered_strings` for everything a widget
could put on screen.

Naming, across the two distributions
------------------------------------
``sybilkit/tests/sybilkit_fixtures.py`` is the mirror of this module and keeps
the same names for the fixtures both distributions hold: ``load``, ``slices``
and ``labeled_subset`` mean the same thing on both sides, and
``test_the_two_readers_keep_the_same_names_for_the_shared_fixtures`` pins that.
The ``worst_case_*`` accessors are deliberately **maxpane-only** — they read
presentation payloads (``*_eth``, ``*_pct``, ENS names, pattern-language copy)
for a TUI that ``sybilkit`` does not have and must not learn about.
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


def worst_case_envelope(name: str) -> dict:
    """One worst-case slice **whole** — provenance, shapes and every payload.

    The slices are envelopes (``synthetic``/``note``/``row_keys``/``rows``
    plus, per fixture, ``worst``, ``worst_cluster``, ``totals`` and
    ``degraded_row``) rather than bare lists, because a bare list has nowhere
    to carry its own provenance — and a fixture whose provenance lives only in
    a README is a fixture whose provenance is one rename from gone.

    Use this, not :func:`worst_case_rows`, for anything that has to be **true
    of the whole payload**: a width sweep, a hostile-string scan, a row-shape
    check.  ``rows`` alone is a partial view, and the widest string in the set
    is not in it — see :func:`row_payloads`.
    """
    return load(name)


def worst_case_rows(name: str) -> list[dict]:
    """Just the ``rows`` list of one worst-case slice.

    Deliberately narrow, and *not* the accessor to reach for by default: the
    two payloads outside ``rows`` are exactly the two a lazy reading misses —
    ``operator_row_worst``'s ``worst`` (the row the brief names) and
    ``segment_rows_worst``'s ``degraded_row`` (the ``None``-share case, and the
    widest ``detail`` string in the whole set at 56 columns).
    """
    return load(name)["rows"]


def row_payloads(name: str) -> list[tuple[str, dict]]:
    """Every **row-shaped** payload in one envelope, labelled by where it lives.

    ``[("rows[0]", {...}), …, ("worst", {...})]`` — the labels are there so a
    failure names the payload rather than an index into a list the reader
    cannot see.

    This is what makes the row-shape check and the pattern-language scan total.
    Before it existed both ran over ``rows`` only, so ``worst`` and
    ``degraded_row`` were committed without either guard ever looking at them —
    and ``degraded_row`` is precisely the row whose shape is easiest to get
    wrong, because it is the one written by hand.

    ``totals`` is **not** included: it is a dict of scalars about the whole
    list, not a row, and it has no entry in ``CURATOR_ROW_KEYS`` to be checked
    against.  :func:`rendered_strings` covers it instead.
    """
    payload = load(name)
    out: list[tuple[str, dict]] = [
        (f"rows[{i}]", row) for i, row in enumerate(payload["rows"])
    ]
    for extra in ("worst", "degraded_row"):
        if extra in payload:
            out.append((extra, payload[extra]))
    return out


#: Envelope fields that carry **provenance**, never anything a widget renders.
#:
#: They are excluded from the pattern-language scan on purpose and not by
#: oversight: ``synthetic`` and ``note`` both name the source directory
#: ``docs/curator_sybil_data/``, so a naive scan of the whole envelope would
#: fail on the word "sybil" in a path that no reader will ever see.  What must
#: be clean is what reaches a screen.
PROVENANCE_FIELDS = ("synthetic", "note", "row_keys", "worst_cluster")


def rendered_strings(name: str) -> list[str]:
    """Every string in one envelope that a widget could actually render.

    Provenance fields (:data:`PROVENANCE_FIELDS`) are excluded; everything
    else — every row, ``worst``, ``degraded_row`` and ``totals`` — is in.
    """
    payload = {
        key: value
        for key, value in load(name).items()
        if key not in PROVENANCE_FIELDS
    }

    out: list[str] = []

    def walk(node) -> None:
        if isinstance(node, str):
            out.append(node)
        elif isinstance(node, dict):
            for key, value in node.items():
                out.append(key)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return out

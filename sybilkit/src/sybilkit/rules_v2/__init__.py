"""The v2 rule set — sybilkit 0.2.0's main analysis utility.

``sk_v2.py`` in this package is shipped **byte-identical** to the file that
produced the published clustermap analysis, and it is pinned by content rather
than by this release:

    sha256(sk_v2.py) == 457fac65506d3ce9693f35c154f2f1d635d3cef5673138e43c3d6332bf71b2b3

That digest is recorded as ``rules_sha256`` in the published analysis
(``2026-08-25-sybilkit-0.2.0``), so anyone can check that this release contains
the detector that produced it, with ``shasum`` and no git checkout. **Editing
``sk_v2.py`` breaks that link** — the rules are frozen here, and a rule change
is a new release *and* a new analysis version, never an edit in place.

Everything a caller needs is re-exported below, so the frozen file itself never
has to be imported by path::

    from sybilkit.rules_v2 import VARIANTS, Rules, run

Why the rules live beside the library rather than inside ``detect()``: v2 lets
funding structure *build* a component, where ``sybilkit.cluster.detect`` unions
only over tier-A edges and folds funding on afterwards as corroboration. That
fold is deliberate and tested (``tests/test_signals_funding.py``,
``tests/test_coverage_invariants.py``); v2 reverses it. Both behaviours ship,
neither silently overwrites the other, and which one produced a given result is
always answerable.

Scope, stated plainly: every constant in v2 was calibrated on one settled
population (THE LIST — 19,522 wallets, 28,353 deposits). The block windows
assume 12-second blocks and the near-minimum band is 1.25x *that* game's 0.05
ETH floor. It has not been evaluated against a second dataset. See
``KNOWN_LIMITATIONS.md``.
"""

from __future__ import annotations

from .farm_windows import PREDICATES as FARM_WINDOW_PREDICATES
from .farm_windows import derive as derive_farm_windows
from .sk_v2 import VARIANTS, Rules, build_extra, metrics, run

__all__ = [
    "FARM_WINDOW_PREDICATES",
    "VARIANTS",
    "Rules",
    "build_extra",
    "derive_farm_windows",
    "metrics",
    "run",
]

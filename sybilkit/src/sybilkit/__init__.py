"""``sybilkit`` — keyless EVM sybil / fan-out cluster analysis.

A standalone distribution.  It knows nothing about maxpane, Textual, or any
dashboard: the core is **stdlib only**, wei-native, and pure.  Optional keyless
fetchers (``sybilkit.sources``, WP2) are the only part that ever opens a socket,
and they are an *extra* — ``import sybilkit`` works with zero third-party
packages installed.

Design rules, carried verbatim from the PRD (§3.1) because every one of them is
a measured finding rather than a preference:

* **Score clusters, not wallets.**  No per-wallet signal separated farms from
  power users in any measured study.  A wallet is flagged only *via* a cluster.
* **Compound conditions.**  A cluster forms only when its members are linked by
  **≥ 2 independent signal families** (amount, sequence, cadence, gas, funding).
  One family alone never convicts.
* **Minimum cluster size ≥ 5.**  Keeps one-human-few-wallets out.
* **Reasons, never verdicts.**  Output is ``reasons: [Reason(family,
  human_string, strength)]`` plus a ``confidence`` in [0, 1] — multiplicative
  and graduated, never binary.  Freshness *discounts*; it never convicts.
* **``None`` is a failed read.**  "no cluster" is not "could not analyze";
  "0 points share" is not "share unknown".

Everything in this package is **read-only analysis**.  Nothing here signs,
sends, or constructs calldata for a state change.

The name is locked
------------------
``sybilkit`` — verified free on PyPI, and every import path in the maxpane
adapter, the CLI entry point and both test suites depends on it.  A rename
after WP1 is a sed across two distributions; see the WP0.1 commit body.

Public surface (frozen in WP0, implemented in WP1/WP2)
------------------------------------------------------
``Dataset`` · ``detect`` · ``DetectConfig`` · ``DetectResult`` ·
``Deposit`` · ``Tx`` · ``Funding`` · ``Cluster`` · ``Reason`` ·
``WalletVerdict``
"""

from __future__ import annotations

# WP0.2 adds the model re-exports here; WP0.3 adds report/cluster/curve.  The
# names above are the freeze; this list is what makes them importable.
__all__: tuple[str, ...] = ()

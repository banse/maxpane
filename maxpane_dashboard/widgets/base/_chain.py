"""The one explorer declaration for the base widgets (refactor programme, Branch 4).

Every address this package renders links to the same explorer, so the chain
is named once here and imported at each ``address_text(..., explorer=)``
site; ``tests/address_sweep/builders.py`` (``SweepCase.explorer``) is the
agreement test that binds this declaration to what the sweep expects.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import BASE

__all__ = ["EXPLORER"]

#: Base (Basescan): read off ``data/base_client.py`` -- GeckoTerminal
#: ``/networks/base/`` (:554 trending, :232 the same path inline), DexScreener
#: pairs filtered to ``chainId == "base"`` (:299), and the ``mainnet.base.org``
#: RPC (:702).
EXPLORER = BASE

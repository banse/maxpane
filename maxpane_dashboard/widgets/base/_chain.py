"""The one explorer declaration for the base widgets (refactor programme, Branch 4).

Every address this package renders links to the same explorer, so the chain
is named once here and imported at each ``address_text(..., explorer=)``
site; ``tests/address_sweep/builders.py`` (``SweepCase.explorer``) is the
agreement test that binds this declaration to what the sweep expects.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import BASE

__all__ = ["EXPLORER"]

#: Base (Basescan): read off ``data/base_client.py:58`` -- GeckoTerminal ``/networks/base/`` pools and DexScreener pairs
#: filtered to ``chainId == "base"`` (:232, :299).
EXPLORER = BASE

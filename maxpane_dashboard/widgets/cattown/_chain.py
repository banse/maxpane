"""The one explorer declaration for the cattown widgets (refactor programme, Branch 4).

Every address this package renders links to the same explorer, so the chain
is named once here and imported at each ``address_text(..., explorer=)``
site; ``tests/address_sweep/builders.py`` (``SweepCase.explorer``) is the
agreement test that binds this declaration to what the sweep expects.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import BASE

__all__ = ["EXPLORER"]

#: Base (Basescan): read off ``data/cattown_client.py:167`` -- ``RPC_URL`` ``mainnet.base.org`` (``MAXPANE_BASE_RPC_URL`` overrides
#: the host, never the chain), fallbacks ``base-rpc.publicnode.com``, ``base.drpc.org``.
EXPLORER = BASE

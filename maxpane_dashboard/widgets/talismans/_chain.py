"""The one explorer declaration for the talismans widgets (refactor programme, Branch 4).

Every address this package renders links to the same explorer, so the chain
is named once here and imported at each ``address_text(..., explorer=)``
site; ``tests/address_sweep/builders.py`` (``SweepCase.explorer``) is the
agreement test that binds this declaration to what the sweep expects.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import ETHEREUM

__all__ = ["EXPLORER"]

#: Ethereum mainnet (Etherscan): read off ``data/talismans_client.py:70`` -- ``_PRIMARY_RPC`` ``ethereum.publicnode.com``, fallbacks
#: ``gateway.tenderly.co/public/mainnet``, ``eth.drpc.org``.
EXPLORER = ETHEREUM

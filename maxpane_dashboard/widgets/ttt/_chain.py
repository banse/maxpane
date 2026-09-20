"""The one explorer declaration for the ttt widgets (refactor programme, Branch 4).

Every address this package renders links to the same explorer, so the chain
is named once here and imported at each ``address_text(..., explorer=)``
site; ``tests/address_sweep/builders.py`` (``SweepCase.explorer``) is the
agreement test that binds this declaration to what the sweep expects.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import ETHEREUM

__all__ = ["EXPLORER"]

#: Ethereum mainnet (Etherscan): read off ``data/ttt_client.py:99`` -- ``_PRIMARY_RPC`` ``ethereum-rpc.publicnode.com``, fallbacks
#: ``gateway.tenderly.co/public/mainnet``, ``eth.drpc.org``.
EXPLORER = ETHEREUM

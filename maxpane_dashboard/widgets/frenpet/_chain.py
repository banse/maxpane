"""The one explorer declaration for the frenpet widgets (refactor programme, Branch 4).

Every address this package renders links to the same explorer, so the chain
is named once here and imported at each ``address_text(..., explorer=)``
site; ``tests/address_sweep/builders.py`` (``SweepCase.explorer``) is the
agreement test that binds this declaration to what the sweep expects.
"""

from __future__ import annotations

from maxpane_dashboard.widgets.explorer import BASE

__all__ = ["EXPLORER"]

#: Base (Basescan): read off ``data/frenpet_client.py:78`` -- ``RPC_URL`` ``mainnet.base.org`` (the Diamond proxy is read there).
#: Imported by the hidden ``screens/frenpet_full`` / ``_wallet`` / ``_perf`` bodies, the
#: package's only address sites; the overview body renders no address.
EXPLORER = BASE

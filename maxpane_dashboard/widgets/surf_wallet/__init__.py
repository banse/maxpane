"""Presentation-only wallet activity; no readers or network operations."""
from maxpane_dashboard.widgets.explorer import for_chain_id

# Per-artifact chain IDs are supplied by the wallet projection; unknown chains do not link.
EXPLORER = for_chain_id
WIDGET_SIGNATURES = {"WalletBody": ("wallet_snapshot",)}

from .body import WalletBody

__all__ = ["WalletBody", "WIDGET_SIGNATURES"]

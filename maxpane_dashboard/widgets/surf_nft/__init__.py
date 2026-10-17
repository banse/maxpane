"""Render-only NFT Explorer panels with per-row chain explorers."""
from maxpane_dashboard.widgets.explorer import for_chain_id

# Evidence supplies the numeric chain; an unknown chain deliberately has no link.
EXPLORER = for_chain_id

from .hero import NftHero
from .table import NftTable
from .detail import NftDetail
from .summary import NftSummary

__all__ = ['NftHero','NftTable','NftDetail','NftSummary']

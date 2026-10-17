"""Primitive NFT catalog contract; nested scanner evidence retains its spelling.

No observation is inferred from a projection clock. All summary counts concern
observed records, not an exhaustive index unless coverage independently says so.
``None`` inventory means unread; ``[]`` means observed empty. Build records use
the same optional families as collections, but cannot carry a contract address.
"""

NFT_KEYS = ('nft_rows', 'nft_build_rows', 'nft_summary', 'nft_selected',
            'nft_sources', 'nft_coverage', 'as_of')
NFT_ROW_FIELDS = (
    'id', 'category', 'chain_id', 'contract', 'project_id', 'name', 'symbol',
    'description', 'standard', 'deployment', 'jobs', 'sites', 'repositories',
    'launch_ids', 'launch_number', 'idmd_benefit', 'mint', 'stats', 'chain_reads',
    'read_block', 'activity', 'evidence', 'unknowns', 'code_hash', 'rule_review',
    'related_tokens', 'utility', 'utility_summary', 'utility_review', 'stage',
    'last_meaningful_at', 'sources',
)
NFT_BUILD_FIELDS = NFT_ROW_FIELDS
NFT_SUMMARY_FIELDS = ('deployed', 'building', 'mint_open', 'idmd_free',
                      'conditional', 'chains', 'mint_known', 'idmd_known',
                      'partial', 'observed_at')
NFT_SOURCE_FIELDS = ('identity', 'observed_at', 'provider_ts', 'block_number',
                     'block_hash', 'block_timestamp', 'state', 'coverage')
NFT_SOURCE_STATES = ('ok', 'partial', 'stale', 'unavailable', 'pending')
NFT_COVERAGE_FIELDS = ('complete', 'sources', 'warnings')

# These are nested source schemas, not translations. Adapter-specific stats,
# dependency evidence and route fields may extend them without losing provenance.
NFT_MINT_FIELDS = ('state', 'start', 'end', 'publicPrice', 'currency', 'limits',
                   'conditions', 'reportedTerms', 'gasIncluded', 'asOf',
                   'readBlock', 'routes')
NFT_ROUTE_FIELDS = ('name', 'state', 'conditions', 'price', 'currency', 'start', 'end')
NFT_BENEFIT_FIELDS = ('status', 'conditions', 'exclusive', 'evidence')
NFT_STATS_FIELDS = ('totalMinted', 'totalSupply', 'maxSupply', 'holders', 'holdersSource')
NFT_UTILITY_FIELDS = ('kind', 'title', 'description', 'status', 'conditions', 'evidence')
NFT_TOKEN_FIELDS = ('symbol', 'name', 'roles', 'conditions', 'address', 'chainId',
                    'status', 'evidence', 'onchain')
NFT_LINK_FIELDS = ('label', 'url')
NFT_JOB_FIELDS = ('id', 'title', 'url', 'status')

NFT_FILTER_DEFAULTS = {'chain': 'all', 'stage': 'launched', 'mint': 'all',
                       'idmd': 'all', 'utility': 'all', 'search': '', 'sort': 'newest'}
NFT_FILTER_VALUES = {
    'chain': ('all', 'ethereum', 'robinhood'),
    'stage': ('launched', 'building'),
    'mint': ('all', 'open', 'route-open', 'closed', 'not-started', 'sold-out',
             'ended', 'paused', 'unconfigured', 'auction / delivery', 'conditional',
             'awaiting-season-end', 'awaiting-finalization', 'blank-season', 'auction-open', 'unknown'),
    'idmd': ('all', 'yes', 'conditional', 'no', 'unknown'),
    'sort': ('newest', 'name'),
}
# Utility choices are "all" plus actual row utility kinds, not a frozen taxonomy.
NFT_WIDGET_SIGNATURES = {
    'NftHero': ('nft_summary',),
    'NftTable': ('nft_rows', 'nft_build_rows', 'as_of'),
    'NftDetail': ('nft_selected', 'nft_sources', 'nft_coverage'),
}

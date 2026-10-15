"""Primitive contract for the selected-token dashboard.

``token`` retains the overview's existing token fields and source clocks.
Unknown lists are None; a successful empty read is []. Contributors are accepted
non-oracle seats, deduplicated by (seat, role, job_id). The hero counts distinct
seats, with a lower-bound marker when contributor coverage is partial, even
after that evidence becomes stale.
"""

SNAPSHOT_KEYS = ('token', 'launch', 'contributors', 'artifacts', 'sources', 'as_of', 'is_mock')
LAUNCH_KEYS = ('id', 'number', 'chain_id', 'status', 'verdict', 'objective',
               'recorded_ts', 'repo_url', 'site_label', 'site_ens_name')
CONTRIBUTOR_KEYS = ('seat', 'role', 'job_id', 'state', 'stage')
ARTIFACT_KEYS = ('kind', 'name', 'address', 'chain_id', 'site_label', 'site_ens_name')
SOURCE_KEYS = ('state', 'read_ts', 'partial')
SOURCE_NAMES = ('launch', 'contributors', 'artifacts')
WIDGET_SIGNATURES = {
    'DetailHero': ('token', 'launch', 'contributors', 'sources', 'is_mock'),
    'LaunchSummary': ('token', 'launch', 'sources', 'is_mock'),
    'ContributorTable': ('contributors', 'sources'),
    'MarketPanel': ('token',),
    'PositionPanel': ('token',),
    'ArtifactTable': ('token', 'artifacts', 'sources', 'is_mock'),
}

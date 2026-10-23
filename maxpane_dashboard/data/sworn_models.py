"""Frozen primitive boundary for the read-only Sworn explorer.

``select(value)`` accepts a decimal token ID or original claimant address;
None selects the latest minted card. Rows are a bounded newest-first page
around the selected token. Unknown row family counts remain None.

Selected: token_id, claimant, holder, minted_at_block, metadata, art, block,
observed_at. Metadata is the bounded onchain tokenURI JSON (including traits,
community IDs, attributes and oracle evidence). Art is prepared on the reader:
png (base64), pixels (128x128 RGB hex strings), hash (content identity).
Claimant and current holder always retain their distinct meanings.
"""

SWORN_KEYS = (
    'sworn_supply', 'sworn_rows', 'sworn_selected', 'sworn_selection',
    'sworn_error', 'sworn_block', 'sworn_observed_at',
)
WIDGET_SIGNATURES = {'SwornExplorer': SWORN_KEYS}


def empty_payload():
    return {**dict.fromkeys(SWORN_KEYS), 'sworn_rows': []}

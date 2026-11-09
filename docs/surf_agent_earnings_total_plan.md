# EARNINGS wallet total footer

2026-11-09. Tier 2 only because this adds a field to the AGENT hero contract.
One small work package; the root session implements it, followed by one final review.

## Specification

The EARNINGS inner footer changes from `x new` to `x total`. Count distinct
`(chain_id, token_address)` assets in the current owner's validated explorer
earned table across the existing production-network policy (Ethereum, Base,
Robinhood). Exclude testnets, unrecognized networks and held allocations without
a token address. Include builder, swarm and early rewards regardless of the
selected seat's work status or claim status. Preserve the existing seat-specific
central number and recent-work metadata. Explain the wallet/mainnet scope on hover.

Unknown sources remain unknown internally, with the existing card retention and
identity-reset behavior. Reuse the earned-table read and cache; add no requests.
No layout pin, new dashboard or endpoint changes are needed.

## Implementation and validation

Root owns `surf_agent_card_sources.py`, `surf_agent_hero.py`, `surf_models.py`,
`widgets/surf/agent_rack_hero.py`, their focused tests and composing screen test.
The shared `widgets/surf/news_hero.py` caption classifier also needs `total` in
its numeric vocabulary so a failed refresh retains the last observed total.

1. Add failing tests for deduplication, production/test networks, shared rewards,
   independence from accepted work, source states, owner switches and the footer.
2. Compute `wallet_total` from validated owner rows, pass it through the primitive
   hero contract, render `x total`, and explain its scope on hover.
3. Render actual public data at 149x45 before review. Check the largest allowed
   count at narrow widths and preserve the existing geometry.
4. Run touched/composing tests and fast guards; prove the network filter and footer
   assertions fail when mutated. One final review; address substantive findings.

All source edits are in this package; there are no independent implementation
packages to delegate. Existing unrelated untracked files remain untouched.

## Completion

Implemented and rendered with public data: `513 total` at 149x45. Focused tests
and mutation checks passed; final review Approved with no findings. Three
unrelated broader-check failures reproduced on baseline `a96b2c83` and are
recorded in `surf_swarm_followups.md` with the validation counts.

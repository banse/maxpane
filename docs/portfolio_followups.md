# PORTFOLIO follow-ups

The owner-approved overview is implemented with live balances, verified ready
claims, wallet-agent association and shared market/liquidity enrichment. The
standalone Textual demo remains offline. Remaining source limits:

- Supply verified remaining-position USD cost basis before enabling numeric
  live P/L. Define acquisition/disposal, transfers/rewards and historical USD
  accounting before emitting a basis; no unbounded crawler is included.
- Unsupported-chain launches keep wallet discovery explicitly partial. Add a
  chain only with verified keyless sources and appropriate explorer support.
- Earned enumeration covers ready/locked allocations, not full historical claimed
  inventory. Known allocations continue to be checked after leaving that list.
- Distributors above eight rounds remain unavailable under the bounded reader.
  Expand that budget only with measured need and retained verification semantics.

Verification environment: color assertions require `NO_COLOR` to be unset.
The application continues to respect the user's normal color preference.

Package reviews A/B/C/D approved after focused fixes to shared enrichment union
and per-allocation freshness. Mutation probes cover artifact decoding, decimals,
chain identity, Merkle verification, unlock/claimed state, cancellation and
A→B→A wallet generations. Final integration review approved after a captured
claim exposed an ISO/numeric unlock-time mismatch. Normalization now happens
at the manager boundary; the mounted-detail regression kills its removal.

Verification: 461 touched/composing tests passed in parallel before final review;
68 relevant tests passed after the timestamp fix, including the new regression.
Fast guards: 124 passed. Registration mounts: 81 passed. Live address sweep,
panel dispatch and claim-priority checks passed. The populated live capture
re-sweep over 138–150 columns and 28–38 rows retained the 145×35 boundary.

Minor presentation follow-up: the inherited empty table placeholder clips in
the TOKEN column. The full empty/unknown state remains visible in the title;
shorten the placeholder when that table adapter is next changed.

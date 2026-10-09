# SWARM TOKENS panel order and paired liquidity

Approved request (2026-10-10): retain the heroes first, then one row containing
Activity, Newly Launched, Best Plays (left to right), with All Tokens below.
Replace the liquidity hero's position counts with paired IMD then paired ETH
totals. Newly Launched replaces LP STATE with PAIRED LP using the table formatter.

Tier 2 because the metric contract changes. One root implementer owns this small
change; under 1,000 production lines, so one final scoped review only.

1. Extend the pure filtered projection and metric keys with independent IMD/ETH
   paired sums and incomplete-coverage state. Sum only current finite nonnegative
   balances; keep successful zero distinct from unavailable. Other currencies
   are excluded; no conversion. Incomplete known sums carry `≥` in the hero.
2. Reuse `_paired` for the new Newly Launched column. Reorder existing widgets
   and transfer the summary row's spacing below it. Keep CSS copies identical,
   existing keyboard interaction, filters, source reads and table columns.
3. Verify filtered totals, unknowns and exact rendered order/values. Render real
   data at 149×45, then recheck the measured boundaries and update their record.
   Mutation-check aggregate semantics and both layout-pin directions. Run only
   touched/composing tests and fast guards; no full suite or registration changes.
4. One final review, bounded fix wave if needed, then commit on the existing
   dedicated branch. Root owns production, tests and docs; reviewer changes none.

# Hub card titles and global supply

Owner request: POOL4 inset `IMD PRICE`; token card outer title `LAUNCHES`,
inset `TOKENS`; PROTOCOL inset `IMD BURNED`, footer `x% of supply`.
Keep routes, digits, counts, meters, geometry and existing activity colors.

## Source and contract

The official https://imd.fun/token/ page's supply reader uses Base FP
`totalSupply()` as the remaining global supply (`left`). Its Ethereum and
Robinhood OFTs represent FP locked in the Base adapter, so adding those supplies
would double-count backing. Read the existing FP address through the existing
SwarmBaseClient state pool, batching totalSupply and decimals. Never hardcode
10 million or decimals; never substitute Ethereum supply. The captured keyless
batch is `tests/fixtures/surf/hub/base_supply.json` (2026-10-10 UTC).

Add `supply` to hub source envelopes, payload `{total_supply: positive number}`.
Use the existing source lifecycle and persisted validation, 600-second cadence
while the hub is visible. Reuse the retained Base client and shutdown path.
Failures retain last-good with its own clock/state; no network in projection.
Footer is current displayed protocol burned / global remaining supply, two
decimal places; tiny positive values use `<0.01%`. Stale supply adds `~` and
discloses state/read time in card detail. Missing/invalid supply, missing burns
or explicit testnet burn data give `unavailable`; no Ethereum fallback.

## Implementation and verification

Tier 2, under 150 production lines. Session owns all files, sequential packages:
source contract and offline tests; existing Base client and manager integration;
card projection and titles. One final scoped review after the live 149×45 render.
No parallel implementation or extra review seats needed for this small change.

Tests: fixture-backed read/decimals/invalid replies; independent task/cadence/
stale clocks/cache; percentage denominator and fallback; composited labels,
digits and footer at 149×45 and existing minimum. Mutation proof for decoding,
denominator and refresh. Touched/composing tests and fast guards before local
commit. No push, full suite, new endpoint pools or layout pin changes.

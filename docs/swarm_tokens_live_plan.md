# SWARM TOKENS live-data integration

The owner approved the native 149×45 design and requested real data. Keep the
existing four heroes, twelve-column table with a 20-character price sparkline,
three supporting widgets, native filter editor and hub route. All production
chains remain eligible; default filter is All. No new top-level dashboard key.
Work stays on `feature/surfboard-hub-9`.

Tier 2: live data clients, a manager and primitive contract extensions. Target
under 1,000 changed production lines: catalogue/manager ~400, market/history
client ~300, shared-source accessor and UI adaptation ~250. Reassess the actual
diff; use one final review only under the repository's small-Tier-2 exception.
No Superpowers. No signing, API keys, dependency additions or networked tests.

## Architecture decision

Use a dedicated `SwarmTokensManager` which borrows a narrow, public snapshot
from the existing `SurfManager`. The adapter owns catalogue and market requests,
their bounded caches, and conversion into the existing token contract. It never
closes the borrowed SurfManager. The app or retained hub owns and closes the
adapter once; returning to the hub does not leak HTTP clients or reset progress.

Two alternatives were considered:

- Putting every source into SurfManager would extend an already large shared
  collector and make unrelated SURF screens pay for market enumeration.
- An entirely independent manager would duplicate the verified launch checks,
  receipt decoding and liquidity calculation, creating conflicting answers.

The small adapter preserves the established launch evidence while keeping the
new source requests local to this feature. Do not call the full
`SurfManager.fetch_and_compute()` from this nested screen. Do not repeat
provenance or liquidity math in the new manager.

## Source boundary and evidence

Root owns this synchronous, nonblocking accessor:

```python
SurfManager.swarm_tokens_source(catalogue=None) -> {
    "rows": list[dict] | None,  # enriched, untruncated swarm_launch_rows
    "as_of": float | None,     # launches route's successful read timestamp
    "pool_ids": dict[str, str] # launch UUID -> validated initialize.pool_id
}
```

A complete catalogue seeds the existing bounded evidence loop, so older tokens
receive refreshed evidence without a second collector. Newer catalogue versions
win over an older cached head. It offers only the existing launch tier when that tier is due and returns its
current cache. It reuses `_swarm_launch_keys()`, existing launch-tier
single-flight scheduling and slot clocks. A launch-list clock does not certify
liquidity freshness: keep the independent `liquidity.read_ts` on each row.

The dedicated catalogue client subclasses `SwarmClient` and adds its own
pagination method. Preserve the existing board's `fetch_launches()` latest-100
contract. Root's live probe on 2026-10-09 returned 414 rows for `/launches` with
`limit=500`; `before=<launchNumber>` is exclusive. An ISO cursor returned 400
and `offset` was ignored. These observations justify a numeric descending
cursor, not a fixed claim that 414 is the total forever. Captures are currently
under `/tmp/swarm-tokens-live/`; implementers commit small representative fixture
payloads under `tests/fixtures/swarm_tokens/` before writing decoder tests.

Enumerate until an empty/short valid page. Reject repeated/nondecreasing cursors
and malformed pages. Bound each refresh and retain cursor progress if a future
catalogue requires more work. A failed or capped scan is explicitly partial,
never a complete empty catalogue. Full and partial results must not erase a
previous complete snapshot. Revisit the head on subsequent refreshes, and give
retained old launches a bounded route to updated metadata.

Join shared evidence using launch UUID; establish token identity using numeric
chain ID plus normalized token contract address from an artifact with role
`token`. A ticker, artifact display name, list position or assumed chain never
identifies a token. Include deployed tokens on confirmed production chains;
exclude testnets and entries with no valid deployed token artifact. Deduplicate
multiple launch records for one chain/address deterministically. Keep historic
deployed tokens visible even if market providers do not index them. Production
chain support is Ethereum (1), Base (8453) and Robinhood (4663) in the current
launch integration; unsupported future chains need an explicit classification.

The market worker researches/probes keyless snapshot, historical-price and
recent-trade endpoints before freezing that client's normalized return shape.
Source selection remains an implementation dependency, not a claim that every
chain/token has indexed market data. Match both chain and exact token address;
validate the returned pool belongs to that token. Preserve price, price change,
market cap and FDV as distinct fields. Never replace absent market cap with FDV.
Never sum duplicate pool metrics or treat one selected market as all markets.

## Primitive contract additions

Root freezes additions in `data/swarm_tokens_models.py` before integration.
Retain current widget signatures wherever possible. The dedicated manager's
`fetch_and_compute()` returns the existing snapshot plus source-health metadata;
the screen still calls pure `project_snapshot()` for every filtered panel.

- Live token `id` becomes `chain_id:lowercase_address`; keep numerical
  `launch_id` for display and retain launch UUID for joining facts.
- Add validated chain/address/pool identifiers needed by detail links. Unknown
  addresses remain absent. Shared explorer/copy helpers own every displayed
  address. Pool IDs that are not addresses are not token/address links.
- Keep independent per-row market, history and liquidity read timestamps with
  source state sufficient to distinguish current, stale, unsupported and not
  yet read. Propagate an aggregate source/coverage summary through projection
  for headings/status/details; never introduce another row above the heroes.
- `as_of` is the injected projection clock for age and rolling windows, not a
  substitute for a source read timestamp. Unknown launch time is `None`; pure
  sorting/new-launch logic must tolerate it and never invent an age.
- First catalogue failure yields unavailable tokens/metrics, not zero tokens.
  A successful empty selection remains distinguishable. Partial enumeration
  displays coverage; hero totals and Best Plays describe the loaded population.
- `None` is an unavailable measurement; numeric zero is a successful zero.
  Preserve independent source failures and stale last-good values.

The price sparkline represents actual comparable samples within its disclosed
24h window. Sort/validate timestamps, reject invalid points and retain gaps
without compressing them into fabricated regular history. Use imported shared
series coercion for persisted points. A new or unsupported token may show
`new` or `--`; never seed history with synthetic prices. A selected market's
trade window is recent, not complete chain-wide trading. Activity may include
verified launch events when trades are unavailable, with that scope visible.
Stable activity identity includes chain and source event identity; deduplicate
before applying the same token filter used by the table and heroes.

LP state remains the observed launch position, independent of market-provider
USD liquidity. Reuse existing position amounts, live decimals and range facts
to map two-sided/token-only/quote-only/withdrawn/unknown. Unknown or stale
liquidity cannot silently become a current two-sided state. Keep state context
in Newly Launched, Best Plays markers, filters and details; do not reintroduce
the removed main-table LP STATE column.

## Work packages and ownership

| Package | Owner | Files | Dependency |
|---|---|---|---|
| A — contract/accessor | Root | `data/swarm_tokens_models.py`, `data/surf_manager.py`, focused accessor/contract tests | Source evidence above |
| B — catalogue/manager | One data implementer | New `data/swarm_tokens_client.py`, `data/swarm_tokens_manager.py`, dashboard-specific cache if needed, corresponding data tests, catalogue fixtures | Frozen A contract; normalized C contract |
| C — market/history/activity | One market implementer | New `data/swarm_tokens_market.py`, corresponding data tests, market fixtures | Validated endpoint/identity evidence |
| D — projection/UI/integration | Root | `analytics/swarm_tokens.py`, `screens/swarm_tokens.py`, `screens/surfboard.py`, dashboard-owned widgets/detail, hub card presentation, relevant tests; `app.py` only if lifecycle ownership requires it | A/B/C |
| E — acceptance/docs/review | Root; one final reviewer | PRD/mechanics/followups/README as needed; explicit task files only | Actual live render and focused verification |

B and C may run in parallel after agreeing their normalized interface; they
own disjoint production and fixture files. Root is the sole shared-file owner.
Do not change other agents' files: report cross-package issues to root. Each
implementer writes failing fixture-backed tests, then the smallest implementation
and refactors once green. No implementer or reviewer spawns further agents.

The existing offline `python -m maxpane_dashboard.demos.swarm_tokens` remains
deterministic, network-isolated and unmistakably MOCK DATA. The hub opens the
live manager instead; demo/live labeling is selected from the snapshot or
explicit provider mode, never inferred from whether some market fields exist.
Retain native filtering, selection by stable identity, detail/back navigation
and the 30s screen cadence. Client TTLs and bounded work prevent filters or
sorting from triggering a full network sweep. Source failures never inject
demo records into a live screen.

## Acceptance and verification

1. Capture real payloads manually; all automated tests use fixture transports
   and an injected clock. Prove numeric pagination, chain/address identity,
   exact token/pool matching, correct market-cap semantics, independent freshness,
   partial reads and last-good retention. Mutation-proof changed decoder and
   concurrency behavior with `scripts/mutate.py`.
2. Check shared source access schedules only the due launch tier, is
   nonblocking/single-flight, returns untruncated rows and cannot close or mutate
   the shared SurfManager. Check live-manager cleanup and repeat hub navigation.
3. Verify production/testnet separation, duplicated tickers/addresses across
   chains, known zero versus unavailable, price-history gaps and unsupported
   markets, event deduplication and common filtered populations. Keep the demo
   contract/no-network tests green.
4. Root shows the actual live 149×45 render before final layout measurements,
   documentation or review. Preserve the approved layout; if a measured pin
   changes, re-sweep its boundary and prove both mutation directions. Address
   cells/links get the required address sweep. No new mandatory metric depends
   on a source that has only been tested with invented payloads.
5. Before commit, run touched tests and composing files once with isolated HOME,
   fast non-mounting guards, and registration checks only if relevant surfaces
   changed. No full suite. Final reviewer receives this scoped diff and named
   data-integrity risks; one fix wave and one scoped rereview for production
   fixes. Minor-only findings go to followups. Commit locally; no push.

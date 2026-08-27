# FWA Ecosystem Dashboard — Product Requirements

**Working title:** `FWA NETWORK`
**Target:** Extend the existing MAXPANE FWA screen
**Chain:** Ethereum mainnet (`chainId = 1`)
**Date:** 2026-08-28
**Status:** Proposed; implementation starts only after direction approval

Source research: [`fwa_ecosystem_research.md`](fwa_ecosystem_research.md)

## 1. Product decision

Keep the existing purchaser-focused **PULLS** terminal intact and add one whole-body
**NETWORK** mode to the same FWA screen.

The new mode answers:

> What is alive across FWA, where are ETH and `$FWA` moving, and which downstream
> products are verifiably connected right now?

This is the KISS option: one dashboard subject, two clear lenses, one data refresh. It
avoids a giant all-at-once screen and avoids adding a top-level dashboard for every FWA
integration.

```text
FWA SCREEN
├── PULLS    existing gacha/purchaser terminal; unchanged default
└── NETWORK  platform + tokenomics + drops + verified integrations
```

Suggested binding: `e` toggles `PULLS ↔ NETWORK`. The screen composes both bodies once and
hides one, following the existing whole-body mode precedent. The existing `c` control
continues to work inside PULLS only. The right status label names the visible mode and the
reciprocal `e` action; the standard left-side freshness remains intact. The final copy must
be measured at 143 columns.

## 2. User and job

Primary user: an ecosystem observer, token holder, builder, or researcher who wants a
chain-backed operational picture without visiting several sites or trusting stale indexes.

Core jobs:

1. See whether the FWA platform is active and healthy.
2. Understand the live fee → buyback → reward/burn flow.
3. Track every FWAIR launch and its actual downstream position state.
4. Compare verified products built on FWA without mixing their accounting.
5. Spot stale APIs, parameter drift, paused contracts, missing distributor rights, or
   changed runtime code.

## 3. Scope

### V1 in scope

- canonical economic graph: FWA core, FWARewards, token, hook, claim, splitter, and FWAIR;
- slow-tier integrity coverage for every official deployment, including VRF service,
  transfer escrow, ERC-20/token wrappers, renderer, and whitelist authority;
- platform queue, escrow, refund, crown, and settlement configuration;
- supply, burned-since-genesis, live buybacks, routing, fee-funded rewards, and the ended
  emissions state;
- all FWAIR launches enumerated from the manager;
- PullPool current state plus outstanding legacy liabilities, GroupPull, and standing
  orders;
- latest MegaRip campaign plus compact comparison and outstanding claims for prior versions;
- FWAP v2 plus v1 outstanding liabilities;
- block/freshness/source health for every group;
- existing keyless market context as non-load-bearing enrichment.

### V1 out of scope

- signing, approving, buying, pulling, claiming, or submitting any transaction;
- API keys or copied public-site credentials;
- wallet-specific claimables and portfolio accounting;
- claims that the integration manifest is an exhaustive list of all third-party projects;
- profit forecasts or a synthesized “ecosystem score” without a defensible unit;
- a new indexer service or backend dependency.

Wallet-specific rewards are a possible later mode after a separate privacy and UX decision.
V1 still covers global reward pools, credits, distributor permissions, and project-level
outstanding liabilities.

## 4. Information architecture

Target layout at the application-wide 143-column pin:

```text
┌ FWA NETWORK · state #25,849,738 · CHAIN LIVE · 1 SOURCE STALE ──────────────┐
│ PLATFORM                      │ $FWA FLOW                 │ NETWORK         │
│ 6,185 active · queue 3/3      │ 986.38m · 1.362% burned   │ 2 drops         │
│ pull .0723Ξ · crown 3.622Ξ    │ buyback 1 block ago       │ 3 families      │
├──────────────────────────────────────────────────┬──────────────────────────┤
│ VALUE FLOW                                       │ FWAIR DROPS              │
│ PROTOCOL ETH ─▶ BUYBACK ─▶ 767.71 FWA            │ #1 COMPLETE 111/111      │
│                     ├─ 40% PURCHASERS            │    terminal 110/111      │
│ caller 0.5% gross ◀┤─ 30% DEPOSITORS             │ #2 COMPLETE 1000/1000    │
│                     └─ 30% BURN                  │    terminal 448/1000     │
│ emissions ENDED · fee-funded rewards LIVE        │ chain newer than index   │
├──────────────────────────────────────────────────┼──────────────────────────┤
│ VERIFIED INTEGRATIONS                            │ NETWORK ACTIVITY         │
│ PullPool   refunding · 367 rounds · VERIFIED     │ buyback · 1 block ago    │
│ MegaRip 3  recovery 67.18% · CHAIN-READ          │ drop #2 terminal +1      │
│ FWAP v2    epoch 7 · 93.87Ξ NAV · API STALE      │ PullPool refunding       │
└──────────────────────────────────────────────────┴──────────────────────────┘
 updated 3s ago · source health         maxpane · fwa · network · e pulls
```

All figures in the wireframe are snapshot examples, not copy constants.

### 4.1 Hero — `FWANetworkHero`

Reuse the three-card `FWAHeroMetrics` structure and responsiveness.

| Card | Primary | Secondary |
|---|---|---|
| PLATFORM | active listings | pull quote, queue, crown pot |
| `$FWA FLOW` | supply and burn | last buyback age/size, routing state |
| NETWORK | launch/project counts | healthy/degraded/unverified counts |

When a value is unavailable, the card says `n/a`; it never turns a failed read into zero.

### 4.2 Signature panel — `FWAFlowRail`

The visual identity is a compact live value-flow rail rather than another generic metric
grid:

```text
fee ETH → buyback execution → FWA bought → purchasers / depositors / burn
                         ↘ caller ETH bounty
```

The panel pairs current configuration with the latest observed execution. It must show both
because configuration alone does not prove that a loop is running. Rows:

- latest `Bought` gross ETH, swap spend, FWA bought, caller reward, age, transaction;
- latest `BuybackRouted` purchaser/depositor/burn amounts;
- configured route bps and sum invariant;
- supply burned since genesis and 24h/7d burn when indexed history is complete;
- emissions status and ongoing fee-funded reward balances;
- protocol/token/hook integrity state.

Flow direction, glyphs, labels, and values convey meaning without relying on colour.

### 4.3 `FWAIRDropBoard`

Enumerate `1 .. nextLaunchId - 1`; do not hardcode names or two rows. Each row contains:

```text
id · collection · phase · supported/tokenCount · launched · terminal · backing · claims
```

At narrow widths, shed claim/reserve columns first and advertise `‹ widen`. Phase,
support-window status, funding, and terminal progress stay separate.

### 4.4 `FWAEcosystemRegistry`

One primary row per current product family/surface:

```text
family · current surface · lifecycle · primary scale · ETH · FWA · source badge · age
```

Initial groups:

- PullPool;
- GroupPull;
- standing orders;
- MegaRip;
- FWAP.

The primary row uses the current production version. A compact indented legacy-liability
row appears only when an older version still holds claimable/accounted ETH or FWA, or has
an integrity warning. Finalized versions with no outstanding state remain research/history,
not permanent screen rows. MegaRip's row may compare the three known gross-recovery ratios
in one fitted detail cell without treating them as investment returns.

Lifecycle and primary scale are adapter-specific. A PullPool round count is not comparable
to a MegaRip gross-recovery ratio or FWAP NAV, so the UI does not collapse them into one
ranking or composite score.

Badges:

- `VERIFIED` — verified source plus expected runtime/dependencies;
- `CHAIN-READ` — callable ABI/events and expected dependencies, source unverified;
- `API STALE` — optional project API lags its own source block/freshness contract;
- `INTEGRITY` — codehash or dependency mismatch;
- `DEGRADED` — current read failed; last-good value includes its age.

### 4.5 `FWANetworkActivity`

A bounded, escaped RichLog merges normalized events without erasing their origin:

```text
time · FWA / DROP / PULLPOOL / MEGARIP / FWAP · event · amount · tx
```

Priority events:

- buyback and routing;
- drop created, supported, launched, terminal, and claimed;
- PullPool round opened/settled/voided/refunded/rewarded;
- MegaRip funded/locked/pulled/settled/finalized/claimed;
- FWAP contribution/redemption/epoch/reward activity.

Project adapters normalize to a shared presentation row but retain raw event identity and
contract version for deduplication.

## 5. MVC architecture

The implementation follows the repository's existing Textual MVC equivalent:

```text
MODEL / DATA
  state clients + log clients + cache + frozen row contracts
          ↓
CONTROLLER
  thin composite manager → one flat umbrella presentation contract
          ↓
VIEW
  FWAScreen mode switch → primitive-only widgets
```

### 5.1 Model and data modules

Proposed focused modules:

```text
maxpane_dashboard/data/
├── fwa_ecosystem_models.py
├── fwa_tokenomics_client.py
├── fwa_drops_client.py
├── fwa_ecosystem_cache.py          # only if existing FWACache cannot hold namespaces
├── fwa_ecosystem_manager.py
├── fwa_composite_manager.py        # thin concurrent merge; no domain calculations
└── fwa_projects/
    ├── base.py
    ├── registry.py
    ├── pullpool.py
    ├── megarip.py
    └── fwap.py
```

Reuse `rpc_common`, Multicall3, `safe_call`, log paging, markup safety, and existing FWA
market/cache helpers. Do not keep growing the 2,000+ line `fwa_manager.py`. A thin composite
manager fetches the existing PULLS manager and the new NETWORK manager concurrently and
merges their complete flat contracts; it performs no domain calculations.

Each project manifest entry pins:

```text
family, version, contract role, address, deployment block,
ABI resource, expected runtime codehash or verified-source expectation,
expected canonical dependency map for only the roles present in that version
```

The registry is curated discovery metadata. All mutable state remains live.

### 5.2 Controller

`FWAScreen` owns mode state, visibility, and widget update dispatch. It calls one composite
manager and does not calculate tokenomics, project accounting, or source fan-out. Both
bodies are composed once; switching does not refetch.

Refresh groups run concurrently and fail independently:

```text
core state | token/reward state | core logs | drops | PullPool | MegaRip | FWAP | market
```

The outer refresh always returns the complete frozen key contract. Last-good data carries
its original block/time and a stale marker.

The composite manager obtains one network state block and passes it to every direct-chain
state client. Logs end at that block; project APIs retain their own source blocks. Existing
PULLS and NETWORK values are never presented as one block-consistent calculation unless
their recorded blocks agree.

### 5.3 View

New widgets import no client, manager, ABI, RPC, or analytics module. They accept primitives
and typed row dictionaries only. All third-party names/symbols/text are escaped.

Use existing theme variables and terminal typography. The deliberate visual signature is
the value-flow rail, not a new palette or decorative frame system.

## 6. Presentation contract

The exact key tuple will be frozen in an approval amendment before implementation
planning. Proposed groups:

```text
meta
  as_of, network_state_block, chain_head, degraded, integrity_warnings

hero
  active_listings, pull_quote_eth, pending_count, unsettled_count,
  crown_pot_eth, token_supply, burned_amount, burned_pct,
  last_buyback_age_s, launch_count, project_family_count, project_health_counts

flow
  buyback_config, latest_buyback, latest_route, burn_series,
  emissions_status, reward_balances, flow_source_status

drops
  list[DropRow]

projects
  list[ProjectRow]

activity
  list[NetworkEventRow]
```

Common row metadata:

```text
source_kind: chain_state | chain_log | project_api | market_api
measurement: measured | derived | estimated
block_number: int | None
observed_at: int | None
stale: bool
verified_source: bool | None
integrity: ok | warning | mismatch | unknown
```

`None` is the only unavailable numeric state. Zero remains a valid measured value.

### 6.1 Contract-freeze gate

The groups above define the product payload but are not yet the parallel-work interface.
After the user approves the screen spine and V1 scope, an amendment must freeze:

- one exact umbrella top-level key tuple composed with the existing `FWA_DATA_KEYS`;
- every drop/project/activity row-key tuple;
- every new widget method signature;
- source-status enums and units for every numeric field.

No implementation plan or work package may be assigned before that amendment is approved.
The umbrella payload remains flat and is returned by one `fetch_and_compute()` interface.

## 7. Data acquisition

### State

- PublicNode primary state RPC, existing state fallbacks.
- One pinned block shared by all direct NETWORK state groups; Multicall where contracts
  permit. Every row still carries its own block provenance.
- Do not use dRPC for quote/state calls that require transaction context.
- Read dependency addresses and runtime codehashes on the slow tier.

### Logs

- Separate log endpoint pool.
- Fixed deployment block per contract version.
- Bounded paging, adaptive ranges, deduplication by `(chain, tx_hash, log_index)`.
- Persist a watermark per adapter/version/topic group.
- Reorg overlap and block-hash check before advancing the watermark.

### APIs

- Existing DexScreener/GeckoTerminal/CoinGecko/DefiLlama clients remain optional context.
- FWAP's public snapshot endpoint can enrich inventory/projection rows only.
- An API must expose source block/time or be marked `unanchored`.
- No endpoint requiring a credential enters the source pool.

## 8. Refresh budget

| Tier | Cadence | Work |
|---|---|---|
| Fast | normal FWA refresh | core queue/quote, token supply/config, current project lifecycle |
| Medium | 30–120 s | recent events, drop/project rows, claim/accounting state |
| Slow | 5–15 min | bytecode/codehash, verified-source status, discovery manifest checks, market context |
| Historical | watermark-driven | 24h/7d flow aggregates and versioned campaign history |

Use the existing skip-never-queue refresh guard. Startup prefetch joins the first screen
refresh to avoid duplicated log counts.

Historical backfills, API enrichment, and slow integrity checks never gate PULLS first
paint. The composite manager starts them once in the background and returns PULLS plus the
latest complete NETWORK snapshot. If a NETWORK task has not completed, its last-good value
or `n/a` is returned; it is never awaited past the existing PULLS critical path. Each
adapter has an explicit request timeout, log-page cap, and per-cycle work budget.

## 9. Correctness and UX rules

- Chain beats docs and project API for mutable state.
- A source error never becomes `0`, `false`, “ended”, or “no activity”.
- `settlementDiscountBps = 9000` renders “90% payout”.
- `topListingShareBps = 50` renders “0.5%”, even while docs say 1%.
- Emissions render ended despite nonzero legacy rate getters.
- Caller bounty renders as 50 bps of gross buyback ETH; `gross = ethSpent + reward`.
- `weightedBackingTotal` is never TVL.
- PullPool and MegaRip economics never merge.
- Legacy/current histories never double-count frontend display offsets.
- A project with unverified source remains visible but visibly qualified.
- `CHAIN-READ` is the single badge for readable semantics whose source is unverified; the
  detail/provenance text spells out `source unverified`.
- `CHAIN-READ` requires non-empty runtime bytecode, a pinned ABI/topic set that decodes
  observed calls/logs, expected canonical dependency reads, and at least one accounting or
  lifecycle invariant. Frontend copy alone never qualifies.
- A runtime-codehash or dependency mismatch makes current semantic metrics unavailable;
  only explicitly dated last-known values may remain until the ABI is revalidated.
- Parameter drift means a change from a prior successful onchain snapshot or a broken
  contract-to-contract invariant. Stale documentation may be annotated in research but is
  never a hidden runtime alarm baseline.
- Stale values display their source age; stale APIs cannot overwrite chain values.
- No semantic state is conveyed by colour alone.
- Rows degrade at measured width tiers and advertise omitted content.
- No API keys, wallet secrets, signing, or transaction submission.

## 10. Testing and acceptance

All tests are offline with recorded fixtures.

### Model/data tests

- frozen output keys, widget signatures, and row schemas;
- strict integer wei until one presentation-boundary conversion;
- ABI selector/topic and vendored-address checks;
- codehash/dependency mismatch handling;
- buyback route invariant and event accounting;
- genesis supply/burn derivation;
- FWAIR enumeration with holes/failures;
- versioned project adapters and history deduplication;
- API-stale-vs-chain precedence;
- `None` propagation and last-good timestamps;
- bounded log paging, watermark, overlap, and reorg fixtures.

### Screen/widget tests

- PULLS remains the default and pixel/compositor contract does not regress;
- `_mode` and `_pulls_view` remain separate state: `e` swaps already-composed bodies
  without a network call, `c` is a true no-op in NETWORK, and `escape` returns to PULLS
  without forgetting the prior odds/activity slot;
- the footer uses the existing active-view surface and retains `updated Ns ago`;
- an in-situ width sweep around the measured boundary fails when the pin is either too low
  or too high; the actual binding panel owns `‹ widen`;
- measured row pin or `‹ taller` behaviour, `min-height` on `1fr` children, and stable
  scrollbar gutters on scrolling columns;
- resize re-tiering after body swaps and identical screen rules in
  `FWAScreen.DEFAULT_CSS` and `themes/minimal.tcss`;
- composited-output assertions, `rich.cells.cell_len` fitting for CJK/emoji/hostile names,
  fitted RichLog row budgets, and unambiguous DataTable headers;
- no wrapped one-row title/status content;
- correct `n/a`, stale, unverified, and integrity badges;
- semantic glyph/word labels in monochrome;
- Rich markup injection fixtures for project/collection/token text;
- every client receives an injected offline transport that raises on unexpected network
  access; age/staleness tests receive a fixed clock;
- recursively prove that new widgets import no `data`, network, ABI, clock, or I/O module;
- arbitrary parameter fixtures such as `8750` settlement and `75` crown bps prove the UI
  renders payload values rather than production constants;
- composite shutdown closes every child client exactly once.

### Acceptance scenarios

1. Core live, all project sources down: platform/tokenomics remain usable; project rows show
   last-good ages or `n/a`.
2. Project API stale, chain live: direct state wins and API badge is visible.
3. State RPC live, logs down: current values render; history/activity says unavailable.
4. Runtime codehash changes: affected adapter stops claiming verified semantics.
5. New FWAIR launch appears: a new row is discovered without a code edit.
6. MegaRip unverified: numbers render with `CHAIN-READ`, never `VERIFIED`.
7. Emission rate getters nonzero after end: hero/flow still says `EMISSIONS ENDED`.
8. Empty-cache history and a timed-out project adapter do not delay PULLS first paint.
9. One broken NETWORK widget does not prevent the other widgets from updating.
10. A FWAIR launch hole does not suppress later valid launch IDs.
11. Unanchored API data never appears as chain-current.

## 11. Alternatives considered

| Option | Benefit | Cost | Decision |
|---|---|---|---|
| Add every panel to existing PULLS body | no navigation | unreadable at 143 columns; mixed user jobs | reject |
| New top-level dashboard per project | maximum depth | fragmented FWA story; repeated plumbing/navigation | reject for V1 |
| Three modes: Protocol / Tokenomics / Ecosystem | explicit categories | tokenomics and ecosystem are causally linked; more state/navigation | defer |
| Existing PULLS + one NETWORK body | focused, reusable, minimal navigation | less per-project detail on first screen | **recommend** |

## 12. Approval checkpoint

Before implementation planning, approve or revise these three product choices:

1. retain PULLS as the unchanged default;
2. add one `NETWORK` body rather than multiple dashboards;
3. show current family rows plus only legacy versions with outstanding liabilities or
   integrity warnings;
4. treat the project list as `verified integrations`, beginning with PullPool/MegaRip and
   FWAP, rather than claiming exhaustive ecosystem discovery.

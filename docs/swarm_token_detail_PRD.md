# SWARM token dashboard

## Approved outcome

On 2026-10-15 the owner selected proposal **2, Built by Swarm**, for a dedicated
token dashboard opened by clicking a token or pressing Enter in SWARM TOKENS.
The dashboard explains the selected token's launch, contributing agents,
artifacts, market, and original launch position. Escape returns to the existing
overview with its applied filters, sort, scroll, and selected token preserved.
This is a nested dashboard; it adds no CLI game, hub card, or global shortcut.

Use the current Textual/Rich application, existing Surfboard card palette and
one-character inner text padding. Target the owner's **149 columns × 45 rows**.
Reuse the six equal, nine-row rack cards and borderless native panels. No new
dependencies, credentials, signing, trading actions, or state-changing requests.

## Approved information hierarchy

```text
SURFBOARD · $DEMO · Demo Token · ETHEREUM · #1844

PRICE          MARKET CAP       VOLUME           LAUNCH       CONTRIBUTORS       POSITION
$0.00124       $86.8k           $18.2k           #1844        8 seats              two-sided
+12.4% /24h                     24h              live                              420 IMD

LAUNCH                                                   MARKET · 24H
objective   Build a community token and public dashboard.   actual hourly price chart
status      live                                         price          $0.00124
verdict     swarm                                        change           +12.4%
recorded    15 Oct 16:42                                  buys / sells    121 / 63
site        demo                                         FDV               $124k
repository  owner/demo-token
                                                         LAUNCH POSITION
CONTRIBUTING AGENTS                                      DEMO               2.4M
seat        role         job          state              IMD                 420
#192        build        29b90556     accepted            fee                0.3%
#363        review       20286bd1     accepted            withdrawn            0%
#1207       review       c27ab1ba     accepted
#535        frontend     68b1c27f     accepted

ARTIFACTS
type        name                    address / destination
token       Demo Token              [token address] [copy]
contract    DemoHook                [hook address]  [copy]
site        demo                    demo.sites.imd.fun

esc tokens · r refresh
```

Numbers and identities above are illustrative, not captured data. The diagram
shows hierarchy rather than final terminal-cell measurements. Role labels and
state values come from proven source records; a frontend workflow stage must
not overwrite an actual build or review role.

### Rack cards

| Card | Main value | Supporting text |
|---|---|---|
| PRICE | Selected indexed pool's USD price | Signed 24-hour change |
| MARKET CAP | Reported market capitalization | USD; never substitute FDV |
| VOLUME | Selected indexed pool's 24-hour USD volume | 24h scope |
| LAUNCH | Selected launch number | Actual launch status |
| CONTRIBUTORS | Distinct accepted contributing seat IDs | Seats; partial count is a lower bound |
| POSITION | Original launch-position sidedness | Paired amount and asset |

Follow existing source-aware hero rendering. State, read time, and missing
values remain explicit. Zero is a successful measurement, while `--` means
unknown. Preserve existing active/inactive and warning card colors rather than
creating a second palette.

### Body panels

- **LAUNCH**: objective, status, verdict, launch-record time, current matched
  site, and source repository. Show the recorded time as recorded, not as a
  proven deployment timestamp. Long objective text wraps within a deliberate
  floor or becomes scrollable; arbitrary addresses in it use shared helpers.
- **CONTRIBUTING AGENTS**: seat, actual role, short job ID, and actual state.
  Keep workflow stage in the payload for distinguishing contracts/frontend
  work without changing the role's meaning. Rows represent accepted non-oracle
  seat/role/job tuples; the card counts distinct seats across those rows.
- **MARKET · 24H**: real hourly price samples and price, change, buys/sells, and
  FDV. This describes the selected indexed pool. Market cap and FDV remain
  independent. Missing sample buckets remain gaps. No invented history,
  interpolation over missing samples, or volume-based price chart.
- **LAUNCH POSITION**: token amount, paired amount/unit, fee percentage, and
  withdrawn percentage from the existing liquidity projection. These values
  do not describe all of the token's market liquidity.
- **ARTIFACTS**: type, name, and address or site destination. Include the token,
  valid helper contracts, and verified matched current sites, once each.
  Every displayed address uses the established copy and explorer helpers;
  site/repository links must pass existing safe-URL handling. Unknown chains
  get no guessed explorer target, and bytes32 pool IDs are not addresses.

## Source research and limits

The source baseline is [SWARM TOKENS research](swarm_tokens_game_mechanics.md),
[IMD Swarm API](imd_swarm_api.md), and the verified joins in
[launch contribution plan](surf_launch_contribution_plan.md). Existing source
code and committed fixtures refine the older API notes:

1. `data/swarm_tokens_manager.py::SwarmTokensManager` already produces a token
   identified by numeric chain plus normalized contract address. The live row
   carries launch UUID, market fields, hourly samples and timestamps, and
   original-position facts. Reuse those fields and their independent source
   state/read clocks; do not create a second quote or liquidity collector.
2. `data/swarm_tokens_client.py::SwarmTokensClient` inherits the keyless
   `SwarmClient` detail routes. `fetch_launch_jobs()` reads
   `/launches/{uuid}?light=1`; the response's `jobs[]` proves job membership
   without reward allocation payloads. The API document's older statement
   that `/launches` has no job ID describes the list response, not this detail
   route. Do not infer membership from objective text or nearby timestamps.
3. `/jobs/{uuid}` supplies actual nodes and workflow reference. The existing
   `data/surf_launch_contribution.py::_job` contract admits accepted
   non-oracle nodes. Preserve that meaning for this dashboard. A seat with
   multiple roles may have multiple rows but counts once in CONTRIBUTORS.
4. A frontend job can be absent from the launch's attached jobs. Admit it only
   after `/workflows/{uuid}` proves both the same contracts job and the same
   launch, following the existing `_workflow` join. Reuse validated identity
   parsing and oracle-node exclusions. Do not scan every launch or job.
5. Launch fields include `sourceRepoUrl`, artifacts, `createdAt`, and
   `updatedAt`. Current published sites carry `jobId`, `label`, `ensName`, and
   `namedAt`. Join sites only through a proven selected launch/job association;
   matching ticker, objective text, or naming resemblance is insufficient.
6. Existing market reads use DexScreener for quotes and GeckoTerminal for
   hourly history with a validated selected pool. Those sources may be
   unindexed, unsupported, pending, unavailable, or stale. Never promise a
   chart or capitalization for every token.

The current production population is inherited from the overview. No testnet
launches are introduced. The source has no new historical completeness claim:
this page describes one selected token and its proven launch associations.

## State, lifecycle, and interaction

- Open immediately using an immutable deep copy of the selected row; enrich in
  the background. A response for another token, chain, launch UUID, job, or
  workflow cannot overwrite the selection.
- The detail manager owns only its selected enrichment tasks. It may borrow
  the existing tokens manager/client and never closes them. Escape cancels
  owned work safely and does not turn cancellation into a failed source.
- Launch, contributor, and artifact reads each expose `state` and `read_ts`.
  `None` lists mean unread/unavailable; `[]` means a successful empty result.
  Failed refreshes retain last-good content with its original clock and stale
  status. Partially proven contributors are marked partial and the count uses
  `≥`; partial data must not look like the exact total.
- Manual refresh and normal polling reuse bounded source work. No network is
  awaited in a click/Enter handler. Reopening detail must not leak tasks or
  clients, and unrelated portfolio priority must remain intact.
- Mock entry points keep their explicit MOCK DATA marker and existing fixture
  values. No fabricated launch jobs, sites, repository, or artifacts are
  invented merely to fill the design, and mock mode performs no network I/O.
- Keep the existing popup class available for other callers, including
  Portfolio. Only the current tokens overview's open action changes route.

## Acceptance

1. Both click and Enter open the exact selected token's full dashboard; Escape
   restores the existing overview state and selected identity.
2. All six cards and five body sections are visible at 149×45. Contributor and
   artifact overflow remains scrollable. At smaller sizes, the screen exposes
   clipping/scroll hints rather than hiding required information silently.
3. A live, keyless 149×45 render is shown before final layout measurements,
   documentation pins, and review. Chart/source gaps are retained honestly.
4. Offline fixtures verify canonical identity, accepted-node filtering,
   deduplication, workflow/frontend association, current-site matching, safe
   addresses/URLs, partial/error/empty states, independent clocks, and task
   lifetime. No automated test reaches the network or actual clipboard.
5. Compositor checks verify real padding, card palette, chart gaps, captions,
   table cells, links, return navigation, and measured overflow behavior.

Implementation ownership and the frozen primitive contract are in
[the implementation plan](swarm_token_detail_plan.md).

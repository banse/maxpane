# SURF NFT Explorer implementation plan

Status: implemented and reviewed, 2026-10-17. Verification and source limitations
are recorded in [surf_nft_followups.md](surf_nft_followups.md).

Execution notes: file ownership and per-package reviews were preserved; local
commits are consolidated into one integrated delivery after the final review.
The real cold capture exposed starvation before chain proof; the early six-send
slice therefore also serves a due reviewed/background candidate when no row is
selected. A confirmed identity can paint before optional enrichment. Cached
filters and navigation stay passive. Collection adapter/source/token reads
share the coherent pinned inspection rather than a separate metadata-cache
layer; unfinished stages resume on normal offers, completed chain observations
use the 120-second TTL and non-NFT probes use 600 seconds.

**Goal:** add the NFT catalog and selected-detail screen, with IDMD/mint filters
and explicit Swarm/source relationships, and replace BOARDROOM's PROTOCOL card
with NFTS while preserving PROTOCOL on `p`.

**Spec:** [surf_nft_PRD.md](surf_nft_PRD.md). Research and inspected source:
[surf_nft_game_mechanics.md](surf_nft_game_mechanics.md).

**Architecture:** a nested SURFBOARD screen, a retained NFT manager, a persisted
catalog/evidence cache, bounded asynchronous public-source readers, and the
scanner's adapted deterministic rules. Existing client → cache → manager →
screen → widget boundaries remain. No tenth global dashboard, scanner subprocess,
local-checkout import, new service, or generic indexing framework.

**Stack:** Python ≥3.11, existing httpx/Textual/Rich, shared RPC/ABI/markup/address
helpers, pytest with committed fixtures and injected transports/clocks.

The `writing-plans` method structures this document; `CLAUDE.md` Tier 2 takes
precedence over the disabled superpowers execution, location and approval flow.
The owner selected the design after requesting its adaptation into MaxPane. The
controller can execute this plan without another routine design confirmation.

## Scope and architectural decisions

The catalog starts useful work with an empty cache and no aidude checkout. It
immediately paints retained evidence, or an honest empty/loading frame on the
first run, and incrementally discovers live collections. A saved aidude catalog
is an explicitly identified seed/fixture, never the sole runtime data source or
an implicitly loaded user file. The installed application must stand alone.

The following source behavior is included, not a later enhancement:

- All supported-chain launch artifacts are inspected regardless of NFT wording.
- Jobs, workflows and historical publications contribute explicit relationships;
  full job details come through the shared `SwarmClient.read_job_detail` memo.
- Reviewed mint adapters, special cases, factory children, proven constructor
  references, related tokens and utility classifications retain scanner parity.
- Current chain identity/code/interface/receipt and rule hashes gate stronger
  conclusions. New or changed contracts stay unknown until their evidence exists.
- Searches and recent sites supplement discovery; neither replaces paginated
  publications or establishes exhaustive coverage.

Two alternatives were considered. Reading `catalog.json` alone is small and
fast, but cannot satisfy independent live discovery or current mint rules.
Running the complete batch scanner would retain its coverage quickly in code,
but carries unbounded history/getter work into navigation. The selected design
adapts its deterministic joins and interpreters, with resumable bounded I/O.
The cost is a larger data layer and explicitly partial results during backfill.

### Non-negotiable semantics

1. Collection identity is `(chain_id, normalized_contract_address)`; build
   identity includes explicit chain and project ID. Names and symbols never join
   deployments. Supported chains are Ethereum `1` and Robinhood `4663` only.
2. Deployment, NFT interface, mint route availability, IDMD benefit, utility
   evidence and personal wallet eligibility remain separate. No wallet
   eligibility simulation or transaction functionality is introduced.
3. Mint routes retain separate states/prices/requirements. Mandatory fees or
   burns are not free. Zero price excludes gas; snapshot claims do not become
   eligible through present ownership. Prices of ERC-20 assets require actual
   token decimals; no default `18` conversion inherited from scanner helpers.
4. Ever minted, live supply, maximum supply, ERC-1155 quantities and explorer
   holder estimates are distinct. Missing values remain `None`, rendered `—`.
5. Observation time, source update time, block time, last attempt and cache save
   time are separate. Completion of an old stage cannot renew its chain reads.
   Filters, selection, reopen and passive repaints never renew observations.
6. Source-failure states remain internal under the October 16 Surf override.
   Neutral timestamps, partial coverage and operational states remain visible.
7. Every external string is escaped/control-stripped at the widget boundary.
   All displayed addresses use shared copy/explorer helpers, with no guessed
   explorer for unknown chains. Websites/repos/jobs retain explicit provenance.
8. Read-only, keyless, no secrets, no network in tests, no real clipboard in
   tests. No paid IMD jobs, local runner invocation, signing or calldata builder.

## Contract to freeze first

`data/surf_nft_models.py` exports `NFT_KEYS`, `NFT_ROW_FIELDS`,
`NFT_BUILD_FIELDS`, `NFT_SOURCE_FIELDS`, `NFT_SUMMARY_FIELDS`,
`NFT_FILTER_VALUES` and `NFT_WIDGET_SIGNATURES`. The flat snapshot is:

```python
NFT_KEYS = (
    "nft_rows", "nft_build_rows", "nft_summary", "nft_selected",
    "nft_sources", "nft_coverage", "as_of",
)
```

Rows retain normalized scanner families rather than flattening away evidence:
`id`, `chain_id`, `contract`, `name`, `symbol`, `standard`, `deployment`,
`mint` (including `routes`), `idmd_benefit`, `stats`, `utility`,
`related_tokens`, `links`, `rule_review`, `sources`. A build has `id`,
`chain_id`, `project_id`, `name`, `description`, `stage`, `last_meaningful_at`,
`jobs`, `links`, `sources`; a build contract is absent until separately proven.

Each source observation retains its identity, `observed_at`, `provider_ts`,
optional `block_number`/`block_hash`/`block_timestamp`, internal `state`, and
coverage. `as_of` is projection time only. Summary contains deployed/build/open/
IDMD-free/conditional/chain counts plus coverage; it does not sum holders.
Unknown inventory is `None`; a successfully observed empty inventory is `[]`.

The manager interface is fixed before UI and data workers fork:

```python
class SurfNftManager:
    def __init__(self, *, swarm, client=None, cache=None, cache_path=None,
                 clock, monotonic): ...
    async def fetch_and_compute(self) -> dict: ...  # schedule, return cache
    def get_snapshot(self) -> dict: ...            # no I/O/task creation
    def select(self, identity: str | None) -> None: ...  # priority only
    def offer_hub(self) -> None: ...               # same bounded queue
    def catalogue_summary(self) -> dict: ...       # passive card projection
    def is_loading(self, view: str | None = None) -> bool: ...
    async def wait_pending(self) -> None: ...
    async def close(self) -> None: ...
```

`SurfManager.nft_manager()` constructs/retains this manager and passes its
existing SwarmClient. Only SurfManager closes that borrowed client. NFT owns and
drains its own tasks and closes only clients it constructed. Selection changes
prioritize new work without making old completions overwrite another identity.

`analytics/surf_nft.py` provides pure `project_snapshot(snapshot, *, filters,
selected_id)` and `select_rows(rows, *, filters)`. Widgets never import data.
Common chain/search/utility/IDMD/mint filters apply to the six headline totals
and both row populations. Stage chooses only which table population is visible;
it does not erase the other population's headline count. The filter summary
names that scope. Only `catalogue_summary()` and the BOARDROOM card remain
global and unfiltered. A filtered-out selection moves to the first remaining
stable row, or clears when none remain.

## Bounded read policy

These initial limits bound resource use; they are not speed measurements.

| Limit | Initial policy |
|---|---|
| HTTP envelope | At most 24 actual owned HTTP attempts plus reserved shared-job credits per cycle |
| RPC work | At most 256 logical read-only RPC operations per cycle |
| RPC batch | At most 32 operations; only where supported; Robinhood single-call fallback consumes the same envelope |
| Index pages | At most 4 pages/cycle, at most 100 records/page; strict progress checks |
| Job details | At most 8 admitted memo reads/cycle, further limited by remaining HTTP credits |
| Parallelism | At most 4 active requests, at most 2 to one host |
| Selected reserve | Reserve 6 HTTP credits and 64 RPC operations for selected enrichment when due |
| Background fairness | Reserve at least one admitted discovery page before spending remaining credits on selected work |
| Factory/item scan | At most 256 entries per collection/factory pass, resumable cursor with partial coverage at the cap |
| Deadline | 15 seconds per cycle; every request timeout is capped by remaining time |
| Retry behavior | Existing pacing helpers, bounded endpoint rotation, 429 `Retry-After` cooldown; no immediate retry loop |

A shared job read reserves the current two-host maximum before admission. A
cache hit may refund its reservation after the memo proves it started no new
read; a joined flight remains conservatively reserved. Tests separately record
actual transport requests and reserved credits. Never infer physical request
counts from a logical API callback or replace the shared client's transport.
Cancellation releases the NFT waiter, not another consumer's shared flight.

Use explicit resumable work records rather than a monolithic inspector call.
The record carries candidate identity, discovery revision, stage, pinned chain
block/header, completed read values, next getter/dependency/factory/item cursor,
and incomplete coverage. A successful stage advances its cursor before the next
budget check; quota/deadline exit preserves progress. An RPC/header failure never
mixes a replacement block with old values. If the pinned block becomes unusable
or the stage is older than 10 minutes, discard only that unfinished stage and
restart that candidate; retain previously published last-good evidence.

Fetch a new block context for each new observation, not once per manager
lifetime. Publish coherent completed families with their actual source clocks;
publish provisional catalog identity/links independently of missing chain data.
Do not advertise reviewed availability before all getters/dependencies required
by that adapter have answered. Large registry scans publish known children with
partial coverage and preserve their cursor; they do not restart at index zero.

Discovery has independent newest-page and history cursors. Each cycle first
services due head updates, then advances the oldest pending source fairly.
Duplicate/nonprogressing pages and changing publication totals keep coverage
partial and preserve the last validated cursor. Reaching a short final page is
evidence only for that enumerator; complete global coverage also requires all
required enumerators, candidate/details and adapter-specific checks.

TTL defaults: discovery/head 300s, chain/mint 120s, source/utility/token metadata
600s, negative or incomplete retry 120s. A partially completed admitted stage can
continue on the next normal offer without pretending a successful new read or
waiting its full success TTL. Per-host cooldown still applies. The screen's
normal 30s refresh schedules work; passive loading repaint schedules none.

Persist versioned JSON atomically to `~/.maxpane/surf_nft_cache.json`, with injected
`cache_path` and clock. This is an evidence/event cache, not a history series.
Bound the disk file to 16 MiB, 1,000 deployed/build records combined, 2,000 compact
explicit relationship facts, 32 unfinished stages and 256 KiB per stage. Validate
each retained record and finite timestamp; reject oversize input before parsing.
When a cap binds, keep the selected/current records and newest valid observations,
mark retained coverage partial, and never convert eviction into a zero total.
Raw full job bodies remain in the existing shared memo; NFT persists extracted
facts with their originating job observation/revision, not a second unbounded
job cache. Persist enough accepted facts/cursors for warm-start progress.

## Ownership, dependencies and review gates

Expected production size is approximately 3,500–5,500 lines, including adapted
interpreters and source validation. This is above the Tier 2 small-change review
exception. Do not reduce reviews by declaring the scanner port “configuration.”

| Package | Agency role / owner | Owned files | Dependencies / parallel work |
|---|---|---|---|
| N0 contract and pure projection | Backend Architect | `data/surf_nft_models.py`, `analytics/surf_nft.py`, their tests | First; freezes seams |
| N1 discovery and budgeted transport | Data Engineer | `data/surf_nft_client.py`, `data/surf_nft_discovery.py`, discovery/client fixtures and tests | N0; parallel N2 and initial N4 |
| N2 chain evidence and scanner semantics | AI Engineer with ethskills | `data/surf_nft_chain.py`, `data/surf_nft_rules/`, chain/rules fixtures and tests | N0; consumes N1 frozen client interface; parallel N1/N4 |
| N3 persisted orchestration | Backend Architect, same central integration owner as N5 | `data/surf_nft_cache.py`, `data/surf_nft_manager.py`, tests | N1+N2 |
| N4 screen, widgets, boardroom presentation | Frontend Developer | `screens/surf_nft.py`, `widgets/surf_nft/`, `screens/surfboard.py`, `widgets/surfboard/rack.py`, `themes/minimal.tcss`, UI/address tests | New UI after N0; final hub wiring after N3/N5 |
| N5 SURF lifecycle and card projection | Backend Architect, same owner as N3 | `data/surf_manager.py`, `data/surf_models.py`, `data/surfboard.py`, composing data tests and `tests/surfboard_fixtures.py` | N3; coordinate frozen card contract with N4 |
| N6 live acceptance, certification and handover | Controller; relevant file owner applies corrections | Measurement artifacts, docs, narrowly assigned verification files | N4+N5 working |

Every worker is told they are not alone, must preserve other edits, cannot spawn
subagents, and may change only owned files. Shared files stay with one owner for
the entire feature. Root owns this plan, PRD, research corrections, README and
followups documentation after planning. No worker edits global dashboard
registration or `app.py` merely to add a nested screen.

With four total seats, run root + N1 + N2 + N4 after N0. N3 starts after the two
source packages stabilize; N5 uses the same central owner after N3. New UI can
develop against the frozen fixture contract while source readers are built.
No visible-diff review is dispatched before the real 149×45 preview. Keep N4's
changes pending review until N5 is integrated and the preview is shown; then
review N4 and N5 once each against disjoint owned diffs. Source-only packages can
be reviewed earlier. A reviewer never fixes their findings.

## N0 — contract, identity and local projections

Read `data/swarm_tokens_models.py`, `analytics/swarm_tokens.py`, the PRD and
`docs/surf_nft_game_mechanics.md`. Create the contract above and compact fixture
rows for all important semantic distinctions; no source I/O belongs here.

- [x] Write failing identity/filter tests: same name on two addresses and two
  chains remains separate; invalid/unsupported chains cannot become Ethereum;
  IDMD `yes`/`conditional`/`no`/`unknown` are four states; “mint open” examines
  route state without promoting a closed IDMD route; a known empty catalog is
  distinct from a failed unknown one.
- [x] Add the selection/summary contract and immutable projection tests:

```python
def test_common_filters_scope_heroes_but_stage_only_changes_table(snapshot):
    filters = {"idmd": "yes", "stage": "launched"}
    launched = project_snapshot(snapshot, filters=filters, selected_id=None)
    builds = project_snapshot(snapshot, filters={**filters, "stage": "building"}, selected_id=None)
    assert launched["nft_summary"] == builds["nft_summary"]
    assert launched["nft_summary"]["deployed"] == len(launched["nft_rows"])
    assert all(row["idmd_benefit"]["status"] == "yes"
               for row in launched["nft_rows"])
```

- [x] Run `.venv/bin/python -m pytest tests/analytics/test_surf_nft.py -q`;
  observe failure, implement the smallest pure projection and run green.
- [x] Keep `None` values in summary instead of manufacturing numeric zeros.
  Preserve six summary cards: Collections, In the making, Mint open, IDMD free,
  Conditional, Chains. Active filter values and enum spelling agree with PRD.
- [x] Add `tests/data/test_surf_nft_models.py` contract tests; widgets later
  restate consumed signatures with an independent agreement test.
- [x] Kill identity/name-join and collapsed-benefit mutants with named tests,
  restore byte-for-byte, run both touched files whole, task review and commit.

## N1 — public discovery, joins and bounded transport

Read scanner `_nft_catalog.py` functions `collect`, `deployment_candidates`,
`related_records`, `pinned_source`, `pinned_abi`, and `_nft_links.py`; existing
`data/swarm_tokens_client.py`, `data/surf_swarm_client.py::read_job_detail`,
`data/rpc_common.py` and `data/rpc_classify.py`. Do not copy `collect`'s full-run
loops or synchronous urllib transport.

The concrete client seam supplied to N2/N3 is:

```python
class SurfNftClient:
    async def page(self, source, *, cursor=None, query=None, budget): ...
    async def detail(self, kind, identity, *, budget): ...
    async def rpc(self, chain_id, calls, *, budget): ...
    async def source_json(self, reference, *, budget): ...
    async def source_text(self, reference, *, budget): ...
    async def close(self): ...

# A page carries rows, next_cursor, terminal, observed_at, provider_total.
# RPC calls are read-only method/params pairs; responses match IDs exactly.
# Source references are validated pinned repos/paths or allowlisted public API
# identities, never an arbitrary URL pulled from untrusted prose.
```

`SurfNftDiscovery.advance(state, *, budget)` returns a new validated discovery
state and extracted candidates. Its constructor receives `client`, borrowed
`swarm`, and clocks. It uses `read_job_detail` for full jobs; does not access or
mutate the memo's private storage. `Budget` is a small NFT-local value object
owned in `surf_nft_client.py`: counters, reservations, deadline, `can_admit` and
`consume`; it is not a shared application framework.

- [x] Commit sanitized API fixtures for jobs/searches, launches/details,
  workflows and historical publications/sites. Include duplicate timestamps,
  repeated cursors, late changing totals, unsupported chain, body truncation,
  and explicit continuation/project links. No test reads the sibling checkout.
- [x] Write failing offline tests that assert strict progress, all-artifact
  discovery, full-job identity/revision preservation, and no name-only join.
  `[]` is a validated negative; transport or malformed-page failure is `None`.
- [x] Implement one head page plus fair resumable history under the shared
  limits. Persist only normalized candidates/explicit relationships. Recent
  `/sites` is supplementary; use historical `/publications` pagination.
- [x] Route source ABI's alternative paths and every retry through the same
  client budget. Pin commit/path, reject malformed reference/oversize content,
  allow read-only methods only; reuse vendored ABI where available. No site
  HEAD request is needed (`normalize_site(..., verify=False)` semantics).
- [x] Implement 429 cooldown and count actual HTTP attempts at the send boundary;
  count each logical RPC operation separately from batch HTTP attempts. Keep
  per-host limits and endpoint policy in this client; reuse existing helpers.
- [x] Test memo sharing with WORK/RECORD via one injected shared SwarmClient:
  two consumers of a job share the transport read; cancelling NFT's waiter
  leaves the other consumer live; original `observed_at` reaches NFT facts.
- [x] Test 24-credit admission including two credits per borrowed job lookup,
  progress across two budget-limited cycles, physical send counts, retry/body
  bounds, and no real network fallthrough. Kill cursor, budget and explicit-link
  mutants; run `tests/data/test_surf_nft_client.py` and
  `tests/data/test_surf_nft_discovery.py` whole, task review and commit.

## N2 — pinned chain evidence and reviewed rule parity

Read aidude `_nft_chain.py`, `_nft_rules.py`, `_nft_children.py`,
`_nft_references.py`, `_nft_tokens.py`, `_nft_utility.py`, `_nft_hints.py`,
`nft-reviewed.json`, `nft-utilities.json` and their `tools/surf/tests/test_nft_*`
tests. Reuse MaxPane `evm_abi`, `keccak` and RPC classification instead of copying
those implementations.

Create `data/surf_nft_rules/` with `__init__.py`, `rules.py`, `utility.py`,
`hints.py`, `references.py`, `children.py`, `tokens.py`, the two attributed JSON
resources, and `SOURCE_MANIFEST.json`. These files have substantive separate
responsibilities; do not introduce an extra abstract adapter class hierarchy.
Import-time/resource JSON reading belongs in data, never pure analytics.

The manifest records original path, SHA-256, capture date and adaptation notes.
The inspected aidude tree has no available commit and no scanner license/SPDX;
do not invent either or claim a mirror revision. The owner requested local
adaptation. No external publication is part of this task.

`SurfNftInspector.advance(candidate, progress, *, budget)` consumes N1's client,
returning new progress and independently complete evidence families. Pure
interpreters retain these recognizable entry points:

```python
apply_rules(record, chain_evidence, now_iso)
reviewed_build(job, now_iso, days=7)
classify_template(chain_evidence)
utility_read_specs(chain_evidence)
enrich_utility(record, chain_evidence, jobs)
infer_utility(record, chain_evidence, jobs)
```

- [x] Adapt the upstream regression cases and compact saved examples into
  committed fixtures under `tests/fixtures/surf/nft/`. Produce a parity matrix
  keyed by every reviewed adapter, special case, child factory and reference
  interpreter, with the exact cases proving retained behavior.
- [x] Write failing tests for chain ID mismatch, empty code, wrong runtime
  hash, ERC-165 invalid-interface behavior, failed/foreign/future receipts,
  clone implementation and factory event mismatches, and dependency code
  changes. A name or ERC-721-shaped interface alone never proves a Swarm launch.
- [x] Port deterministic classification and utility without lifting transport.
  Preserve exact source/job/commit evidence, active-days rules, accepted build
  evidence and superseded projects. Unreviewed/code-mismatched contracts retain
  reported claims separately and lose verified mint/IDMD conclusions.
- [x] Adapt chain inspection to async resumable stages pinned to one verified
  block context. Probe only required selectors and schema-known optional getters;
  bind code hash before running a reviewed adapter. Read actual ERC-20 decimals,
  retain integer quantities until exact formatting, and show unknown prices if
  conversion evidence is unavailable. Native gas units remain chain-defined.
- [x] Preserve reviewed factory child registries, creation receipt events,
  Seasons constructor references, dependency/item reads, and related-token roles.
  Replace the hidden `_courier_items` direct `_http_json` path with N1's client.
  All child/item/source/metadata reads consume the same budget and deadline.
- [x] Prove staged progress and coherent clocks with a deliberately tiny budget:

```python
async def test_inspection_continues_without_mixing_blocks(inspector, candidate, budget):
    first = await inspector.advance(candidate, None, budget=budget(2))
    second = await inspector.advance(candidate, first.progress, budget=budget(2))
    assert second.progress.completed_operations > first.progress.completed_operations
    assert second.progress.block_number == first.progress.block_number
```

  Complement this with stale/unavailable-block restart and wrong-hash tests:
  no old getter value can appear under the replacement block/observation.
- [x] Assert IMDenza paid/open versus IDMD-route state; FarmItems minted/live/
  burned distinctions; public-free Pulse versus IDMD-exclusive privilege;
  Genesis/OGPass/Pepeolithic independent routes; same-name BMC deployments;
  required fees/burns; missing decimals; utility planned versus deployed.
- [x] Kill exact hash/chain, factory proof, mandatory-fee/free and block-renewal
  mutants with named tests. Run owned `test_surf_nft_chain.py`,
  `test_surf_nft_rules.py`, `test_surf_nft_utility.py`,
  `test_surf_nft_children.py`, `test_surf_nft_references.py`,
  `test_surf_nft_tokens.py` whole, task review and commit.

## N3 — persisted manager and responsive scheduling

Read `data/swarm_tokens_manager.py::_start/get_snapshot/close`,
`data/portfolio_manager.py` task ownership, `data/surf_cache.py` atomic persisted
evidence patterns, and `screens/surf_loading.py` passive loading protocol.

- [x] Write cache round-trip tests with real saved observation times, a hand-edited
  corrupt row, future timestamp, oversize stage/file, cancelled write and partial
  cursor state. A malformed row cannot discard unrelated valid observations.
- [x] Implement validated versioned evidence persistence using existing atomic
  write conventions. No second raw-job memo, no series subclass without series.
  Unknown/incomplete sources remain distinct from confirmed empty sources.
- [x] Write event-gated tests proving `fetch_and_compute()` returns before a
  blocked source, a new empty-cache installation starts live discovery, and
  `get_snapshot()` creates no task/HTTP request or new source timestamp.
- [x] Implement the frozen manager with owned tasks, selected-stage priority,
  independent source TTL/attempt clocks, fair discovery, per-host cooldown and
  budgeted continuation. Cache/store completion uses completion wall time for
  HTTP observations while chain block time and partial-stage provenance remain
  unchanged. Compare observations with a clock taken after completion, never
  the beginning of the refresh that would make new data look “future.”
- [x] Preserve successful evidence when another family fails or when a newer
  incomplete stage is pending. Latest known IDMD/mint truth retains its source
  time; a failed current read cannot upgrade a historical rule to current.
- [x] Test two selected identities switching during delayed responses; only the
  matching identity's evidence updates. Confirm repeated keys/refreshes join
  work, reopening keeps snapshot/filter state, and shutdown cancels/drains every
  owned stage even if an active-task lookup was replaced.
- [x] Test conditional source invalidation by changed runtime hash, discovery
  revision and linked deployment identity; caches never cross chains/contracts.
- [x] Kill passive-I/O, renewed-clock, missing-budget-resume and orphan-task
  mutants. Run `tests/data/test_surf_nft_cache.py` and
  `tests/data/test_surf_nft_manager.py` whole, task review and commit.

## N4 — NFT Explorer and BOARDROOM presentation

Read `screens/swarm_tokens.py` and `screens/surf_loading.py` for lifecycle,
`widgets/swarm_tokens/` for panel/table/filter shapes, shared `panels`, `address`,
`explorer`, `markup_safety`, `rowfit`, and `.claude/skills/terminal-layout/SKILL.md`.
Existing `widgets/surf/nft.py` is the separate legacy IDMD panel; leave it intact.

Create `widgets/surf_nft/{__init__,hero,table,detail,filter}.py` and
`screens/surf_nft.py::SurfNftScreen(SurfDashboardScreen)`. Reuse shared panel
bases/filter controls. The screen dispatches flat primitives; no network await
in event handlers, custom refresh worker, or direct data imports in widgets.

- [x] Write composited widget tests first for the approved six heroes, deployed/
  in-the-making switch, catalog rows and selected mint/utility/token/source
  details. Label actual observations; never display saved example numbers as
  runtime defaults. Do not create floor/volume/personal-eligibility placeholders.
- [x] Implement catalog left and selected details right, with scrollable source
  details reachable without losing list/selection. Filters cover search, chain,
  mint state, four IDMD statuses and utility kind; support newest/name sort.
  Common filters scope heroes and rows; stage scopes only the visible table,
  and the filter/editor state survives repaint. Search covers name, symbol,
  exact contract and job/project identity, retaining utility evidence labels.
  `Esc` first leaves focused search/filter editing, then returns to BOARDROOM.
  `Enter` focuses/opens the selected detail section; rows remain selectable.
- [x] Show explicit routes, requirement text, public versus IDMD price, original
  clocks/block, related token roles, linked jobs, website and pinned source.
  No implicit joins, executable markup, arbitrary-site fetching or click-time
  network validation. Unknown chain receives an address copy icon without a link.
- [x] Add schema/signature and analytics-import purity tests. Address/copy
  coverage includes collection, factory, implementation, tokens and any address
  embedded in utility/conditions. Use helper rendering for third-party prose.
- [x] After N5 is ready, replace rack `SLOTS` key `protocol` at `(1, 0)` with
  `surf-nft`/`NFTS`. Main digits show deployed collections; footer shows building/
  open and visible partial-catalog qualification. Keep six rack columns,
  center terminal, card height and tagline anchors. Update anchor lookup from
  protocol to NFTS without moving the unrelated TOKENS side.
- [x] Add non-priority `n → action_nfts → push SurfNftScreen(nft_manager())` and
  `p → action_protocol → app.open_surf_mode(MODE_POOL4)` on SurfboardScreen.
  Card activation uses the same NFT route. Leave native SURF `e` intact.
  Explicitly guard Input focus, so typing `n`/`p` in the command or seat entry
  does not navigate. Add hints within existing measured status-bar width.
- [x] Align the new screen's default CSS and production theme rules. Test
  normal, unknown, partial, empty, long/CJK/markup-bearing payloads; lower-priority
  detail lines scroll with visible geometry hints rather than clipping.
- [x] Extend `tests/address_sweep/builders.py` and the relevant registry/import
  files with one screen case; run the new case and address-rule checks offline.
  Add `tests/widgets/test_surf_nft.py`, `tests/screens/test_surf_nft.py`, and
  focused rack/screen key tests. Do not certify a pin from the ASCII mockup.
- [x] Hold the visual diff for N6's real 149×45 preview before task review.
  After preview corrections, measure in situ and add honest `#:` blocks and
  boundary-set tests; mutate the pin both lower and higher and verify failure.
  Run touched/composing UI files whole, one task review, bounded fixes, commit.

## N5 — shared SURF lifecycle and card facts

Concrete starting symbols: `SurfManager.close` near line 1313,
`swarm_tokens_manager` near 5646, hub `is_loading` near 7384, card assembly near
7732, `get_hub_snapshot` near 7801 and `fetch_hub_snapshot` near 7863.
`data/surfboard.py::cards` builds PROTOCOL near 590; the card model tuple is
`SURFBOARD_CARD_FIELDS` in `data/surf_models.py` near 1588. These are entry points,
not permission to refactor unrelated Surf scheduling.

- [x] Write failing lifecycle/card tests: lazy manager identity is stable,
  shared SwarmClient is borrowed, close drains NFT before shared client closes,
  initial hub refresh offers bounded NFT work, passive hub projection does not.
- [x] Add lazy `nft_manager()`, NFT loading participation for hub/native NFT view,
  bounded `offer_hub` in active hub refresh and owned shutdown. Do not add an app
  manager attribute or change global startup prefetch/registry.
- [x] Add `nft_summary` to `SURFBOARD_CARD_FIELDS`, with an agreement test for
  exact fields, and optional `nft_catalogue` input to `surfboard.cards`.
  Replace only the projected PROTOCOL card with the NFTS summary; leave the
  native PROTOCOL payload and existing POOL4 source fetching intact.
- [x] Use one card projection for full and passive hub paths so cached counts,
  partial coverage and clocks agree. Display no numeric count if catalog
  inventory is unknown; do not turn a partial retained set into an exact total.
- [x] Update composing fixtures and expectations only for the replaced slot
  and new contract field. Existing market, WORK, RECORD and token memo behavior
  must keep their tests; never silence unrelated baseline failures wholesale.
- [x] Test with clock advancing inside a delayed source read: newly completed
  observations survive validation and appear without being stamped at cycle
  start. Kill renewed-clock and passive-request mutants. Run touched data files
  plus `tests/data/test_surf_manager_surfboard.py` whole.
- [x] Join N6 live preview before reviewing visible projection changes, then
  task review and commit the owned integration diff separately from N4.

## N6 — live preview, certification and final delivery

- [x] Build a bounded one-shot live capture using the actual app/managers and
  production stylesheet at **149×45**. Empty isolated HOME; no fixture manager
  and no aidude runtime import. Permit at most four admitted NFT cycles, each
  under the documented budget, and a 90s overall deadline; retain actual send
  counts, reserved credits, logical RPC counts, response statuses and timings.
  On 429 honor cooldown; do not keep rerunning until a pleasant result appears.
- [x] Show the live BOARDROOM card and NFT Explorer to the owner before layout
  hardening or visible-diff review. Use a real discovered collection when one
  arrives; otherwise show actual partial discovery honestly and report why.
  An explicit seed run may demonstrate retained data, but is separately labeled
  and cannot replace proof that an empty installation starts live discovery.
- [x] Exercise `n`, card click/Enter, selection, IDMD/mint filters, source links,
  `Esc`, and `p` returning to the original PROTOCOL body. Check typing `n`/`p`
  in hub inputs remains literal. Record responsive cached navigation, request
  counts and observation behavior; do not invent performance improvement ratios.
- [x] After owner-visible preview corrections, finish new-screen and replaced-
  card in-situ boundary sweeps, CSS agreement and address sweep. Preserve the
  hub's current six-column/149×45 shape; measured pins may only change for a
  demonstrated unavoidable content requirement documented beside the constant.
- [x] Run final touched/composing files once with isolated HOME and no
  `NO_COLOR`; use `-n 4 --dist worksteal` where supported. Keep a serial rerun
  only for a failure unique to worksteal. No full suite.

```bash
env HOME="$(mktemp -d)" .venv/bin/python -m pytest -n 4 --dist worksteal \
  tests/analytics/test_surf_nft.py tests/data/test_surf_nft_models.py \
  tests/data/test_surf_nft_client.py tests/data/test_surf_nft_discovery.py \
  tests/data/test_surf_nft_chain.py tests/data/test_surf_nft_rules.py \
  tests/data/test_surf_nft_utility.py tests/data/test_surf_nft_children.py \
  tests/data/test_surf_nft_references.py tests/data/test_surf_nft_tokens.py \
  tests/data/test_surf_nft_cache.py tests/data/test_surf_nft_manager.py \
  tests/data/test_surf_manager_surfboard.py tests/data/test_surfboard.py \
  tests/widgets/test_surf_nft.py tests/widgets/test_surfboard_rack.py \
  tests/screens/test_surf_nft.py tests/screens/test_surfboard_screen.py \
  tests/screens/test_surfboard_layout.py tests/test_surfboard_registration.py
.venv/bin/python -m pytest -m 'guard and not mounts_app' tests
env HOME="$(mktemp -d)" .venv/bin/python -m pytest -m mounts_app \
  tests/test_surf_registration.py tests/test_curator_registration.py tests/test_fwa_guardrails.py
.venv/bin/python -m pytest -m docpin \
  tests/test_surf_registration.py tests/test_curator_registration.py
```

Include additional directly touched test files and the named new address-sweep
case; do not broaden into whole directories. The eight previously reproduced
baseline failures from `docs/surf_data_loading_followups.md` remain known
baseline evidence. If encountered again, identify exact nodes and compare only
the relevant baseline; they are not an exemption for new failures.

- [x] Controller supplies the whole change to one final reviewer on the most
  capable available model, with `CLAUDE.md`'s reviewer contract verbatim, spec,
  plan, task-review results, live evidence and named risks below. Each package
  gets at most two fix rounds; final review permits **one fix wave**, and
  **one scoped re-review** only if that wave changes production code. Minor-only
  findings are filed, not fixed in another round. Reviews never spawn agents.
- [x] Update research selection status, README shortcuts, PRD/plan completion
  and `docs/surf_nft_followups.md`; include parity manifest, tests/mutations,
  live coverage limitations, measured timings and outstanding Minor findings.
  No source values are hardcoded into docs as guaranteed current counts.
- [x] Commit local reviewed changes, verify status without disturbing original
  user files, preserve useful evidence outside the temporary plan workspace,
  and remove only that feature's temporary workspace. No push/release requested.

## Final review focus and acceptance

| Risk | Named evidence / owning package |
|---|---|
| Shared name or wrong-chain/hash evidence produces a plausible NFT or mint claim | N0 identity mutant; N2 hash/chain/factory mutants |
| Hidden child/source/token request bypasses quota or repeats forever after budget exhaustion | N1 actual MockTransport counts; N2 staged progress/cursor/deadline tests |
| New completion is discarded as future, or cached block becomes falsely current | N3 completion-clock/reopen tests; N5 delayed read integration; N2 block-context mutant |
| Selected-detail cancellation breaks another consumer or leaves work after shutdown | N1 shared memo waiter test; N3 task-retirement/shutdown test |
| Rich text/address/source links or printable shortcuts break the terminal UI | N4 malicious-text/address sweep/input tests; N6 real render and boundary mutants |

Acceptance requires independently working live cold discovery, retained warm
snapshots, every included adapter family exercised offline, no guessed values,
bounded progress under quotas, the selected visual combination, the replacement
card and preserved PROTOCOL route. Source outages or incomplete public history
can legitimately leave unknown facts and visible partial coverage. They cannot
be hidden by silently omitting required source paths or claiming complete scan.

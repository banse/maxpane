# FWA NETWORK — Conflict-free Work Packages

This file executes [`fwa_ecosystem_implementation_plan.md`](fwa_ecosystem_implementation_plan.md).
The contract in that file is frozen. A package may report a contract defect, but it must
not rename a key, add an alias, or edit another package's files.

## Execution rules

- One owner per file. The paths listed under a package are exclusive until it lands.
- Parallel workers run only their package tests, never the full suite.
- Tests use `.venv/bin/python -m pytest` and injected deny-network transports.
- A package commits only its owned files and names its targeted green run in its summary.
- Do not touch `FWA_DATA_KEYS`, `FWA_WIDGET_SIGNATURES`, or `FWA_ROW_KEYS`.
- Do not add credentials, env vars for keys, signing code, state-changing calldata, or a
  runtime ABI/source download.
- Do not wait for NETWORK work from the PULLS critical path.
- If another package is wrong, send the owner the evidence. Do not repair its file.
- Review packages report findings; fixes are separately assigned and re-reviewed.

Recorded baseline: 688 FWA tests pass. The 12 existing failures in
`tests/widgets/test_fwa_accessibility.py` are known baseline failures; no package may add
another failing node id.

## Dependency graph

```text
Wave 1
  WP-01 contract ─────────┬───────────────────────────────────────┐
  WP-02 manifests/ABIs ───┼──────────────┐                        │
                          │              │                        │
Wave 2                    ▼              ▼                        ▼
  WP-03 core+flow   WP-04 drops   WP-05 PullPool   WP-06 MegaRip
  WP-07 FWAP        WP-08 cache   WP-10 fitting    WP-11 hero+flow widgets
                                                \  WP-12 board/feed widgets
Wave 3                                          \
  WP-09 ecosystem manager  <── WP-03..08          \
  WP-13 composite manager  <── WP-09                \
                                                    \
Wave 4                                              ▼
  WP-14 screen/app/theme integration <── WP-10..13

Wave 5
  WP-15 independent verification <── WP-14
```

WP-03 through WP-08 are independent vertical data slices. WP-10 through WP-12 are
independent view slices. Shared production surfaces exist only in WP-14.

## Wave 1 — freeze the seams

### WP-01 — Presentation contract and offline test boundary

**Owner:** model-contract worker<br>
**Depends on:** none<br>
**Creates:** the only new presentation vocabulary

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_ecosystem_models.py`
- `tests/data/test_fwa_ecosystem_models.py`
- `tests/fwa_ecosystem_fixtures.py`

**Tasks:**

1. Implement the exact `FWA_NETWORK_DATA_KEYS`, `FWA_UMBRELLA_DATA_KEYS`, row tuples,
   enums, frozen extra-forbidden row/boundary models, and widget signatures from the
   implementation plan. Models are strict-wei; only dumped presentation rows use ETH/FWA
   floats.
2. Add `load_fwa_ecosystem_fixture`, `FixedClock`, and a transport whose every request
   raises unless explicitly handled by the test. Assert tuple order, no collision with
   existing PULLS keys, exact row dumps, unavailable `None`, and rejection of floats in
   wei fields.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_ecosystem_models.py
```

**Done when:** downstream agents can import one exact contract, blank payload creation
produces all 40 NETWORK keys, and no existing FWA model file changed.

### WP-02 — Addresses, manifests, and vendored ABI/topic resources

**Owner:** chain-contract worker<br>
**Depends on:** WP-01<br>
**Creates:** immutable discovery metadata; no live mutable values

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_ecosystem_addresses.py`
- `maxpane_dashboard/data/fwa_projects/__init__.py`
- `maxpane_dashboard/data/fwa_projects/base.py`
- `maxpane_dashboard/data/fwa_projects/registry.py`
- `maxpane_dashboard/abis/fwa/fwair_manager.json`
- `maxpane_dashboard/abis/fwa/fwair_launch.json`
- `maxpane_dashboard/abis/fwa/pullpool_v1.json`
- `maxpane_dashboard/abis/fwa/pullpool_v2.json`
- `maxpane_dashboard/abis/fwa/standing_orders_v1.json`
- `maxpane_dashboard/abis/fwa/standing_orders_v2.json`
- `maxpane_dashboard/abis/fwa/group_pull.json`
- `maxpane_dashboard/abis/fwa/group_orders.json`
- `maxpane_dashboard/abis/fwa/megarip_v1.json`
- `maxpane_dashboard/abis/fwa/megarip_v2.json`
- `maxpane_dashboard/abis/fwa/megarip_v3.json`
- `maxpane_dashboard/abis/fwa/fwap_house_v1.json`
- `maxpane_dashboard/abis/fwa/fwap_house_v2.json`
- `maxpane_dashboard/abis/fwa/fwap_share_v1.json`
- `maxpane_dashboard/abis/fwa/fwap_share_v2.json`
- `maxpane_dashboard/abis/fwa/fwap_receipt_v1.json`
- `maxpane_dashboard/abis/fwa/fwap_receipt_v2.json`
- `tests/data/test_fwa_ecosystem_addresses.py`
- `tests/data/test_fwa_project_registry.py`

**Tasks:**

1. Encode the exact official and project manifest tables from the implementation plan as
   frozen values. Include deployment block, ABI resource, runtime hash, source status,
   current flag, and exact getter dependency pairs. Never fetch metadata at runtime.
2. Vendor the smallest read/event ABI for each adapter. Verified resources come from
   verified source; MegaRip v3 contains only the chain-confirmed surface and is explicitly
   unverified. Test ABI JSON loads, declared functions/events exist, addresses normalize,
   deployment blocks precede the reference block, and every ABI path resolves.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/data/test_fwa_ecosystem_addresses.py \
  tests/data/test_fwa_project_registry.py
```

**Done when:** every adapter can be written without consulting a frontend bundle or
network, and MegaRip v3 cannot be classified `VERIFIED`.

## Wave 2 — independent data and view slices

### WP-03 — Core, tokenomics, rewards, buyback flow

**Owner:** EVM data worker<br>
**Depends on:** WP-01, WP-02

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_tokenomics_client.py`
- `maxpane_dashboard/analytics/fwa_ecosystem.py`
- `tests/data/test_fwa_tokenomics_client.py`
- `tests/analytics/test_fwa_ecosystem.py`
- `tests/fixtures/fwa/ecosystem/core/`

**Tasks:**

1. Add a block-tagged, injected-transport client for core/token/rewards and a separate
   log-pool path for buyback/routing events. Read live queue, quote, escrow, refunds,
   crown, payout/config, supply, reward balances, emissions schedule, and official
   integrity. No call may mutate state or depend on gas-provider behaviour already
   rejected by `FWAClient`.
2. Add pure transformations for strict wei conversion, genesis burn, emissions end,
   buyback gross/caller accounting, route-sum invariant, and exact ordered `FLOW_ROW_KEYS`.
   Mutation fixtures 8,750 payout bps and 75 crown bps must change output.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/analytics/test_fwa_ecosystem.py \
  tests/data/test_fwa_tokenomics_client.py
```

**Done when:** current state and value-flow rows are block-provenanced; 40/30/30 is read,
not copied; ended emissions render ended despite nonzero rate getters.

### WP-04 — FWAIR enumeration and launch state

**Owner:** EVM data worker<br>
**Depends on:** WP-01, WP-02

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_drops_client.py`
- `tests/data/test_fwa_drops_client.py`
- `tests/fixtures/fwa/ecosystem/drops/`

**Tasks:**

1. Read `nextLaunchId`, enumerate every id in `1..next-1`, and block-tag manager and
   child calls. Decode the exact `DROP_ROW_KEYS`; map the seven source phases to the
   frozen lowercase vocabulary.
2. Treat a zero address, failed child, or malformed name as a per-id hole and continue.
   Validate manager/core/token links and child runtime hash. Add fixtures for two launches,
   a hole followed by a valid launch, a new third launch, and a mismatched child hash.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_drops_client.py
```

**Done when:** future launches appear without a code change and one bad id cannot suppress
later rows.

### WP-05 — PullPool, GroupPull, and order surfaces

**Owner:** protocol-adapter worker<br>
**Depends on:** WP-01, WP-02

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_projects/pullpool.py`
- `tests/data/test_fwa_pullpool_adapter.py`
- `tests/fixtures/fwa/ecosystem/pullpool/`

**Tasks:**

1. Implement current/legacy PullPool state, GroupPull, standing-order factories, and group
   orders from their separate manifests. Derive open/refunding/settled and outstanding ETH/
   FWA; do not use the frontend's synthetic `+375` count.
2. Emit exact project rows and normalized events with manifest version retained. Include a
   legacy row only for a positive liability or integrity warning. Test dependency mismatch,
   distributor loss, overlapping history dedupe, zero liability omission, and one failed
   satellite surface leaving current PullPool readable.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_pullpool_adapter.py
```

**Done when:** PullPool, GroupPull, and orders keep distinct accounting and no cumulative
creation counter is labelled active.

### WP-06 — MegaRip versions and outstanding claims

**Owner:** protocol-adapter worker<br>
**Depends on:** WP-01, WP-02

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_projects/megarip.py`
- `tests/data/test_fwa_megarip_adapter.py`
- `tests/fixtures/fwa/ecosystem/megarip/`

**Tasks:**

1. Implement v1-v3 lifecycle/accounting at one block. Derive gross recovery as final pot /
   deposits and keep its label; do not call it return. Compute outstanding ETH/FWA from
   contract accounting and claims, not depositor UI rows.
2. Emit the current v3 row, only liability-bearing legacy rows, and normalized versioned
   events. Enforce v3 `CHAIN-READ`; codehash/dependency mismatch suppresses current
   semantics. Test zero deposits, incomplete event history, three unclaimed depositors,
   and no-distributor/no-FWA distribution state.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_megarip_adapter.py
```

**Done when:** all three generations reconcile independently and no unverified contract is
ever badged `VERIFIED`.

### WP-07 — FWAP chain state and optional API enrichment

**Owner:** protocol-adapter worker<br>
**Depends on:** WP-01, WP-02

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_projects/fwap.py`
- `tests/data/test_fwa_fwap_adapter.py`
- `tests/fixtures/fwa/ecosystem/fwap/`

**Tasks:**

1. Implement v1/v2 house/share/receipt reads at one block: positions, independent active/
   returned/inventory counts, NAV/liquid capital, epoch, balances, supply, and dependencies.
2. Add the keyless public snapshot only as optional enrichment. Accept it only with source
   block/time; stale/unanchored API values cannot overwrite chain state. Emit v2 current and
   v1 only for liabilities/integrity. Tests inject both RPC and HTTP transports and prove an
   unexpected request raises.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_fwap_adapter.py
```

**Done when:** chain values remain authoritative, API staleness is visible, and no public
site credential appears in source or fixtures.

### WP-08 — Namespaced cache, watermarks, and atomic snapshots

**Owner:** persistence worker<br>
**Depends on:** WP-01

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_ecosystem_cache.py`
- `tests/data/test_fwa_ecosystem_cache.py`
- `tests/fixtures/fwa/ecosystem/cache/`

**Tasks:**

1. Implement fast/medium/API/integrity tiers, per-group last-good entries, and one atomic
   complete NETWORK snapshot under `~/.maxpane/fwa_ecosystem_cache.json`. Inject the clock;
   validate every persisted row and discard only the malformed slot.
2. Persist `(adapter, version, topic_group)` watermarks with block hash and overlap. Test
   TTL/failure backoff, corrupt/null points, old schema, reorg rewind, atomic temp/replace,
   and original last-good timestamp retention.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_ecosystem_cache.py
```

**Done when:** partial work never becomes the visible snapshot and an outage cannot be
persisted as zero.

### WP-10 — Shared terminal cell/table fitting primitives

**Owner:** terminal-layout worker<br>
**Depends on:** none

**Files (exclusive):**

- `maxpane_dashboard/widgets/table_tiers.py`
- `maxpane_dashboard/widgets/cell_fitting.py`
- `maxpane_dashboard/widgets/curator/_table.py`
- `maxpane_dashboard/widgets/surf/feed.py`
- `maxpane_dashboard/widgets/surf/launchpad_activity.py`
- `tests/widgets/test_table_tiers.py`
- `tests/widgets/test_cell_fitting.py`

**Tasks:**

1. Promote the existing curator tier-cost/install/title helpers and Surf cell-fit/pad
   helpers into shared pure modules; leave compatibility re-exports. Use `cell_len` /
   `set_cell_size`, never `len`, and keep absent-cell gaps absent.
2. Rewire only the source modules above to the shared helpers with byte-for-byte
   composited output. Prove ASCII, CJK, emoji, wide-boundary, markup-looking text, and
   too-narrow cases. Mutate a width/cell implementation to prove the tests redden.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/widgets/test_table_tiers.py tests/widgets/test_cell_fitting.py \
  tests/widgets/test_surf_launchpad_activity.py \
  tests/widgets/test_surf_widgets_b.py
```

**Done when:** new widgets can reuse one tested fitter and existing Surf/Curator pixels do
not change.

### WP-11 — NETWORK hero and value-flow rail

**Owner:** Textual widget worker<br>
**Depends on:** WP-01, WP-10

**Files (exclusive):**

- `maxpane_dashboard/widgets/fwa/fwa_network_hero.py`
- `maxpane_dashboard/widgets/fwa/fwa_flow_rail.py`
- `tests/widgets/test_fwa_network_hero.py`
- `tests/widgets/test_fwa_flow_rail.py`

**Tasks:**

1. Implement the three-card hero against its exact signature, reusing the existing FWA
   hero structure without importing it through `data`. Render unavailable values as `n/a`
   and separate healthy/degraded/unverified counts.
2. Implement the semantic ETH -> buyback -> FWA branch rail from ordered flow rows. Show
   observed execution beside configured bps, history completeness, stale age, and integrity;
   direction must survive monochrome.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/widgets/test_fwa_network_hero.py tests/widgets/test_fwa_flow_rail.py
```

**Done when:** blank/full/mutated/stale/integrity payloads render without I/O or clocks and
the 8,750/75 fixture values—not production constants—reach pixels.

### WP-12 — Drop board, ecosystem registry, and network activity

**Owner:** Textual widget worker<br>
**Depends on:** WP-01, WP-10

**Files (exclusive):**

- `maxpane_dashboard/widgets/fwa/fwair_drop_board.py`
- `maxpane_dashboard/widgets/fwa/fwa_ecosystem_registry.py`
- `maxpane_dashboard/widgets/fwa/fwa_network_activity.py`
- `tests/widgets/test_fwa_network_boards.py`
- `tests/widgets/test_fwa_network_activity.py`

**Tasks:**

1. Implement exact-row DataTables with measured column tiers. Drops preserve id/phase/
   funding/terminal dimensions; registry preserves labels/units and visually indents only
   qualifying legacy rows. Shed columns whole and advertise `‹ widen`.
2. Implement a bounded, escaped `RichLog(wrap=False)` from pre-normalized event rows.
   Fit before write, retain source/version, dedupe by `event_id`, and distinguish unavailable,
   quiet, and labelled last-good states.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/widgets/test_fwa_network_boards.py \
  tests/widgets/test_fwa_network_activity.py
```

**Done when:** hostile names, markup, CJK, emoji, extreme amounts, and narrow widths cannot
clip silently or crash the message pump.

## Wave 3 — orchestration

### WP-09 — Ecosystem manager and normalized flat payload

**Owner:** controller/data worker<br>
**Depends on:** WP-01 through WP-08

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_ecosystem_manager.py`
- `tests/data/test_fwa_ecosystem_manager.py`
- `tests/data/test_fwa_ecosystem_refresh_budget.py`

**Tasks:**

1. Obtain one state block, fan out direct groups with that explicit block, independently
   unwrap failures, and normalize exact flow/drop/project/event rows. Enforce source
   precedence, health counts, visible-legacy rule, and exact full-key output.
2. Run historical/API/integrity work as bounded single-flight background tasks and atomically
   commit complete snapshots. Test per-adapter failure isolation, time/page caps, source
   blocks, event dedupe, first empty cache, and close cancellation.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/data/test_fwa_ecosystem_manager.py \
  tests/data/test_fwa_ecosystem_refresh_budget.py
```

**Done when:** every failure combination returns exactly 40 keys and no adapter can mark a
healthy peer stale.

### WP-13 — Detached composite manager

**Owner:** concurrency worker<br>
**Depends on:** WP-01, WP-09

**Files (exclusive):**

- `maxpane_dashboard/data/fwa_composite_manager.py`
- `tests/data/test_fwa_composite_manager.py`

**Tasks:**

1. Own existing `FWAManager` and `FWAEcosystemManager`. Start/reuse NETWORK in the
   background, await only PULLS, consume NETWORK only when already done, and return the
   exact union with blank/last-good NETWORK keys.
2. Test a never-finishing NETWORK future, raised child, repeated ticks, atomic completion,
   exact key enforcement, cancellation, and close-each-child-exactly-once. The timing test
   must prove PULLS return is not behind NETWORK completion.

**Verify:**

```bash
.venv/bin/python -m pytest -q tests/data/test_fwa_composite_manager.py
```

**Done when:** PULLS latency is independent of NETWORK and no detached-task exception or
shutdown leak exists.

## Wave 4 — the only shared production integration package

### WP-14 — Screen, theme, package exports, and app wiring

**Owner:** integration/layout worker<br>
**Depends on:** WP-10, WP-11, WP-12, WP-13

**Files (exclusive):**

- `maxpane_dashboard/screens/fwa.py`
- `maxpane_dashboard/widgets/fwa/__init__.py`
- `maxpane_dashboard/themes/minimal.tcss`
- `maxpane_dashboard/app.py`
- `tests/screens/test_fwa_screen.py`
- `tests/screens/test_fwa_network_layout.py`
- `tests/widgets/test_fwa_widget_contract.py`
- `tests/test_app_startup.py`
- `tests/test_fwa_guardrails.py`
- `tests/test_fwa_theme.py`

**Tasks:**

1. Replace app ownership with one `FWACompositeManager`; prefetch, screen, and shutdown all
   use that same object. Compose NETWORK hidden without wrapping/reseaming existing PULLS.
   Add `_mode`/`_pulls_view`, `e`, `escape`, NETWORK-aware `c`, exact widget dispatch guards,
   title selection, and StatusBar active-view strings. Switching must issue zero fetches.
2. Add one `#fwa-network-body` with two vertical scrolling columns: 3fr left containing
   Flow then Registry, and 2fr right containing Drops then Activity. Duplicate CSS rules
   exactly in screen and theme. Measure in situ, set width/row constants, add stable
   gutters/min-heights/markers, then sweep boundary widths/heights and resize after both
   body switches.
3. Add recursive widget-import purity, full signature dispatch, manager registration,
   PULLS-default, first-paint, and compositor tests. Preserve the existing PULLS title and
   seven-widget payload dispatch.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/screens/test_fwa_screen.py tests/screens/test_fwa_network_layout.py \
  tests/widgets/test_fwa_widget_contract.py \
  tests/test_app_startup.py tests/test_fwa_guardrails.py tests/test_fwa_theme.py

.venv/bin/python -m pytest -q \
  tests/data/test_fwa_*.py tests/analytics/test_fwa_*.py \
  tests/screens/test_fwa_screen.py tests/screens/test_fwa_network_layout.py \
  tests/widgets/ \
  --ignore=tests/widgets/test_fwa_accessibility.py
```

**Done when:** PULLS first paint and controls remain intact, NETWORK is complete on first
toggle from cached/blank state, and the app-wide width pin is still 143.

## Wave 5 — independent verification

### WP-15 — Goal-backward review and release gate

**Owner:** fresh reviewer; never an implementation owner<br>
**Depends on:** WP-14<br>
**Production file ownership:** none

**Review targets:**

- all files added/changed by WP-01 through WP-14;
- `docs/fwa_ecosystem_PRD.md` and the implementation plan as authority;
- generated compositor captures at width 143, the measured boundary ±2, and the measured
  height boundary ±2, in PULLS odds/activity and NETWORK modes.

**Tasks:**

1. Verify observable truths: PULLS is default and not delayed; mode switches do not fetch;
   sources fail independently; semantic metrics disappear on integrity mismatch; future
   FWAIR ids appear; API data never outranks chain; no state-changing/keyed path exists.
2. Mutate the tree to prove timing, row schema, codehash, bps, width, height, markup, and
   offline tests bite; restore every mutation and confirm the worktree contains only the
   implementation diff.
3. Run the final focused set and full suite once. Compare accessibility failures by exact
   node id with the 12-item baseline. File findings; do not fix them in this package.

**Verify:**

```bash
.venv/bin/python -m pytest -q \
  tests/data/test_fwa_*.py tests/analytics/test_fwa_*.py \
  tests/screens/test_fwa*.py tests/widgets/ \
  tests/test_fwa_guardrails.py tests/test_fwa_theme.py \
  --ignore=tests/widgets/test_fwa_accessibility.py

.venv/bin/python -m pytest -q tests/widgets/test_fwa_accessibility.py
.venv/bin/python -m pytest
git diff --check
git status --short
```

**Done when:** every new/targeted test is green, no new baseline failure exists, the review
has no blocker/high finding, and any lower finding is explicitly accepted or assigned to a
new conflict-free follow-up package.

## Merge/rollout gate

Land packages by dependency wave, not completion timestamp. Do not expose the new binding
or construct the composite in `app.py` before WP-14. If a later package changes a frozen
contract, stop, amend both planning documents, and re-run every dependent package's
contract tests before continuing.

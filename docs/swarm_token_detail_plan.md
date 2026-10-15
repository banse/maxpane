# SWARM token dashboard implementation plan

## Scope and sequence

The owner approved Built by Swarm proposal 2. Implement the nested dashboard in
[the PRD](swarm_token_detail_PRD.md) on the existing branch. This is **Tier 2**:
a new screen, widgets, and a primitive data contract. Superpowers is disabled
by `CLAUDE.md`. Keep changes local; no new dependencies, top-level dashboard
registration, transaction support, or replacement of the existing token model.

Expected production size is approximately **850–990 lines**: selected adapter
and validation 300–360, contract 30–40, hero/panels 360–400, screen/integration/CSS
160–190. This is a planning estimate, not a cap to game. Recount the actual
production diff before review. Below roughly 1,000 production lines, package
reviews are waived and there is one final whole-diff review. If it exceeds that
scope, the controller applies the repository's normal Tier-2 review rule.

Sequence:

1. Controller freezes the contract below and assigns whole-file ownership.
2. Data and widgets run in parallel against the frozen contract. The controller
   builds screen composition and overview navigation against the same seam.
3. Integrate, exercise the actual data paths, and show a live keyless render at
   **149×45**. Land any owner visual corrections before hardening.
4. Measure layout in the real screen, record its own pin, prove mutation
   witnesses, and run the bounded touched/composing checks.
5. One final generic reviewer, one fix wave, a scoped re-review only if that
   wave changes production. File Minor-only findings. Commit locally.

Every implementer is working alongside others, owns only the named files, must
preserve concurrent edits, and must report defects across seams instead of
fixing another owner's files. No subagents spawn subagents.

## Frozen primitive contract

New module: `maxpane_dashboard/data/swarm_token_detail_models.py`. Existing
`data/swarm_tokens_models.py` keys and signatures remain stable. The controller
freezes the module before implementation and explicitly hands its ownership to
the data implementer; the controller does not edit it concurrently afterward.

```python
SNAPSHOT_KEYS = (
    'token', 'launch', 'contributors', 'artifacts', 'sources', 'as_of', 'is_mock',
)
LAUNCH_KEYS = (
    'id', 'number', 'chain_id', 'status', 'verdict', 'objective',
    'recorded_ts', 'repo_url', 'site_label', 'site_ens_name',
)
CONTRIBUTOR_KEYS = ('seat', 'role', 'job_id', 'state', 'stage')
ARTIFACT_KEYS = ('kind', 'name', 'address', 'chain_id', 'site_label', 'site_ens_name')
SOURCE_KEYS = ('state', 'read_ts', 'partial')
# sources: launch / contributors / artifacts -> SOURCE_KEYS
```

- `token`: deep-copied existing live token payload (`LIVE_TOKEN_KEYS`), or
  original `TOKEN_KEYS` payload in mock mode. Preserve its independent market,
  history, and liquidity states/read clocks, samples, and sample timestamps.
  Identity is chain plus normalized address, never ticker or displayed number.
- `launch`: above dictionary or `None`. `id` is the selected launch UUID;
  `number` is the display number. `recorded_ts` is source launch-record time.
  Verdict reuses existing verified evidence rather than re-scoring contracts.
- `contributors`: list of the above primitive rows or `None`. Only accepted
  non-oracle nodes. Deduplicate by seat/role/job; count unique seat IDs for the
  hero. `stage` distinguishes contracts/frontend; it does not overwrite role.
- `artifacts`: list or `None`; token, valid helper contracts, and verified
  matched current sites, deduplicated. Site rows have no invented address;
  contract rows have no invented site destination.
- `sources`: separate `launch`, `contributors`, and `artifacts` states/clocks.
  States cover `pending`, `ok`, `partial`, `stale`, `unavailable` as applicable.
  `read_ts` always denotes successful source evidence, not evaluation time.
  `partial` preserves incomplete coverage independently of freshness, so aging
  or failed reads cannot make a lower-bound contributor count appear exact.
- `as_of`: injected evaluation time, used for display windows/ages only.
- `is_mock`: explicit bool. Mock mode never starts live enrichment and never
  manufactures jobs or sites.

Lists preserve `None` versus `[]`. A known zero stays zero. Last-good data must
retain its original clock on refresh failure. Partial contributors are a lower
bound and render `≥` in the card; missing contributor evidence renders `--`.

Manager seam:

```python
SwarmTokenDetailManager(tokens_manager, token, *, client=None, clock=...)
async fetch_and_compute() -> dict  # returns promptly; schedules bounded work
async wait_pending()              # deterministic tests / live one-shot capture
async close()                     # owns selected tasks only, not borrowed clients
```

Screen seam: `SwarmTokenScreen(manager)`, subclassing `DashboardScreen` and
using `PANELS` adapters. New widgets expose `update_data()` with the applicable
subset of `token=None, launch=None, contributors=None, artifacts=None,
sources=None, as_of=None, is_mock=False`. Declare exact signatures in the new
models module; widget-side literal agreement is bound by a test, since widgets
must not import `data/`.

## Package A — selected data and lifetime

**Owner:** data implementer.

**Files:**

- `maxpane_dashboard/data/swarm_token_detail_models.py` after explicit handoff.
- New `maxpane_dashboard/data/swarm_token_detail.py`.
- `maxpane_dashboard/data/swarm_tokens_manager.py`: only the small public
  selected-token priority/read helper and its scheduling integration.
- New `tests/data/test_swarm_token_detail.py` and dedicated fixtures under
  `tests/fixtures/swarm_tokens/detail/`.
- Focused additions to `tests/data/test_swarm_tokens_live.py` if the helper's
  composing/scheduling tests belong there.

**Starting symbols and evidence:**

- `SwarmTokensManager._tokens`, `_refresh_details`, `_offer_enrichment`,
  `_snapshot`, `fetch_and_compute`, `fetch_portfolio`, and `close`; existing token
  projections already hold quote/history/position facts.
- `SwarmTokensClient` inherits `SwarmClient.fetch_launch_jobs`, `fetch_job`,
  `fetch_workflow`, and `fetch_sites`. Reuse these public keyless routes.
- `data/surf_launch_contribution.py::_launch`, `_job`, `_workflow`, and
  `tests/fixtures/surf/launch_contribution/captured.json` prove the selected
  launch/job/workflow join. Reuse established UUID/seat parsers and oracle
  exclusions instead of weakening their identity checks.
- `data/surf_swarm.py::launch_rows`, `site_rows`, and
  `SurfManager.swarm_tokens_source` establish the existing source projection.

**Implementation:**

1. Capture the selected row and immutable canonical identity. The helper gives
   selected tokens bounded priority within existing market/history scheduling
   and returns a fresh exact-identity projection. It must coexist with
   portfolio priority and avoid exposing mutable manager caches.
2. Read only the selected launch's light detail. Validate UUID, chain, and
   deployed token address before accepting metadata or artifacts. Fetch only
   its attached job IDs and verified frontend job. Never enumerate other
   launches to build this page.
3. Prove a workflow references the same contracts job and same launch before
   admitting frontend membership. Derive accepted non-oracle rows and unique
   seats from actual nodes. Reject malformed identity fields; do not turn a
   partially decoded source into a complete empty result.
4. Join current successful sites only by proved launch/job association. Reuse
   an available shared site snapshot; if a read is required, use the existing
   public sites route with a bounded refresh and decode, not a history crawl.
5. Bound request count, payload row counts, and retries for a selected token.
   Name budget constants in the adapter and expose partial when exhausted;
   do not silently truncate then claim completeness. Cache within the detail
   instance with explicit successful clocks and retry timing. Preserve prior
   successful data on refresh failure.
6. Keep `fetch_and_compute()` nonblocking; inject clock/client. `close()`
   cancels only owned selected tasks, removes only its own priority request,
   and leaves shared managers/clients usable. No new disk cache is required.

**Focused tests first:** two same-ticker tokens on different chains; mismatched
launch/address response; wrong workflow launch/contracts relationship; duplicate
seat/role/job; repeated seat across roles counted once; rejected/oracle nodes
excluded; malformed accepted seat; selected-only bounded calls; linked and
unrelated sites; known empty versus unread; partial/stale/failure transitions;
deep-copy protection; cancellation and reopening; borrowed-client lifetime;
mock mode refusing all transport use. Mutation witnesses must break identity,
frontend membership, contributor deduplication, and task/clock isolation.

## Package B — pure cards and panels

**Owner:** widget implementer. Independent of Package A after contract freeze.

**Files:** new `maxpane_dashboard/widgets/swarm_token_detail/` package and new
`tests/widgets/test_swarm_token_detail.py` (split hero tests only if useful).
No screen CSS, source manager, or existing shared widget edits.

**Starting symbols:** `widgets/swarm_tokens/hero.py::token_records/TokensHero`,
`widgets/surf/news_hero.py::HeroRecord/LocalSourceHeroCard`,
`widgets/panels.py::PanelBase/TableLeaderboard/SparklinePanel`,
`widgets/swarm_tokens/__init__.py` formatters, `widgets/sparkline_common.py`,
and the shared address, explorer, markup safety, row-fitting helpers.

**Implementation:**

- `DetailHero`: six rack cards in the PRD's order; reuse the current renderer,
  source state rules, and single-character text padding. Keep price values
  legible with units/scales; do not drop precision into a false zero.
- `LaunchSummary`: source-aware objective, status, verdict, recorded time,
  current matched site, repository, with safe text and links.
- `ContributorTable`: seat/role/job/state, deterministic order, internal
  scrolling, explicit pending/partial/empty/failure captions.
- `MarketPanel`: actual 24 hourly samples with gaps, source caption and
  price/change/buys-sells/FDV. All components use the same selected pool.
- `PositionPanel`: token balance, paired balance/unit, fee and withdrawn
  percentage with liquidity's own clock and state.
- `ArtifactTable`: type/name/address-or-site, all valid rows retained and
  internally scrollable. Declare package `EXPLORER` once. Every visible full
  or shortened address uses the shared copy/explorer helpers.

Widgets receive primitives only; no clock, network, manager import, or source
data module. Any helper needed twice is reused or hoisted within this package.
Request controller ownership before an essential change to a shared helper.

**Focused tests first:** all card values/palette/padding in compositor; real
zeros and unknowns; partial contributor lower bound; source clocks; hostile
markup and wide-cell names; full address/copy/explorer destinations; safe site
and repository links; missing and discontinuous chart samples; long objective
text and table scrolling. Do not certify layout pins in a bare widget harness.

## Package C — composition, navigation, and delivery

**Owner:** controller. May scaffold concurrently with A/B after contract freeze.

**Files:**

- New `maxpane_dashboard/screens/swarm_token_detail.py`.
- `maxpane_dashboard/screens/swarm_tokens.py` overview open handler/imports.
- `maxpane_dashboard/themes/minimal.tcss`, exclusively owned here.
- New `tests/screens/test_swarm_token_detail.py` plus the composing overview
  tests `tests/screens/test_swarm_tokens.py` and
  `tests/screens/test_swarm_tokens_live.py` as needed.
- Address sweep/registry test files if required by the new screen's address
  surfaces; any registry contract test adjustments remain controller-owned.
- These docs after the planning handoff, `docs/swarm_tokens_followups.md`, and
  relevant README/rule/skill notes after the live visual checkpoint.

**Starting symbols:** `SwarmTokensScreen.on_tokens_table_selected`,
`DashboardScreen` lifecycle and `PANELS`,
`widgets/swarm_tokens/detail.py::SwarmTokenDetail` (retain other callers),
`TokensTable.Selected`, and the overview's existing selection restoration.

Push `SwarmTokenScreen` with its own selected adapter. Paint selected cached
values immediately, then refresh through the established screen worker. Keep
overview mounted rather than rebuilding it, preserving filters, sorting,
selected identity, focus, and scroll. Escape pops detail and safely closes only
its adapter. The existing popup is not removed or rerouted for Portfolio.

Compose six nine-row cards above a broad left column (LAUNCH then CONTRIBUTING
AGENTS), a right column (MARKET then LAUNCH POSITION), and full-width ARTIFACTS
below. Keep a native status bar and identity heading. Use explicit content
floors, stable scrollbar gutters, and internal table scrolling so smaller
terminals disclose overflow. Mirror structural screen CSS in minimal.tcss.
The new detail screen owns its own measured pin; do not change the overview's
146×34 pin merely because this new view has different dimensions.

Integration tests prove actual click and Enter routes, returned overview state,
selection after asynchronous updates, data/panel signatures, close while loading,
mock isolation, and real composited layout at 149×45 and boundary sizes. Include
the new copy/link surfaces in the established address sweep, with transport and
clipboard stubs. Mutate the dispatch and measured pin in both directions.

## Final verification gates

- During editing: focused node IDs for touched behavior only. Avoid running
  full screen files after every edit.
- Functional checkpoint: live public, keyless data shown at **149×45** before
  pin comments, layout documentation, or reviewer dispatch. A fixture render
  is useful during development but cannot replace this checkpoint.
- After the live checkpoint: measure the new screen in situ, sweep its clean
  width/height boundaries, and record the binding content in its `#:` block.
  Existing Surf s/a/b pins use `scripts/measure_layout.py` only if touched;
  this dedicated screen requires its own real-screen harness.
- Stable implementation: once run touched data/widget/screen tests plus their
  composing files using isolated HOME, `env -u NO_COLOR`, `-n 4 --dist worksteal`.
  Run `-m 'guard and not mounts_app' tests`, and required docpin/registration
  checks for the surfaces changed. Run focused address sweeps. No full suite.
- Use `scripts/mutate.py` for decoder, concurrency, and layout proof; inverse
  restore only. Record which assertion fails, never count an import failure as
  a semantic witness.
- A final generic reviewer receives the diff, exact tested risks, live render,
  mutations, and the repository's reviewer contract verbatim. No parallel
  duplicate review. File Minor-only residuals in the existing followups doc.
- Controller finishes with `git diff --check`, respects existing untracked or
  unrelated files, and creates the local commit with concise validation evidence.

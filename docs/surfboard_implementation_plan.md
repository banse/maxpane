# SURFBOARD hub implementation plan

Status: **implemented and verified**. Dashboard 9 and the shared
source-consistency correction are present on the dedicated branch.
Branch: `feature/surfboard-hub-9`, based on `6a22d54b`.
Authority: `CLAUDE.md` → [PRD](surfboard_PRD.md) → [source research](surfboard_game_mechanics.md)
→ this plan. No Superpowers. Preserve unrelated work and the standalone mock.

## Decision and scope

Implement `SurfboardScreen(DashboardScreen)` as a separate rack entrance, sharing the
existing `SurfManager`, clients and cache with the installed `SurfScreen`.
App routing opens its seven existing modes and supplies an explicit return context.
The alternative, a new inherited `SurfScreen` hub mode, saves a routing seam but extends
its hero/body/title/scroll invariants and repaints every hidden panel. Separate screens
is the selected, reversible choice; no existing body is copied or remounted in the rack.

The PRD owns appearance and formulas. Keep exactly 7 active + 3 planned + 2 empty positions:
top ANNOUNCE/SWARM/AGENT/BOARD/LAUNCHPAD/POOL4; lower left PROTOCOL/PORTFOLIO/BAY 11;
lower right SWARM TOKENS/EARNINGS/BAY 12. The terminal spans columns 2–5, rows 2–4.
The target is 149×45; actual minimum-size pins are measured after the live preview.

This is Tier 2: new dashboard, data keys, shared lifecycle seams and legacy source changes.
Estimate **1,850–2,650 changed/new production lines**, excluding tests, fixtures and prose:
contract/client 200–300; source/manager/commands 650–900; new and migrated widgets 650–900;
screen/routing/lifecycle 350–550. These are sizing estimates, not line-count acceptance gates.
The under-1,000-line review exemption does not apply. Each package gets one task review,
at most two fix rounds; final whole-branch review uses the most capable available model,
one fix wave and one scoped re-review only if production code changed. File Minor findings.
WP0's reader/contract review can precede UI integration. Hold display-affecting WP1–WP3
task reviews until the first integrated live preview; then review each owned diff once.

## Execution and ownership

| Package | Owner | Depends on | Parallel work |
|---|---|---|---|
| WP0 contract, API and fixtures | Data implementer A | This spec | None |
| WP1 source consistency, scheduling, meter projection | Data implementer A | WP0 frozen | WP2 |
| WP2 rack, terminal, legacy widget migration | UI implementer B | WP0 frozen | WP1 |
| WP3 screen, routing and registration | Integration implementer C | WP1 + WP2 | None |
| WP4 live preview, measured layout and completion | Controller with original file owners | WP3 | Disjoint corrections only |

One implementer owns each package; A retains ownership across WP0/WP1. C alone edits
`app.py`, `__main__.py`, `screens/game_select.py`, `screens/surf.py`, shared screen lifecycle
modules and `themes/minimal.tcss`. Contract amendments return to A before dependent edits.
WP2 owns its widget files even during WP4; reviews report defects and do not fix them.
The controller owns final documentation and the follow-ups update. No worktree is required
for this already dedicated branch; remove any temporary planning workspace if one is used.

## Scheduling contract to implement

Use injected time and a small number of explicit tasks; do not build a polling framework.

1. `fetch_and_compute()` joins a manager-owned full-collection task with cancellation shielding.
   An eligible start records its start time; another call joins it, never queues another cycle.
   A call before the configured poll interval expires assembles cached data. Explicit refresh
   also coalesces and respects source failure backoff. The startup prefetch uses this same seam.
2. `fetch_hub_snapshot()` offers due full work without awaiting it, offers due lightweight
   sources, and immediately assembles available cache snapshots. It never awaits seat detail,
   records, RPC history, ENS or full collection before painting. Completed work paints next tick.
3. The hub uses one inherited lifecycle timer with interval `min(15, poll_interval)` seconds,
   after the existing positive-interval validation. Due work starts on the next hub tick, never
   sooner than its source/full-collection minimum interval. A non-dividing configured interval
   can add less than one tick of delay; do not add a one-second timer to obtain exact alignment.
   Standard screens keep their configured timer; suspending stops the hub timer.
4. Overview success TTL is 15s while the rack is visible and 60s elsewhere, failure backoff 30s.
   Hourly steps use 60s success/failure intervals and are eligible only while the rack is visible.
   Records use the existing BOARD 120s cadence/backoff; retain the provider cache disclosure ≤600s.
   Existing workers/contributors remain on their BOARD cadence and independent last-good slots.
5. Each source has one in-flight task and one slot publisher, shared by both refresh entry points.
   Full collection and hub ticks must offer/join the same overview/records task, never competing
   writers. Reuse `_spawn_swarm_board` for BOARD ownership; independent source clocks prevent
   successful workers from making failed records fresh. Unrelated existing detached sweeps stay.
6. Cache publication replaces a whole validated source envelope synchronously. Assembly captures
   slot references/copies once, without awaits, before deriving cards, selected outcomes and rank.
   Overlay those newly captured source families on the last full payload; do not reuse stale
   contributor-derived outcomes from it. No valid full payload yet means explicit unavailable
   values for its families, while available lightweight sources can already paint.
7. A successful observation updates `read_ts` even if the payload is unchanged; provider time
   and content version remain distinct. Failed attempts retain the previous successful `read_ts`.
   Rank baselines advance only from validated canonical content, never read-clock changes.
8. Waiter cancellation does not cancel shared source/full tasks. `close()` marks the manager
   closing, rejects new offers, cancels/awaits each owned task once, then saves/closes once.
   Screen navigation changes eligibility, not ownership, and must not close the manager.

Add `DashboardScreen._fetch_data()` defaulting to its current manager call. The hub overrides
only that hook, retaining `PANELS` dispatch and inherited scheduling. Add a default-true
`RefreshGuard.JOIN_STARTUP_PREFETCH`; the hub alone sets it false after manager protection exists.
Otherwise a slow startup full collection would block its lightweight feed before the hook runs.
Regression tests must preserve joining and scheduling behavior for every existing screen.

## WP0 — freeze contract, readers and evidence

Owned production: `data/surf_models.py`, `data/surf_swarm_client.py`; required narrow additions
to `data/surf_client.py` only where launchpad completeness cannot be represented/read already.
Owned tests: `tests/data/test_surf_models.py`, `test_surf_swarm_models.py`,
`test_surf_swarm_client.py`; sanitized `tests/fixtures/surf/swarm/hub/` and a provenance manifest.

- Freeze new overview/events/hourly, canonical selected-outcome and source-state fields, plus
  rack/terminal widget signatures in the existing model contract. Explicitly separate identity,
  outcome, effort and presence clocks. Update BOARD row/summary contracts for failed outcomes.
- Output contract: extend `SURF_KEYS` with `SURFBOARD_KEYS`, naming `surfboard_cards`,
  `surfboard_overview`, `surfboard_events`, `surfboard_hourly` and `surfboard_sources`; add
  `swarm_seat_outcome` and `swarm_outcomes_source` independently of `swarm_seat_summary/state`.
  Cards carry `key/title/status/primary/secondary/detail/destination`, `meter_kind`, exact
  `numerator/denominator`, and eight `points` for a sparkline; unused alternatives are `None`.
  Outcomes carry `token_id/listed/attempts/accepted/rejected/failed/pending/accept_rate/rank/ranked_of`.
  Overview carries separately named network counters; event rows preserve timestamp, kind,
  canonical job/seat IDs, role, step, state and objective. Unknown source lists are `None`,
  successful empty lists `[]`; planned cards are explicit records, empty bays are layout positions.
  `SURFBOARD_WIDGET_SIGNATURES` binds rack and terminal inputs to these keys, with agreement tests.
- Freeze each source envelope: normalized payload, successful `read_ts`, optional provider
  timestamp, content version, last-attempt state/time. Persisted validation uses the same rules.
- Add GET readers for `/swarm`, `/seats/records`, `/steps/hourly` on the existing host pool.
  Validate jobs `limit` 1–500, exclusive ISO `before`, and `q` length ≤200 through `params`.
  Invalid caller values cause no request. Preserve host rotation and `None` on failed reads.
- Capture exact response shapes and timestamps. Keep mismatching seat 420 records/contributors,
  valid seat 1836 records and invalid `/swarm.seats` 0-attempt/1-accepted examples. Add malformed,
  empty, missing-field, duplicate-ID and hostile-text variants with clear synthetic provenance.
- Inventory every `fetch_jobs()` caller: explicitly bounded recent history stays bounded;
  completeness claims need bounded pagination with an incomplete flag. Freeze that contract now.
- Freeze meter readiness, including uncapped launchpad population/history/day-swap completeness.
  Existing display `launchpad_coins` is insufficient; any extra raw coverage facts are model keys.
- Pin terminal limits: 512 input characters, 200 command/reply lines, 20 search results,
  one uncached lookup per screen, existing client timeouts; freeze supported role/state mappings.
  Reuse existing identifiers and explorer allowlists rather than introducing a URL parser.
  A job prefix resolves to a unique canonical job in known events; ambiguity remains a reply.
  A search-URL fallback requires a documented allowlisted route, never a guessed URL.

TDD: fail on missing readers/fields and invalid query acceptance; then implement the minimum.
Run the three owned test files. Review WP0 and freeze the contract before parallel dispatch.
The readers, source slots, lightweight manager API and native command executor do not exist yet;
later packages must implement them, not assume the mock or existing client already provides them.

## WP1 — correct sources and make refreshes safe

Owned production: `data/surf_manager.py`, `data/surf_cache.py`, `data/surf_swarm.py`, new
`data/surfboard.py` for normalization/projection/command service as needed; pure meter and
command parsing helpers in `analytics/surfboard.py`. A retains WP0 files for contract fixes.
Do not introduce another manager, cache file, HTTP client pool or UI import into these modules.

- Implement the scheduling contract above, three independent source slots and safe hydration.
  Split cached projection from collection only where needed; avoid rewriting the whole manager.
- Replace contributor-based BOARD outcomes/ranking in `_swarm_board_keys` and `_seat_rank_delta`.
  Normalize records once, reject the whole inconsistent snapshot, join effort/presence by token.
  Rank with integer fraction comparison; preserve worker-only records outside ranked population.
- Keep selected outcome availability independent of `/seats/{id}` availability. Derive AGENT,
  BOARD and hub ratios/ranks from the same records snapshot, never patch a fresher detail row in.
  Tag the rank slot `seat-records-v1`; discard only old-basis delta baselines, preserving other
  cache history/seat selection. Same-basis absent/new seats have no fabricated previous rank.
- Project SWARM headlines from overview only; keep global jobs, oracles and accepted steps distinct.
  Keep local observed-job history explicitly scoped; fix misleading pagination/global-count usage.
- Project all seven meter definitions from research. Derive detector denominator from SIGNAL_NAMES;
  use full launchpad pool-ID coverage, existing pool4 snapshot values and `measured_split`.
  Validate zero/unknown/invalid independently; no clamping or defaults that turn failure into zero.
- Implement read-only command lookups with existing keyless ENS/address helpers. Reuse source tasks;
  bound uncached identity lookup concurrency and timeouts. No command triggers a full history scan.
  Return data/navigation intents to the screen, never execute a shell or navigate from the manager.

Tests: add `tests/data/test_surfboard.py`, `test_surf_manager_surfboard.py`,
`tests/analytics/test_surfboard.py`; extend `test_surf_swarm_board.py`, `test_surf_cache_swarm.py`,
`test_surf_manager_swarm.py`, `test_surf_swarm_seats.py` and affected existing manager tests.
Use controlled futures/clock: simultaneous callers, slow full startup with successful overview,
tick cadence/backoff, cancellation isolation, slot-version coherence and close-during-fetch.
Assert seat 1836's bad overview row cannot contaminate canonical rank; divergent seat 420 sources
produce identical acceptance/rank everywhere. Cover count mismatch, duplicate normalized IDs,
bool/nonfinite/negative counters, invalid partition, empty valid population, partial source outage,
cache migration and newer detail history. Mutation proof targets partition validation and shared tasks.
Run targeted cases while editing; entire touched data/analytics files at package completion.

## WP2 — rack/terminal and legacy widgets

Owned production: new `widgets/surfboard/{__init__,rack,terminal}.py`; existing
`widgets/surf/swarm_agent_hero.py`, `swarm_board_hero.py`, `swarm_leaderboard.py`,
`swarm_fleet.py`, `swarm_hero.py` and their directly used `_swarm*` rendering helpers if needed.
Widgets receive frozen plain data; they never import clients/managers or consult the clock.

- Reuse `HeroBoxBase`, `PanelBase`, row fitting, sparkline, markup safety and address helpers.
  Rack owns twelve fixed slots and publishes card-activation/focus messages. Focused details
  disclose exact meter denominator, source time and cache limit without expanding every card.
- Build bounded recent-event reconciliation, stable row keys, adjacent-job grouping and separate
  bounded command replies. Preserve scroll anchor/tail policy and input draft/focus across updates.
  Unknown event states remain literal; sanitize ANSI/control/markup and untrusted link text.
- Terminal input emits command requests; it performs no I/O. Implement local command display
  states/help/clear from the contract; planned cards explain their state and create no route.
- Migrate legacy AGENT/BOARD/SWARM render contracts: ACCEPTED WORK, recorded-seat population,
  independent effort/summary clocks and no pending-as-running. Do not redesign their bodies.

Tests: add `tests/widgets/test_surfboard_rack.py`, `test_surfboard_terminal.py`; update
`test_surf_widget_contract.py` and changed `test_surf_swarm_{agent_hero,board_hero,leaderboard,
fleet,hero}.py` files. Assert composited text, source degradation, real zero, invalid ratios,
partial/incomplete meter data, long identifiers, inert hostile strings and shared address behavior.
Use repeat/changed/overlapping event snapshots to prove no duplicate appends, lost replies or
cursor jumps. Test every planned card and empty bay separately from active card activation.
Run targeted cases while editing and whole owned widget files before the package review.

## WP3 — integrate screens, navigation and dashboard 9

Owned production: new `screens/surfboard.py`; `screens/surf.py`, `screens/dashboard_screen.py`,
`screens/refresh_guard.py`, `app.py`, `__main__.py`, `screens/game_select.py`,
`themes/minimal.tcss`. C owns the same files in later layout corrections.

- Add the two small shared lifecycle hooks, the rack's declared `PANELS`, source eligibility
  and normal polling. Keep inherited refresh guard; no new exclusive-worker scheduler.
- Add public validated `SurfScreen.open_mode(mode, return_context=...)`, callable before/after
  mounting. App routes all seven cards through its existing installed screen with `switch_screen`.
  Keep `_current_game='surfboard'` during visits; same-body toggles and Escape honor return context.
  Local filter editor/modal closes first. Explicit entry 1, menu and Tab clear transient context.
  Reentering the hub restores originating card focus, terminal draft and scroll position.
- Set visible-mode eligibility on every entry/exit, including AGENT→menu/Tab/hub. Do not let a
  suspended screen overwrite it when a prior refresh completes. Async command replies carry a
  screen-generation token invalidated on navigation; cancel/suppress stale replies without
  cancelling manager-owned shared work. `open #n` uses existing validated seat selection behavior.
- Implement arrow-card navigation, `/`, Enter and Escape. App Tab falls through while input is
  focused; test literal q/m/t/r/digits and slash. Outside input preserve dashboard cycling.
- Append game ID `surfboard` as 9; prefetch maps to `_surf_manager`. Update app, CLI then GAMES,
  preserving existing defaults/order. No new manager attribute or shutdown call. Update ALL_GAMES
  in `tests/test_app_startup.py`; the four MANAGER_ATTRS lists remain unchanged.

Tests: new `tests/screens/test_surfboard_screen.py`, `tests/test_surfboard_registration.py`;
extend `tests/screens/test_dashboard_screen.py`, `test_refresh_guard.py`,
`test_surf_swarm_v2_integration.py`, affected body composing tests, startup and CLI agreement tests.
Cover menu9, cycle8→9→1, prefetch alias, all seven routes, body-to-body then hub, modal/editor Escape,
entry1 isolation, repeated menu/Tab transitions without stack growth and exact-once manager close.
Mount the real app with every manager stubbed; assert live-feed progress while startup full work
is blocked, unchanged legacy prefetch joining and stale command results suppressed after navigation.

## WP4 — preview, measurement and branch completion

Show the actual keyless live 149×45 render before layout hardening or final review; correct it
through the original file owners. Fixture/mock screenshots do not satisfy this project gate.
Then measure independent hub boundaries in situ using normal/stress/empty/degraded/wide-text
payloads. Add `tests/screens/test_surfboard_layout.py` and the harness registration needed by
`scripts/measure_layout.py`; controller owns measurement tooling/registry additions only.
Re-sweep changed AGENT/BOARD/SWARM labels/clocks; retain each body's independent measured pins.
Update the local terminal-layout skill table and `#:` evidence only after measurement. Verify
smaller viewports scroll visibly, the six-column topology survives, and the status/detail bars fit.

Controller updates README, `CLAUDE.md`, `.claude/rules/{dashboard-registry,surf}.md`,
`docs/imd_swarm_api.md`, this plan's status and `docs/surf_swarm_followups.md`. Correct
active “no jobs pagination” claims; retain dated historical research as historical evidence.
Run decoder/concurrency/layout mutation proofs with `scripts/mutate.py`, restoring byte-for-byte.

Before completion, run whole touched and composing files once using isolated HOME and the
project's parallel pytest command; include affected legacy body files, not every screen suite.
Run `.venv/bin/python -m pytest -m 'guard and not mounts_app' tests`, plus registration mounts
`-m mounts_app tests/test_surf_registration.py tests/test_curator_registration.py
tests/test_fwa_guardrails.py tests/test_surfboard_registration.py` and docpin tests.
No full suite unless the owner requests it or a version is tagged. Final whole-branch review
checks the PRD, same-source invariants, actual live preview, targeted evidence and residuals.
Only then mark implementation complete.

## Implementation evidence — 2026-10-09

- Registered `surfboard` at 9 without a second manager or changing the original default.
- Live 149×45 renders used public endpoints and an isolated cache. Network overview painted
  within six seconds while full collection continued; missing POOL4 return-window evidence
  remained unavailable. The owner received the live render before measurements and reviews.
- The rack measures 140×36 with the short-window scrollbar allowance; 139×36 fits without
  vertical scrolling. The app-wide 143-column pin is unchanged. Four payload classes and
  both sides of each boundary are covered; event prose may retain its own truncation marker.
- WP0 review approved readers/contracts. WP1 review corrected timestamp range checks,
  independent meter freshness and service status output. WP2 review corrected freshness on
  absent recorded seats. WP3 review corrected persistence of terminal seat selection.
- Mutation checks cover malformed job limits, outcome partition rejection, shared-fetch
  cancellation isolation, startup-prefetch opt-out, late command suppression, event scroll
  anchors and both directions of each layout pin. Each mutation restores the original bytes.
- Final whole-branch review raised two POOL4 text-fit findings. The single fix wave keeps
  the exact meter ratio and both independent clocks visible, uses a complete compact seven-day
  label, and marks longer focused details for widening. Scoped re-review: **Approved**;
  all three production-projector/compositor regressions passed.
- Final checks passed: 1,534 data/widget/startup cases; composing-screen coverage with the
  former contributor-based expectations migrated; 104 final-fix data/screen/layout cases;
  122 guards; 82 registration mounts; five affected address cases; 12 documentation pins.
  Tests use fixtures and isolated caches. The final public-API preview was refreshed separately.
- Full-suite execution is intentionally excluded by the project's Tier 2 workflow; scoped
  data, widget, composing-screen, address, registration and documentation checks are the gates.

## Terminal parity extension — complete

Base `63771d53` on `feature/surfboard-hub-9`. The owner requests live events after command
replies, the imd.fun footer, and the reference terminal's text columns/appearance. This is
Tier 2 because it adds a data contract key. Estimate **360–620 production lines** for the
whole extension: data 120–180, terminal 200–350, screen integration 40–90. The under-1,000-line
rule applies: no package reviews; one final review after the live preview and targeted checks.
The original implementation evidence above remains historical, not proof of this extension.

### Frozen data and presentation seam

- Add only `surfboard_footer` to `SURFBOARD_KEYS` and the terminal's update signature. Its
  plain dictionary fields are `market_value_usd`, `market_basis`, `market_state`,
  `market_read_ts`, `inference_tokens`, `overview_state`, `overview_read_ts`, `provider_ts`,
  and `as_of`. Basis is `market_cap`/`fdv`/None; states use ok/stale/unavailable. Values and
  clocks may be None except `as_of`, which is the manager's injected current timestamp.
- Add optional-default `MarketSnapshot.market_cap_usd`, read from the already verified
  DexScreener pair's `marketCap`; use existing `fdv_usd` only with a visible FDV label.
  Preserve pool verification, existing request cadence and source clocks; no new endpoint.
  Validate finite nonnegative values without treating genuine zero as missing. Market failure
  retains honest last-good/stale behavior and does not erase available inference statistics.
- Add optional strict nonnegative integer `inference_tokens` from `/swarm.counts.inferenceTokens`
  to normalized overview; absence must not invalidate otherwise useful older cached snapshots.
  Normalize numeric `/swarm.at` milliseconds to seconds at that endpoint boundary. Do not
  change generic timestamp handling for sources that already serve seconds or ISO timestamps.
- `$1B` is the named website presentation goal, not a fetched protocol parameter. Its 24-cell
  bar may saturate at the goal while the exact actual value remains visible. Show compact token
  usage and provider snapshot age; never present local read age as provider freshness.
- Terminal `update_age(elapsed)` accepts injected nonnegative elapsed seconds, computes age
  from `as_of + elapsed - provider_ts` with a zero floor, and repaints only footer chrome.
  Missing provider time renders unknown age. `update_data` resets elapsed to zero. The screen
  owns an injected monotonic clock and one lifecycle-stopped one-second display timer; this
  timer causes no manager call, network request, transcript repaint or widget clock access.

### Bounded mixed transcript and reference rendering

Keep stable mixed event/reply order, at most 60 current event rows and 200 reply lines. A valid
snapshot replaces event payloads, removes event keys outside its bounded window, retains reply
positions, and appends unseen events after the latest reply. Repeated/overlapping snapshots
must not duplicate rows. A failed/None event update preserves available rows with failure
disclosure; a successfully empty list clears event rows only. `clear` removes replies only.
There is no durable history or unbounded seen-key set. Preserve input draft/cursor/focus and
the existing keyed scroll anchor; follow the tail only when the reader was already following.
Commands break adjacent-job tree grouping, so an event after a reply starts a visible new group.

Use the public reference's columns after the tree prefix: time 7 cells, event 8, actor 13,
state 13, then flexible objective text. Node rows display as job rows; `agent #n` means the
served token ID, never agent ID. Reuse literal text fitting, address units and safe links.
Keep unknown states explicit and preserve the real role/step meaning when choosing verbs.
Use the agreed phosphor styling within the terminal; do not change the outer rack topology.
The footer must fit the current 140-column rack pin and 149×45 target, with visible truncation
disclosure at narrower widths rather than losing tokens, freshness or FDV meaning silently.

### Packages, ownership and acceptance

| Package | Owner and files | Dependency |
|---|---|---|
| T1 footer source/projection | Data worker: `data/surf_models.py`, `surf_client.py`, `surfboard.py`, `surf_manager.py`; their targeted data tests | Frozen contract above |
| T2 transcript/footer rendering | UI worker: `widgets/surfboard/terminal.py`, `tests/widgets/test_surfboard_terminal.py` | Frozen contract; parallel with T1 |
| T3 integration/live verification | Controller: `screens/surfboard.py`, screen/layout tests, fixtures, README/PRD/research and source/guard documentation | T1 + T2 |

Workers preserve others' changes. This planning agent owns only this appended plan. Tests
precede implementations: T1 proves market-cap preference, labelled FDV fallback, verified-pair
selection, missing/bool/nonfinite values, optional cached fields, milliseconds and separate clocks.
T2 reproduces command→new event ordering in composited output, then covers repeated snapshots,
aged-out keys, failed versus empty reads, bounded replies, clear, anchors, draft and literal text.
Test exact reference column starts, footer unavailable/stale states, goal saturation and a
footer age change that leaves RichLog rows and scroll unchanged. T3 proves the one-second
display timer resets on data, stops on suspend, resumes once and makes no additional fetch.

Show the actual keyless live 149×45 render before layout hardening or final review. Then run
changed data/widget files and composing screen/layout/contract tests, fast guards and applicable
docpins; run address tests if address fitting changed. No full suite. Mutate the ordering fix
and footer source/age decoding to prove the new regressions fail, then restore original bytes.
Re-measure affected boundaries in situ without guessing a larger pin. Final review gets one
fix wave and one scoped re-review only for production fixes; file Minor findings in follow-ups.
Record extension-specific evidence before marking this extension complete.

### Extension verification — 2026-10-09

- The final keyless public-API capture at 149×45 visibly shows two new event rows after a
  `status` reply. The reference columns, service markers, one-line prompt and valuation/
  inference/age footer fit in the existing three-row terminal span. Card styling is retained.
- A mixed bounded transcript fixes the event/reply ordering. The footer reuses the verified
  market pair and independent overview clock; its display-only age timer stops on suspension.
  Valid older overview envelopes migrate with an unknown token count while retaining their
  original clocks and events, even when the next refresh fails. Original hashes are checked.
- Data verification passed 587 cases initially and 317 affected data/composing cases after
  the legacy-cache preservation change. The final UI/contract/composing run passed 251 cases;
  122 fast guards, 12 documentation pins and two hub address-sweep cases also passed.
- Six targeted mutants were killed and restored: strict inference-count decoding, original
  legacy-cache hash validation, live-event ordering, footer elapsed age, screen capture reset,
  and timer stopping. The prompt overflow regression failed at both 140 and 149 columns before
  the input's width was corrected.
- The in-situ 139–141 by 35–37 boundary measurement confirms the existing 140×36 rack pin;
  the four payload-class layout tests also pass. No layout pin changed.
- Final whole-diff review: **Approved**, no findings, with 12 additional focused tests. No
  review fix wave was needed. No full suite was run, per the scoped Tier 2 workflow.

## Event semantics and 30-second terminal — complete

Base `6c078a77`; same dedicated branch. The owner compared the terminal with imd.fun and
identified unknown launch/site states and incorrect event labels, actors and descriptions.
Implement reference event semantics and a fixed 30-second inner-terminal refresh. This
supersedes the earlier plan's 15-second active overview cadence; previous completion evidence
does not certify this extension. Tier 2, estimated **200–400 production lines**, so no package
reviews; one final review after live preview and scoped verification. No Superpowers.

### Frozen event contract

Append sparse `details` to `SURFBOARD_EVENT_FIELDS`. Its allowed string keys are token,
ens_name, cid, failure, reason and owner; integer keys are launch_number, chain_id, steps,
scores, accepted, seat_accepted, seat_failed and owner_seats; last_work is a timestamp.
Reject bool as an integer and validate owner as an address. Invalid/missing optional live
values are omitted; persisted unsupported keys or malformed values invalidate restoration.
Preserve raw state/role/step; vocabulary belongs to the renderer. Details may use context
from the same served overview without changing canonical outcome/ranking sources.

Hash original event fields except key/details for stable row identity. Verify the original
envelope hash and each original event hash before adding details={} to valid older events;
then validate and hash the upgraded envelope. Compose this with the existing optional
inference_tokens migration. Keep source clocks, unknown metadata and last-good outage behavior.
Metadata-only updates must not move events past command replies or create duplicate rows.
Older cached building/reviewing states may already have lost the raw served state: preserve
their validated identity on migration; do not guess that state back from the display word.

### Disjoint packages

| Package | Owner and files | Dependency |
|---|---|---|
| E1 metadata normalization/cache migration | Data worker: `data/surf_models.py`, `data/surfboard.py`, their model/normalizer data tests and sanitized event fixtures/manifest | Frozen seam above |
| E2 reference renderer and cadence | Controller: `widgets/surfboard/terminal.py`, `data/surf_manager.py`, `screens/surfboard.py`, matching widget/manager/screen/layout tests | Can start with E1 fixtures; integrate after E1 |
| E3 live proof and closure | Controller: rendering, scoped verification, source/follow-up docs; planning agent owns this plan and PRD until handoff | E1 + E2 |

E1 first writes failing typed-metadata, raw-state and cache-migration cases. Validate every
detail family and legacy format with/without inference_tokens. Tampered envelope/event hashes,
unknown cached keys and invalid counters must fail; valid pre-extension caches survive a
failed subsequent fetch. Add paired rows proving metadata changes leave the event key stable.
The data worker owns fixture provenance; no tests request network data.

E2 first reproduces launch/site unknown text in composited output, then implements the official
feedLine/job-classification rules captured from the imd.fun bundle. Cover job, node, done,
review, site, launch, agent and oracle cases. Test actor, state and description together:
publisher hosted/published with ENS/CID; deployer deployed with token/launch number and chain;
verifier onchain with available score counts; node role/step verbs and cancellation reasons;
joined agents with served owner/history rather than guessed success. Use the existing injected
footer capture time for last-work age. Preserve full owner address/copy behavior, neutral
unknown states and inert third-party text; do not add ENS/avatar reads.

Keep reference columns 7/8/13/13 after the tree marker, native title/grouping conventions,
bounded mixed transcript, input draft and anchor behavior. Launches/arrivals do not group merely
because their payload includes a job ID; replies reset grouping. An enriched retained event
updates in place. The existing footer and four-row/six-column rack remain structurally intact.

Set the screen's inherited refresh interval to 30 seconds. Change active overview due and
freshness thresholds to 30 seconds; inactive stays 60 and overview failure backoff stays 30.
Do not alter full-collection, records or hourly source gates, or the display-only one-second
footer age timer. Controlled-clock tests prove no overview request before 30, eligibility at
30, inactive behavior, and unchanged other source intervals without sleeping or network I/O.

### Verification and completion

Run targeted data/widget cases during development, then whole touched files plus composing
`tests/screens/test_surfboard_screen.py`, `test_surfboard_layout.py` and widget-contract tests.
Show the keyless live 149×45 terminal before layout hardening/final review; verify reference
rows against source facts, not invented demo values. Check the current 140×36 boundary and
address sweep if address rendering changed. Add decoder/hash and active-cadence mutation proof.
Run applicable fast guards/docpins; no full suite. Final review allows one fix wave and one
scoped re-review for production fixes. Record new evidence and residuals before marking this
extension complete; preserve the earlier completed extension's evidence as historical.

### Event extension verification — 2026-10-09

- The public bundle and API confirmed kind-specific actor/state/detail semantics. A live
  149×45 capture shows `job / deployer / deployed / PixelToken · Ethereum` and `30s poll`.
  Launch/site metadata, completion counts, verifier scores and arrival history now survive
  normalization; unknown metadata stays explicit. The highlighted input and footer are retained.
- The initial integrated run passed 574 data, widget, contract and composing cases; the address
  link addition passed 127 terminal/screen/layout cases. Fast guards passed 122 cases, docpins
  12, and the hub address sweep two. Tests use offline fixtures and isolated caches.
- Nine targeted mutants were killed and byte-restored: metadata-dependent identity, legacy
  event-hash bypass, malformed owner acceptance, early fetch, early staleness, early screen
  refresh, missing blocked-failure semantics, missing cancellation step, and equal-time
  arrival misclassification. Source interval tests use injected time without sleeps.
- Final review found three Important event edge cases. The single fix wave maps captured
  blocked completions to stopped with failure detail, retains cancelled-node steps and limits
  arrival work history to preceding events. Four focused regressions passed; scoped re-review
  marked all three **ADDRESSED / Approved**. No remaining review findings were filed.
- The four-payload rack boundary checks keep the 140×36 pin unchanged. No full suite was run.

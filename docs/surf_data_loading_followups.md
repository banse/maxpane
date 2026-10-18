# Surf data loading — execution and follow-ups

Implementation of [the approved specification](surf_data_loading_spec.md) and
[plan](surf_data_loading_plan.md), starting at `888a1dd4` on
`feature/surfboard-hub-9`. The application remains keyless and read-only.

## Scope and decisions

- P1/P2: exact Ethereum reference-pool identity, validated token orientation,
  DexScreener primary with same-pool GeckoTerminal fallback, and a separate
  ETH/USD client read. Missing market cap is not replaced with FDV.
- P3: instance-scoped complete job-detail memo, independent consumer copies,
  shared requests, bounded storage, explicit source observations, and safe
  cancellation/shutdown.
- P4: active WORK details are confirmed after the relevant discovery page;
  historical context can reuse the memo. Pagination, semantic budgets and atomic
  snapshot publication remain.
- P5: RECORD revalidates complete terminal facts after 600 seconds and incomplete
  facts after 120 seconds, within the existing four-answer/two-detail caps.
  Failed reads retain last-good facts without renewing their source times.
- P6 mandatory quote-slot/projection integration is implemented: independent
  successful quote observations, consistent full/passive price projection,
  independent pool clocks and identity-sensitive price direction.

The numeric EIP-155 `chain_id` in the specification takes precedence over the
initial plan's string annotation; the plan and implementation were corrected.

Conditional P6 scheduler changes, a shared Gecko gate/deadline change, and P7
RECORD stage reordering are deferred. The baseline was censored and does not
establish their performance benefit or a combined quota overrun. Existing token
pacing and scheduling remain. These are follow-ups requiring measurements, not
unfinished mandatory implementation.

## Evidence and limits

The [baseline note](research_notes/surf_data_loading_baseline.md) records the
original measurements and their limitations. Initial instrumentation missed
clients created lazily; historical live totals are explicitly unknown. The
measurement tool now instruments those factories before their first request.

Offline transport tests establish five simultaneous same-job readers sharing
one logical HTTP fetch, while preserving complete independent payloads. This is
a request-count result, not a measured end-user latency improvement.

An actual MaxPaneApp live render at 149×45 was shown for BOARDROOM and AGENT on
2026-10-17. The corrected instrumentation recorded 80 requests, 75 HTTP 200
responses and five requests cancelled at the cap, with no new request after
the freeze. Seat #527 came from the real board. Its detail request was attempt
80 and was cancelled before completion: the summary rendered, but RECORD was
unavailable. No complete RECORD live acceptance or UI speedup follows from this
run.

The final integration render again used 80 actual requests: 76 HTTP 200,
one read error and three cancellations at the cap; no request began after the
freeze. ETH/USD was successfully stored in its own slot while the pool-market
slot was absent, confirming that partial-success behavior with real data.
The selected seat request again did not finish before the cap, so complete
RECORD live coverage remains open. Parallel offline checks and censored
collection rule out a comparative latency claim.

## Review corrections

- P0: capture late-created HTTP clients and compare measured attempts with an
  independent transport counter. Scoped re-review approved; 16 tests passed.
- P1: use numeric chain IDs. Scoped re-review approved; 71 tests passed.
- P2: task review approved; 308 client/decoder tests passed and identity,
  orientation, cap/FDV and cancellation mutations were caught.
- P3: keep ownership of retiring scope tasks until drained, including during
  concurrent close. Scoped re-review approved; 198 client/cache tests passed.
- P4: task review approved; 55 WORK-reader tests passed and four discovery/cap
  mutations were caught.
- P5: retain invalidations beyond the per-cycle caps and after failed early
  refreshes; acknowledge a version only after its resource read succeeds.
  Scoped re-review approved; 238 freshness/answer/card/decoder tests passed.
- P6: 516 owned cache/manager/projection/hero tests passed; six clock, identity,
  legacy-cache, numeric-validation and quote-source mutations were caught.
  Review found a cycle-start/future-quote mismatch and an AGENT fallback-source
  mismatch. Both were corrected; three new regressions and two rollback
  mutations verify the fixes. Scoped re-review approved; 140 affected
  manager/hero tests passed after the corrections.

These are package-level results, not a whole-suite claim. No full suite has
been run for this change. Existing unrelated layout failures F-R4/F-R5 remain
documented in [the AGENT follow-ups](surf_agent_record_view_followups.md).

The first composing run also exposed an erroneous empty `HOME` in the
controller's shell invocation. The affected BOARDROOM failures are environment
failures and require a correctly isolated rerun. Four old test expectations
were updated to the independent quote and source-observation contracts. An
order-dependent measurement-test constructor patch was fixed and now blocks
real HTTP transports before sending; its 16 tests pass.

Eight other composing failures were reproduced serially both on the current
implementation and on an untouched `888a1dd4` archive, with separate temporary
HOME directories, `NO_COLOR` unset, verified import paths and zero guarded
network attempts (8 failures in each run, identical assertion signatures):

- `test_surf_manager_swarm.py::test_board_keys_are_exact_before_finalization_and_survive_cold_start`:
  existing `swarm_launch_read_ts` key is absent from the test's expected set.
- `test_submission_detail.py::test_markup_in_metadata_and_other_seat_cap_are_literal`
  and `test_job_line_exposes_cached_read_time[unavailable]`: tests expect an
  unavailable marker that the existing UI suppresses.
- `test_oracle_answer.py::test_popup_question_notes_and_address_list_use_shared_copy_and_link_helpers[4663]`:
  test expects no link for the existing Robinhood explorer address.
- `test_oracle_answer.py::test_popup_snapshot_invalid_and_failed_answers[unavailable]`:
  same suppressed unavailable marker expectation.
- `test_oracle_answer.py::test_resume_real_manager_keeps_fresh_seat_answers_and_oracle_cache`:
  existing observable-state settlement assertion fails.
- `test_surf_swarm_details.py::test_swarm_layout_parks_exported_widgets_and_puts_launches_below_workflows`:
  existing layout expects rows at equal y coordinates (actual 23 versus 12).
- `test_surf_screen.py::test_every_list_row_in_the_fixture_matches_the_frozen_row_shape`:
  existing `swarm_site_rows` fixture omits `named_ts`.

These baseline failures are follow-ups, not broadened repair scope. The final
correctly isolated composing run finished with **683 passed and exactly those
8 baseline failures** in 147.19 seconds. Fast guards: **125 passed**;
documentation pins: **12 passed**.

The final whole-change review found two Important integration defects: popup
completion observations were pruned against an older cycle clock, and known
server revisions did not invalidate the RECORD projection's due filter. The
single final correction wave uses the post-await injected validation clock and
includes already-known revisions in each resource's confirmation signature.
It retains invalidations across caps and failed reads without another polling
path. Seven new regression cases passed, and four rollback mutations were
caught. The affected whole-file/composing run finished with **408 passed and
the one known BOARD-key baseline failure**; fast guards again **125 passed**.
Scoped re-review **Approved** both corrections, with no remaining Critical or
Important findings. The reviewer independently passed all seven cases and
caught/restored both rollback mutations. Final production commit: `f40f6df0`.
The review also caught a deliberately removed exact-seat provenance gate; the
mutation was inversely restored and the rejection test passed again.

## Filed follow-up

- **Minor — logical detail measurement boundaries:**
  `scripts/measure_surf_loading.py` instruments `fetch_job`, while new consumers
  call `read_job_detail`. Actual HTTP attempts remain counted, but logical
  detail start/end events need to follow the new API on the next tooling touch.
  Do not infer a logical-read latency comparison from the present measurements.

## Visible dashboard lifecycle (2026-10-17)

Implements [the lifecycle specification](dashboard_data_lifecycle_spec.md) and
[plan](dashboard_data_lifecycle_plan.md), starting at `09a84ddc` on the same
branch. Agency Software Architect, Backend Architect and Frontend Developer
packages were integrated by the controller.

- BOARDROOM uses the narrow card reader and bounded NFT deployment proofs;
  it does not start full destination-board collectors or mint/source reads.
  Splash/menu no longer start a full Surf prefetch.
- Dashboard entry paints cache before awaiting the cancellation barrier,
  offers a fresh read immediately and polls every 30 seconds while visible.
  Leaving cancels and drains screen workers and detached manager reads;
  completed cache values, cursors and clients survive navigation.
- The shared footer centers its animated loading signal independently of side
  labels. Refresh/navigation/poll/age hints are omitted; keys still work.
  Generated stale/unavailable notices become neutral missing-value markers.
  Internal observations and failures remain intact; domain prose is preserved.

### Measurements and live evidence

An offline comparison with identical injected clients recorded **33 → 15
client operations** for cold hub entry (about 55% fewer). These are client
method calls, not wire HTTP requests and not a measured latency improvement.
The trace is `/tmp/maxpane-layer-trace.json`.

Bounded public keyless live runs used fresh empty HOME/cache directories and
149×45 production renders. BOARDROOM, NFT entry/reentry, token overview/detail,
NEWS, SWARM, TTT, FWA and Curator were inspected. The final navigation trace
recorded 174 HTTP starts and 23 cancellations; returning from token detail
asserted that the overview regained active ownership. These totals describe
the whole navigation scenario, not BOARDROOM alone. Public source failures
remained visible in logs; e.g. FWA refused derived values after a partial slot
sweep failed its existing invariants. No speed or complete-source claim is
inferred from the live run. Artifacts: `/tmp/maxpane-layered-live/`.

Event-gated tests establish the stronger ownership guarantees, including
cross-screen cancellation finalizers, borrowed token manager handoff, native
BOARD timers, rapid reentry, passive projection and preserved cache clocks.
Rollback mutations of cancellation, scope whitelists, reentry offers and
footer placement were caught. The final review's four Important findings
(late child unmount, cross-screen drain barrier, retained POOL4 source state,
generated FWA failure notices) were fixed in one wave. Scoped re-review marked
all four **ADDRESSED**, passed the original repros plus six additional cases,
and independently caught/restored the owner-deactivation mutation.

### Verification and baseline limits

No full suite was run. The initial whole touched/composing screen batch had
2,323 passes and 21 failures. Three changed-contract assertions were corrected
and passed; 18 failures predate this task. Nine are the documented Portfolio
hero/layout failures; nine Surf fixture/layout failures were reproduced on an
untouched `09a84ddc` archive with isolated HOME and no network:

- POOL4: `test_the_bindings_are_refresh_and_the_two_view_toggles`,
  `test_the_three_bodies_are_never_showing_at_once`.
- POOL4 market: `test_the_clip_detector_sees_a_clip_inside_a_doubly_padded_leaf`,
  `test_exactly_one_hero_shows_in_every_mode[launchpad]`,
  `test_exactly_one_hero_survives_every_transition_between_bodies`.
- SWARM: `test_busy_agent_cards_keep_independent_records_at_the_pin`,
  `test_the_agent_card_row_keeps_seat_values_and_has_no_third_row`,
  `test_swarm_layout_parks_exported_widgets_and_puts_launches_below_workflows`.
- NEWS: `test_every_list_row_in_the_fixture_matches_the_frozen_row_shape`.

The post-fix 26-file batch had 1,654 passes and two failures: one remaining
FWA old-marker assertion (corrected; the full FWA screen file passed all 22
tests), plus
`test_launch_tab_click_schedules_progress_preserves_rows_and_opens_seat`.
That BOARD test's expectation of loading text inside a metric card also fails
unchanged on `09a84ddc`; it remains a baseline follow-up, not a production fix.
The additional eight shared-marker consumer test files passed all 224 tests.
The earlier backend whole-file run passed 349 tests. Results overlap and must
not be added into a unique suite total.

Registration mounts: 79 passed, one known baseline failure
(`test_a_full_outage_renders_explicit_states_not_zeros` expects a title warning
already suppressed before this change). Baseline evidence is in
`/tmp/maxpane-layered-live/baseline-tests.log` and
`/tmp/maxpane-nft-review-20261017/portfolio-baseline.log`; current whole-file
logs are in `/tmp/maxpane-layered-live/`.

Final fast guards: **126 passed**. Documentation pins: **12 passed**.
`git diff --check` is clean. Known baseline failures above remain open; this is
not a claim that the repository's full suite is green.

### Filed Minor findings

- `.claude/rules/surf.md`, old Keys and bodies paragraph: obsolete startup
  prefetch, footer hints/poll and width wording conflicts with the new explicit
  owner override at the top. Align on the next touch.
- `screens/refresh_guard.py`, module/PREFETCH_WORKER_NAME comments: describe
  the retained startup joining helper as compatibility behavior on next touch.

## Independent UI and reader threads (2026-10-18)

Implements [the reader specification and plan](reader_thread.md), based on
`5fe52bbf`. Agency Software Architect, UX Architect and Performance Benchmarker
packages were integrated by the controller. A single lazy reader thread owns
manager construction, clients, cache I/O, projections, polling and shutdown.
Textual consumes locally published snapshots and revision/loading metadata.
View and identity generations prevent a late completion from replacing the
current view. Inactive dashboards stop acquisition; retained data paints on
reentry before fresh reads finish. CURATOR queries and child NFT/token managers
use the same reader boundary. Hidden SURF bodies and unchanged snapshots no
longer receive repeated widget updates.

### Measurements and live evidence

The offline public-capture comparison at 149×45 measured navigation median
**598 → 97 ms**, navigation p95 **721 → 159 ms**, and UI heartbeat lateness p95
**520 → 90 ms**. Mounting measured **715 → 315 ms**. Eight navigation samples
are diagnostic evidence, not a latency guarantee. Mounting does not mean the
sources finished loading; the new UI refresh consumes local data while the
reader works independently. This does not establish faster API responses.
See the specification for workload and measurement limits.

BOARDROOM and AGENT were rendered with live keyless sources at 149×45 using a
separate temporary public-only cache. The Matrix theme, populated values and
animated loading footer were inspected before final review. Temporary evidence:
`/tmp/maxpane-reader-live-preview/`, `/tmp/maxpane-reader-benchmark/`.

### Verification and baseline limits

The initial touched/composing run had **1,102 passed and five failures**. One
test expected NEWS to prepopulate a hidden AGENT table while refresh scheduling
was disabled. Its setup now explicitly refreshes the selected AGENT body and
asserts that NEWS leaves it untouched. The other four failures were reproduced
on an untouched `5fe52bbf` archive with isolated HOME and no network:

- `test_surf_registration.py::test_a_full_outage_renders_explicit_states_not_zeros`:
  expects the previously suppressed outage warning.
- `test_surf_screen.py::test_every_list_row_in_the_fixture_matches_the_frozen_row_shape`:
  fixture omits `named_ts`.
- `test_surf_pool4_screen.py::test_the_bindings_are_refresh_and_the_two_view_toggles`:
  expects the older key set.
- `test_surf_pool4_screen.py::test_the_three_bodies_are_never_showing_at_once`:
  expects the older launchpad hero.

The additional WORK/POOL4-market composing run had **58 passed and two failures**,
also reproduced on untouched `5fe52bbf`:
`test_exactly_one_hero_shows_in_every_mode[launchpad]` and
`test_exactly_one_hero_survives_every_transition_between_bodies` both expect the
older launchpad hero. These six baseline failures remain open. Fast guards:
**126 passed**. No full suite was run; overlapping run totals must not be summed.

Logs: `/tmp/maxpane-reader-final-tests.log`,
`/tmp/maxpane-reader-mode-tests.log`, `/tmp/maxpane-reader-baseline-tests.log`,
`/tmp/maxpane-reader-baseline-mode-tests.log`, `/tmp/maxpane-reader-guards.log`.

The single final review found two Important issues. Its one correction wave
settles query Futures even when the reader task is cancelled before its first
step, and publishes only the narrow contribution result for idle BOARD offers.
Both synchronous cached updates and asynchronous completions remain visible,
including tasks that complete between monitor ticks. Core tests: **19 passed**.
The scoped re-review marked both findings **ADDRESSED** and approved the change;
it independently passed all five regression cases and killed/restored both
rollback mutations. Generation rejection, snapshot isolation, cancellation
barriers, UI-copy avoidance, visible-only dispatch and CURATOR I/O also have
targeted mutation evidence. No Critical or Important review finding remains.

After the corrections, the affected reader/app/startup/shutdown/CURATOR/AGENT
and handoff files passed **163 tests in 43.37 seconds**. Final fast guards:
**126 passed**. `git diff --check` passed. Logs:
`/tmp/maxpane-reader-postfix-tests.log`, `/tmp/maxpane-reader-finalguards.log`.

### Remaining measured performance work

- The reader still performs expensive cached projections and JSON serialization
  (baseline medians 187 ms and 141 ms). Thread isolation removes these operations
  from Textual's loop, but Python GIL contention can still cause jitter. Profile
  repeated seat-history projection before considering a process boundary;
  `_swarm_seat_keys` accounted for approximately 69% of the baseline projection
  profile. This is a separate measured optimization, not a reason to repaint or
  poll hidden dashboards.

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
documentation pins: **12 passed**. Final whole-change review is pending.

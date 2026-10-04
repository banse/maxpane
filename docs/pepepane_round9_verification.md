# PEPEPANE round 9 verification

Package evidence is recorded below. The final whole-branch review and its single finding-only re-review are approved. Repository suites and the deployment archive are pending; host installation and probing are owner-only actions.

## Committed work

| Package | Commit | Evidence |
|---|---|---|
| WP0 | c53a54d | Baseline 1,584 passed, 2 skipped, 1 deselected; spec body SHA256 97d4b205299b7863f75e18619e6ad15135bb9a6416046e3062a495fa84c40df6; 93 deploy/plumbing checks passed; review approved |
| WP1 | 4433345 | Eight initial RED cases; final 52 passed; additive contract, explicit shapes, old document fold and 2 MiB guard; review correction approved |
| WP2 | 347a95d | Initial 16 failed, 2 passed; final 668 passed, 2 skipped; 29 focused checks; review approved; canary sanitizer, identity parsing, Claude metadata, persisted startup/session facts, journal slow tier, busy and idle tail |
| WP3 | 1532082 | 569 scoped passed, 1 skipped, one unchanged fake-probe timeout; exact unchanged case passed serially; review launch-provenance correction gate 137 passed and scoped re-review approved |
| WP4 | 230ccd8 | Six composed bodies and selectable hero; final affected 213 passed; required separate files 27/9/45/168/69/6 passed; two review findings fixed and five-case scoped re-review approved |
| WP5 hoist 1 | 2d15bc4 | Fitted prose address helpers; precommit 45 passed; postcommit frozen SURF layout plus moved-module and guard checks 592 passed |
| WP5 hoist 2 | e348e9c | Oracle presentation helpers; precommit 316 passed; postcommit frozen SURF layout plus moved-module and guard checks 863 passed |
| WP5 bodies/flow/detail | fe3521d | Owned618passed plus corrected stale one-day assertion/whole cost9passed; final affected163passed; two review findings fixed and scoped8-case re-review approved; parent final six separate files27/9/46/170/69/6passed |
| WP6 | 52fa9f2 | Expanded layout/render gate 186 passed; contract/lean/models/docs gate 198 passed; cold peak 62.3 MiB; six compatibility files 27/9/46/170/69/6 passed; task review approved; test-only paint correction passed the full 95-case layout/cursor gate |

| WP7 identity/docs | cf69e45 | Identity regression RED at 0.1.4; 474 scoped checks passed, one pinned operator paragraph corrected and seven focused checks then passed; review approved; broker compile and manifest guards passed |
| Final review corrections | 5f5b996 | One fix wave for three findings; 412 affected checks passed, periodic-timer isolation followed by 32 navigation/regression checks passed; 13 finding-only review checks passed, all three findings addressed |

## Defect evidence

The nine success criteria map to these tests and measurements:

1. Six-card keys/clicks, one selected border, LIVE start: tests/screens/test_seat_round9_navigation.py and tests/widgets/test_seat_hero.py.
2. Six independent pins, caps, boundaries and tightness: tests/screens/test_seat_layout.py certifies all six bodies with healthy, worst and unattributed payloads.
3. First-cycle running objective and terminal cache reuse: tests/data/test_seat_round9_cache.py::test_local_running_job_uses_standing_objective_before_detail plus route budget/terminal-read tests and JOB compositor tests in tests/widgets/test_seat_round9_bodies.py.
4. CONFIG change paths, complete skills listing and original skill/boot safety flow: tests/widgets/test_seat_config_machine.py, tests/widgets/test_seat_round9_bodies.py, tests/screens/test_seat_round9_flow.py, tests/screens/test_seat_control.py.
5. RECORDS columns/filter/colours/window/cursor/Enter: tests/widgets/test_seat_round9_bodies.py, tests/widgets/test_seat_round9_tables.py, tests/screens/test_seat_round9_navigation.py and final layout certificate.
6. NODES aggregate and coverage facts: tests/data/test_seat_round9_cache.py, tests/data/test_seat_models.py, tests/widgets/test_seat_round9_bodies.py.
7. CONTROL keeps existing gate/confirm/audit safety: all 37 mapped predecessors in tests/screens/test_seat_control.py plus actual Input/detail/late-plan cases in tests/screens/test_seat_round9_flow.py and fast phase compositor in tests/data/test_seat_round9_control.py. Old modal deleted.
8. Seat 3 metadata behavior: synthetic worker-home D2, persisted-fact D3, bounded-journal D4 and end-to-end recovered-error D5 tests, with MACHINE/output-token/hero compositor tests. Owner host verification remains explicitly pending deployment.
9. Broker/protected-path scope: cumulative diff audit and Python 3.11 compileall passed at 5f5b996; all protected paths and both redactor copies are unchanged.

| Defect | Commit/package | Named failing-before test |
|---|---|---|
| D1 digit-string identities | 347a95d | tests/data/test_seat_round9_defects.py::test_d1_real_capture_string_identities_match |
| D2 worker-home Claude slugs | 347a95d | tests/data/test_seat_round9_defects.py::test_d2_root_home_classifies_tasks_research_doctor_manual[/home/imd-worker] |
| D3 persisted startup facts | 347a95d | tests/data/test_seat_round9_defects.py::test_d3_startup_facts_and_restart_flag_survive_empty_tail |
| D4 journal facts | 347a95d + WP5 presentation | tests/data/test_seat_round9_defects.py::test_d4_journal_facts_use_three_bounded_reads; tests/widgets/test_seat_round9_bodies.py::test_machine_transcripts_label_once_and_journal_explicit_reason |
| D5 recovered API errors | 347a95d | tests/data/test_seat_round9_defects.py::test_d5_summariser_ledger_document_and_fresh_process_agree (401/403/429, recovered and unrecovered) |
| D6 runtime version short form | 230ccd8 | test_claude_short_form_uses_version_number_not_code_suffix; original suffix extraction inverse paints claude Code), RED |
| D7 duplicate retention label | fe3521d | tests/widgets/test_seat_round9_bodies.py::test_machine_transcripts_label_once_and_journal_explicit_reason |
| D8 obsolete CONTROL lines | fe3521d | tests/screens/test_seat_control.py::test_control_dashboard_shows_dynamic_verbs_config_pointer_and_audit |
| D9 busy retry/backoff | 347a95d, integrated 1532082/230ccd8 | tests/data/test_seat_round9_defects.py::test_d9_busy_stops_retry_and_applies_class_floor; test_d9_busy_does_not_gate_ledger_verdicts; test_d9_busy_keeps_ledger_day_counts_and_timestamp |
| D10 idle empty tail | 347a95d | tests/data/test_seat_round9_defects.py::test_d10_successful_empty_backfill_with_watermark_is_healthy |
| D11 canary gap | 347a95d | tests/data/test_seat_round9_defects.py::test_d11_objective_reply_document_is_not_refused (base64/100kb/jwt); test_d11_sanitizer_cut_and_dollar_join_boundaries |
| D12 stable cursor/scroll | 230ccd8 + WP5 integration | test_ledger_refresh_insert_preserves_row_and_scroll; tests/screens/test_seat_round9_flow.py::test_skill_toggle_after_refresh_resize_and_hidden_update_uses_same_id |

## Required mutation proofs

All reported inverse edits were restored byte-for-byte; each named RED is from an executed test.

| Proof | Mutation | Named RED test |
|---|---|---|
| 1 | Health colours selection border | test_selection_border_and_health_label_are_independent |
| 2 | Selection changes label colour | test_selection_border_and_health_label_are_independent |
| 3 | Skip hidden LOG update | test_hidden_log_emitted_line_is_visible_once_after_live |
| 4 | LIVE r dispatches restart | test_live_refresh_and_control_keys_never_open_plan_elsewhere |
| 5 | Keep pending/planned plan on switch | test_dashboard_switch_drops_confirm_and_never_applies_its_plan |
| 6 | Retry busy / bypass pause guard, separately | test_d9_busy_stops_retry_and_applies_class_floor |
| 7 | Bypass reply storage sanitizer | test_ledger_sanitizes_raw_projected_reply_at_storage_boundary |
| 8 | Remove reply cap / retain401 texts, separately | test_ledger_sanitizes_raw_projected_reply_at_storage_boundary; test_retention_401st_expires_text_but_preserves_structure |
| 9 | Refuse digit-string ids | test_d1_real_capture_string_identities_match |
| 10 | Hard-code old Claude home | test_d2_root_home_classifies_tasks_research_doctor_manual[/home/imd-worker] |
| 11 | Count recovered API error | test_d5_summariser_ledger_document_and_fresh_process_agree recovered401 case |
| 12 | Skip persisted startup metadata | test_d3_startup_facts_and_restart_flag_survive_empty_tail |
| 13 | Put4096-character answer per RECORDS row in document | test_round9_worst_document_under_2mib_mutation13; mutated size7,715,955 bytes |
| 14 | Pick first node before ambiguity check | test_fallback_requires_unique_attempt_and_uses_node_state[ambiguous_nodes] |
| 15 | Unknown paid count becomes0 | test_nodes_unknown_payer_is_dim_dot_and_footer_defines_coverage |
| 16 | Remove residual JWT canary cleanup | test_d11_objective_reply_document_is_not_refused base64 case |
| 17 | Ignore SeatTable saved view | test_skill_toggle_after_refresh_resize_and_hidden_update_uses_same_id; wrong actual broker target |
| 18a | Enter priority=True only | test_the_screen_declares_data_not_control_flow RED; behavioral prompt interaction remains protected by independent check_action guard |
| 18b | Priority=True AND restore missing old prompt guard | test_confirm_owns_digits_verbs_tab_q_t_focus_and_real_enter RED; zero applies instead of one |
| 19 | Stop verify tick while detail is pushed | test_actual_detail_popup_does_not_pause_timer_driven_verdict; verifying instead of done |
| 20 | Use structural check status for outcome | test_fallback_requires_unique_attempt_and_uses_node_state[review_verifier] |

Proof18 separates the exact single-flag declaration regression from the compound reproduction of original behavior. Both independent protections remain; no guard was weakened to create evidence.

## Final layout and footprint measurements

| Body | Columns | Rows |
|---|---:|---:|
| SEAT | 131 | 40 |
| LIVE | 131 | 30 |
| CONFIG & SKILLS | 131 | 22 |
| RECORDS | 131 | 20 |
| NODES | 131 | 20 |
| CONTROL | 131 | 29 |

The resulting screen pin is **131×40**. All 18 payload/body exact corners clear. At 130 columns the hero clips; one row below each body pin scrolls and shows the taller marker. CONTROL healthy content clears at 28 rows, but worst and unattributed need 29. Widths were swept independently from 134 down to 100, heights from 50 down to 16, then heights repeated at the observed 131-column width.

Full tiers clear at terminal widths LEDGER 126, RECORDS 108 and NODES 119. LEDGER compact clears at 107. SKILLS has no horizontal loss at 98 and advertises it at 97. COST clears at panel width 54 (terminal 110); panel width 53 (terminal 109) marks. **No above-pin wider-tier exception remains**; the old LEDGER 210-column exception is removed.

The expanded worst payload has 50 skills, 400 records with bounded long-answer previews, 20 ledger rows, three running jobs, 4096-character questions and replies, 20 audit lines, 40 long log lines and three orphans. Text carries a 0x address, a canary-shaped base64 value, literal Rich tags and newlines through the actual sanitizer and document fold. The real JOB scroll proof reaches QUESTION and RESULT tails without shortening text.

The WP6 fixture/offline cold test measured **62.3 MiB** lifetime physical peak using the existing libproc v4 fallback, below the 160 MiB limit. All six fresh body observations passed. The driver visits keys 1–6, then LIVE/heartbeats, and fails a missing visit even with a positive memory sample; persistent hero labels cannot satisfy it. Final cold test: 1 passed in 71.07 s.

Final seat suite and split full suites: pending. Python 3.11 compileall passed; final whole-branch review corrections are approved.

## Follow-ups and interpretation

Follow-up57 preserves the open-ended gap after an unsuccessful empty cursor attach: synthetic fixture reproduces exit1 and no first available timestamp. That cannot distinguish lost history from attach failure; successful empty reads after a valid watermark are fixed separately by D10. No live host diagnosis was attempted.

Launch/workflow association follows the explicit cache fields of spec8.2 and the captured changelog's use of link for the structured objects. Existing job explorer remains separately labelled; no launch/workflow URL was invented. Follow-ups 58 and 59 reserve the two unchanged shared redactor overmatches for round 10: all 64-hex prose and sk- inside ordinary words. Earlier unresolved follow-ups remain.

## Owner deployment steps

Use the same final archive for seat 7 (imd-vps, Python 3.14, agent 51075) and seat 3 (imd-vps3, Python 3.12, agent 52082). On each: check ping for no armed drain and nothing in flight; stop active broker; run installer for that seat; confirm imd-dashd 0.1.5; rerun probe. Seat 3 worker drop-in and probe20 remain owner-controlled independent work. No live systems were contacted during implementation.


## Complete CONTROL predecessor/successor inventory


Every original scenario now runs against the dashboard. Four test names changed; the remaining 33 keep their names with the migrated harness.

| Removed test | Successor |
|---|---|
| test_verb_keys_and_static_lines_are_the_contract_s | tests/screens/test_seat_control.py::test_verb_keys_and_static_lines_are_the_contract_s |
| test_verb_lines_carry_the_live_gate_words | tests/screens/test_seat_control.py::test_verb_lines_carry_the_live_gate_words |
| test_the_modal_shows_verbs_static_lines_and_the_audit_footer | tests/screens/test_seat_control.py::test_control_dashboard_shows_dynamic_verbs_config_pointer_and_audit |
| test_restart_plans_confirms_applies_and_polls_verify_until_a_verdict | tests/screens/test_seat_control.py::test_restart_plans_confirms_applies_and_polls_verify_until_a_verdict |
| test_control_modal_never_replans_on_its_own | tests/screens/test_seat_control.py::test_control_dashboard_never_replans_on_its_own |
| test_a_broker_error_is_shown_and_never_retried | tests/screens/test_seat_control.py::test_a_broker_error_is_shown_and_never_retried |
| test_force_typed_twice_and_disabled_without_graceful_stop | tests/screens/test_seat_control.py::test_force_typed_twice_and_disabled_without_graceful_stop |
| test_local_only_gate_needs_the_typed_ack | tests/screens/test_seat_control.py::test_local_only_gate_needs_the_typed_ack |
| test_skills_set_takes_a_typed_id_gated_by_the_regex | tests/screens/test_seat_control.py::test_skills_set_uses_cursor_id_and_rejects_ids_outside_regex |
| test_boot_flips_between_enable_and_disable_and_orphans_carry_their_pids | tests/screens/test_seat_control.py::test_boot_flips_between_enable_and_disable_and_orphans_carry_their_pids |
| test_unreachable_broker_greys_every_verb_and_ignores_keys | tests/screens/test_seat_control.py::test_unreachable_broker_greys_every_verb_and_ignores_keys |
| test_skills_set_apply_marks_restart_required_and_offers_drain | tests/screens/test_seat_control.py::test_skills_set_apply_marks_restart_required_and_offers_drain |
| test_open_plan_sets_manager_plan_open_and_close_clears_it | tests/screens/test_seat_control.py::test_open_plan_sets_manager_plan_open_and_close_clears_it |
| test_the_modal_runs_the_manager_cycle_so_gate_words_and_plan_open_are_live | tests/screens/test_seat_control.py::test_dashboard_panels_receive_manager_gate_cycles_and_plan_open |
| test_verb_keys_are_not_swallowed_by_the_confirm_field | tests/screens/test_seat_control.py::test_verb_keys_are_not_swallowed_by_the_confirm_field |
| test_doctor_output_has_its_dollar_figure_stripped | tests/screens/test_seat_control.py::test_doctor_output_has_its_dollar_figure_stripped |
| test_combined_force_and_local_only_require_both_typed_acknowledgements | tests/screens/test_seat_control.py::test_combined_force_and_local_only_require_both_typed_acknowledgements |
| test_broker_apply_does_not_block_escape_or_issue_a_second_write | tests/screens/test_seat_control.py::test_broker_apply_does_not_block_escape_or_issue_a_second_write |
| test_verified_and_connection_have_independent_composited_colors | tests/screens/test_seat_control.py::test_verified_and_connection_have_independent_composited_colors |
| test_root_lost_apply_reply_keeps_plan_and_recovers_verification | tests/screens/test_seat_control.py::test_root_lost_apply_reply_keeps_plan_and_recovers_verification |
| test_unknown_plan_keeps_minimum_retry_window_then_requires_explicit_new_plan | tests/screens/test_seat_control.py::test_unknown_plan_keeps_minimum_retry_window_then_requires_explicit_new_plan |
| test_mac_timeout_result_is_unknown_then_reads_real_verify | tests/screens/test_seat_control.py::test_mac_timeout_result_is_unknown_then_reads_real_verify |
| test_irrelevant_connection_state_has_no_yellow_pending_phrase | tests/screens/test_seat_control.py::test_irrelevant_connection_state_has_no_yellow_pending_phrase |
| test_apply_late_tells_operator_whether_plan_was_spent | tests/screens/test_seat_control.py::test_apply_late_tells_operator_whether_plan_was_spent |
| test_partial_kill_retains_pids_and_polls_real_watch | tests/screens/test_seat_control.py::test_partial_kill_retains_pids_and_polls_real_watch |
| test_recovered_skill_apply_keeps_restart_required_workflow | tests/screens/test_seat_control.py::test_recovered_skill_apply_keeps_restart_required_workflow |
| test_root_queue_timeout_verifies_actual_outcome_and_clears_restart_note | tests/screens/test_seat_control.py::test_root_queue_timeout_verifies_actual_outcome_and_clears_restart_note |
| test_kill_refusal_formats_every_pid_and_only_partial_actions_verify | tests/screens/test_seat_control.py::test_kill_refusal_formats_every_pid_and_only_partial_actions_verify |
| test_new_prompt_clears_previous_partial_note | tests/screens/test_seat_control.py::test_new_prompt_clears_previous_partial_note |
| test_lost_reply_verify_failures_have_a_bounded_uncertain_outcome | tests/screens/test_seat_control.py::test_lost_reply_verify_failures_have_a_bounded_uncertain_outcome |
| test_real_broker_first_signal_refusal_never_polls_verify | tests/screens/test_seat_control.py::test_real_broker_first_signal_refusal_never_polls_verify |
| test_ignored_verb_keeps_active_partial_evidence | tests/screens/test_seat_control.py::test_ignored_verb_keeps_active_partial_evidence |
| test_uncertain_action_retains_known_consumption | tests/screens/test_seat_control.py::test_uncertain_action_retains_known_consumption |
| test_first_signal_status_preserves_uncertainty_and_what | tests/screens/test_seat_control.py::test_first_signal_status_preserves_uncertainty_and_what |
| test_plan_displays_integer_verify_seconds | tests/screens/test_seat_control.py::test_plan_displays_integer_verify_seconds |
| test_later_non_prompt_status_clears_partial_evidence | tests/screens/test_seat_control.py::test_later_non_prompt_status_clears_partial_evidence |
| test_full_apply_deadline_leaves_ten_seconds_for_unknown_outcome | tests/screens/test_seat_control.py::test_full_apply_deadline_leaves_ten_seconds_for_unknown_outcome |

## Related screen-level CONTROL tests migrated in WP4

| Removed test | Successor |
|---|---|
| tests/screens/test_seat_screen.py::test_c_opens_the_control_modal_over_the_manager_s_broker | tests/screens/test_seat_screen.py::test_c_selects_control_and_escape_returns_to_live |
| tests/screens/test_seat_screen.py::test_the_control_modal_paints_its_cycles_onto_the_suspended_screen | tests/screens/test_seat_round9_navigation.py::test_hidden_log_emitted_line_is_visible_once_after_live and test_hidden_updated_then_shown_matches_visible_updated_strips[5] |

All 37 original named scenarios remain in the dashboard-backed test file. Cursor-selected skill ids replace typed ids with a separate invalid-row regex case. Ordinary PANELS refresh replaces modal payload forwarding. Held broker tests dispatch actual Escape Key events and wait for the rendered LIVE selection while the reply remains held. Parametrized scenarios (transport/root/mac/partial/refusal) remain intact. The final WP5 affected gate passed 163 checks and its finding-only review passed eight. The six compatibility files separately passed 27/9/46/170/69/6 checks.


## Final whole-branch review and fix wave

The required whole-branch review found one Critical and two Important issues after 84 focused checks: JOB collapsed running nodes sharing a job id; auto-update was never populated; CONTROL lacked audit input for its doctor timestamp. Permanent regressions first produced 7 failures and 2 passing unknown-state controls. The single fix wave addresses all three, plus the Minor schema-state spelling correction. The affected gate passed 412 checks; its one key-count test observed an unrelated periodic refresh. Isolating that test timer kept the exact five manual refreshes and no-plan assertions, then the full navigation file plus all 12 new finding cases passed 32 checks. The revised key test also failed under the original wrong-verb mutation (zero refreshes instead of five), then source bytes were restored. Finding-only re-review is approved; final suites are pending.

- `tests/widgets/test_seat_round9_bodies.py::test_same_job_attempts_keep_identity_text_and_detail_while_stepping` covers separate attempt text and detail keys, standing-only node keys, partial cache, stepping and refresh selection.
- `tests/data/test_seat_round9_defects.py::test_execstart_auto_update_reaches_document_fold_and_config` covers true, false, nonmatching flags and missing/empty ExecStart through the real document fold and CONFIG compositor.
- `tests/widgets/test_seat_round9_bodies.py::test_control_doctor_last_run_arrives_through_panels_audit_contract` binds the latest doctor timestamp to ordinary panel dispatch.

The final finding-only re-review approved all three corrections: 13 targeted checks passed. Restoring the job-only cache match made the attempt regression fail; byte-identical restoration passed again. No review finding remains open.

## Final verification compatibility correction

The first exact serial seat run at 5f5b996 completed with 1,814 passed, two skipped, one deselected and two failures in 1,232.18 seconds. Both failures were the original round-4 long-journal-message cases. The generic sanitizer's default API cap had also cut their in-memory lifecycle fields. The targeted correction preserves that older journal boundary while retaining the common canary cleanup and all API cache/storage limits. The original tests remain unchanged; `test_journal_lifecycle_preserves_long_text_after_canary_cleanup` also failed before the correction. This verification-discovered compatibility fix is separate from the completed review's single fix wave; no second broad review was opened.

The affected journal, ledger, cache, manager and detail checks passed: 219 tests in 12.86 seconds.

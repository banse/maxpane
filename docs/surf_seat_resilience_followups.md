# Surf seat resilience — execution notes and follow-ups

Implements `surf_seat_resilience_plan.md` on `feature/surf-seat-resilience`.
The branch starts at `250e4eb`, preserving the runtime and rank fixes already present in the
owner's workspace, rather than reverting to the older base named in the plan.

## Layout refinement

At the unchanged AGENT pin, COLLAB has 14 content columns; `busy · retrying` needs 15.
It uses two existing body lines (`busy ·`, then `retrying`) when needed. The other cards fit
the complete line. No pin or CSS geometry changes are needed.

## Honest loading words

- RECORD answer: valid job UUID and submission hash in its selected window show dim
  `loading…`; an ineligible `not_read` row retains `not read`. The manager normally marks
  malformed answer identities `unavailable` before they reach the widget.
- Panel: only oracle nodes with valid identities show dim `loading…`. Ineligible `not_read`
  rows retain `not read`; non-oracle rows retain `–`.
- SUBMISSION job: only non-joined rows with valid identities and answer state `read` or
  `no_reply` show dim `loading…`; ineligible snapshots retain `not read yet`.

## Verification environment

Use `env -u NO_COLOR .venv/bin/python -m pytest …` for composited color checks. The session
environment sets `NO_COLOR=1`, which removes colors before the tests inspect them. The two
existing screen color failures reproduced on untouched `250e4eb` and passed with that variable
unset. No production or test assertions were changed to accommodate monochrome output.

## Final review

The whole-branch review found one Important issue: a raw HTTP 200 `{"error":"busy"}` body
could compare equal to the normalized busy result. The final fix preserves transport provenance
with the immutable sentinel inside the client and rejects raw busy error bodies from HTTP 200.
Both new HTTP 200 regressions failed before the fix. Scoped re-review: **Approved**, F1
**ADDRESSED**, five focused cases passed. No other findings remain.

## Verification

Commands use `env -u NO_COLOR .venv/bin/python -m pytest`. Counts overlap: each package's
consumer checks are intentional, and the same final guard run covers WP1–WP4.

| Package | Passing checks |
| --- | --- |
| WP0 | 145 model/widget-contract tests on the integrated tree; composing screen has 72 cases and passes in WP1/WP2/WP3; shared guard 199 |
| WP1 | 180 client + composing-screen tests before review; **183 passed** in the expanded run after F1; shared guard 199 |
| WP2 | 356 coercer/cache/manager tests; 494 dependent-data + composing-screen tests; shared guard 199 |
| WP3 | 411 widget/popup + composing-screen tests; 209 AGENT/RECORD layout tests; shared guard 199 |
| WP4 | 234 doc-pinning tests; composing screen shared with WP3; shared guard 199 |

WP0 model/widget files: `tests/data/test_surf_swarm_models.py`,
`tests/widgets/test_surf_widget_contract.py`. WP1 client file:
`tests/data/test_surf_swarm_client.py`. Every composing-screen run includes
`tests/screens/test_surf_swarm_screen.py`.

WP2 core files: `tests/data/test_surf_swarm_seats.py`, `test_surf_cache_swarm.py`,
`test_surf_manager_swarm.py`. Its dependent files are `test_surf_cache.py`,
`test_surf_manager.py`, `test_surf_manager_answers.py`, `test_surf_manager_oracle.py`,
`test_surf_swarm_board.py`, all under `tests/data/`.

WP3 widget files under `tests/widgets/`: `test_surf_swarm_seat_state.py`,
`test_surf_swarm_seat_record.py`, `test_surf_swarm_agent_cards.py`,
`test_surf_swarm_agent_hero.py`; popup files under `tests/screens/`:
`test_submission_detail.py`, `test_oracle_answer.py`. Layout command:
`tests/screens/test_surf_swarm_layout.py -k "agent or record"` (336 deselected).

Doc-pinning files: `tests/test_surf_registration.py`, `tests/test_curator_registration.py`,
`tests/data/test_curator_captures.py`, `tests/data/test_curator_sybil_data.py`,
`tests/data/test_surf_captures.py`. These are the files that read the referenced docs; the wider
grep also finds many comments that merely mention CLAUDE.md. Guard command: `-m guard -q`
(10,595 deselected).

## Mutation evidence

Every mutant below made the named test fail; each edit was inverse-restored. Restored checks
passed (three manager cases and two widget cases), as did the package runs above.

| Requirement | Mutation | Test that turned red |
| --- | --- | --- |
| WP1 (M) exact busy error | Remove `error == "busy"` check | `tests/data/test_surf_swarm_client.py::test_fetch_seat_503_with_another_error_is_not_busy` |
| WP2 (M) seat isolation | Serve newest entry instead of selected token | `tests/data/test_surf_manager_swarm.py::test_seat_a_then_b_then_a_busy_keeps_a_record_and_own_timestamp` |
| WP2 (M) own timestamp | Use enclosing slot timestamp instead of entry timestamp | Same A/B/A test; B's 14:03 replaced A's 14:00 |
| WP2 (M) empty busy state | Return None instead of busy | `tests/data/test_surf_manager_swarm.py::test_never_read_seat_busy_is_distinct_from_failed[result0-busy-busy]` |
| WP3 (M) busy title | Remove suffix; separately change yellow to red | `tests/widgets/test_surf_swarm_seat_record.py::test_busy_record_title_is_yellow_and_keeps_its_own_as_of[139]` |
| WP3 (M) loading answer/panel | Change answer to `not read`; separately change panel to `not read` | `tests/widgets/test_surf_swarm_seat_record.py::test_pending_answer_and_panel_loading_only_for_eligible_rows[changes0-words0]` |

## Deferred work

The controller's full-suite run remains required before integration, as specified in the plan.
There is no merge, push or tag in this work package.

# AGENT card labels implementation plan

Contract: [approved specification](surf_agent_card_labels_spec.md). Freeze `surf_agent_hero.status.current_action: str | None` before dispatch. Only the ten specified action words are valid. Production scope is below 1,000 lines; packages run without task reviews and receive one final whole-change review.

## Package 1 — current-node data

Owner: data implementer. Own `maxpane_dashboard/data/surf_models.py`, `data/surf_agent_hero.py`, `data/surf_manager.py`, `tests/data/test_surf_agent_hero.py`, `tests/data/test_surf_agent_hero_manager.py`, and a minimal committed fixture if needed. No widget or screen edits.

1. Add the contract field and tests for fresh selected-seat attribution, all action mappings, parallel nodes, invalid data, failures/expiration, and selection changes.
2. Capture the existing live swarm source with the hero's frozen inputs. Pass the raw current details and their existing source freshness to the pure projector; no new network work or reliance on `surf_work`.
3. Select/map the current node as specified. Clearing or refreshing the source must change the caption on the next projection. Worker count, history and other hero facts stay independent.
4. Run focused data/manager tests while editing. Prove selection/freshness decoder regressions bite using the repository mutation tool, restoring inverse edits exactly. Report production diff and verification to controller.

Acceptance: a direct AGENT read can show the selected working seat's actual action; pending submissions, another seat, terminal nodes, old/failing snapshots cannot masquerade as that action. No new requests beyond existing sources.

## Package 2 — card labels and record spacing

Owner: UI implementer. Own `maxpane_dashboard/widgets/surf/agent_rack_hero.py`, `widgets/surf/swarm_seat_record.py`, `tests/widgets/test_surf_agent_rack_hero.py`, and `tests/widgets/test_surf_swarm_seat_record.py`. No models, manager, global CSS, or screen edits. This package can run in parallel with Package 1 against the frozen field.

1. Add compositor regressions for requested SEAT labels, current-action/fallback and idle behavior, cleared outer footers with inner content retained, and the one-row RECORD title gap.
2. Update the existing record-to-card mapping; allow only the agreed action words and use `working` when unknown. Remove the RECORD-specific zero-margin exception so normal title spacing applies; amend its now-obsolete inline comments.
3. Preserve dimensions, border/digit styling, links, copy actions, table filters, and scrolling. Do not infer or move pins.
4. Run focused widget tests; report the changed paint and verification to controller.

## Package 3 — integration, live preview, layout and final review

Owner: controller. Own composing screen tests, `tests/surf_agent_hero_fixtures.py` if its explicit contract fixture needs updating, layout measurement, and any measured pin plus associated `#:`/documentation/global-CSS edits. Do not edit either implementer's owned files concurrently.

1. Integrate both packages and exercise direct AGENT activation plus refresh with current-node data. Add a composing assertion covering the live action and record-title gap. Existing selected-seat identity guards must continue passing.
2. Fetch public data into a temporary cache and show the real 149×45 AGENT render before hardening. Inspect an active seat for its current-action caption; show the screenshot seat #420 as needed for identity labels. Do not write the user's cache.
3. Measure the AGENT layout in situ using `scripts/measure_layout.py`. The blank title row consumes record viewport space; only the measurement decides whether the minimum pin moves. Update measured pins/comments and boundary tests together if necessary, then demonstrate both-direction pin mutations when a pin changed.
4. Once before commit, run touched widget/data test files and composing manager/screen files whole, plus fast guards. Isolate HOME for parallel tests. Include layout boundaries and docpin checks if their owned files changed; no full suite.
5. Dispatch one final whole-change reviewer with CLAUDE's verbatim reviewer contract. At most one fix wave and scoped production re-review; file minor-only findings in the existing AGENT followups document. Commit scoped files, leaving unrelated workspace files intact.

Dependencies: Package 1 and Package 2 depend only on the frozen contract and can run in parallel. Package 3 starts integration after both land; its live preview precedes pin/document hardening and review. No workers spawn subagents or revert another owner's edits.

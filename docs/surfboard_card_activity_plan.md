# Surfboard card activity implementation plan

Date: 2026-10-11. Basis: [accepted specification](surfboard_card_activity_spec.md).
Tier 2, expected below 1,000 production lines. Root coordinates three implementation
packages; no task reviews, one final review. No subagents below the root controller.

## Ownership and dependencies

| Package | Owner and exclusive files | Depends on |
|---|---|---|
| WP0: freeze contracts | Root: `data/surf_models.py` and its agreement tests | Accepted spec |
| WP1: launch volume | Volume implementer: `data/swarm_tokens_market.py`, `data/swarm_tokens_manager.py`, their focused market/live tests; optionally `analytics/surfboard_volume.py` and its own tests | WP0 |
| WP2: observed agent activity | Activity implementer: new `data/surfboard_activity.py`, `data/surf_cache.py`, new activity tests and relevant cache tests | WP0 |
| WP3: projection, integration, render | Root: `data/surf_manager.py`, `data/surfboard.py`, `widgets/surfboard/rack.py`, their tests and Surfboard composing/layout fixtures/tests | WP0; final integration consumes WP1/WP2 |
| WP4: live validation and final review | Root; one separate final reviewer | WP1–WP3 |

Production paths above are relative to `maxpane_dashboard/`; tests remain under
`tests/`. The planner owns only these two documents until root updates the final
evidence. All implementers share the workspace, preserve user/unrelated edits, report
cross-package defects to their owner, and never revert another owner's changes.

WP1 and WP2 run in parallel once WP0 freezes the contract. Root can implement the
agreed rendering/projection contract concurrently. Whole-file ownership applies even
when two changes would touch different functions. Root retains manager/model/rack seams.

## WP0 — contract freeze

1. Root has frozen `meter_state` and `share_price` card fields without changing widget
   signatures.
2. Freeze `catalogue_summary()['volume']` and the activity module API exactly as in
   the spec. Freeze cache slot name `SLOT_SURFBOARD_ACTIVITY='surfboard_activity'`;
   WP2 owns adding/exporting the constant in `data/surf_cache.py` and persistence
   validation wiring; the cache constant does not belong in `surf_models.py`.
3. Freeze `cards(..., activity=None)`: root passes the persisted activity payload and
   projects selected/rank-one token activity using the injected card projection clock.
4. Tell both implementers that unknown never means zero, worker staleness is 300s,
   worker observation cadence remains 120s, and hub offers catalogue/markets/volume
   only, excluding existing price history and trades.

## WP1 — aggregate USD volume

1. Add failing fixture-based tests to `tests/data/test_swarm_tokens_market.py` for
   candle volume/timestamp admission and unchanged price-history behavior.
2. Add separate `fetch_volume_history` using the same keyless OHLCV endpoint and rate
   limiter with `include_empty=true` and completed-hour candles. Keep existing
   `fetch_history` requests and price semantics unchanged. Reject booleans,
   negative/nonfinite values, malformed timestamps, and duplicate observations as
   appropriate; preserve legitimate zero candles and missing hours.
3. Add pure aggregation tests, using `tests/analytics/test_surfboard_volume.py` if
   the optional helper is created: eight three-hour buckets, latest completed-hour
   boundary, deduplicated chain/pool pairs, all catalogue deployments including inactive
   and retired ones, no token preview limit, gaps, partial coverage, stale retained data,
   and absent markets. Unsupported/ambiguous deployments count against coverage.
   Inject `now`.
4. Extend `SwarmTokensManager` with bounded hub catalogue/market/volume offers sharing
   tasks/rate limiting. Expose the volume summary, retaining clocks and coverage.
   Exercise scheduling in `tests/data/test_swarm_tokens_live.py`; prove no hub price-
   history or trade fetch and no duplicate in-flight work across screen transitions.
5. Run changed cases plus consuming manager/screen cases; provide a decoder/aggregation
   mutation proof and hand root the summary contract and named passing tests.

## WP2 — persisted observed stops

1. Add failing tests in `tests/data/test_surfboard_activity.py` using explicit clocks
   and normalized worker fixtures. Cover any-positive across devices, all-known-zero,
   confirmed absence, unknown counters, cold idle, busy→idle, repeated idle, resumed
   work, 12h/24h boundaries, freshness expiry, and failed-attempt history retention.
2. Implement `observe`, `coerce`, and `project` as pure functions in the new module.
   Track per-token current evidence and prior transition history; observation metadata
   advances on every successful read, including an unchanged normalized response.
3. Add the cache slot, require its injected coercer on load, and export its constant.
   Cover restart round-trip, missing old slot, malformed per-token entries/timestamps,
   future data, and no contamination between token identities in cache tests.
4. Hand root the exact normalized-worker input and failure-update calls. Root owns
   calling them in the manager and adding the clock-injected cache loader coercer.
5. Run focused tests and a mutation that resets stop time on each idle observation
   or treats missing work as zero; demonstrate that a named test fails and restore it.

## WP3 — manager, cards, and rendering

1. Add focused failing manager/card tests. In `_pool_swarm_board`, observe workers
   success/failure independently of contributors and version changes. Persist the
   resulting activity slot; `_project_hub` passes it to card projection. Test fresh
   unchanged workers, contributor-only failure, workers failure, restart, and selected
   versus rank-one token selection.
2. Offer bounded launch-volume enrichment from hub refresh; project the volume summary
   to LAUNCHES while retaining its catalogue and detected-news semantics.
3. Replace acceptance meters with activity remaining/86400 and `meter_state`. Keep
   acceptance facts available in detail. Unknown/stale current evidence renders an
   unknown meter, never a live BUSY/IDLE claim.
4. Supply the POOL4 share rate from `pool4_share_price`, with a six-decimal detail
   value and width-fitted footer. Preserve independent pool source health markers.
5. Update rack rendering: sparkline gaps and partial amber `~24H`; green IDLE/orange
   BUSY footer labels and fill; three aligned protocol columns without colons;
   render-only known-zero inner-footer suppression for announce/LAUNCHES. Unknown
   secondary text must remain visible. Preserve title, padding, and destinations.
6. Extend composited widget/layout tests, including resize and unknown states. Update
   old PASS/STAKE expectations to the accepted behavior; retain coverage of invalid
   ratios on cards that still use them. Do not delete source honesty assertions.

## WP4 — live render, hardening, and delivery

1. Show the functioning dashboard against live keyless sources at **149×45**. Owner
   corrections precede hardening and review. Read the terminal-layout skill before
   sizing-related checks; preserve existing pins unless measurements require a change.
2. Check the relevant boundary widths and resize paths in
   `tests/screens/test_surfboard_layout.py`. Assert complete footer labels, protocol
   column alignment, volume gaps, and LAUNCHES without a widen marker.
3. Complete focused mutation proofs for changed decoder and timing behavior. During
   editing run only affected cases; once before commit run touched test files and
   their composing manager/screen files with the repository's isolated-home,
   four-worker worksteal recipe. Include `tests/data/test_surf_manager_surfboard.py`,
   `tests/widgets/test_surfboard_rack.py`, `tests/screens/test_surfboard_screen.py`, and
   affected Surfboard/token layout consumers. Run the fast `guard and not mounts_app`
   set and the repository docpin command. No full suite or unrelated registration run.
4. Dispatch exactly one final whole-change review with the repository reviewer contract
   and named risk checks. Allow one fix wave and one scoped re-review only if that wave
   changes production. File Minor-only findings in the appropriate followups document.
5. Record live-render evidence, tests, mutation outcomes, and residual limitations in
   the commit/report required by project conventions. Remove only task-owned temporary
   planning workspaces; leave existing user docs, environments, and worktrees intact.

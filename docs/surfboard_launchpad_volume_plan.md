# Surfboard launchpad volume implementation plan

Date: 2026-10-11. Basis: [specification](surfboard_launchpad_volume_spec.md).
Tier 2, expected below 1,000 production lines. Root coordinates two independent
implementation packages and one final review, with no package reviews or child
agents. Preserve unrelated changes in the shared workspace.

## Ownership and sequence

Production paths are relative to `maxpane_dashboard/`; test paths are repo-relative.

| Package | Exclusive owner and files | Dependency |
|---|---|---|
| WP0: freeze the seam | Root and data owner agree the optional internal snapshot; no public key additions | Specification |
| WP1: complete launchpad history | `volume_history`: `data/surf_models.py`, `data/surf_client.py`, `data/surf_manager.py`, `data/surf_launchpad_volume.py`, and corresponding data tests/fixtures | WP0 |
| WP2: footer and terminal presentation | Root: `data/surfboard.py` and its projection tests, `widgets/surfboard/rack.py`, `screens/surfboard.py`, `themes/minimal.tcss`, terminal code only if required, `tests/surfboard_fixtures.py`, affected widget/screen tests | WP0; integrate WP1 after parallel implementation |
| WP3: live evidence and completion | Root; one final reviewer after integration; root owns any measured pin/skill-table edits | WP1 and WP2 |

WP1 and WP2 run concurrently without shared-file edits. The planner owns only
this spec and plan. Report cross-owner defects; do not fix another owner's file.

## WP0 — contract

1. Keep public Surf/Surfboard keys and widget signatures unchanged. Add optional
   `LaunchpadState.volume_2h` with a default so existing callers remain valid.
2. Freeze the internal snapshot shape with eight native-quote buckets, state,
   independent read/head timestamps, and `until`. Existing launchpad slot persistence and
   `launchpad=` projection input carry it. Reuse card `points`, `meter_kind`,
   and `meter_state`; card states are `ok`, `partial`, `stale`, or `unavailable`.
3. Freeze eight closed UTC 15-minute bins ending at the observed head's last
   closed quarter-hour and exact block-header timestamps. Allow 256 unique
   swap-block header reads in batches of 32, plus head/scan-start headers, with a
   20-second overall hydration timeout. Use a 600-second volume TTL independent
   of the slot clock and a fresh valid cached ETH/USD quote. No new transport
   pool or per-coin price hydration.

## WP1 — source and persistence; root owns projection integration

1. Start at `surf_client.py::_launchpad_logs`, `_decode_curve_swap_log`,
   `_LaunchpadSweep`, and `fetch_launchpad`; then `_launchpad_payload` and
   `_project_hub` in the manager and `surfboard.py::cards`.
2. Add failing tests showing trades from launchpad pools beyond both the rendered
   coin cap and feed cap contribute. Use buys and sells, repeated block numbers,
   duplicate tickers with different pool IDs, and integer quote amounts. Verify
   only the ETH quote leg contributes and existing counts/feed remain unchanged.
3. Add deterministic cases at the start, internal boundaries, window end, and
   open interval; successful empty ranges; malformed log values; missing block
   headers; inadequate range/population coverage and factory-count mismatch;
   malformed/conflicting event IDs; failed log sweeps; expired
   snapshots; and exhausted read/deadline budgets. Inject all clocks/transports.
4. Implement the smallest bounded header hydration and pure aggregation over the
   uncapped sweep. Prove the fetched range covers claimed intervals. Deduplicate
   header reads and preserve missing buckets whenever coverage cannot be proven.
   Keep event ETH wei as integers until the numeric conversion boundary. Missing
   time coverage, invalid headers, or exhausted budget cannot produce a chart;
   factory-count mismatch projects partial without claiming a complete total.
5. Pass/persist the optional snapshot without advancing its clock on unrelated
   successful getters. Old caches remain valid. Validate persisted fields and
   each bucket; failed refresh retains last-good only with explicit stale state.
6. Add projection tests for valid cached ETH/USD conversion, absent/zero/negative/
   nonfinite/stale quotes, fresh launchpad slot with old volume snapshot, current
   volume with failed logs, old cache without the field, and repaint after expiry.
   Project the eight USD points through the existing sparkline card fields.
7. Run only named changed tests and consuming manager/card cases during edits.
   Use focused `scripts/mutate.py` checks to prove the quote-word decoder,
   cap-independent population, time boundaries, and stale/coverage gate bite.
   Coordinate mutations with root; restore byte-for-byte before handoff.
8. Hand root the exact snapshot shape, budget/deadline values, test node IDs,
   mutation evidence, and any source limitation affecting the visible label.

## WP2 — UI and full central terminal

1. Add failing composited tests for PROTOCOL's aligned label/amount/IMD columns,
   inter-column/end padding, no colons, and empty inset bottom border.
2. Render those columns directly from the existing protocol content. Preserve
   underlying supply/burn/reward values and card contracts.
3. Make LAUNCHES and LAUNCHPAD sparklines use SWARM's green glyphs. Test fresh,
   partial, stale, all-zero, all-missing, and mixed-gap data. Keep amber `~24H`
   and `~2H` labels for degraded data and an explicit unknown presentation when
   no chart is available. Remove the old LAUNCHPAD `TRADE` ratio presentation.
4. Remove the focused detail Static, rendering callback/state, and center wrapper.
   Restore the terminal directly in its existing grid span. Remove obsolete CSS
   in both screen and theme; preserve terminal controls and normal scroll hints.
5. Replace detail-specific expectations with meaningful assertions that no detail
   element is mounted, focus/activation still works, and the terminal occupies the
   full central region. Preserve swapped cards, empty bays, activity colors,
   protocol spacing, and unchanged LAUNCHES title in updated fixtures/tests.
6. Run named widget/screen/terminal cases while editing with `env -u NO_COLOR`.
   Do not harden a new pin from a fixture-only render.

## WP3 — live render, boundaries, and final review

1. Integrate both packages and show the actual keyless 149×45 screen to the owner.
   Confirm full-center terminal, label-first protocol rows, green charts, and
   honest volume state. Incorporate any correction before pin/docs hardening.
2. Follow the terminal-layout skill and measure actual compositor regions with
   normal, stress, unavailable, and wide-text cases. Probe both sides of the
   measured width/height threshold and retain useful scrolling below it. If a pin
   changes, update its `#:` evidence and skill table and prove mutations above
   and below the measured pin fail. Do not infer dimensions from constants.
3. Once before completion run touched and composing test files whole, using the
   repository isolated test-home environment and `-n 4 --dist worksteal` recipe,
   with `NO_COLOR` removed. Include affected client/model/manager/card/analytics
   files, `tests/widgets/test_surfboard_rack.py`,
   `tests/widgets/test_surfboard_card_activity.py`,
   `tests/screens/test_surfboard_screen.py`,
   `tests/screens/test_surfboard_layout.py`, and terminal tests if changed.
4. Run the fast `guard and not mounts_app` set and the documentation pins:
   `env -u NO_COLOR .venv/bin/python -m pytest -m docpin tests/test_surf_registration.py tests/test_curator_registration.py`.
   No full suite or unrelated app-mount registration run is required.
5. Dispatch one final reviewer with the repository reviewer contract verbatim,
   exact diff scope, and named risks: capped source leakage, wei decoder, missing
   coverage becoming zero, stale quote/snapshot freshening, protocol columns,
   direct terminal geometry, and footer colors. Permit one fix wave and one
   scoped re-review only if that wave changes production. File Minor-only findings.
6. Record final tests, mutations, measured pins, live-render evidence, and any
   residual source limits. Preserve user files and existing worktrees.

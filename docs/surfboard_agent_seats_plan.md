# Four Surfboard agent seats implementation plan

Date: 2026-10-12. Basis: [specification](surfboard_agent_seats_spec.md).
Tier 2, target below 1,000 production lines. Three implementation packages have
exclusive files and run in parallel after the plain-data seam is frozen. One
final review only; no package reviews, child agents, or unrelated refactors.

## Ownership and dependencies

Production paths are relative to `maxpane_dashboard/`.

| Package | Exclusive files / owner | Dependency |
|---|---|---|
| WP0: contract freeze | Root confirms the accepted fields/seams; data worker implements model contract | Spec |
| WP1: assignments and projections | Data worker: `data/surf_models.py`, `config.py`, `data/surf_manager.py`, `data/surfboard.py`, narrowly required analytics constant, configuration/data/cache tests | WP0 |
| WP2: four interactive cards | UI worker: `widgets/surfboard/rack.py`, widget tests, `tests/screens/test_surfboard_layout.py`, `tests/surfboard_fixtures.py` | WP0 |
| WP3: startup and origin-aware routing | Root: `__main__.py`, `app.py`, `screens/surf.py`, `screens/surfboard.py`, `screens/seat_input.py`, corresponding routing/prompt tests | WP0; integrates WP1/WP2 |
| WP4: live verification and final review | Root; one final reviewer | Integrated WP1–WP3 |

Root owns any later measured pin or terminal-layout skill-table change. Root
coordinates fixture expectations with the UI owner instead of editing their
file. The data worker owns `tests/test_seat_config.py`, including root-requested
startup assertions there; root adds routing tests in its own files. The planner
owns only this spec and plan. Preserve all other workspace changes.

## WP0 — freeze before parallel work

1. Add card fields `seat_slot` and `token_id`, None for other cards; no new
   top-level keys or widget signatures. Freeze zero-based slots 0..3 and keys
   `agent`, `agent-2`, `agent-3`, `agent-4`, all titled `AGENT`.
2. Freeze `get_surfboard_seats` / `save_surfboard_seat`, manager `get_hub_seats` /
   `set_hub_seats`, optional `surfboard_seats` startup argument, and
   `cards(agent_seats=...)` projections.
   Explicitly separate the primary assignment from active `_seat_saved`.
3. Freeze activation payload (optional slot/token) and
   `SeatSubmitted(seat_slot, value)`. Empty cards use `status=meter_state='empty'`, destination None;
   assigned cards retain their agent destination through fetch failures.
4. Freeze routing semantics: open without saving; native selections update the
   originating slot; native/menu entry resets to slot 0. Keep full detail fetching
   limited to the active seat and share worker-based status across all cards.

## WP1 — data and persistence

1. Add failing config tests for primary compatibility, three independent extra
   values, restart round-trip, token zero, unrelated config preservation, malformed
   sections/values, and invalid slot/value rejection without a partial write.
2. Store secondary assignments as scalar TOML values; use no new serializer.
   Keep configuration reads out of the manager. Accept injected assignments and
   provide a validated, synchronous assignment update seam.
3. Add projection tests for no saved primary despite a populated roster; four
   distinct saved tokens; one missing/failed token while others remain valid;
   reassignment; duplicate tokens; unchanged source read refresh; per-token
   stopped timestamps; and projection while another token is actively opened.
4. Factor the current AGENT card projection into one local reusable path and
   call it for all four plain slot snapshots. Use the shared normalized workers,
   canonical outcomes, and activity data. Preserve all existing activity states
   and cooldown arithmetic, and produce explicit empty cards without a token.
5. Reuse the existing token-keyed persisted seat cache. Add focused regression
   evidence that switching/opening seats preserves each token's record, a failed
   active read does not overwrite another, and stale in-flight results do not
   leak into a newly selected token. Do not introduce four managers or a full
   seat-read loop for the cards.
6. Run changed config/data cases and the consuming manager cases. Prove the
   no-fallback/selection-isolation tests bite with focused mutations, coordinated
   with root. Hand root exact seams, tests, and any source/cache limitation.

## WP2 — card input and rendering

1. Add failing composited tests for four `AGENT` titles; each empty card's black
   background, `EMPTY SEAT`, input, `type in seat no`, and unfilled `EMPTY` meter.
   Include all-filled and mixed states, not just a single empty placeholder.
2. Replace BAY 10/11/12 identities in `SLOTS`. Keep every agent card focusable.
   The UI worker chooses the smallest composition/input overlay that fits the
   current five-line inset and does not require a larger layout pin.
3. Input submission emits the new message and consumes Enter so it cannot also
   activate the card. Empty-card activation focuses input. Populated activation
   carries its own slot/token. Preserve drafts across polling and permit normal
   editing keys without firing screen/rack navigation underneath the input.
4. Reuse the existing AGENT face/meter for every assigned slot. Retain grey IDLE,
   all decay phases, OFF/BUSY colors, and launch marks. Remove the news renderer's
   dependency on finding an `.empty` bay; use the actual muted style directly.
5. Update shared fixtures and meaningful layout assertions for four assignments.
   Verify input, border, inset footer, and outer meter are painted at 149×45 and
   existing pin boundaries. Use `env -u NO_COLOR` for named editing tests.

## WP3 — startup and routing

1. Inject saved assignments from `__main__` through the app into the manager.
   Preserve the existing `seat=` entry point and bare app/manager test isolation.
   Coordinate startup expectations with the owner of `tests/test_seat_config.py`.
2. Handle `SeatSubmitted` with the existing seat parser, a write to only that
   assignment, manager tuple update, and refresh. Valid save populates the card
   without navigation. Invalid input leaves stored assignments unchanged.
3. Extend app routing to carry `seat_slot`. Opening an assigned card selects its
   token transiently without running the old unconditional primary-save path.
4. Give `SeatInputScreen` optional current/saver parameters with compatible
   defaults. Make `i`, leaderboard row selection, and programmatic selection use
   the same screen-owned origin context. Reset that context on native/menu entry
   and on leaving the rack visit; restore primary active selection appropriately.
5. Add routing tests for every slot, back navigation, primary stability while a
   secondary is opened, secondary `i` and leaderboard edits, primary native edits,
   cancelled/invalid prompts, save-without-open, and unscoped command behavior.
   Test with token zero and repeated tokens to catch truthiness or identity errors.
6. Assert only the active seat needs a full detail request and ordinary hub polling
   still refreshes all four projected statuses. Keep message handlers free of
   network awaits and retain existing keyboard registration.

## WP4 — integration evidence and completion

1. Integrate all packages and show the owner a real keyless 149×45 render before
   pin hardening or review. Include empty and assigned cards as the live data and
   saved configuration permit; do not alter their saved choices for a screenshot.
2. Measure actual compositor content with normal, stress, unavailable, wide-text,
   empty, and all-filled cases. Target unchanged 144×35. If evidence requires a
   pin move, update its `#:` block and skill table and prove mutations both above
   and below the measured threshold fail; preserve truthful overflow below it.
3. Run named tests during edits. Once integrated, run touched and composing files
   whole with `env -u NO_COLOR` and the repository isolated test-home, four-worker
   worksteal recipe. Include configuration/startup, card data/manager/activity,
   rack, card activity, Surfboard screen/layout, and native seat routing/prompt
   files touched by this feature. No full suite.
4. Run `guard and not mounts_app` and required docpins. Add app-mount registration
   guards only if a registration surface actually changed. Coordinate mutations
   so no worker observes another package's temporary broken code.
5. Dispatch one final reviewer with the repository contract verbatim, scoped diff,
   and named risks: primary overwrite, hidden roster fallback, token cache/history
   leakage, input event bubbling, empty-card background, all-filled news crash,
   and layout clipping. One fix wave; scoped re-review only for production fixes.
   File Minor-only findings instead of opening another work package.
6. Report final tests, mutation evidence, live render, and measured dimensions.
   Leave unrelated files and existing worktrees untouched.

# Production launch toasts

## Approved specification

Show a local Textual toast for every newly detected production token launch while
any Surf mode or the IMD boardroom is active. Exclude testnets. Notify once per
token; loading initial history and restarting the app must remain silent.

Use the existing native notification overlay: title `Token launched`, body
`$TICKER · NETWORK` followed by `Launch #N` on the next line, timeout 10 seconds. Missing ticker metadata uses
`Unknown token`; malformed launch numbers are ignored. Flatten and escape external
text with the existing markup helpers. Do not add an address to the toast.
Each newly eligible token in a batch gets its own toast.

The existing launch detector is authoritative: it admits live launches on chains
1, 8453 and 4663, seeds history silently, and exposes `swarm_launch_fired` with
`launch_id`, `ts`, `number`, `ticker`, `chain_id` and `token_address`. Reuse these
events instead of interpreting launch status again. Delivery follows the current
source refresh and signal-computation cadence; no endpoint, timer, persistent store or dependency is added. Work/Oracles offer the
existing launch worker at its existing tier cadence while leaving unrelated
full-cycle sources paused. Their cached projections advance only launch signals.

## Scope and ownership

Tier 2 because two dashboards consume the change. Expected production diff is
under 1,000 lines. The root session owns all implementation, tests and integration;
this planner owns this document only. Packages run sequentially because the
integration depends on the shared tracker. There are no package reviews: one
final review covers the whole diff, following CLAUDE.md's fix-wave limits.
The existing Python ≥3.11, Textual and Rich stack remains in use. Layout pins,
widget signatures, endpoint pools and dashboard registration do not change.
The sole new flat key is `swarm_launch_read_ts: float | None`, frozen in
`data/surf_models.py`: it is the successful current-session launch-list read
behind the signal snapshot, never a persisted fired timestamp or a wall-clock
substitute. It is None for a failed/missing reading even if fired news survives.
Root also owns the model-key, screen-dispatch and registration provenance
agreement tests for this key.

## Shared behavior and interfaces

Create `maxpane_dashboard/launch_notifications.py` with a small session-local
`LaunchNotifications.consume(data: dict) -> list[dict]` and a Textual
`SurfLaunchesUpdated(screen, data)` message. `MaxPaneApp` owns one tracker and handles
the message; Surf and Surfboard only publish their successful refresh snapshots.
The app accepts a message only while its originating screen is the current Surf
or Surfboard screen, before consuming events. A late refresh from a suspended
screen must not consume an unseen event.

- Treat `sig_swarm_state` in `ok`, `watch`, `fired` with a list-valued
  `swarm_launch_fired` as a usable baseline. Missing, loading, failed or malformed
  snapshots do not arm the tracker. `swarm_launch_read_ts` must be finite and
  between the injected app-session start time and now: a retained fired signal
  without a new session read cannot arm notifications. A valid empty initial
  list from a session read does arm it.
- The first usable snapshot records all event identities without notification,
  including persisted fired entries, and records an injected wall-clock timestamp
  as the session baseline. Source `as_of` clocks can precede event detection and
  are not used as the notification clock. Future-dated events are ignored without
  consuming their identities. Later delivered events with `ts` at or before that
  baseline remain silent, including historical events absent from an initial
  empty snapshot. Later snapshots emit only unseen tokens newer than the baseline.
- Retain launch UUIDs and, where a valid address is supplied, normalized
  `(chain_id, token_address)` aliases for the app session; validate with the
  existing `is_address` helper and lowercase only the address. Never infer one.
  Repeated UUIDs teach newly available address aliases across the whole snapshot
  before selecting any notifications, independent of row order;
  another UUID for an already-known token also remains silent. Token identity
  includes chain, so equal addresses on different supported chains are distinct.
- Retain identities when an event leaves the fired window, a snapshot becomes
  empty, or the user changes modes. A fresh app instance starts with a silent
  baseline. Do not use ticker or launch number alone as token identity.
- Reject malformed rows and unsupported chains without crashing. A failed
  snapshot must not reset the baseline or the already-observed identities.

## Implementation packages

### 1. Session tracker and safe toast content

Owner: root. Files: new `maxpane_dashboard/launch_notifications.py` and
`tests/test_launch_notifications.py`. No dependency on package 2.

- [x] Write focused failing tests using production fixtures from
  `tests/surf_launch_fixtures.py::launch_event`, then implement the smallest tracker
  and body formatter that pass them.
- [x] Cover cold/missing/unavailable snapshots followed by historical rows; first valid
  empty snapshot followed by one launch; persisted entries on restart; repeated
  refreshes; multiple new tokens; disappearing/reappearing events; metadata
  enrichment; token aliases; same address on different chains; testnet/malformed
  rows; historical events delivered after an empty baseline; and hostile ticker
  markup/control characters. Reuse `_swarm_chain.chain_word` for chain labels and
  existing flatten/clip/escape helpers for ticker content.
- [x] Assert exact emitted events and rendered plain text. Preserve existing
  fixture values rather than introducing network reads or fabricated addresses.

Acceptance: all scenarios emit the expected count and content, initial history
is silent, and state survives an empty event window. Focused command:
`.venv/bin/python -m pytest tests/test_launch_notifications.py`.

### 2. App ownership and both refresh hooks

Depends on package 1. Owner: root. Files: `maxpane_dashboard/app.py`,
`maxpane_dashboard/screens/surf.py`, `maxpane_dashboard/screens/surfboard.py`,
and focused additions in `tests/screens/test_surf_launch_notifications.py`.
Root also owns `analytics/surf_signals.py`, `data/surf_manager.py` and
`tests/data/test_surf_manager_launches.py` for the optimized-view signal path.

- [x] Add the app-owned tracker and message handler; invoke native
  `self.notify(body, title="Token launched", timeout=10)` once per emitted event.
  Perform no asynchronous network work in the handler.
- [x] Publish from `SurfScreen._do_refresh()` after the dictionary guard and before
  mode-specific rendering. Publish from `SurfboardScreen._update_title(data)` so
  both normal and cache-only hub snapshots use the same path.
- [x] Write failing offline integration tests first, reusing the real app routing
  and manager doubles in `tests/screens/test_surfboard_screen.py`. Prove startup
  silence, a visible native toast, multiple events, Surf mode independence,
  boardroom delivery, a Surf/boardroom round trip without duplication, and a late
  hidden-screen reply that does not consume the event.
- [x] Confirm existing `SurfManager` full and hub refresh paths continue publishing
  the launch signals in every Surf mode, including optimized Work/Oracles paths.
  The Work/Oracles projection advances only the existing launch detector and merges
  its baseline changes without touching unrelated detectors; offer the existing
  detached launch worker during their scheduled refresh. The hub projection
  starts from `_last_full_payload`; do not derive notifications
  from the one-hour display projection `recent_launch_news()`.

Acceptance: real app routing shares exactly one tracker, notification delivery
does not depend on the selected Surf body, and ordinary widget refreshes still
work. Tests use committed fixtures/stubs with network and clipboard disabled;
await observable state rather than wall-clock sleeps. Focused command:
`.venv/bin/python -m pytest tests/screens/test_surf_launch_notifications.py`.

### 3. Live check, targeted verification and final review

Depends on packages 1–2. Owner: root. Documentation: this plan and the applicable
Surf follow-ups document if residual findings exist.

- [x] Show the real app against current keyless data at the known owner terminal
  size 149×45 before review. Confirm startup produces no historical toast. If no
  actual launch occurs during that check, state that live event delivery was not
  observed; the deterministic offline integration test supplies that evidence.
- [x] Prove the duplicate/visibility guard tests bite using `scripts/mutate.py`;
  restore mutations immediately. Run focused tests during editing, then run the
  touched test files plus composing `tests/screens/test_surf_screen.py` and
  `tests/screens/test_surfboard_screen.py` once with `-n 4 --dist worksteal` and
  isolated home/cache state. Include manager composing tests only if manager code
  needs a change. Run `guard and not mounts_app` and the repository's docpin checks.
  Do not run the full suite or registration mount checks for unchanged bindings.
- [x] Dispatch one final whole-diff review with CLAUDE.md's verbatim reviewer
  contract. Its focused risks are startup/restart suppression, production-only
  filtering, metadata aliases, cross-screen lifecycle races and ticker safety.
  Apply the allowed fix wave; scoped re-review only for production fixes.
- [x] Record residual Minor findings, mark completed packages, and commit only
  this task's changes. Leave no temporary planning workspace behind.

Acceptance: targeted tests and guards pass, the live-check limitation is reported
accurately, the final review has no unresolved Critical/Important findings, and
the existing polling latency is preserved.

## Execution evidence

The initial notification tests failed on the missing module; optimized Work/Oracles
manager tests failed on the absent launch signal. The persisted-cache startup test
then exposed premature baseline arming and passed after source-read provenance was
added. Six mutants (startup gate, token aliases, repeat delivery, optimized-view
polling, source clock and hidden-screen consumption) are exercised before final
verification. All mutation edits are restored byte for byte.

Live preview at 149×45 used public launch data and a temporary copy of the local
cache; startup showed zero notifications. A demonstration toast for existing
MAINNET launch #1797 rendered through native Textual Toasts. Its list response had
no ticker, so the Unknown token fallback was visible. This was a demonstration
of an existing live launch, not an observed new launch. The SVG is
`/private/tmp/maxpane-launch-toast-live.svg`; no preview artifact is committed.

Final verification initially passed 859 cases and exposed a pre-existing fixture
contract mismatch: `tests/screens/test_surf_screen.py::_sample_data` omitted
`launch_state`, which HEAD already required. The fixture now declares `not_read`.
The first final review found one Important issue: same-batch enrichment could
arrive after a new UUID alias and duplicate the toast. The fix learns aliases for
known UUIDs across all valid rows before selecting notifications. Both orderings
are pinned by a regression which failed before the fix. All 29 focused unit,
integration and fixture checks passed after this fix wave.

Final result: the corrected composing screen file passed all 96 tests. The 29
focused post-fix checks, 124 fast guards and 12 documentation pins passed. The
scoped re-review marked the sole Important finding ADDRESSED; removing alias
prelearning reddened the alias-first regression and the mutation was restored.
No open findings remain from this review. No full suite was run.

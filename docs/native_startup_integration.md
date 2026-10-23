# Native startup and BOARDROOM reveal

## Approved behavior

The normal CLI uses the native Python intro once per local profile, recorded in
`~/.maxpane/.intro_seen`. `--intro` explicitly replays it. Normal startup treats
the historical `always` setting as first-run; disabled/never skips the automatic
intro. An explicit replay overrides those settings. Completion records seen;
decline/interruption does not. Standalone previews stay marker-free. Preserve
the intro's current rain/typewriter tempo and slower MAXPANE fade.

MaxPaneApp opens the existing menu without the legacy static splash. Launchers
delegate to Python and no longer build or run Rust. Help/version remain fast and
do not create startup state. Decline and interruption stop before reader creation.

Opening BOARDROOM as a dashboard plays the saved five-second terminal Matrix
effect over its complete outer region, including header, borders, command input
and footer. Cards keep their existing layout. New menu/cycle entry replays;
returning from pushed or switched detail views does not. Suspend/unmount cancels
both pending callbacks and active animation. Interaction may reveal the terminal
immediately. Loading and polling remain independent, and the actual latest
terminal is exposed at completion. Demos remain usable offline.

## Work packages and ownership

This Tier 2 change is sized below 1,000 production lines. There are no task
reviews; one final whole-change review follows integration and scoped checks.

1. Startup implementer owns `__main__.py`, `app.py`, intro startup helper,
   launch scripts and startup/CLI tests. Root does not edit these concurrently.
2. Root owns the production terminal effect, `screens/surfboard.py`, shared
   pure demo renderer extraction and terminal lifecycle/render tests.
3. Root owns this document, follow-ups, actual-data preview, integration checks
   and final commit. Unrelated work remains untouched.

Frozen seam: `_launch_game('surfboard')` calls
`SurfboardScreen.prepare_entry_animation()` before push/switch. No return path
calls it. The screen consumes pending entry only when current and laid out.

## Validation

Test first/second/forced startup, invalid config, skip/decline/interruption,
help/version side effects and launch forwarding. Test complete terminal coverage,
completion exposing new data, geometry on resize, nonblocking input and loading,
new-entry replay, return without replay, and cancellation before deferred start.
Use injected clocks and network-free managers. Show an actual-data BOARDROOM at
149x45 before final review. Run affected/composing files, required registration
and fast guards, doc pins, plus focused mutation checks; no full suite.

## Implementation evidence (2026-10-23)

- 281 affected/composing tests passed (49.91s), including the full BOARDROOM
  geometry and navigation files, intro screens and startup/CLI tests.
- A final combining-character/cell-cropping refinement passed 26 tests across
  the Matrix frame test and complete terminal-entry/intro-screen test files.
- 129 fast guards passed; 12 documentation pins passed.
- Mounted registration checks: 79 passed, one pre-existing failure at
  `tests/test_surf_registration.py:2404`,
  `test_a_full_outage_renders_explicit_states_not_zeros`. It still expects the
  obsolete outage warning; the same failure was independently reproduced from
  an isolated export of starting commit `f865025a`. Left unchanged.
- Actual production-reader preview at 149×45 showed the full terminal under
  rain, midway through reveal and after completion. This used real reader/cache
  content (60 events), not a fixture; it does not certify freshness of every API.
- Python 3.13 PTY smoke: first launch showed intro, second opened menu directly,
  `--intro` showed intro again; all exited 0. Escape skips the intro and counts
  as completed, preserving the existing intro interaction.
- Frame generation at 149×45: median 18.15ms, max 47.60ms over 25 fade frames
  with wide-text content, against a 50ms animation interval. This measures frame
  generation, not end-to-end input latency; the timer stops after five seconds.
- Two mutations killed: accidental replay on subview resume; historical `always`
  incorrectly forcing normal playback on every launch. Original bytes restored.
- Some old CLI-only test doubles initially opened the intro; the doubles now
  stub that boundary explicitly. No test-specific behavior was added to production.
- Final bounded review: Approved, no findings. Reviewer independently passed
  30 focused startup/lifecycle/Unicode tests and killed/restored the resume-replay
  mutation. `git diff --check` passed.

# Native Python intro — completion and follow-ups

2026-10-23: the standalone port is complete. Final bounded review: **Approved**,
no findings. Production startup integration is now implemented in
`native_startup_integration.md`; the three saved Matrix demos remain runnable.

Validation:

- 54 affected model/CLI/composited-screen tests passed; independently reproduced
  by the final reviewer.
- 129 fast repository guards and 12 documentation pins passed.
- Three mutations were killed: bypassed logo hold, swallowed prompt input and
  preview writing the seen marker. Reviewer independently killed the hold mutant.
- Actual Python 3.13 preview ran in a 149×45 PTY through all phases, Y acceptance
  and the final key: exit 0 after 27.31 seconds, terminal restored, no seen marker.
- Full/compact/minimal renders, Unicode input, resizing and custom colors covered.
- No network, Rust build/runtime or dashboard data source is used by the intro.

Run instructions and the retained demo commands are in `python_intro_plan.md`.

## Owner refinements

The original Rust text/reveal contract in the plan is superseded by these UI
requests: use Pepe and Swarm in the built-in messages, ask “Are you ready to enter
the Swarm?”, and show “locking in...” in lowercase. Custom Easter-egg text remains
user-authored.

The default background now follows MaxPane's Matrix theme. The subtitle below
MAXPANE uses the same idle ink as the BOARDROOM's Japanese middle captions.
Explicit custom background colors and the amber/C64 presets remain selectable.

Only MAXPANE's per-character fade is slowed, from 0.8s to 2s. Its scattered start
pattern, 3.5s default rain lead-in, rain movement, four-second transition window,
typewriter delays and three-second final hold are unchanged. Earlier demo behavior
is preserved; normal startup uses the greeting until an explicit `y`, then begins
with fullscreen rain and the logo reveal on each subsequent launch.

## Startup integration

Normal CLI and launchers use the native intro, with `--intro` for full replay.
Only literal `y` records `.intro_accepted`, immediately before the animation.
Early decline/skip/interruption leaves the greeting enabled; old `.intro_seen`
markers are ignored because they also recorded skips. Preview stays marker-free.
The legacy Rust binary remains available separately but is no longer invoked at
startup. BOARDROOM uses the saved terminal-only effect on explicit dashboard
entry, not on return from a detail view. Its absolute paint layer leaves the
143×37 layout pin and 149×45 owner geometry unchanged. Production reader preview
at 149×45 showed real cached/API-backed content under the fade, including all
terminal chrome. Final validation and review are recorded in the integration plan.

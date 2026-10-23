# Native Python intro — completion and follow-ups

2026-10-23: the standalone port is complete. Final bounded review: **Approved**,
no findings. Production startup integration remains a separate, optional task;
the current launcher and all three saved Matrix demos are unchanged.

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
typewriter delays and three-second final hold are unchanged. Earlier demo scripts
and normal startup remain unchanged.

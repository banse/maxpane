# Seat house rendering spike

Status: approved rendering experiment, 2026-10-23. Tier 2 because the experiment
adds an animated view. Target: fewer than 1,000 production lines; one final review.

## Scope

Build a standalone Python demo at `scripts/seat_house_demo.py`. Show the same
320×200, 16-colour scene inside the real BOARDROOM terminal region and fullscreen.
The inner view covers the terminal's header, input line and border. Preserve the
normal application, startup, dashboard registration and existing matrix demos.

Use the original C64 *Little Computer People* house arrangement as the visual
reference ([approved reference image](https://i.sstatic.net/L0RIC.jpg)). Draw fresh art; do not import a game ROM
or disk. Reuse the local idea prototype's drawing primitives and sprite approach
with attribution. This is a scripted offline sample, not a live seat simulation.
Label both the boardroom data and animation accordingly.

Controls: fullscreen/panel toggle, pause, replay, and quit. Resizing must preserve
the current animation state. No terminal profile or font changes, new terminal
tabs, network calls, paid jobs, writes to aidude, or normal-dashboard bindings.

## Rendering decision

One pure palette-index framebuffer feeds two adapters:

1. **Half-block, always available.** Each character contains two vertical pixels
   using foreground/background colours. Start with a reduced whole-house overview
   to show the owner's requested original arrangement; `Z` toggles an actor-following
   crop at native pixel resolution. The full house is native when at least
   320×100 cells are available. At 149×45 terminal size, the existing
   inner region is roughly 99×31 cells, therefore about 99×62 source pixels.
2. **Optional real graphics.** Kitty TGP through `textual-image` is the preferred
   experiment, selected explicitly with `--renderer tgp`; half-block is default.
   Preserve the entire 320×200 scene, integer nearest-neighbour scaling and
   letterboxing within the available pixel rectangle. Unknown/unsupported
   terminals, missing extras and headless runs keep the half-block path usable.

Raw ANSI drawing inside a Textual widget would fight its compositor, so it is
excluded. `TerminalReveal` is a temporary snapshot effect and is not the house
renderer. There is no need for a reader thread in a network-free scripted test;
the pure scene remains suitable for later snapshots from the existing reader.

`textual-image` 0.14.2 currently requires Python ≥3.12; MaxPane remains ≥3.11.
Keep graphics dependencies demo-only and optional. Existing `.venv` is Python
3.13; `.venv311` retains the normal fallback. The optional packages were installed
only in `.venv` (textual-image 0.14.2 and Pillow 13.0.0) using
`uv pip install --python .venv/bin/python 'textual-image==0.14.2'`. Do not raise the core
project minimum or add this as a mandatory dependency.

## Graphics integration details

The public widget API is `textual_image.widget.TGPImage(image)` with subsequent
`.image = PIL.Image` updates. Import it and probe before `App.run()`: Textual owns
stdin after startup. Do not import/probe for half-block or headless execution.
Keep terminal capability/protocol code outside the pure scene module.

The image should be palette-mode, expanded with nearest-neighbour into an exact
cell-pixel-sized canvas. The library's default resize can smooth RGB images.
Textual places/clips the TGP Unicode placeholder cells; set the graphics widget
to the actual panel or fullscreen rectangle. Installed 0.14.2 has 297 diacritic
entries and rejects larger placeholder dimensions; conservatively cap each
graphics dimension at 256 cells while preserving the half-block option.

Explicitly clear `.image = None` before hiding/removing the graphics widget and
on exit; the base widget does not implement an unmount cleanup hook. Installed
0.14.2 uploads with `i=<id>` but cleanup sends `a=d,I=<id>` without a selector.
Use a local renderable subclass overriding cleanup to send
`a=d,d=I,i=<id>,q=2`, then clear its ID. Pass it to a local `TGPImage` subclass via
the `Renderable=` class keyword. This avoids editing or globally monkeypatching
the installed dependency. A recording-sender regression must verify the selector.
Do not use a global delete operation that could remove unrelated terminal images.

Generic TGP support alone does not prove Unicode-placeholder support: the
upstream README documents a false positive on Warp. Use explicit TGP selection,
probe before startup, and show a fallback reason when unsupported. Sixel is a
later option; upstream documents animation/scrolling flicker and compositor
workarounds, so it is not necessary to establish this small experiment.

## Work packages and ownership

| Package | Owner | Files/responsibility | Dependency |
|---|---|---|---|
| Scene | Art implementer | `scripts/seat_house_scene.py`, `tests/test_seat_house_scene.py`; layout, palette, deterministic sprite frames and camera | Original-layout reference |
| App/adapters | Root | Demo entrypoint and optional graphics helper/requirements | Scene interface |
| Checks | Same implementer as relevant package | Focused scene/rendering tests | Implementation |
| Documentation | Architect initially, root for outcomes | This file | Measured demo |
| Final review | One reviewer | Whole experiment diff only | Preview and checks |

Do not modify each other's owned files. Scene and app work may run in parallel
after agreeing a pure `frame(elapsed)`/state/camera interface. Root owns integration.

## Acceptance and evidence

- Fallback runs with existing runtime dependencies and Python 3.11; no external
  files are required after checkout.
- Deterministic samples preserve 320×200 bounds and palette membership; pause
  freezes state and replay resets it.
- Composited tests prove panel containment, fullscreen switch/back, resize and
  intact surrounding cards at 149×45. Test a small viewport and a viewport large
  enough for the whole house. Inject a transport that raises on network use.
- Missing graphics dependency/unsupported capability produces a usable fallback;
  backend cleanup is tested with a recording fake, never a real terminal probe
  from tests. Keep actual terminal rendering separate from stub evidence.
- Show the owner the actual standalone demo render, explicitly marked SAMPLE /
  OFFLINE. This task does not modify a live dashboard, so sample content is the
  requested subject rather than a substitute for live-data acceptance.
- Run affected/composing tests once, guard checks, docs pins, and one targeted
  mutation. One final review only. Record measured frame preparation separately
  from terminal throughput; do not claim end-to-end FPS from pure timings.
- Actual graphics on a capable terminal is a separate verification result. If
  unavailable locally, say so; half-block screenshots do not prove TGP rendering.

## Sources

- Local idea and prototype: `/Library/Vibes/aidude/ideas/seat-house-life-sim.md`
  and `ideas/evidence/seat-house-life-sim/house_demo_v2-2026-10-23.py`.
- Existing integration example: `scripts/matrix_terminal_demo.py`.
- [textual-image API and terminal limitations](https://github.com/lnqs/textual-image).
- [Widget image setter/cleanup](https://github.com/lnqs/textual-image/blob/main/textual_image/widget/_base.py).
- [TGP renderable and placeholder limits](https://github.com/lnqs/textual-image/blob/main/textual_image/renderable/tgp.py).
- [Current dependency metadata](https://github.com/lnqs/textual-image/blob/main/pyproject.toml).
- [Kitty deletion selectors](https://sw.kovidgoyal.net/kitty/graphics-protocol/#deleting-images).

## Follow-ups

Live seat-event adaptation, daily letters, dashboard registration, Sixel/iTerm2
adapters and packaging are outside this rendering spike.

## Running the test

From `/Users/banse/codex/maxpane`:

```sh
.venv/bin/python scripts/seat_house_demo.py
.venv/bin/python scripts/seat_house_demo.py --fullscreen
# Optional: a terminal with Kitty graphics AND Unicode-placeholder support.
.venv/bin/python scripts/seat_house_demo.py --renderer tgp
```

`F`: panel/fullscreen, `Z`: whole house/close-up, `Space`: pause/resume,
`R`: restart the 93.8-second replay, `Enter`: house/underlying terminal,
`Q` or `Escape`: quit. Replay preserves the pause setting. The demo does not
load a seat or contact any API. Start it from the source checkout; its surrounding
BOARDROOM deliberately uses the existing test fixture.

Owner-size render: 149×45, inner area 99×31 characters; fullscreen reserves one
footer line and uses 149×44. Captures shown during implementation:
`/private/tmp/seat-house-panel.svg`, `/private/tmp/seat-house-fullscreen.svg`.
The scene is a fresh redraw of the original arrangement, not an emulator or an
extracted original game asset.

Measured frame preparation only (80 frames, local Python 3.13): half-block
99×31 median 1.36 ms/max 2.17 ms; 149×44 median 2.68 ms/max 4.48 ms;
320×100 median 12.10 ms/max 33.86 ms. These include scene composition, nearest
sampling and strip preparation, not terminal paint or end-to-end frame rate.
The replay clock advances at 10 updates/sec, with static background and palette
styles cached. No backlog of animation frames is queued.

Real graphics painting remains unverified on a capable terminal: none is installed
on this machine. The installed library's palette preservation, placement, resize
fallback/recovery and image cleanup are exercised with a recording protocol sink.
An Apple Terminal half-block render is not evidence for Kitty graphics support.

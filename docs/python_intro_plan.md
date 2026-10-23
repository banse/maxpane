# Native Python intro

Owner request: preserve the two saved Matrix demos and rebuild the complete Rust
intro in Python. This is a separately runnable port; normal startup remains as
configured. Tier 2, estimated below 1,000 production lines, root sole writer,
Agency architecture consultation and one final review.

## Contract and source

Use the executable behavior in `maxpane/src/intro/{mod,typewriter,prompt,rain,logo}.rs`,
`config.rs`, `theme.rs`, `terminal.rs` and `main.rs`, rather than stale comments.
The actual sequence is typewriter → prompt → rain/reveal → logo hold/splash → done.
`splash.rs` is unused. Retain the four messages, trailing-dot delays, text holds
and blank pauses, bounded prompt, responses and built-in/custom Easter eggs,
edge-to-center logo reveal, three-second logo hold, ambient drops, blinking
final prompt, notice, themes and English/Japanese tagline.

Y on an empty prompt proceeds immediately; N needs Enter to permit `ngmi`.
Empty Enter means yes. Custom eggs precede built-ins; unknown input/action retries.
Global any/esc/none skipping must preserve prompt input and the logo hold.
Ctrl+C exits everywhere. Distinguish dashboard-ready, declined and interrupted.

Read `[intro]` from TOML with the Rust defaults and strict field types; malformed
configuration warns and falls back. Use `~/.maxpane/.intro_seen` only for normal
mode and successful completion/skip with mode exactly `first_run`. The preview
script forces visibility and never writes this marker, including `mode=never`.
No networking, subprocess, Rust build/runtime, dashboard launch or normal-launch
script edit is part of this port.

Intentional improvements: handle resizing, fit all text by terminal cells, use
one stable minimal logo in rain and settled phases, distribute minimal rain
across the width. Random rain trajectories and ambient flicker need not be
bit-identical to Rust's RNG or frame-dependent integration. Preserve their
appearance, phases and configured duration; use elapsed time and bounded work.

## Work packages and ownership

1. Root: settings and pure state machine in `maxpane_dashboard/intro/`, with
   failing behavioral tests first. Freeze the state/config interface.
2. Root: terminal renderer and Textual controller, consuming package 1; snapshot
   real renders at 149×45 before final hardening. This intro has no live data.
3. Root: CLI/preview entry, configuration/seen-marker tests and use instructions.
   No changes to the saved demo scripts.
4. Final reviewer: bounded independent review of this diff; root fixes material
   findings in one wave and files Minor-only refinements.

## Validation

Use an injected clock: test timed phases, all prompt branches, skip modes,
interrupts, input bounds and Unicode. Inspect composited full/compact/minimal
frames and tiny windows, resize transitions, theme colors and stable logo
position. Verify preview/config/seen boundaries with temporary paths, rejecting
network transports. Kill targeted state/config mutations, run affected files,
fast guards and doc pins; no full suite. Preserve unrelated work.

## Run the saved previews

From `/Users/banse/codex/maxpane`:

```bash
.venv/bin/python scripts/python_intro.py
```

This previews the whole Rust sequence using native Python/Textual, including the
prompt and Easter eggs. It reads existing `[intro]` settings, always displays the
intro, and does not mark it as seen. `--config /path/to/config.toml` selects a
separate configuration. Defaults: Y/Enter proceeds at the question; N + Enter
declines; Escape skips; Ctrl+C interrupts. After the three-second logo hold,
any key finishes. The preview returns to the shell.

To honor `enabled`, `mode` and first-run state instead, invoke
`.venv/bin/python -m maxpane_dashboard.intro`. It is still standalone and does
not launch a dashboard. Exit codes: 0 complete/skipped, 1 declined, 130 interrupted.

The earlier previews remain independently runnable and unchanged:

- `scripts/matrix_demo.py`: rain into the MaxPane logo.
- `scripts/matrix_terminal_demo.py`: rain/reveal over the entire inner terminal.
- `scripts/matrix_boardroom_demo.py`: fullscreen rain, cards first, terminal later.

The normal `scripts/start.sh` entry point and the Rust crate are unchanged.

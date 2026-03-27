# MaxPane Intro Sequence -- Implementation Plan

**Date:** 2026-03-27
**PRD:** `/Library/Vibes/autopull/docs/MAXPANE_Intro_PRD.md`
**Mode:** Standard (medium risk, self-contained binary, clear PRD)

---

## 1. Overview

The MaxPane Intro Sequence is a standalone Rust TUI binary that lives inside the existing `autopull` repo (which currently contains only Python/JS code for the dashboard analytics). The Rust project will be rooted at `/Library/Vibes/autopull/maxpane/` to keep it isolated from the existing Python project.

The binary implements a 5-screen Matrix-inspired terminal intro sequence using Ratatui + Crossterm + Tokio. There is no interaction with the existing Python code -- this is a greenfield Rust project that happens to share a repository.

### Architecture Summary

```
maxpane/
  Cargo.toml
  src/
    main.rs              -- Entry point, tokio runtime, event loop
    config.rs            -- TOML config parsing, first-run detection, defaults
    theme.rs             -- Color scheme definitions (phosphor, amber, c64, custom)
    terminal.rs          -- Terminal setup/teardown, raw mode, size detection
    intro/
      mod.rs             -- State machine orchestrator, IntroSequence, IntroAction, LayoutMode
      typewriter.rs      -- Screen 1: character-by-character text rendering
      prompt.rs          -- Screen 2: Y/N input, easter eggs
      rain.rs            -- Screen 3+4: Matrix rain engine + logo reveal
      logo.rs            -- Screen 5: Static logo + tagline + ambient rain drops
      charset.rs         -- RAIN_CHARS constant, random_rain_char()
      animation.rs       -- Shared primitives: lerp, easing, brightness_to_color
```

### Key Design Decisions

- The Rust project is a **Cargo workspace member** placed at `maxpane/` -- it does NOT touch `pyproject.toml` or any Python files.
- The state machine is a linear enum (`Typewriter -> Prompt -> Rain -> Reveal -> Logo -> Done | Exit`).
- Rain and Reveal are two phases of a single `RainState` struct (not separate screens internally).
- All screens share the same `IntroTheme` and `IntroConfig` passed through the orchestrator.
- The event loop runs at 30 FPS using `tokio::time::interval(33ms)` with non-blocking crossterm input polling.

---

## 2. Dependency Graph

```
WP1 (Skeleton + Cargo.toml + main.rs stub)
 |
 +------+------+------+------+
 |      |      |      |      |
WP2    WP3    WP4    WP5    WP6
Config Theme  Chars  Term   Animation
 |      |      |      |      |
 +------+------+------+------+
 |
WP7 (State Machine Orchestrator -- intro/mod.rs)
 |
 +------+------+------+------+
 |      |      |      |      |
WP8    WP9    WP10   WP11   (all need WP7 types)
Type   Prompt Rain   Logo
writer        +Reveal
 |      |      |      |
 +------+------+------+
 |
WP12 (Integration -- wire main.rs event loop)
 |
WP13 (Tests)
```

**Critical path:** WP1 -> WP7 -> WP10 (rain is the most complex screen)

---

## 3. Work Packages

### WP1 -- Project Skeleton

**Description:** Create the Cargo project, all empty module files, and update `.gitignore`. This is the foundation that unblocks all other WPs. Every file should have minimal placeholder content that compiles.

**Files to create:**
- `maxpane/Cargo.toml`
- `maxpane/src/main.rs` (minimal tokio main that prints "MaxPane" and exits)
- `maxpane/src/config.rs` (empty pub mod with placeholder struct)
- `maxpane/src/theme.rs` (empty pub mod with placeholder struct)
- `maxpane/src/terminal.rs` (empty pub mod)
- `maxpane/src/intro/mod.rs` (empty pub mod, re-exports)
- `maxpane/src/intro/typewriter.rs` (empty pub mod)
- `maxpane/src/intro/prompt.rs` (empty pub mod)
- `maxpane/src/intro/rain.rs` (empty pub mod)
- `maxpane/src/intro/logo.rs` (empty pub mod)
- `maxpane/src/intro/charset.rs` (empty pub mod)
- `maxpane/src/intro/animation.rs` (empty pub mod)

**Files to modify:**
- `.gitignore` -- add `maxpane/target/`

**Dependencies:** None

**Acceptance criteria:**
- `cd maxpane && cargo build` succeeds with zero errors
- `cargo run` prints something and exits cleanly
- All module files exist and are wired into `main.rs` via `mod` declarations
- All dependencies from Cargo.toml resolve (ratatui 0.29+, crossterm 0.28+, tokio, serde, toml, fastrand, dirs)

**Suggested agent:** Rust scaffold agent

---

### WP2 -- Config System

**Description:** Implement TOML config parsing, defaults, first-run detection, and the `IntroConfig` struct with all fields from the PRD section 4.

**Files to create/modify:**
- `maxpane/src/config.rs` (full implementation)

**Dependencies:** WP1

**Key details:**
- `Config::load()` reads from `~/.maxpane/config.toml` (using `dirs::home_dir()`)
- All fields have sensible defaults via `serde(default)`
- `IntroConfig` includes: `enabled`, `mode`, `tagline`, `skip_key`, `rain_duration_ms`, `typewriter_speed_ms`, `color_scheme`, custom colors, `easter_eggs` vec
- `should_show()` method checks `mode` (always/first_run/never) and the `.intro_seen` flag file
- `mark_intro_seen()` writes the flag file
- `EasterEgg` struct with `input`, `response`, `action` (proceed/retry/exit)
- If config file does not exist, use all defaults without error

**Acceptance criteria:**
- `Config::load()` returns valid defaults when no config file exists
- Parsing a complete TOML config file produces correct values for all fields
- `should_show()` returns correct results for all mode/flag combinations
- `mark_intro_seen()` creates the flag file; `has_seen_intro()` detects it
- Easter egg deserialization works for custom entries
- Unit tests for config parsing, defaults, and first-run logic

**Suggested agent:** Rust backend agent

---

### WP3 -- Theme System

**Description:** Implement the three built-in color themes (phosphor, amber, c64) plus custom color parsing from config.

**Files to create/modify:**
- `maxpane/src/theme.rs` (full implementation)

**Dependencies:** WP1

**Key details:**
- `IntroTheme` struct with fields: `background`, `text`, `rain_bright`, `rain_dim`, `logo_color`, `tagline_color`, `cursor_color` (all `ratatui::style::Color`)
- `phosphor_theme()`, `amber_theme()`, `c64_theme()` factory functions with exact RGB values from PRD section 5.9
- `IntroTheme::from_config(config: &IntroConfig) -> IntroTheme` that selects built-in or constructs custom theme from hex colors
- Hex color string parsing (`"#33ff33"` -> `Color::Rgb(51, 255, 51)`)

**Acceptance criteria:**
- All three built-in themes match PRD RGB values exactly
- `from_config` dispatches to correct theme based on `color_scheme` string
- Custom hex color parsing works for valid 6-digit hex with `#` prefix
- Invalid hex gracefully falls back to phosphor theme
- Unit tests for all themes and hex parsing

**Suggested agent:** Rust backend agent

---

### WP4 -- Character Set

**Description:** Implement the rain character set constant and the random character selection function.

**Files to create/modify:**
- `maxpane/src/intro/charset.rs` (full implementation)

**Dependencies:** WP1

**Key details:**
- `RAIN_CHARS: &[char]` constant with all characters from PRD section 5.6 (box-drawing, block elements, katakana, digits, symbols)
- `random_rain_char(rng: &mut fastrand::Rng) -> char` function
- Consider also exposing `LOGO_CHARS` subset (box-drawing + block elements only) for use in reveal transition

**Acceptance criteria:**
- `RAIN_CHARS` contains all characters listed in PRD
- `random_rain_char` returns only characters from the set
- Compiles and is importable from other modules

**Suggested agent:** Rust backend agent (trivial -- can be combined with another WP if desired)

---

### WP5 -- Terminal Management

**Description:** Implement terminal setup, teardown, and size detection with proper panic handling.

**Files to create/modify:**
- `maxpane/src/terminal.rs` (full implementation)

**Dependencies:** WP1

**Key details:**
- `setup_terminal()` -> `Result<Terminal<CrosstermBackend<Stdout>>>`: enables raw mode, enters alternate screen, hides cursor, creates crossterm backend
- `restore_terminal(terminal)` -> `Result<()>`: disables raw mode, leaves alternate screen, shows cursor
- Panic hook that calls `restore_terminal` so the user's terminal is not left in raw mode on crash
- `LayoutMode` enum (`Full >= 100x30`, `Compact >= 80x24`, `Minimal < 80x24`) and `detect_layout(width, height)` function

**Acceptance criteria:**
- `setup_terminal` and `restore_terminal` are inverse operations
- Panic hook is installed and restores terminal
- `detect_layout` returns correct mode for boundary values (100x30, 99x30, 80x24, 79x23)
- Unit tests for `detect_layout`

**Suggested agent:** Rust backend agent

---

### WP6 -- Animation Primitives

**Description:** Implement shared animation utility functions used by multiple screens.

**Files to create/modify:**
- `maxpane/src/intro/animation.rs` (full implementation)

**Dependencies:** WP1

**Key details:**
- `lerp(a: f32, b: f32, t: f32) -> f32` -- linear interpolation
- `lerp_u8(a: u8, b: u8, t: f32) -> u8` -- for RGB channel interpolation
- `brightness_to_color(brightness: f32, frozen: bool, theme: &IntroTheme) -> Color` -- the core color mapping function from PRD section 5.6
- `ease_out_quad(t: f32) -> f32` -- for reveal slowdown (may be useful)
- `ease_in_cubic(t: f32) -> f32` -- optional, for rain acceleration

**Acceptance criteria:**
- `lerp(0.0, 10.0, 0.5)` == `5.0`
- `brightness_to_color` returns `theme.logo_color` when `frozen == true`
- `brightness_to_color` interpolates between `rain_dim` and `rain_bright` for non-frozen chars
- Unit tests for all functions including edge cases (t=0, t=1, t>1 clamped)

**Suggested agent:** Rust backend agent

---

### WP7 -- State Machine Orchestrator

**Description:** Implement `IntroSequence`, `IntroState`, `IntroAction`, and the orchestrator that drives screen transitions. This is the central coordination module.

**Files to create/modify:**
- `maxpane/src/intro/mod.rs` (full implementation)

**Dependencies:** WP1, WP2 (for IntroConfig types), WP3 (for IntroTheme), WP5 (for LayoutMode)

**Key details:**
- `IntroState` enum: `Typewriter(TypewriterState)`, `Prompt(PromptState)`, `Rain(RainState)`, `Reveal` (same struct as Rain, different phase), `Logo(LogoState)`, `Done`, `Exit`
- `IntroAction` enum: `Continue`, `NextScreen`, `Skip`, `Exit`
- `IntroResult` enum: `Dashboard`, `Exit`
- `IntroSequence` struct with `state`, `config`, `theme`, `layout_mode`
- `IntroSequence::new(config, theme, width, height)` -- initializes in `Typewriter` state
- `IntroSequence::tick(&mut self) -> IntroAction` -- delegates to current state's tick
- `IntroSequence::handle_input(&mut self, key: KeyEvent) -> IntroAction` -- ESC handling at top level, delegates rest
- `IntroSequence::render(&self, frame: &mut Frame)` -- delegates to current state's render
- `IntroSequence::advance(&mut self)` -- transitions to next state
- `IntroSequence::is_done(&self) -> bool`
- Skip key behavior respects config (`any`, `esc`, `none`)

NOTE: This WP defines the trait/interface that each screen state must implement but does NOT implement the screen states themselves (those are WP8-11). Use placeholder/stub implementations for the individual states that compile but do nothing (return `IntroAction::NextScreen` immediately or similar). The real implementations will replace these stubs.

**Acceptance criteria:**
- `IntroSequence::new()` compiles and starts in Typewriter state
- `advance()` transitions through all states in order: Typewriter -> Prompt -> Rain -> Logo -> Done
- ESC input returns `IntroAction::Skip` from any state
- Skip key config is respected
- The module compiles with stub state implementations
- Unit tests for state transition sequence and ESC handling

**Suggested agent:** Rust architecture agent

---

### WP8 -- Screen 1: Typewriter

**Description:** Implement the typewriter text effect for Screen 1.

**Files to create/modify:**
- `maxpane/src/intro/typewriter.rs` (full implementation)

**Dependencies:** WP7 (for IntroAction, state interface), WP3 (for theme), WP6 (for animation utils)

**Key details:**
- `TypewriterState` struct as specified in PRD section 5.4
- Four lines of text: "Wake up, anon...", "The chain has you...", "Follow the white rabbit.", "Knock, knock."
- Character-by-character reveal with configurable `speed_ms` (default 45ms)
- Ellipsis (`...`) rendered at 2x speed_ms for dramatic effect
- `line_pause_ms` (default 1200ms) between lines
- Blinking cursor `\u{258C}` (left half block) at current position, 530ms blink interval
- Text horizontally and vertically centered based on terminal size
- After all lines complete + final pause: return `IntroAction::NextScreen`
- On any key press (if skip_key allows): return `IntroAction::Skip`
- Hard cut to black (clear screen) before transitioning

**Acceptance criteria:**
- Characters appear one at a time at the configured speed
- Ellipsis characters are slower
- Pauses occur between lines
- Cursor blinks at the correct rate
- Text is centered for various terminal sizes
- Transition occurs after all text is displayed
- No panics on very small terminals

**Suggested agent:** Rust UI agent

---

### WP9 -- Screen 2: Prompt

**Description:** Implement the interactive Y/N prompt with easter egg support.

**Files to create/modify:**
- `maxpane/src/intro/prompt.rs` (full implementation)

**Dependencies:** WP7 (for IntroAction, state interface), WP2 (for EasterEgg config), WP3 (for theme)

**Key details:**
- `PromptState` with `PromptPhase` enum: `Question`, `WaitingForInput`, `ResponseY`, `ResponseN`, `ResponseOther`
- Display "> Do you want to see the chain?" then "> [Y/N]: _"
- Input handling:
  - `y`, `Y`, Enter -> "JACKING IN..." -> pause 800ms -> `IntroAction::NextScreen`
  - `n`, `N` -> "Maybe next time, anon." -> pause 1s -> `IntroAction::Exit`
  - Any other single char or string -> check easter eggs (custom first, then defaults) -> display response -> reset to WaitingForInput or proceed/exit per egg action
- Default easter eggs from PRD section 5b (morpheus, vitalik, gm, wagmi, ngmi, satoshi)
- Multi-character input: buffer keypresses until Enter is pressed, then evaluate the full buffer
- Blinking cursor at 530ms interval
- Text centered like Screen 1

**Acceptance criteria:**
- Y/Enter proceeds to next screen with "JACKING IN..." message
- N exits with goodbye message
- Default easter eggs all produce correct responses and actions
- Custom easter eggs from config are checked before defaults
- Unknown input shows "There is no spoon. Try again." and resets
- Cursor blinks correctly
- Unit tests for input matching logic and easter egg priority

**Suggested agent:** Rust UI agent

---

### WP10 -- Screen 3+4: Rain Engine + Logo Reveal

**Description:** Implement the Matrix rain animation and the logo crystallization reveal. This is the most complex and performance-critical work package.

**Files to create/modify:**
- `maxpane/src/intro/rain.rs` (full implementation)

**Dependencies:** WP7 (for IntroAction, state interface), WP3 (for theme), WP4 (for charset), WP6 (for animation utils)

**Key details:**

**Rain engine (Screen 3 -- FullRain phase):**
- `RainState` struct with `columns: Vec<RainColumn>`, `phase: RainPhase`, `logo_mask: LogoMask`, timing fields
- One `RainColumn` per terminal column, each with: speed (4.0-12.0 rows/sec, randomized), head_y (float), trail_length (5-20, randomized), active flag
- Per frame (30 FPS): advance head_y by speed * delta_time, spawn new char at head, decay brightness of trail chars by 0.85, remove chars below 0.05 brightness
- 2% per-frame flicker chance: replace existing char with new random char
- Rain head (brightness 1.0) rendered as bright/white; trail fades through theme colors
- Duration from config (`rain_duration_ms`, default 3500)

**Logo reveal (Screen 4 -- Revealing phase):**
- `LogoMask` struct: 2D grid of the MAXPANE ASCII logo, centered in terminal
- `reveal_order(x, y) -> f32`: distance-from-edge metric (outside-in reveal)
- `reveal_progress` advances from 0.0 to 1.0 over ~2.5 seconds
- As progress advances: rain chars at logo positions freeze, get replaced with actual logo char, brightness set to 1.0
- Non-logo rain columns: speed *= 0.95 per frame (decelerate and fade)
- When progress >= 1.0 and all non-logo chars gone -> return `IntroAction::NextScreen`

**Responsive:**
- `Full` mode: full MAXPANE logo
- `Compact` mode: reduced logo (shorter or "MAX" only as PRD suggests)
- `Minimal` mode: text-only "MAXPANE", fewer rain columns

**Acceptance criteria:**
- Rain renders at stable 30 FPS (frame time < 33ms for a 200-column terminal)
- Rain columns have visually varied speeds and trail lengths
- Character flicker effect is visible
- Logo reveal progresses from edges inward
- Frozen logo characters display in logo_color
- Non-logo rain fades out during reveal
- No panics on terminal resize during animation
- Renders correctly in all three layout modes
- Unit tests for: RainColumn physics (speed, brightness decay), LogoMask reveal_order correctness, phase transitions

**Suggested agent:** Rust animation/graphics agent (most experienced agent)

---

### WP11 -- Screen 5: Static Logo

**Description:** Implement the final static logo display with tagline and ambient rain drops.

**Files to create/modify:**
- `maxpane/src/intro/logo.rs` (full implementation)

**Dependencies:** WP7 (for IntroAction, state interface), WP3 (for theme), WP6 (for animation utils)

**Key details:**
- `LogoState` struct with tagline variant, ambient rain drops, hold timer
- Logo data: `LOGO_BLOCK` constant (the ASCII art from PRD section 5.7), `TAGLINE_EN`, `TAGLINE_JP`
- Logo centered horizontally and vertically; tagline centered below logo with 2-line gap
- Ambient effect: sparse `|` characters fading in from top and bottom edges (decorative, not full rain)
- Hold for 2 seconds, then return `IntroAction::NextScreen` (which maps to Done)
- Responsive: Full mode shows full logo, Compact shows reduced, Minimal shows text only

**Acceptance criteria:**
- Logo renders centered in terminal
- Correct tagline variant shown based on config (english/katakana)
- Ambient rain drops visible and fading
- Transitions to Done after hold duration
- Looks correct in all layout modes
- No panic on small terminals

**Suggested agent:** Rust UI agent

---

### WP12 -- Integration: Event Loop + main.rs

**Description:** Wire everything together in `main.rs`. Implement the async event loop from PRD section 5.11, connect config loading, terminal setup, intro sequence, and clean shutdown.

**Files to create/modify:**
- `maxpane/src/main.rs` (replace stub with full implementation)

**Dependencies:** WP2, WP3, WP5, WP7, WP8, WP9, WP10, WP11 (all previous WPs)

**Key details:**
- `#[tokio::main(flavor = "current_thread")]`
- Load config, resolve theme, setup terminal (with panic hook)
- Check `config.intro.should_show()` -- if false, print "MaxPane ready." and exit (no dashboard yet)
- `run_intro()` async function: 30 FPS interval, non-blocking input poll, tick + render loop
- Handle `IntroResult::Exit` (quit) vs `IntroResult::Dashboard` (print "Entering dashboard..." placeholder and exit)
- After successful intro in `first_run` mode, call `mark_intro_seen()`
- Graceful cleanup: `restore_terminal()` always runs, even on error (use scopeguard or Drop)

**Acceptance criteria:**
- `cargo run` with no config file: shows full intro sequence, exits cleanly after logo screen
- `cargo run` with `mode = "never"`: skips intro entirely
- `cargo run` after first run with `mode = "first_run"`: skips intro (flag file exists)
- ESC at any screen: clean exit to "dashboard" placeholder
- N at prompt: clean exit with goodbye message
- Terminal is always restored (no raw mode leak), even on panic
- No compiler warnings

**Suggested agent:** Rust integration agent

---

### WP13 -- Test Suite

**Description:** Comprehensive unit and integration tests for all modules.

**Files to create/modify:**
- `maxpane/tests/integration.rs` (integration tests)
- Unit tests inline in each module (added to existing files from WP2-WP11)

**Dependencies:** WP12 (everything must be wired up)

**Key details:**

Unit tests (inline `#[cfg(test)]` modules -- verify these exist or add them):
- Config: parsing, defaults, first-run detection, should_show logic
- Theme: all built-in themes, hex parsing, custom theme construction
- Charset: RAIN_CHARS completeness, random_rain_char returns valid chars
- Animation: lerp, brightness_to_color, easing functions
- Terminal: detect_layout boundary values
- Orchestrator: state transitions, ESC handling, skip key modes
- Typewriter: timing logic, line progression, ellipsis speed
- Prompt: input matching, easter egg priority, phase transitions
- Rain: column physics, brightness decay, logo mask reveal order, phase transitions
- Logo: hold duration, tagline selection

Integration tests:
- Headless full sequence run (construct IntroSequence, feed synthetic ticks and inputs, verify it reaches Done without panic)
- Skip sequence (ESC immediately)
- Exit sequence (N at prompt)
- Small terminal (80x24) full sequence without panic

**Acceptance criteria:**
- `cargo test` passes with zero failures
- Coverage of all state machine paths
- Coverage of config edge cases
- No flaky tests (no real timing dependencies -- use mock time or deterministic ticks)

**Suggested agent:** Rust test agent

---

## 4. Execution Waves

### Wave 1: Foundation (sequential, single agent)

| WP | Title | Agent | Est. effort |
|----|-------|-------|-------------|
| WP1 | Project Skeleton | Scaffold | Small |

**Gate:** `cargo build` succeeds. All module files exist and compile.

---

### Wave 2: Leaf Modules (fully parallel, 5 agents)

| WP | Title | Agent | Est. effort |
|----|-------|-------|-------------|
| WP2 | Config System | Backend | Medium |
| WP3 | Theme System | Backend | Small |
| WP4 | Character Set | Backend | Trivial |
| WP5 | Terminal Management | Backend | Small |
| WP6 | Animation Primitives | Backend | Small |

**Gate:** All five WPs compile. Unit tests pass for each. No cross-WP dependencies in this wave.

**Compilation note:** Each WP agent writes its module in isolation. Because WP1 created stub files with placeholder types, each agent replaces only its own file. No agent in Wave 2 imports types from another Wave 2 module -- they only depend on external crates and their own module. If a module needs a type from another Wave 2 module (e.g., animation.rs needs IntroTheme from theme.rs), the agent should define a minimal local trait or accept generic parameters, OR simply use `ratatui::style::Color` directly.

**Practical concern:** `animation.rs` (`brightness_to_color`) needs `IntroTheme`. Resolution: the function takes individual `Color` parameters (`rain_dim`, `rain_bright`, `logo_color`) rather than an `IntroTheme` reference. This way WP6 has zero dependency on WP3.

---

### Wave 3: Orchestrator (sequential, single agent)

| WP | Title | Agent | Est. effort |
|----|-------|-------|-------------|
| WP7 | State Machine Orchestrator | Architecture | Medium |

**Gate:** `cargo build` succeeds with the orchestrator importing types from WP2, WP3, WP5, WP6. Stub screen states compile. State transition unit tests pass.

**Why sequential:** The orchestrator defines the trait/interface contract that all screen implementations depend on. Getting this wrong would cascade into all four screen WPs.

---

### Wave 4: Screens (fully parallel, 4 agents)

| WP | Title | Agent | Est. effort |
|----|-------|-------|-------------|
| WP8 | Screen 1: Typewriter | UI | Medium |
| WP9 | Screen 2: Prompt | UI | Medium |
| WP10 | Screen 3+4: Rain + Reveal | Animation | Large |
| WP11 | Screen 5: Logo | UI | Small |

**Gate:** Each screen compiles and passes its unit tests in isolation. `cargo build` succeeds with all screens wired into the orchestrator.

**Compilation note:** Each screen agent receives the state interface contract from WP7 (the struct shape, required methods, return types). They implement their state struct to conform to it. The orchestrator's stub implementations get replaced by the real ones.

---

### Wave 5: Integration (sequential, single agent)

| WP | Title | Agent | Est. effort |
|----|-------|-------|-------------|
| WP12 | Event Loop + main.rs | Integration | Medium |

**Gate:** `cargo run` launches the full intro sequence. Manual testing confirms all 5 screens render and transition correctly.

---

### Wave 6: Tests (sequential, single agent)

| WP | Title | Agent | Est. effort |
|----|-------|-------|-------------|
| WP13 | Test Suite | Test | Medium |

**Gate:** `cargo test` passes. All state machine paths covered. Integration tests run headless without panic.

---

## 5. Risks and Unknowns

| Risk | Severity | Mitigation |
|------|----------|------------|
| Ratatui 0.29 API changes vs PRD code snippets | Medium | PRD snippets are illustrative, not copy-paste. Agents must check actual ratatui 0.29 API (e.g., `frame.buffer_mut()` might be `frame.buffer_mut()` or require different access pattern). |
| Crossterm 0.28 compatibility with Ratatui 0.29 | Low | These are commonly paired. Cargo will catch version mismatches at build time. |
| Wide Unicode characters (Katakana are double-width) | Medium | Rain columns with Katakana chars consume 2 cells. The rain engine must account for `unicode_width` or skip double-width chars in rain columns. May need the `unicode-width` crate. |
| Terminal resize during animation | Low | Ratatui handles resize events. The orchestrator should re-detect layout mode on resize. Not critical for MVP but should not panic. |
| Performance on large terminals (300+ columns) | Low | 30 FPS with simple per-cell updates should be fine. Profile if needed. |
| Merge conflicts with existing Python code | None | Rust project is in a new `maxpane/` directory with no overlap. |

## 6. Resolved Questions

1. **Dashboard placeholder:** YES — "print message and exit" for now. Later the intro will transition into the app's splash screen.

2. **Unicode width:** Add `unicode-width` crate. Use double-width Katakana by default, but also provide a single-width-only option as fallback.

3. **Logo for Compact mode:** Create a dedicated `LOGO_COMPACT` constant showing only "MAX" in block font (31 chars wide). Cleaner than dynamic truncation.

---

## 7. Validation Plan

After all waves complete:

1. **Smoke test:** `cd maxpane && cargo run` -- full sequence plays through, terminal restored
2. **Skip test:** Press ESC during Screen 1 -- clean exit
3. **Exit test:** Type `n` at prompt -- goodbye message, clean exit
4. **Easter egg test:** Type `gm` at prompt -- proceed with custom message
5. **Config test:** Create `~/.maxpane/config.toml` with `color_scheme = "amber"` -- amber colors render
6. **First-run test:** Run once (creates `.intro_seen`), run again with `mode = "first_run"` -- skips intro
7. **Small terminal test:** Resize to 80x24, run -- compact mode renders without overflow or panic
8. **Automated:** `cargo test` -- all unit and integration tests green
9. **Performance:** No visible stutter during rain animation on a standard terminal emulator

//! Integration tests for the MaxPane intro sequence.
//!
//! These exercise the full `IntroSequence` state machine without a real
//! terminal, using synthetic key events and the public API (`tick`,
//! `handle_input`, `advance`, `is_done`, `result`).
//!
//! Screens that rely on `Instant`-based timing (Typewriter, Rain, Logo,
//! and the Prompt response timer) are either advanced manually with
//! `advance()` or given a short `thread::sleep` to let wall-clock time
//! expire the internal timers.

use std::thread;
use std::time::Duration;

use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers};

use maxpane::config::{EasterEgg, IntroConfig};
use maxpane::intro::{IntroAction, IntroResult, IntroSequence};
use maxpane::theme::phosphor_theme;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Create a synthetic key press event.
fn key(code: KeyCode) -> KeyEvent {
    KeyEvent {
        code,
        modifiers: KeyModifiers::NONE,
        kind: KeyEventKind::Press,
        state: KeyEventState::NONE,
    }
}

/// Create an IntroConfig with skip_key = "esc" so non-ESC keys delegate
/// to the active screen.
fn esc_only_config() -> IntroConfig {
    IntroConfig {
        skip_key: "esc".to_string(),
        ..IntroConfig::default()
    }
}

/// Create an IntroConfig with skip_key = "none" so no key triggers global
/// skip.
fn no_skip_config() -> IntroConfig {
    IntroConfig {
        skip_key: "none".to_string(),
        ..IntroConfig::default()
    }
}

/// Advance a freshly created sequence to the Prompt screen and tick once
/// so it enters WaitingForInput. Uses `advance()` to skip the Typewriter.
fn advance_to_prompt_input(seq: &mut IntroSequence) {
    seq.advance(); // Typewriter -> Prompt
    seq.tick(); // ShowingQuestion -> WaitingForInput
}

/// Sleep just long enough for the prompt response timer to expire
/// (the longest response duration is 1000ms for NO / easter eggs),
/// then tick repeatedly to let the state machine process the expiry.
/// Returns the last non-Continue action observed, if any.
fn sleep_and_tick_past_response(seq: &mut IntroSequence) -> Option<IntroAction> {
    thread::sleep(Duration::from_millis(1100));
    let mut last_action = None;
    for _ in 0..100 {
        let action = seq.tick();
        if action != IntroAction::Continue {
            last_action = Some(action);
        }
        if seq.is_done() {
            break;
        }
    }
    last_action
}

// ---------------------------------------------------------------------------
// 1. Full sequence headless run
// ---------------------------------------------------------------------------

/// Run the full intro sequence to completion using `advance()` to skip
/// timing-based screens and injecting a 'y' keypress at the Prompt.
/// Verifies no panic and result is Dashboard.
#[test]
fn full_sequence_headless_reaches_done() {
    let config = no_skip_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    // Screen 1: Typewriter -- skip via advance().
    seq.advance(); // -> Prompt

    // Screen 2: Prompt -- tick to WaitingForInput, then send 'y'.
    seq.tick(); // ShowingQuestion -> WaitingForInput
    seq.handle_input(key(KeyCode::Char('y')));

    // Wait for the "JACKING IN..." response timer (800ms).
    thread::sleep(Duration::from_millis(900));
    // Tick until the prompt finishes (should return NextScreen).
    let mut advanced = false;
    for _ in 0..100 {
        let action = seq.tick();
        if action == IntroAction::NextScreen {
            advanced = true;
            break;
        }
    }
    assert!(advanced, "prompt should advance after 'y' response timer expires");

    // Screen 3: Rain -- skip via advance().
    seq.advance(); // -> Logo

    // Screen 4: Logo (hold then splash phase) -- skip via advance().
    seq.advance(); // -> Done

    assert!(seq.is_done());
    assert_eq!(seq.result(), IntroResult::Dashboard);
}

// ---------------------------------------------------------------------------
// 2. ESC skip at each screen
// ---------------------------------------------------------------------------

#[test]
fn esc_skips_from_typewriter() {
    let config = esc_only_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    let action = seq.handle_input(key(KeyCode::Esc));
    assert_eq!(action, IntroAction::Skip);
}

#[test]
fn esc_skips_from_prompt() {
    let config = esc_only_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    seq.advance(); // -> Prompt
    let action = seq.handle_input(key(KeyCode::Esc));
    assert_eq!(action, IntroAction::Skip);
}

#[test]
fn esc_skips_from_rain() {
    let config = esc_only_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    seq.advance(); // -> Prompt
    seq.advance(); // -> Rain
    let action = seq.handle_input(key(KeyCode::Esc));
    assert_eq!(action, IntroAction::Skip);
}

#[test]
fn esc_skips_from_logo() {
    let config = esc_only_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    seq.advance(); // -> Prompt
    seq.advance(); // -> Rain
    seq.advance(); // -> Logo
    let action = seq.handle_input(key(KeyCode::Esc));
    assert_eq!(action, IntroAction::Skip);
}

// ---------------------------------------------------------------------------
// 3. Exit via N at prompt
// ---------------------------------------------------------------------------

#[test]
fn exit_via_n_at_prompt() {
    let config = esc_only_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    advance_to_prompt_input(&mut seq);

    // Type 'n' then Enter.
    seq.handle_input(key(KeyCode::Char('n')));
    seq.handle_input(key(KeyCode::Enter));

    // Wait for response timer (1000ms for NO) then tick.
    let action = sleep_and_tick_past_response(&mut seq);

    // The prompt signals Exit via tick() return value. The orchestrator
    // in IntroSequence::tick() passes it through to the caller (it only
    // auto-handles NextScreen). The caller (main loop) is responsible
    // for acting on Exit. Verify we got the Exit action.
    assert_eq!(action, Some(IntroAction::Exit));
}

// ---------------------------------------------------------------------------
// 4. Easter egg flow
// ---------------------------------------------------------------------------

#[test]
fn easter_egg_proceed_advances_past_prompt() {
    let config = IntroConfig {
        skip_key: "none".to_string(),
        easter_eggs: vec![EasterEgg {
            input: "hodl".to_string(),
            response: "Diamond hands activated.".to_string(),
            action: "proceed".to_string(),
        }],
        ..IntroConfig::default()
    };
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    advance_to_prompt_input(&mut seq);

    // Type the easter egg and press Enter.
    for c in "hodl".chars() {
        seq.handle_input(key(KeyCode::Char(c)));
    }
    seq.handle_input(key(KeyCode::Enter));

    // Wait for response timer (1000ms for easter eggs) then tick.
    thread::sleep(Duration::from_millis(1100));
    let mut advanced = false;
    for _ in 0..100 {
        let action = seq.tick();
        if action == IntroAction::NextScreen {
            advanced = true;
            break;
        }
    }

    assert!(advanced, "proceed easter egg should advance to next screen");
    // Still has Rain + Logo remaining.
    assert!(!seq.is_done());
}

#[test]
fn easter_egg_retry_stays_in_prompt() {
    let config = IntroConfig {
        skip_key: "none".to_string(),
        easter_eggs: vec![EasterEgg {
            input: "rugged".to_string(),
            response: "Trust no one.".to_string(),
            action: "retry".to_string(),
        }],
        ..IntroConfig::default()
    };
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    advance_to_prompt_input(&mut seq);

    // Type the easter egg and press Enter.
    for c in "rugged".chars() {
        seq.handle_input(key(KeyCode::Char(c)));
    }
    seq.handle_input(key(KeyCode::Enter));

    // Wait for retry response timer then tick.
    thread::sleep(Duration::from_millis(1100));
    for _ in 0..100 {
        seq.tick();
    }

    // After retry, the sequence is still in the prompt (not done).
    assert!(!seq.is_done());

    // We can still proceed by typing 'y'.
    seq.handle_input(key(KeyCode::Char('y')));
    thread::sleep(Duration::from_millis(900));
    let mut advanced = false;
    for _ in 0..100 {
        let action = seq.tick();
        if action == IntroAction::NextScreen {
            advanced = true;
            break;
        }
    }
    assert!(advanced, "should be able to proceed after retry easter egg");
}

// ---------------------------------------------------------------------------
// 5. Small terminal (80x24) full run -- Compact mode
// ---------------------------------------------------------------------------

#[test]
fn compact_terminal_full_run() {
    let config = no_skip_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 80, 24);

    // Skip Typewriter, handle Prompt, skip Rain + Logo.
    seq.advance(); // -> Prompt
    seq.tick(); // -> WaitingForInput
    seq.handle_input(key(KeyCode::Char('y')));
    thread::sleep(Duration::from_millis(900));
    for _ in 0..100 {
        let action = seq.tick();
        if action == IntroAction::NextScreen {
            break;
        }
    }
    seq.advance(); // -> Logo
    seq.advance(); // -> Done

    assert!(seq.is_done());
    assert_eq!(seq.result(), IntroResult::Dashboard);
}

// ---------------------------------------------------------------------------
// 6. Minimal terminal (60x20) full run
// ---------------------------------------------------------------------------

#[test]
fn minimal_terminal_full_run() {
    let config = no_skip_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 60, 20);

    // Skip Typewriter, handle Prompt, skip Rain + Logo.
    seq.advance(); // -> Prompt
    seq.tick(); // -> WaitingForInput
    seq.handle_input(key(KeyCode::Char('y')));
    thread::sleep(Duration::from_millis(900));
    for _ in 0..100 {
        let action = seq.tick();
        if action == IntroAction::NextScreen {
            break;
        }
    }
    seq.advance(); // -> Logo
    seq.advance(); // -> Done

    assert!(seq.is_done());
    assert_eq!(seq.result(), IntroResult::Dashboard);
}

// ---------------------------------------------------------------------------
// 7. Y at prompt proceeds to Rain
// ---------------------------------------------------------------------------

#[test]
fn y_at_prompt_proceeds_to_rain() {
    let config = esc_only_config();
    let theme = phosphor_theme();
    let mut seq = IntroSequence::new(config, theme, 120, 40);

    advance_to_prompt_input(&mut seq);

    // Send 'y' -- immediate single-char accept.
    seq.handle_input(key(KeyCode::Char('y')));

    // Wait for the "JACKING IN..." response timer (800ms) to expire.
    thread::sleep(Duration::from_millis(900));

    let mut advanced = false;
    for _ in 0..100 {
        let action = seq.tick();
        if action == IntroAction::NextScreen {
            advanced = true;
            break;
        }
    }

    assert!(advanced, "'y' at prompt should advance past prompt to rain");
    // Rain and Logo remain.
    assert!(!seq.is_done());
}

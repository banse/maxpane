//! Intro sequence orchestrator — linear state machine.
//!
//! Drives the six-screen intro sequence:
//! Typewriter -> Prompt -> Rain -> Logo -> Splash -> Done
//! and handles global input (ESC/skip) before delegating to individual screen
//! states.

pub mod animation;
pub mod charset;
pub mod logo;
pub mod prompt;
pub mod rain;
pub mod splash;
pub mod typewriter;

use crossterm::event::{KeyCode, KeyEvent};

use crate::config::IntroConfig;
use crate::terminal::{detect_layout, LayoutMode};
use crate::theme::IntroTheme;

// ---------------------------------------------------------------------------
// Action / Result enums
// ---------------------------------------------------------------------------

/// Returned by `tick()` and `handle_input()` to signal what the orchestrator
/// (or caller) should do next.
#[derive(Debug, PartialEq)]
pub enum IntroAction {
    /// Keep running the current screen.
    Continue,
    /// The current screen is finished; advance to the next one.
    NextScreen,
    /// Skip the entire intro and go straight to the dashboard.
    Skip,
    /// Quit the application.
    Exit,
}

/// Final outcome of the intro sequence, consumed by `main`.
#[derive(Debug, PartialEq)]
pub enum IntroResult {
    /// Proceed to the main dashboard.
    Dashboard,
    /// The user chose to exit (e.g. answered "N" at the prompt).
    Exit,
}

// ---------------------------------------------------------------------------
// IntroState
// ---------------------------------------------------------------------------

/// The current screen within the intro sequence.
pub enum IntroState {
    Typewriter(typewriter::TypewriterState),
    Prompt(prompt::PromptState),
    Rain(rain::RainState),
    Logo(logo::LogoState),
    Done,
    Exit,
}

// ---------------------------------------------------------------------------
// IntroSequence
// ---------------------------------------------------------------------------

/// Orchestrates the full intro sequence as a linear state machine.
pub struct IntroSequence {
    state: IntroState,
    config: IntroConfig,
    theme: IntroTheme,
    layout: LayoutMode,
    width: u16,
    height: u16,
}

impl IntroSequence {
    /// Create a new intro sequence starting at the Typewriter screen.
    ///
    /// `width` and `height` are the current terminal dimensions used to select
    /// the appropriate [`LayoutMode`] and passed to screen states for proper
    /// centering and column count.
    pub fn new(config: IntroConfig, theme: IntroTheme, width: u16, height: u16) -> Self {
        let layout = detect_layout(width, height);
        let tw = typewriter::TypewriterState::new(&config, &theme, layout);
        Self {
            state: IntroState::Typewriter(tw),
            config,
            theme,
            layout,
            width,
            height,
        }
    }

    /// Advance the simulation by one tick. Delegates to the active screen's
    /// `tick()`. When the screen signals `NextScreen`, calls [`advance`] to
    /// move to the next state.
    pub fn tick(&mut self) -> IntroAction {
        let action = match &mut self.state {
            IntroState::Typewriter(s) => s.tick(),
            IntroState::Prompt(s) => s.tick(),
            IntroState::Rain(s) => s.tick(),
            IntroState::Logo(s) => s.tick(),
            IntroState::Done | IntroState::Exit => return IntroAction::Continue,
        };

        if action == IntroAction::NextScreen {
            self.advance();
        }

        action
    }

    /// Handle a key event. The global skip-key check runs first (respecting
    /// `config.skip_key`), then delegates to the active screen's
    /// `handle_input`.
    ///
    /// The Prompt screen is exempt from `skip_key = "any"` because it needs
    /// keyboard input for Y/N and easter eggs. ESC still works as skip there.
    pub fn handle_input(&mut self, key: KeyEvent) -> IntroAction {
        let needs_input = matches!(
            self.state,
            IntroState::Prompt(_) | IntroState::Logo(_)
        );

        // Global skip-key handling based on config.
        // Screens that need keyboard input (Prompt, Splash) are exempt from
        // "any key skips" — only ESC skips there.
        match self.config.skip_key.as_str() {
            "any" if !needs_input => return IntroAction::Skip,
            "any" if needs_input && key.code == KeyCode::Esc => return IntroAction::Skip,
            "esc" => {
                if key.code == KeyCode::Esc {
                    return IntroAction::Skip;
                }
            }
            // "none" or any unrecognised value: no global skip
            _ => {}
        }

        // Delegate to active screen.
        let action = match &mut self.state {
            IntroState::Typewriter(s) => s.handle_input(key),
            IntroState::Prompt(s) => s.handle_input(key),
            IntroState::Rain(s) => s.handle_input(key),
            IntroState::Logo(s) => s.handle_input(key),
            IntroState::Done | IntroState::Exit => IntroAction::Continue,
        };

        match action {
            IntroAction::NextScreen => {
                self.advance();
                action
            }
            IntroAction::Exit => {
                self.state = IntroState::Exit;
                action
            }
            _ => action,
        }
    }

    /// Render the current screen into the given frame.
    pub fn render(&self, frame: &mut ratatui::Frame) {
        match &self.state {
            IntroState::Typewriter(s) => s.render(frame),
            IntroState::Prompt(s) => s.render(frame),
            IntroState::Rain(s) => s.render(frame),
            IntroState::Logo(s) => s.render(frame),
            IntroState::Done | IntroState::Exit => {}
        }
    }

    /// Transition to the next screen in the linear sequence:
    /// Typewriter -> Prompt -> Rain -> Logo -> Done.
    pub fn advance(&mut self) {
        self.state = match &self.state {
            IntroState::Typewriter(_) => {
                IntroState::Prompt(prompt::PromptState::new(&self.config, &self.theme, self.layout))
            }
            IntroState::Prompt(_) => {
                IntroState::Rain(rain::RainState::new(
                    &self.config,
                    &self.theme,
                    self.layout,
                    self.width,
                    self.height,
                ))
            }
            IntroState::Rain(_) => {
                IntroState::Logo(logo::LogoState::new(&self.config, &self.theme, self.layout))
            }
            IntroState::Logo(_) => IntroState::Done,
            IntroState::Done => IntroState::Done,
            IntroState::Exit => IntroState::Exit,
        };
    }

    /// Returns `true` when the intro has finished (either completed or exited).
    pub fn is_done(&self) -> bool {
        matches!(self.state, IntroState::Done | IntroState::Exit)
    }

    /// Returns the final result of the intro sequence. Should only be called
    /// once [`is_done`](Self::is_done) returns `true`.
    pub fn result(&self) -> IntroResult {
        match self.state {
            IntroState::Exit => IntroResult::Exit,
            _ => IntroResult::Dashboard,
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers};

    /// Helper: create a default IntroSequence with standard config.
    fn make_seq() -> IntroSequence {
        let config = IntroConfig::default();
        let theme = crate::theme::phosphor_theme();
        IntroSequence::new(config, theme, 120, 40)
    }

    /// Helper: create a KeyEvent for a given KeyCode.
    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent {
            code,
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        }
    }

    // -- State transitions ------------------------------------------------

    #[test]
    fn starts_in_typewriter() {
        let seq = make_seq();
        assert!(matches!(seq.state, IntroState::Typewriter(_)));
    }

    #[test]
    fn advances_typewriter_to_prompt() {
        let mut seq = make_seq();
        seq.advance();
        assert!(matches!(seq.state, IntroState::Prompt(_)));
    }

    #[test]
    fn advances_prompt_to_rain() {
        let mut seq = make_seq();
        seq.advance(); // -> Prompt
        seq.advance(); // -> Rain
        assert!(matches!(seq.state, IntroState::Rain(_)));
    }

    #[test]
    fn advances_rain_to_logo() {
        let mut seq = make_seq();
        seq.advance(); // -> Prompt
        seq.advance(); // -> Rain
        seq.advance(); // -> Logo
        assert!(matches!(seq.state, IntroState::Logo(_)));
    }

    #[test]
    fn advances_logo_to_done() {
        let mut seq = make_seq();
        seq.advance(); // -> Prompt
        seq.advance(); // -> Rain
        seq.advance(); // -> Logo
        seq.advance(); // -> Done
        assert!(matches!(seq.state, IntroState::Done));
    }

    #[test]
    fn full_state_transition_sequence() {
        let mut seq = make_seq();
        assert!(matches!(seq.state, IntroState::Typewriter(_)));
        seq.advance();
        assert!(matches!(seq.state, IntroState::Prompt(_)));
        seq.advance();
        assert!(matches!(seq.state, IntroState::Rain(_)));
        seq.advance();
        assert!(matches!(seq.state, IntroState::Logo(_)));
        seq.advance();
        assert!(matches!(seq.state, IntroState::Done));
    }

    #[test]
    fn done_stays_done_on_advance() {
        let mut seq = make_seq();
        // Advance through everything.
        for _ in 0..4 {
            seq.advance();
        }
        assert!(matches!(seq.state, IntroState::Done));
        seq.advance();
        assert!(matches!(seq.state, IntroState::Done));
    }

    #[test]
    fn exit_stays_exit_on_advance() {
        let mut seq = make_seq();
        seq.state = IntroState::Exit;
        seq.advance();
        assert!(matches!(seq.state, IntroState::Exit));
    }

    // -- tick drives advance ----------------------------------------------

    #[test]
    fn tick_returns_continue_for_realtime_screens() {
        let mut seq = make_seq();
        // Typewriter and Prompt are real implementations with timer-based
        // transitions. The first tick returns Continue (not NextScreen)
        // because the typewriter animation has just started.
        let action = seq.tick();
        assert_eq!(action, IntroAction::Continue);
        assert!(matches!(seq.state, IntroState::Typewriter(_)));

        // Advancing manually exercises the state machine transitions.
        seq.advance(); // -> Prompt
        assert!(matches!(seq.state, IntroState::Prompt(_)));

        // Prompt first tick transitions ShowingQuestion -> WaitingForInput.
        let action = seq.tick();
        assert_eq!(action, IntroAction::Continue);
        assert!(matches!(seq.state, IntroState::Prompt(_)));

        seq.advance(); // -> Rain
        assert!(matches!(seq.state, IntroState::Rain(_)));

        seq.advance(); // -> Logo
        assert!(matches!(seq.state, IntroState::Logo(_)));

        seq.advance(); // -> Done
        assert!(matches!(seq.state, IntroState::Done));
    }

    // -- ESC / skip_key handling ------------------------------------------

    #[test]
    fn esc_returns_skip_with_default_config() {
        // Default skip_key is "any", so any key returns Skip.
        let mut seq = make_seq();
        let action = seq.handle_input(key(KeyCode::Esc));
        assert_eq!(action, IntroAction::Skip);
    }

    #[test]
    fn any_key_returns_skip_with_default_config() {
        let mut seq = make_seq();
        let action = seq.handle_input(key(KeyCode::Char('x')));
        assert_eq!(action, IntroAction::Skip);
    }

    #[test]
    fn skip_key_esc_only_skips_on_esc() {
        let config = IntroConfig {
            skip_key: "esc".to_string(),
            ..IntroConfig::default()
        };
        let theme = crate::theme::phosphor_theme();
        let mut seq = IntroSequence::new(config, theme, 120, 40);

        // ESC should skip.
        let action = seq.handle_input(key(KeyCode::Esc));
        assert_eq!(action, IntroAction::Skip);
    }

    #[test]
    fn skip_key_esc_does_not_skip_on_other_keys() {
        let config = IntroConfig {
            skip_key: "esc".to_string(),
            ..IntroConfig::default()
        };
        let theme = crate::theme::phosphor_theme();
        let mut seq = IntroSequence::new(config, theme, 120, 40);

        // Non-ESC key should delegate to screen (stub returns Continue).
        let action = seq.handle_input(key(KeyCode::Char('a')));
        assert_eq!(action, IntroAction::Continue);
    }

    #[test]
    fn skip_key_none_ignores_esc() {
        let config = IntroConfig {
            skip_key: "none".to_string(),
            ..IntroConfig::default()
        };
        let theme = crate::theme::phosphor_theme();
        let mut seq = IntroSequence::new(config, theme, 120, 40);

        // ESC should NOT skip.
        let action = seq.handle_input(key(KeyCode::Esc));
        assert_eq!(action, IntroAction::Continue);
    }

    #[test]
    fn skip_key_none_ignores_all_keys() {
        let config = IntroConfig {
            skip_key: "none".to_string(),
            ..IntroConfig::default()
        };
        let theme = crate::theme::phosphor_theme();
        let mut seq = IntroSequence::new(config, theme, 120, 40);

        let action = seq.handle_input(key(KeyCode::Char('y')));
        assert_eq!(action, IntroAction::Continue);
    }

    // -- is_done() --------------------------------------------------------

    #[test]
    fn is_done_false_during_screens() {
        let seq = make_seq();
        assert!(!seq.is_done());
    }

    #[test]
    fn is_done_true_when_done() {
        let mut seq = make_seq();
        for _ in 0..4 {
            seq.advance();
        }
        assert!(seq.is_done());
    }

    #[test]
    fn is_done_true_when_exit() {
        let mut seq = make_seq();
        seq.state = IntroState::Exit;
        assert!(seq.is_done());
    }

    #[test]
    fn is_done_false_for_prompt() {
        let mut seq = make_seq();
        seq.advance(); // -> Prompt
        assert!(!seq.is_done());
    }

    #[test]
    fn is_done_false_for_rain() {
        let mut seq = make_seq();
        seq.advance(); // -> Prompt
        seq.advance(); // -> Rain
        assert!(!seq.is_done());
    }

    #[test]
    fn is_done_false_for_logo() {
        let mut seq = make_seq();
        seq.advance(); // -> Prompt
        seq.advance(); // -> Rain
        seq.advance(); // -> Logo
        assert!(!seq.is_done());
    }

    // -- result() ---------------------------------------------------------

    #[test]
    fn result_dashboard_when_done() {
        let mut seq = make_seq();
        for _ in 0..4 {
            seq.advance();
        }
        assert_eq!(seq.result(), IntroResult::Dashboard);
    }

    #[test]
    fn result_exit_when_exit() {
        let mut seq = make_seq();
        seq.state = IntroState::Exit;
        assert_eq!(seq.result(), IntroResult::Exit);
    }

    #[test]
    fn result_dashboard_when_still_running() {
        // Even mid-sequence, result() returns Dashboard (not Exit).
        let seq = make_seq();
        assert_eq!(seq.result(), IntroResult::Dashboard);
    }

    // -- Layout detection in constructor ----------------------------------

    #[test]
    fn constructor_detects_full_layout() {
        let config = IntroConfig::default();
        let theme = crate::theme::phosphor_theme();
        let seq = IntroSequence::new(config, theme, 120, 40);
        assert_eq!(seq.layout, LayoutMode::Full);
    }

    #[test]
    fn constructor_detects_compact_layout() {
        let config = IntroConfig::default();
        let theme = crate::theme::phosphor_theme();
        let seq = IntroSequence::new(config, theme, 80, 24);
        assert_eq!(seq.layout, LayoutMode::Compact);
    }

    #[test]
    fn constructor_detects_minimal_layout() {
        let config = IntroConfig::default();
        let theme = crate::theme::phosphor_theme();
        let seq = IntroSequence::new(config, theme, 60, 20);
        assert_eq!(seq.layout, LayoutMode::Minimal);
    }
}

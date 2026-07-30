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

use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyModifiers};

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

    /// Returns `true` for the universal terminal interrupt, Ctrl+C.
    ///
    /// Raw mode suppresses SIGINT, so crossterm hands us the interrupt as an
    /// ordinary key event and it is on us to honour it. Some terminals report
    /// Ctrl+Shift+C as CONTROL|SHIFT plus an uppercase 'C', so accept both
    /// cases.
    fn is_interrupt(key: &KeyEvent) -> bool {
        key.modifiers.contains(KeyModifiers::CONTROL)
            && matches!(key.code, KeyCode::Char('c') | KeyCode::Char('C'))
    }

    /// Handle a key event.
    ///
    /// Order of handling, and why:
    /// 1. Non-press events (key release / auto-repeat) are dropped. Terminals
    ///    that implement the kitty keyboard protocol — and Windows Terminal —
    ///    report both press and release, which would otherwise make every
    ///    keystroke count twice.
    /// 2. Ctrl+C aborts, ahead of everything else, so the interrupt works on
    ///    every screen of the animation and under every `skip_key` setting.
    /// 3. The global skip-key check runs (respecting `config.skip_key`).
    /// 4. Otherwise the event is delegated to the active screen.
    ///
    /// The Prompt screen is exempt from `skip_key = "any"` because it needs
    /// keyboard input for Y/N and easter eggs. ESC still works as skip there.
    ///
    /// This is the single choke point through which every key event reaches
    /// every screen state, so filtering here covers the whole intro.
    pub fn handle_input(&mut self, key: KeyEvent) -> IntroAction {
        // 1. Only key presses are input. Ignore Release and Repeat.
        if key.kind != KeyEventKind::Press {
            return IntroAction::Continue;
        }

        // 2. Ctrl+C interrupts the entire sequence, whatever the screen or
        //    the skip_key config says.
        if Self::is_interrupt(&key) {
            self.state = IntroState::Exit;
            return IntroAction::Exit;
        }

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

    /// Helper: Ctrl+C as crossterm delivers it in raw mode.
    fn ctrl_c() -> KeyEvent {
        KeyEvent {
            code: KeyCode::Char('c'),
            modifiers: KeyModifiers::CONTROL,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        }
    }

    /// Helper: a key *release* event (emitted by Windows Terminal and by
    /// terminals with the kitty keyboard protocol enabled).
    fn key_release(code: KeyCode) -> KeyEvent {
        KeyEvent {
            code,
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Release,
            state: KeyEventState::NONE,
        }
    }

    /// Helper: build a sequence with an explicit skip_key setting.
    fn seq_with_skip_key(skip_key: &str) -> IntroSequence {
        let config = IntroConfig {
            skip_key: skip_key.to_string(),
            ..IntroConfig::default()
        };
        IntroSequence::new(config, crate::theme::phosphor_theme(), 120, 40)
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

    // -- Ctrl+C interrupt (LOW-1) -----------------------------------------

    /// Ctrl+C must abort from every screen of the animation, not just one
    /// phase. Raw mode suppresses SIGINT, so the sequence has to honour it.
    #[test]
    fn ctrl_c_exits_from_every_screen() {
        for screens_to_advance in 0..4 {
            let mut seq = seq_with_skip_key("none");
            for _ in 0..screens_to_advance {
                seq.advance();
            }
            let action = seq.handle_input(ctrl_c());
            assert_eq!(
                action,
                IntroAction::Exit,
                "Ctrl+C should exit after {screens_to_advance} advance(s)"
            );
            assert!(seq.is_done(), "Ctrl+C should end the sequence");
            assert_eq!(seq.result(), IntroResult::Exit);
        }
    }

    /// Ctrl+C must win over every skip_key setting — including the default
    /// "any", where it would otherwise be read as "skip into the dashboard",
    /// the opposite of the user's intent.
    #[test]
    fn ctrl_c_exits_under_every_skip_key_setting() {
        for skip_key in ["any", "esc", "none", "bogus"] {
            let mut seq = seq_with_skip_key(skip_key);
            let action = seq.handle_input(ctrl_c());
            assert_eq!(
                action,
                IntroAction::Exit,
                "Ctrl+C should exit with skip_key = {skip_key:?}"
            );
            assert_eq!(seq.result(), IntroResult::Exit);
        }
    }

    /// At the Y/N prompt Ctrl+C must abort rather than being typed into the
    /// input buffer as a literal 'c'.
    #[test]
    fn ctrl_c_at_prompt_exits_instead_of_typing() {
        let mut seq = seq_with_skip_key("none");
        seq.advance(); // -> Prompt
        seq.tick(); // ShowingQuestion -> WaitingForInput

        assert_eq!(seq.handle_input(ctrl_c()), IntroAction::Exit);
        assert!(seq.is_done());
        assert_eq!(seq.result(), IntroResult::Exit);
    }

    /// Ctrl+Shift+C (reported as CONTROL|SHIFT + 'C' by some terminals) is
    /// also an interrupt.
    #[test]
    fn ctrl_shift_c_also_exits() {
        let mut seq = seq_with_skip_key("none");
        let key = KeyEvent {
            code: KeyCode::Char('C'),
            modifiers: KeyModifiers::CONTROL | KeyModifiers::SHIFT,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        };
        assert_eq!(seq.handle_input(key), IntroAction::Exit);
    }

    /// A plain 'c' (no CONTROL) must not be treated as an interrupt.
    #[test]
    fn plain_c_is_not_an_interrupt() {
        let mut seq = seq_with_skip_key("none");
        assert_eq!(seq.handle_input(key(KeyCode::Char('c'))), IntroAction::Continue);
        assert!(!seq.is_done());
    }

    // -- Key release filtering (LOW-2) ------------------------------------

    /// Terminals that report press *and* release must not have each keystroke
    /// counted twice: a release event is not a keypress.
    #[test]
    fn key_release_does_not_trigger_skip() {
        let mut seq = make_seq(); // default skip_key = "any"
        let action = seq.handle_input(key_release(KeyCode::Enter));
        assert_eq!(
            action,
            IntroAction::Continue,
            "the release of the Enter that launched the binary must not skip the intro"
        );
        assert!(!seq.is_done());
    }

    /// Release events must not reach the prompt's input buffer either —
    /// otherwise typing 'n' buffers "nn" and is not recognised as No.
    #[test]
    fn key_release_is_ignored_at_prompt() {
        let mut seq = seq_with_skip_key("none");
        seq.advance(); // -> Prompt
        seq.tick(); // -> WaitingForInput

        // 'n' press + release, then Enter press + release. With releases
        // filtered the buffer holds "n" and the prompt answers No (Exit).
        seq.handle_input(key(KeyCode::Char('n')));
        seq.handle_input(key_release(KeyCode::Char('n')));
        seq.handle_input(key(KeyCode::Enter));
        seq.handle_input(key_release(KeyCode::Enter));

        std::thread::sleep(std::time::Duration::from_millis(1100));
        let mut saw_exit = false;
        for _ in 0..100 {
            if seq.tick() == IntroAction::Exit {
                saw_exit = true;
                break;
            }
        }
        assert!(
            saw_exit,
            "press+release of 'n' + Enter should answer No, not buffer \"nn\""
        );
    }

    /// A release event of Ctrl+C is still just a release — it must not exit.
    #[test]
    fn ctrl_c_release_does_not_exit() {
        let mut seq = seq_with_skip_key("none");
        let key = KeyEvent {
            code: KeyCode::Char('c'),
            modifiers: KeyModifiers::CONTROL,
            kind: KeyEventKind::Release,
            state: KeyEventState::NONE,
        };
        assert_eq!(seq.handle_input(key), IntroAction::Continue);
        assert!(!seq.is_done());
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

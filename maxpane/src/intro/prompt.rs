/// Screen 2 -- "Entscheidung" (Prompt)
///
/// Interactive Y/N prompt: "Do you want to see the chain?"
/// Supports single-char immediate input (y/Y/n/N), multi-char buffered input
/// with Enter, easter eggs (custom + defaults), blinking cursor, and timed
/// response display before transitioning.

use std::time::{Duration, Instant};

use crossterm::event::{KeyCode, KeyEvent};
use ratatui::{
    layout::Rect,
    style::Style,
    text::{Line, Span},
    Frame,
};

use crate::config::{EasterEgg, IntroConfig};
use crate::terminal::LayoutMode;
use crate::theme::IntroTheme;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const QUESTION_TEXT: &str = "> Do you want to enter the Ether?";
const INPUT_PREFIX: &str = "> [Y/N]: ";

const RESPONSE_YES: &str = "LOCKING IN...";
const RESPONSE_NO: &str = "Maybe next time, anon.";
const RESPONSE_DEFAULT: &str = "There is no spoon. Try again.";

const CURSOR_BLINK_MS: u64 = 530;
const RESPONSE_YES_MS: u64 = 800;
const RESPONSE_NO_MS: u64 = 1000;
const RESPONSE_OTHER_MS: u64 = 1000;

/// Default easter eggs. Tuple: (input, response, action).
/// Action: "proceed" = NextScreen, "retry" = reset to WaitingForInput, "exit" = Exit.
const DEFAULT_EGGS: &[(&str, &str, &str)] = &[
    (
        "morpheus",
        "I can only show you the door. You're the one that has to walk through it.",
        "retry",
    ),
    (
        "vitalik",
        "The merge is complete. Are you ready to see what's next?",
        "proceed",
    ),
    ("gm", "gm anon. Let's go.", "proceed"),
    ("wagmi", "We're all gonna make it. Starting up...", "proceed"),
    ("ngmi", "Not with that attitude. Try again.", "retry"),
    (
        "satoshi",
        "Chancellor on brink of second bailout for banks.",
        "proceed",
    ),
];

// ---------------------------------------------------------------------------
// Phase / ResponseAction
// ---------------------------------------------------------------------------

/// What to do after displaying a response message.
#[derive(Debug, Clone, PartialEq)]
enum ResponseAction {
    /// Advance to the next screen.
    Proceed,
    /// Return to the input prompt.
    Retry,
    /// Exit the application.
    Exit,
}

/// Internal phase state machine for the prompt screen.
#[derive(Debug)]
enum Phase {
    /// The question line is being displayed (typewriter or instant).
    ShowingQuestion,
    /// Cursor is blinking, waiting for user input.
    WaitingForInput,
    /// A response message is displayed with a timed pause.
    ShowingResponse(String, ResponseAction),
    /// The screen is finished; carry this action up.
    Done(super::IntroAction),
}

// ---------------------------------------------------------------------------
// PromptState
// ---------------------------------------------------------------------------

pub struct PromptState {
    phase: Phase,
    input_buffer: String,
    cursor_visible: bool,
    cursor_timer: Instant,
    response_timer: Option<Instant>,
    response_duration: Duration,
    /// Custom easter eggs from user config (checked first).
    custom_eggs: Vec<EasterEgg>,
    /// Colors for rendering.
    text_color: ratatui::style::Color,
    cursor_color: ratatui::style::Color,
    bg_color: ratatui::style::Color,
    _layout: LayoutMode,
}

impl PromptState {
    pub fn new(
        config: &IntroConfig,
        theme: &IntroTheme,
        layout: LayoutMode,
    ) -> Self {
        Self {
            phase: Phase::ShowingQuestion,
            input_buffer: String::new(),
            cursor_visible: true,
            cursor_timer: Instant::now(),
            response_timer: None,
            response_duration: Duration::ZERO,
            custom_eggs: config.easter_eggs.clone(),
            text_color: theme.text,
            cursor_color: theme.cursor_color,
            bg_color: theme.background,
            _layout: layout,
        }
    }

    pub fn tick(&mut self) -> super::IntroAction {
        match &self.phase {
            Phase::ShowingQuestion => {
                // Instantly transition to WaitingForInput (question shown all at once).
                self.phase = Phase::WaitingForInput;
                self.cursor_timer = Instant::now();
                super::IntroAction::Continue
            }
            Phase::WaitingForInput => {
                // Update cursor blink.
                if self.cursor_timer.elapsed() >= Duration::from_millis(CURSOR_BLINK_MS) {
                    self.cursor_visible = !self.cursor_visible;
                    self.cursor_timer = Instant::now();
                }
                super::IntroAction::Continue
            }
            Phase::ShowingResponse(_, _) => {
                if let Some(timer) = self.response_timer {
                    if timer.elapsed() >= self.response_duration {
                        // Extract the action before mutating phase.
                        let action = match &self.phase {
                            Phase::ShowingResponse(_, ResponseAction::Proceed) => {
                                super::IntroAction::NextScreen
                            }
                            Phase::ShowingResponse(_, ResponseAction::Exit) => {
                                super::IntroAction::Exit
                            }
                            Phase::ShowingResponse(_, ResponseAction::Retry) => {
                                self.input_buffer.clear();
                                self.phase = Phase::WaitingForInput;
                                self.cursor_visible = true;
                                self.cursor_timer = Instant::now();
                                self.response_timer = None;
                                return super::IntroAction::Continue;
                            }
                            _ => unreachable!(),
                        };
                        self.phase = Phase::Done(action.clone_action());
                        return action;
                    }
                }
                super::IntroAction::Continue
            }
            Phase::Done(action) => action.clone_action(),
        }
    }

    pub fn handle_input(&mut self, key: KeyEvent) -> super::IntroAction {
        // Only accept input during WaitingForInput.
        if !matches!(self.phase, Phase::WaitingForInput) {
            return super::IntroAction::Continue;
        }

        match key.code {
            // y/Y with empty buffer: process immediately without Enter.
            KeyCode::Char('y') | KeyCode::Char('Y') if self.input_buffer.is_empty() => {
                self.show_response(
                    RESPONSE_YES.to_string(),
                    ResponseAction::Proceed,
                    Duration::from_millis(RESPONSE_YES_MS),
                );
                super::IntroAction::Continue
            }
            // n/N: buffer the character (not immediate, to allow easter eggs
            // like "ngmi" that start with 'n'). Handled on Enter instead.
            KeyCode::Char('n') | KeyCode::Char('N') => {
                self.input_buffer.push(match key.code {
                    KeyCode::Char(c) => c,
                    _ => unreachable!(),
                });
                super::IntroAction::Continue
            }
            // Enter: process the buffer contents.
            KeyCode::Enter => {
                if self.input_buffer.is_empty() {
                    // Empty Enter = same as Y.
                    self.show_response(
                        RESPONSE_YES.to_string(),
                        ResponseAction::Proceed,
                        Duration::from_millis(RESPONSE_YES_MS),
                    );
                } else {
                    let input = self.input_buffer.clone();
                    // Check for single-char n/N in buffer (typed after
                    // backspacing, etc.) before easter egg lookup.
                    if input.eq_ignore_ascii_case("n") {
                        self.show_response(
                            RESPONSE_NO.to_string(),
                            ResponseAction::Exit,
                            Duration::from_millis(RESPONSE_NO_MS),
                        );
                    } else if input.eq_ignore_ascii_case("y") {
                        self.show_response(
                            RESPONSE_YES.to_string(),
                            ResponseAction::Proceed,
                            Duration::from_millis(RESPONSE_YES_MS),
                        );
                    } else {
                        let (response, action) = self.lookup_easter_egg(&input);
                        self.show_response(
                            response,
                            action,
                            Duration::from_millis(RESPONSE_OTHER_MS),
                        );
                    }
                }
                super::IntroAction::Continue
            }
            // Backspace: delete last buffered char.
            KeyCode::Backspace => {
                self.input_buffer.pop();
                super::IntroAction::Continue
            }
            // Any other printable char: buffer it.
            KeyCode::Char(c) => {
                self.input_buffer.push(c);
                super::IntroAction::Continue
            }
            _ => super::IntroAction::Continue,
        }
    }

    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();
        let text_style = Style::default().fg(self.text_color).bg(self.bg_color);
        let cursor_style = Style::default().fg(self.cursor_color).bg(self.bg_color);
        let bg_style = Style::default().bg(self.bg_color);

        // Fill entire background first.
        let buf = frame.buffer_mut();
        for y in area.y..area.y + area.height {
            for x in area.x..area.x + area.width {
                buf[(x, y)].set_style(bg_style);
            }
        }

        // Calculate vertical center: question + blank line + input (+ response).
        let total_lines: u16 = match &self.phase {
            Phase::ShowingResponse(_, _) => 5, // question + blank + input + blank + response
            _ => 3, // question + blank + input
        };
        let start_y = area.y + area.height.saturating_sub(total_lines) / 2;

        // Line 1: question
        let question = QUESTION_TEXT;
        let q_x = area.x + area.width.saturating_sub(question.len() as u16) / 2;
        let q_rect = Rect::new(q_x, start_y, question.len() as u16, 1);

        frame.render_widget(
            ratatui::widgets::Paragraph::new(Line::from(Span::styled(
                question,
                text_style,
            ))),
            q_rect,
        );

        // Line 2: blank (gap)
        // Line 3: input line (with cursor or response override).
        let input_y = start_y + 2;

        match &self.phase {
            Phase::ShowingQuestion => {
                // Input line not yet visible.
            }
            Phase::WaitingForInput => {
                let cursor_char = if self.cursor_visible { "_" } else { " " };
                let display = format!("{}{}{}", INPUT_PREFIX, self.input_buffer, cursor_char);
                let x = area.x + area.width.saturating_sub(display.len() as u16) / 2;
                let rect = Rect::new(x, input_y, display.len() as u16, 1);

                // Build spans: prefix + buffer in text style, cursor in cursor style.
                let prefix_and_buf = format!("{}{}", INPUT_PREFIX, self.input_buffer);
                let spans = vec![
                    Span::styled(prefix_and_buf, text_style),
                    Span::styled(cursor_char, cursor_style),
                ];
                frame.render_widget(
                    ratatui::widgets::Paragraph::new(Line::from(spans)),
                    rect,
                );
            }
            Phase::ShowingResponse(response, _) => {
                // Show the input line frozen (no cursor).
                let frozen_input = format!("{}{}", INPUT_PREFIX, self.input_buffer);
                let x = area
                    .x
                    + area.width.saturating_sub(frozen_input.len() as u16) / 2;
                let rect = Rect::new(x, input_y, frozen_input.len() as u16, 1);
                frame.render_widget(
                    ratatui::widgets::Paragraph::new(Line::from(Span::styled(
                        frozen_input,
                        text_style,
                    ))),
                    rect,
                );

                // Response text below input with blank line gap.
                let resp_y = input_y + 2;
                let rx = area
                    .x
                    + area.width.saturating_sub(response.len() as u16) / 2;
                let resp_rect = Rect::new(rx, resp_y, response.len() as u16, 1);
                frame.render_widget(
                    ratatui::widgets::Paragraph::new(Line::from(Span::styled(
                        response.as_str(),
                        text_style,
                    ))),
                    resp_rect,
                );
            }
            Phase::Done(_) => {
                // Render nothing extra; the orchestrator will transition.
            }
        }
    }

    // -- Private helpers ----------------------------------------------------

    fn show_response(&mut self, message: String, action: ResponseAction, duration: Duration) {
        self.phase = Phase::ShowingResponse(message, action);
        self.response_timer = Some(Instant::now());
        self.response_duration = duration;
    }

    /// Look up an easter egg by input text. Custom eggs take priority, then
    /// defaults. Returns the response text and the corresponding action.
    fn lookup_easter_egg(&self, input: &str) -> (String, ResponseAction) {
        // Check custom eggs first.
        for egg in &self.custom_eggs {
            if egg.input.eq_ignore_ascii_case(input) {
                return (egg.response.clone(), parse_action(&egg.action));
            }
        }

        // Check default eggs.
        for &(egg_input, response, action) in DEFAULT_EGGS {
            if egg_input.eq_ignore_ascii_case(input) {
                return (response.to_string(), parse_action(action));
            }
        }

        // Unknown input -> default response.
        (RESPONSE_DEFAULT.to_string(), ResponseAction::Retry)
    }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn parse_action(s: &str) -> ResponseAction {
    match s {
        "proceed" => ResponseAction::Proceed,
        "exit" => ResponseAction::Exit,
        _ => ResponseAction::Retry,
    }
}

/// Extension trait so we can "clone" an IntroAction (it doesn't derive Clone).
trait CloneAction {
    fn clone_action(&self) -> Self;
}

impl CloneAction for super::IntroAction {
    fn clone_action(&self) -> Self {
        match self {
            super::IntroAction::Continue => super::IntroAction::Continue,
            super::IntroAction::NextScreen => super::IntroAction::NextScreen,
            super::IntroAction::Skip => super::IntroAction::Skip,
            super::IntroAction::Exit => super::IntroAction::Exit,
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

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent {
            code,
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        }
    }

    fn make_prompt() -> PromptState {
        let config = IntroConfig::default();
        let theme = crate::theme::phosphor_theme();
        PromptState::new(&config, &theme, LayoutMode::Full)
    }

    fn make_prompt_with_custom_eggs(eggs: Vec<EasterEgg>) -> PromptState {
        let config = IntroConfig {
            easter_eggs: eggs,
            ..IntroConfig::default()
        };
        let theme = crate::theme::phosphor_theme();
        PromptState::new(&config, &theme, LayoutMode::Full)
    }

    /// Advance past ShowingQuestion into WaitingForInput.
    fn advance_to_input(state: &mut PromptState) {
        state.tick(); // ShowingQuestion -> WaitingForInput
    }

    /// Tick until we get a non-Continue action, or panic after too many ticks.
    /// Uses a fake "elapsed" approach by directly manipulating the timer.
    fn tick_until_done(state: &mut PromptState) -> super::super::IntroAction {
        // Fast-forward the response timer.
        if let Some(ref mut timer) = state.response_timer {
            // Set the timer to the past so the next tick fires.
            *timer = Instant::now() - state.response_duration - Duration::from_millis(10);
        }
        state.tick()
    }

    // -- Y/Enter -> NextScreen --------------------------------------------

    #[test]
    fn y_lowercase_proceeds() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        let action = state.handle_input(key(KeyCode::Char('y')));
        assert_eq!(action, super::super::IntroAction::Continue); // deferred
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::NextScreen);
    }

    #[test]
    fn y_uppercase_proceeds() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Char('Y')));
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::NextScreen);
    }

    #[test]
    fn enter_empty_buffer_proceeds() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Enter));
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::NextScreen);
    }

    // -- N -> Exit --------------------------------------------------------

    #[test]
    fn n_lowercase_exits() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Char('n')));
        state.handle_input(key(KeyCode::Enter));
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::Exit);
    }

    #[test]
    fn n_uppercase_exits() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Char('N')));
        state.handle_input(key(KeyCode::Enter));
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::Exit);
    }

    // -- Default easter eggs ----------------------------------------------

    #[test]
    fn easter_egg_morpheus() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "morpheus".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        // Should show response and retry.
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert!(msg.contains("show you the door"));
                assert_eq!(*action, ResponseAction::Retry);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::Continue);
        assert!(matches!(state.phase, Phase::WaitingForInput));
    }

    #[test]
    fn easter_egg_vitalik() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "vitalik".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert!(msg.contains("merge is complete"));
                assert_eq!(*action, ResponseAction::Proceed);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::NextScreen);
    }

    #[test]
    fn easter_egg_gm() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "gm".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert!(msg.contains("gm anon"));
                assert_eq!(*action, ResponseAction::Proceed);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
    }

    #[test]
    fn easter_egg_wagmi() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "wagmi".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert!(msg.contains("gonna make it"));
                assert_eq!(*action, ResponseAction::Proceed);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
    }

    #[test]
    fn easter_egg_ngmi() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "ngmi".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert!(msg.contains("Not with that attitude"));
                assert_eq!(*action, ResponseAction::Retry);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
    }

    #[test]
    fn easter_egg_satoshi() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "satoshi".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert!(msg.contains("Chancellor"));
                assert_eq!(*action, ResponseAction::Proceed);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
    }

    // -- Custom easter egg priority ---------------------------------------

    #[test]
    fn custom_egg_overrides_default() {
        let custom = vec![EasterEgg {
            input: "gm".to_string(),
            response: "Custom GM response!".to_string(),
            action: "exit".to_string(),
        }];
        let mut state = make_prompt_with_custom_eggs(custom);
        advance_to_input(&mut state);
        for c in "gm".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert_eq!(msg, "Custom GM response!");
                assert_eq!(*action, ResponseAction::Exit);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
    }

    // -- Unknown input -> "There is no spoon" -> retry --------------------

    #[test]
    fn unknown_input_shows_default_response_and_retries() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "foobar".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, action) => {
                assert_eq!(msg, RESPONSE_DEFAULT);
                assert_eq!(*action, ResponseAction::Retry);
            }
            _ => panic!("expected ShowingResponse phase"),
        }
        let result = tick_until_done(&mut state);
        assert_eq!(result, super::super::IntroAction::Continue);
        assert!(matches!(state.phase, Phase::WaitingForInput));
    }

    // -- Case-insensitive matching ----------------------------------------

    #[test]
    fn easter_egg_case_insensitive() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        // Type "MORPHEUS" in uppercase.
        for c in "MORPHEUS".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        state.handle_input(key(KeyCode::Enter));
        match &state.phase {
            Phase::ShowingResponse(msg, _) => {
                assert!(msg.contains("show you the door"));
            }
            _ => panic!("expected ShowingResponse phase"),
        }
    }

    // -- Input during non-WaitingForInput is ignored ----------------------

    #[test]
    fn input_ignored_during_showing_question() {
        let mut state = make_prompt();
        // Still in ShowingQuestion phase.
        let action = state.handle_input(key(KeyCode::Char('y')));
        assert_eq!(action, super::super::IntroAction::Continue);
        // Should still be in ShowingQuestion (not transitioned).
        assert!(matches!(state.phase, Phase::ShowingQuestion));
    }

    #[test]
    fn input_ignored_during_showing_response() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Char('y')));
        // Now in ShowingResponse.
        assert!(matches!(state.phase, Phase::ShowingResponse(_, _)));
        // Further input should be ignored.
        let action = state.handle_input(key(KeyCode::Char('n')));
        assert_eq!(action, super::super::IntroAction::Continue);
    }

    // -- Backspace --------------------------------------------------------

    #[test]
    fn backspace_removes_last_char() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Char('a')));
        state.handle_input(key(KeyCode::Char('b')));
        assert_eq!(state.input_buffer, "ab");
        state.handle_input(key(KeyCode::Backspace));
        assert_eq!(state.input_buffer, "a");
    }

    #[test]
    fn backspace_on_empty_buffer_is_noop() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Backspace));
        assert_eq!(state.input_buffer, "");
    }
}

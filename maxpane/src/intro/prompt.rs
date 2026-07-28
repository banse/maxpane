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
use unicode_width::{UnicodeWidthChar, UnicodeWidthStr};

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

/// Maximum number of characters buffered at the prompt.
///
/// The longest built-in easter egg is 8 characters; 64 leaves generous room
/// for custom eggs from `~/.maxpane/config.toml` while bounding both memory
/// and the amount of text the renderer has to lay out.
const MAX_INPUT_LEN: usize = 64;

/// Appended to the input line once the buffer is full, so a rejected
/// keystroke is visible to the user rather than silently swallowed.
const MAX_INPUT_MARKER: &str = " [max]";

/// Prefixed to the input line when it is too wide for the terminal, so the
/// user can tell the line is scrolled rather than mysteriously short.
const TRUNCATION_MARKER: char = '\u{2026}';

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
                let c = match key.code {
                    KeyCode::Char(c) => c,
                    _ => unreachable!(),
                };
                self.push_input_char(c);
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
                self.push_input_char(c);
                super::IntroAction::Continue
            }
            _ => super::IntroAction::Continue,
        }
    }

    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();
        // Every terminal size is legal input. A zero-dimension area has no
        // cell to write to, so there is nothing to draw.
        if area.width == 0 || area.height == 0 {
            return;
        }

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
        if let Some(q_rect) = centered_line_rect(area, start_y, QUESTION_TEXT) {
            frame.render_widget(
                ratatui::widgets::Paragraph::new(Line::from(Span::styled(
                    QUESTION_TEXT,
                    text_style,
                ))),
                q_rect,
            );
        }

        // Line 2: blank (gap)
        // Line 3: input line (with cursor or response override).
        let input_y = start_y.saturating_add(2);

        match &self.phase {
            Phase::ShowingQuestion => {
                // Input line not yet visible.
            }
            Phase::WaitingForInput => {
                let cursor_char = if self.cursor_visible { "_" } else { " " };
                let marker = if self.input_at_capacity() {
                    MAX_INPUT_MARKER
                } else {
                    ""
                };
                let marker_width = display_width(marker);

                // Reserve columns for the cursor (1) and the capacity marker,
                // then fit the prefix + buffer into whatever is left. Fitting
                // is by display column and on char boundaries, so wide and
                // multi-byte characters are safe.
                let head_budget = area.width.saturating_sub(marker_width + 1);
                let head = fit_line_tail(
                    &format!("{}{}", INPUT_PREFIX, self.input_buffer),
                    head_budget,
                );

                let total_width = display_width(&head) + marker_width + 1;
                if let Some(rect) = centered_rect(area, input_y, total_width) {
                    let mut spans = vec![Span::styled(head, text_style)];
                    if !marker.is_empty() {
                        spans.push(Span::styled(marker, cursor_style));
                    }
                    spans.push(Span::styled(cursor_char, cursor_style));
                    frame.render_widget(
                        ratatui::widgets::Paragraph::new(Line::from(spans)),
                        rect,
                    );
                }
            }
            Phase::ShowingResponse(response, _) => {
                // Show the input line frozen (no cursor).
                let frozen_input = fit_line_tail(
                    &format!("{}{}", INPUT_PREFIX, self.input_buffer),
                    area.width,
                );
                if let Some(rect) = centered_line_rect(area, input_y, &frozen_input) {
                    frame.render_widget(
                        ratatui::widgets::Paragraph::new(Line::from(Span::styled(
                            frozen_input,
                            text_style,
                        ))),
                        rect,
                    );
                }

                // Response text below input with blank line gap.
                let resp_y = input_y.saturating_add(2);
                if let Some(resp_rect) = centered_line_rect(area, resp_y, response) {
                    frame.render_widget(
                        ratatui::widgets::Paragraph::new(Line::from(Span::styled(
                            response.as_str(),
                            text_style,
                        ))),
                        resp_rect,
                    );
                }
            }
            Phase::Done(_) => {
                // Render nothing extra; the orchestrator will transition.
            }
        }
    }

    // -- Private helpers ----------------------------------------------------

    /// True once the input buffer has reached [`MAX_INPUT_LEN`] characters.
    fn input_at_capacity(&self) -> bool {
        self.input_buffer.chars().count() >= MAX_INPUT_LEN
    }

    /// Buffer a printable character, dropping it when the buffer is full.
    ///
    /// A dropped keystroke is not silent: [`render`](Self::render) draws
    /// [`MAX_INPUT_MARKER`] on the input line while the buffer is at capacity.
    fn push_input_char(&mut self, c: char) {
        if self.input_at_capacity() {
            return;
        }
        self.input_buffer.push(c);
    }

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

/// Display width of `text` in terminal columns, saturated to `u16`.
fn display_width(text: &str) -> u16 {
    u16::try_from(UnicodeWidthStr::width(text)).unwrap_or(u16::MAX)
}

/// Horizontally centered single-row `Rect` at row `y`, clamped to `area`.
///
/// Returns `None` when the row lies outside `area` or there is no width to
/// draw into. The returned rect never extends past `area`, which is what
/// keeps ratatui's raw buffer indexing in bounds on tiny terminals.
fn centered_rect(area: Rect, y: u16, width: u16) -> Option<Rect> {
    if area.width == 0 || area.height == 0 || width == 0 {
        return None;
    }
    if y < area.y || y >= area.y.saturating_add(area.height) {
        return None;
    }
    let w = width.min(area.width);
    let x = area.x + (area.width - w) / 2;
    Some(Rect::new(x, y, w, 1))
}

/// [`centered_rect`] sized to the display width of `text`.
fn centered_line_rect(area: Rect, y: u16, text: &str) -> Option<Rect> {
    centered_rect(area, y, display_width(text))
}

/// Fit `text` into `max_width` columns, keeping the *tail* visible.
///
/// The input line grows to the right, so the end is the interesting part.
/// When the text does not fit, the visible remainder is prefixed with
/// [`TRUNCATION_MARKER`] so the user can see the line is scrolled rather than
/// wondering where their typing went. Splitting is per character, so
/// multi-byte and double-width characters are never cut in half.
fn fit_line_tail(text: &str, max_width: u16) -> String {
    let max_width = max_width as usize;
    if max_width == 0 {
        return String::new();
    }
    if UnicodeWidthStr::width(text) <= max_width {
        return text.to_string();
    }

    // Reserve one column for the truncation marker.
    let budget = max_width - 1;
    let mut tail_rev: Vec<char> = Vec::new();
    let mut used = 0usize;
    for ch in text.chars().rev() {
        let w = UnicodeWidthChar::width(ch).unwrap_or(0);
        if used + w > budget {
            break;
        }
        tail_rev.push(ch);
        used += w;
    }

    let mut out = String::with_capacity(text.len());
    out.push(TRUNCATION_MARKER);
    out.extend(tail_rev.into_iter().rev());
    out
}

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

    // -- Tiny terminals (MEDI-2) ------------------------------------------

    use ratatui::{backend::TestBackend, Terminal};

    /// Render `state` on a `w x h` terminal and return the flattened buffer
    /// contents as one string per row.
    fn render_rows(state: &PromptState, w: u16, h: u16) -> Vec<String> {
        let mut terminal = Terminal::new(TestBackend::new(w, h)).unwrap();
        terminal.draw(|frame| state.render(frame)).unwrap();
        let buf = terminal.backend().buffer().clone();
        (0..h)
            .map(|y| (0..w).map(|x| buf[(x, y)].symbol()).collect::<String>())
            .collect()
    }

    #[test]
    fn render_survives_terminal_narrower_than_question() {
        // QUESTION_TEXT is 33 columns; 25 columns must not panic.
        let mut state = make_prompt();
        advance_to_input(&mut state);
        render_rows(&state, 25, 10);
    }

    #[test]
    fn render_survives_one_column_terminal() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        render_rows(&state, 1, 1);
    }

    #[test]
    fn render_survives_one_row_terminal() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        render_rows(&state, 80, 1);
    }

    #[test]
    fn render_response_survives_short_terminal() {
        // ShowingResponse needs 5 rows; a 4-row terminal must not panic.
        let mut state = make_prompt();
        advance_to_input(&mut state);
        state.handle_input(key(KeyCode::Char('y')));
        assert!(matches!(state.phase, Phase::ShowingResponse(_, _)));
        render_rows(&state, 40, 4);
        render_rows(&state, 40, 2);
        render_rows(&state, 20, 10);
    }

    #[test]
    fn render_survives_every_size_in_a_sweep() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "morpheus".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        for w in 1..=40u16 {
            for h in 1..=8u16 {
                render_rows(&state, w, h);
            }
        }
    }

    // -- Unbounded input (MEDI-3) -----------------------------------------

    #[test]
    fn input_buffer_is_capped() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..500 {
            state.handle_input(key(KeyCode::Char('x')));
        }
        assert_eq!(state.input_buffer.chars().count(), MAX_INPUT_LEN);
    }

    #[test]
    fn n_char_also_respects_the_cap() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..500 {
            state.handle_input(key(KeyCode::Char('n')));
        }
        assert_eq!(state.input_buffer.chars().count(), MAX_INPUT_LEN);
    }

    #[test]
    fn backspace_reopens_capacity() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..MAX_INPUT_LEN + 10 {
            state.handle_input(key(KeyCode::Char('x')));
        }
        state.handle_input(key(KeyCode::Backspace));
        state.handle_input(key(KeyCode::Char('z')));
        assert_eq!(state.input_buffer.chars().count(), MAX_INPUT_LEN);
        assert!(state.input_buffer.ends_with('z'));
    }

    #[test]
    fn full_buffer_shows_a_visible_capacity_marker() {
        // A rejected keystroke must be visible, not silently swallowed.
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..MAX_INPUT_LEN + 5 {
            state.handle_input(key(KeyCode::Char('x')));
        }
        let rows = render_rows(&state, 120, 10);
        assert!(
            rows.iter().any(|r| r.contains(MAX_INPUT_MARKER.trim())),
            "expected capacity marker in rendered output, got: {rows:?}"
        );
    }

    #[test]
    fn overlong_input_is_visibly_truncated_not_silently_clipped() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for c in "abcdefghijklmnopqrstuvwxyz0123456789".chars() {
            state.handle_input(key(KeyCode::Char(c)));
        }
        // 40 columns cannot hold the 9-col prefix + 36 chars + cursor.
        let rows = render_rows(&state, 40, 24);
        let input_row = rows
            .iter()
            .find(|r| r.contains(TRUNCATION_MARKER))
            .unwrap_or_else(|| panic!("expected truncation marker, got: {rows:?}"));
        // The tail — where the user is typing — must stay visible.
        assert!(
            input_row.contains("6789"),
            "expected the tail of the input to remain visible, got: {input_row:?}"
        );
    }

    #[test]
    fn full_line_that_exactly_fits_is_not_truncated() {
        // prefix(9) + MAX_INPUT_LEN(64) + marker(6) + cursor(1) == 80.
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..MAX_INPUT_LEN {
            state.handle_input(key(KeyCode::Char('x')));
        }
        let rows = render_rows(&state, 80, 24);
        assert!(
            rows.iter().all(|r| !r.contains(TRUNCATION_MARKER)),
            "line fits exactly and must not be truncated, got: {rows:?}"
        );
    }

    // -- fit_line_tail unit behaviour -------------------------------------

    #[test]
    fn fit_line_tail_passes_through_when_it_fits() {
        assert_eq!(fit_line_tail("abc", 3), "abc");
        assert_eq!(fit_line_tail("abc", 10), "abc");
        assert_eq!(fit_line_tail("", 5), "");
    }

    #[test]
    fn fit_line_tail_keeps_the_tail_and_marks_the_cut() {
        assert_eq!(fit_line_tail("abcdef", 4), "\u{2026}def");
        assert_eq!(fit_line_tail("abcdef", 1), "\u{2026}");
        assert_eq!(fit_line_tail("abcdef", 0), "");
    }

    #[test]
    fn fit_line_tail_never_splits_a_wide_char() {
        // '世' is 2 columns wide. With a 4-column budget the marker takes 1,
        // leaving 3 -> only one full '世' fits; it must not be halved.
        let out = fit_line_tail("\u{4e16}\u{4e16}\u{4e16}", 4);
        assert_eq!(out, "\u{2026}\u{4e16}");
        assert!(UnicodeWidthStr::width(out.as_str()) <= 4);
    }

    #[test]
    fn fit_line_tail_output_never_exceeds_budget() {
        let text = "> [Y/N]: \u{4e16}a\u{20ac}b\u{4e16}c\u{20ac}defgh";
        for w in 0..=30u16 {
            let out = fit_line_tail(text, w);
            assert!(
                UnicodeWidthStr::width(out.as_str()) <= w as usize,
                "width {w}: {out:?} is too wide"
            );
        }
    }

    #[test]
    fn render_survives_overlong_input_on_standard_terminal() {
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..200 {
            state.handle_input(key(KeyCode::Char('x')));
        }
        render_rows(&state, 80, 24);
    }

    #[test]
    fn render_survives_multibyte_input() {
        // Wide/multi-byte chars must not blow the byte-vs-column arithmetic
        // nor split a char boundary during truncation.
        let mut state = make_prompt();
        advance_to_input(&mut state);
        for _ in 0..40 {
            state.handle_input(key(KeyCode::Char('世')));
            state.handle_input(key(KeyCode::Char('€')));
        }
        render_rows(&state, 80, 24);
        render_rows(&state, 12, 6);
        render_rows(&state, 2, 3);
    }
}

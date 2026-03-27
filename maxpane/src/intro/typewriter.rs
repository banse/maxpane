/// Screen 1 — "Stille" (Typewriter)
///
/// Character-by-character text reveal inspired by the Matrix "Wake up, Neo..."
/// scene. Four lines of text appear one character at a time with configurable
/// speed, dramatic ellipsis pacing, and a blinking cursor.

use std::time::{Duration, Instant};

use crossterm::event::KeyEvent;
use ratatui::{
    style::Style,
    text::{Line, Span},
    Frame,
};

use crate::config::IntroConfig;
use crate::terminal::LayoutMode;
use crate::theme::IntroTheme;

use super::IntroAction;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const LINES: &[&str] = &[
    "Wake up, Anon...",
    "The Ether has you...",
    "Follow the white rabbit.",
    "Lock in, Anon.",
];

/// Cursor character: LEFT HALF BLOCK (U+258C).
const CURSOR_CHAR: char = '\u{258C}';

/// Default inter-line pause in milliseconds.
const DEFAULT_LINE_PAUSE_MS: u64 = 1200;

/// Cursor blink interval in milliseconds.
const CURSOR_BLINK_MS: u64 = 530;

/// Final pause after last line completes, in milliseconds.
const FINAL_PAUSE_MS: u64 = 1500;

/// Ellipsis characters are rendered at this multiplier of the base speed.
const ELLIPSIS_SPEED_MULTIPLIER: u64 = 2;

// ---------------------------------------------------------------------------
// TypewriterPhase
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum TypewriterPhase {
    /// Currently revealing characters in a line.
    Typing,
    /// Line complete, text stays visible for a beat.
    LineHold,
    /// Black screen between lines.
    LinePause,
    /// All lines done; holding for the final dramatic pause.
    FinalPause,
    /// Ready to transition to the next screen.
    Done,
}

// ---------------------------------------------------------------------------
// TypewriterState
// ---------------------------------------------------------------------------

pub struct TypewriterState {
    /// The lines of text to display.
    lines: Vec<String>,
    /// Index of the line currently being typed.
    current_line: usize,
    /// Number of characters revealed so far in the current line.
    current_char: usize,
    /// Phase of the typewriter state machine.
    phase: TypewriterPhase,

    // Timing ---
    /// Base speed: milliseconds per character.
    speed_ms: u64,
    /// Pause between lines in milliseconds.
    line_pause_ms: u64,
    /// When the last character was revealed (or typing started).
    char_timer: Instant,
    /// Set when entering LinePause or FinalPause; tracks pause start.
    pause_timer: Option<Instant>,
    /// Tracks cursor blink toggling.
    cursor_timer: Instant,
    /// Whether the cursor is currently visible.
    cursor_visible: bool,

    // Theme ---
    text_style: Style,
    cursor_style: Style,
    bg_style: Style,

    // Layout ---
    _layout: LayoutMode,
}

impl TypewriterState {
    pub fn new(
        config: &IntroConfig,
        theme: &IntroTheme,
        layout: LayoutMode,
    ) -> Self {
        let now = Instant::now();
        Self {
            lines: LINES.iter().map(|s| s.to_string()).collect(),
            current_line: 0,
            current_char: 0,
            phase: TypewriterPhase::Typing,
            speed_ms: config.typewriter_speed_ms,
            line_pause_ms: DEFAULT_LINE_PAUSE_MS,
            char_timer: now,
            pause_timer: None,
            cursor_timer: now,
            cursor_visible: true,
            text_style: Style::default().fg(theme.text),
            cursor_style: Style::default().fg(theme.cursor_color),
            bg_style: Style::default().bg(theme.background),
            _layout: layout,
        }
    }

    /// Advance the typewriter animation by one tick.
    ///
    /// Returns `IntroAction::NextScreen` once all text has been displayed and
    /// the final pause has elapsed. Otherwise returns `IntroAction::Continue`.
    pub fn tick(&mut self) -> IntroAction {
        let now = Instant::now();

        // Update cursor blink state.
        if now.duration_since(self.cursor_timer) >= Duration::from_millis(CURSOR_BLINK_MS) {
            self.cursor_visible = !self.cursor_visible;
            self.cursor_timer = now;
        }

        match self.phase {
            TypewriterPhase::Typing => {
                self.tick_typing(now);
            }
            TypewriterPhase::LineHold => {
                // Text stays visible for the same duration as the black pause.
                if let Some(start) = self.pause_timer {
                    if now.duration_since(start) >= Duration::from_millis(self.line_pause_ms) {
                        if self.current_line >= self.lines.len() - 1 {
                            // Last line: go to final black pause.
                            self.phase = TypewriterPhase::FinalPause;
                        } else {
                            self.phase = TypewriterPhase::LinePause;
                        }
                        self.pause_timer = Some(now);
                    }
                }
            }
            TypewriterPhase::LinePause => {
                // Black screen between lines.
                if let Some(start) = self.pause_timer {
                    if now.duration_since(start) >= Duration::from_millis(self.line_pause_ms) {
                        // Move to next line.
                        self.current_line += 1;
                        self.current_char = 0;
                        self.phase = TypewriterPhase::Typing;
                        self.char_timer = now;
                        self.pause_timer = None;
                    }
                }
            }
            TypewriterPhase::FinalPause => {
                if let Some(start) = self.pause_timer {
                    if now.duration_since(start) >= Duration::from_millis(FINAL_PAUSE_MS) {
                        self.phase = TypewriterPhase::Done;
                    }
                }
            }
            TypewriterPhase::Done => {
                return IntroAction::NextScreen;
            }
        }

        IntroAction::Continue
    }

    /// Input is not handled by the typewriter screen (skip is handled by
    /// the orchestrator). Always returns `IntroAction::Continue`.
    pub fn handle_input(&mut self, _key: KeyEvent) -> IntroAction {
        IntroAction::Continue
    }

    /// Render the typewriter text into the given frame.
    ///
    /// Matrix-style: only the current line is shown, centered in the middle
    /// of the screen. Each line replaces the previous one.
    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();

        // Fill background.
        let buf = frame.buffer_mut();
        for y in area.y..area.y + area.height {
            for x in area.x..area.x + area.width {
                buf[(x, y)].set_style(self.bg_style);
            }
        }

        // Black screen during LinePause, FinalPause, and Done.
        if matches!(
            self.phase,
            TypewriterPhase::LinePause | TypewriterPhase::FinalPause | TypewriterPhase::Done
        ) {
            return;
        }

        // Only show the current line, centered on screen.
        if self.current_line >= self.lines.len() {
            return;
        }

        let line_text = &self.lines[self.current_line];

        // During LineHold, show the full line. During Typing, show partial.
        let visible_text = if self.phase == TypewriterPhase::LineHold {
            line_text.as_str()
        } else {
            let byte_end = char_to_byte_index(line_text, self.current_char);
            &line_text[..byte_end]
        };

        // Center horizontally (based on full line width for stable positioning)
        let full_width = line_text.len() as u16;
        let start_x = area.x + area.width.saturating_sub(full_width) / 2;
        // Center vertically
        let row = area.y + area.height / 2;

        // Build spans
        let mut spans = vec![Span::styled(visible_text.to_string(), self.text_style)];

        // Blinking cursor (only during Typing phase)
        if self.phase == TypewriterPhase::Typing && self.cursor_visible {
            spans.push(Span::styled(
                CURSOR_CHAR.to_string(),
                self.cursor_style,
            ));
        }

        let paragraph_line = Line::from(spans);
        let line_area = ratatui::layout::Rect {
            x: start_x,
            y: row,
            width: area.width.saturating_sub(start_x - area.x),
            height: 1,
        };

        frame.render_widget(
            ratatui::widgets::Paragraph::new(paragraph_line),
            line_area,
        );
    }

    // -- Private helpers ----------------------------------------------------

    fn tick_typing(&mut self, now: Instant) {
        let line = &self.lines[self.current_line];
        let total_chars = line.chars().count();

        if self.current_char >= total_chars {
            // Line is complete.
            // Hold text visible first, then black pause (for all lines including last).
            self.phase = TypewriterPhase::LineHold;
            self.pause_timer = Some(now);
            return;
        }

        // Determine the delay for the current character.
        let delay = self.delay_for_char(line, self.current_char);

        if now.duration_since(self.char_timer) >= delay {
            self.current_char += 1;
            self.char_timer = now;
        }
    }

    /// Returns the delay duration for revealing the character at index `idx`
    /// within the given line. Ellipsis dots (`'.'` that are part of a trailing
    /// `"..."`) get a slower speed for dramatic effect.
    fn delay_for_char(&self, line: &str, idx: usize) -> Duration {
        if is_ellipsis_char(line, idx) {
            Duration::from_millis(self.speed_ms * ELLIPSIS_SPEED_MULTIPLIER)
        } else {
            Duration::from_millis(self.speed_ms)
        }
    }
}

// ---------------------------------------------------------------------------
// Free helpers
// ---------------------------------------------------------------------------

/// Return the byte offset corresponding to the first `n` chars of `s`.
fn char_to_byte_index(s: &str, n: usize) -> usize {
    s.char_indices()
        .nth(n)
        .map(|(i, _)| i)
        .unwrap_or(s.len())
}

/// Determine whether the character at char-index `idx` in `line` is part of a
/// trailing ellipsis (`"..."`). We consider a `'.'` to be an ellipsis char if
/// it is one of three consecutive dots ending the line (ignoring surrounding
/// whitespace for robustness).
fn is_ellipsis_char(line: &str, idx: usize) -> bool {
    let chars: Vec<char> = line.chars().collect();
    if idx >= chars.len() || chars[idx] != '.' {
        return false;
    }

    // Find the position of the last trailing "..." sequence.
    let trimmed = line.trim_end();
    if !trimmed.ends_with("...") {
        return false;
    }

    // Find the char-index where the "..." starts.
    let trimmed_chars: Vec<char> = trimmed.chars().collect();
    let ellipsis_start = trimmed_chars.len() - 3;

    // The char at `idx` is an ellipsis char if it falls within [ellipsis_start, ellipsis_start+3).
    idx >= ellipsis_start && idx < ellipsis_start + 3
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers};
    use ratatui::{backend::TestBackend, Terminal};

    fn default_config() -> IntroConfig {
        IntroConfig::default()
    }

    fn default_theme() -> crate::theme::IntroTheme {
        crate::theme::phosphor_theme()
    }

    fn key(code: KeyCode) -> KeyEvent {
        KeyEvent {
            code,
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        }
    }

    // -- Construction -----------------------------------------------------

    #[test]
    fn new_starts_in_typing_phase() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        assert_eq!(tw.phase, TypewriterPhase::Typing);
        assert_eq!(tw.current_line, 0);
        assert_eq!(tw.current_char, 0);
    }

    #[test]
    fn new_loads_all_four_lines() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        assert_eq!(tw.lines.len(), 4);
        assert_eq!(tw.lines[0], "Wake up, Anon...");
        assert_eq!(tw.lines[3], "Lock in, Anon.");
    }

    #[test]
    fn new_uses_config_speed() {
        let mut config = default_config();
        config.typewriter_speed_ms = 100;
        let tw = TypewriterState::new(&config, &default_theme(), LayoutMode::Full);
        assert_eq!(tw.speed_ms, 100);
    }

    // -- Phase transitions ------------------------------------------------

    #[test]
    fn typing_transitions_to_line_hold() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        // Simulate having revealed all chars on line 0.
        tw.current_char = tw.lines[0].chars().count();
        tw.char_timer = Instant::now() - Duration::from_secs(1);

        tw.tick();

        assert_eq!(tw.phase, TypewriterPhase::LineHold);
        assert!(tw.pause_timer.is_some());
    }

    #[test]
    fn line_hold_transitions_to_line_pause() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        tw.phase = TypewriterPhase::LineHold;
        tw.pause_timer = Some(Instant::now() - Duration::from_millis(DEFAULT_LINE_PAUSE_MS + 1));

        tw.tick();

        assert_eq!(tw.phase, TypewriterPhase::LinePause);
        assert!(tw.pause_timer.is_some());
    }

    #[test]
    fn line_pause_transitions_to_typing_next_line() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        tw.phase = TypewriterPhase::LinePause;
        tw.current_line = 0;
        // Set the pause timer in the past so it triggers immediately.
        tw.pause_timer = Some(Instant::now() - Duration::from_millis(DEFAULT_LINE_PAUSE_MS + 1));

        tw.tick();

        assert_eq!(tw.phase, TypewriterPhase::Typing);
        assert_eq!(tw.current_line, 1);
        assert_eq!(tw.current_char, 0);
    }

    #[test]
    fn last_line_complete_transitions_to_line_hold() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        tw.current_line = tw.lines.len() - 1;
        tw.current_char = tw.lines.last().unwrap().chars().count();
        tw.char_timer = Instant::now() - Duration::from_secs(1);

        tw.tick();

        // Last line also gets a hold first.
        assert_eq!(tw.phase, TypewriterPhase::LineHold);
    }

    #[test]
    fn last_line_hold_transitions_to_final_pause() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        tw.current_line = tw.lines.len() - 1;
        tw.phase = TypewriterPhase::LineHold;
        tw.pause_timer = Some(Instant::now() - Duration::from_millis(DEFAULT_LINE_PAUSE_MS + 1));

        tw.tick();

        assert_eq!(tw.phase, TypewriterPhase::FinalPause);
    }

    #[test]
    fn final_pause_transitions_to_done() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        tw.phase = TypewriterPhase::FinalPause;
        tw.pause_timer = Some(Instant::now() - Duration::from_millis(FINAL_PAUSE_MS + 1));

        tw.tick();

        assert_eq!(tw.phase, TypewriterPhase::Done);
    }

    #[test]
    fn done_returns_next_screen() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        tw.phase = TypewriterPhase::Done;

        let action = tw.tick();
        assert_eq!(action, IntroAction::NextScreen);
    }

    #[test]
    fn full_phase_sequence() {
        // Typing -> LineHold -> LinePause -> Typing -> ... -> FinalPause -> Done
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);

        for line_idx in 0..LINES.len() {
            assert_eq!(tw.phase, TypewriterPhase::Typing);
            assert_eq!(tw.current_line, line_idx);

            // Fast-forward: reveal all chars.
            tw.current_char = tw.lines[line_idx].chars().count();
            tw.char_timer = Instant::now() - Duration::from_secs(1);
            tw.tick();

            if line_idx < LINES.len() - 1 {
                assert_eq!(tw.phase, TypewriterPhase::LineHold);
                // Fast-forward through hold.
                tw.pause_timer = Some(Instant::now() - Duration::from_millis(DEFAULT_LINE_PAUSE_MS + 1));
                tw.tick();
                assert_eq!(tw.phase, TypewriterPhase::LinePause);
                // Fast-forward through pause.
                tw.pause_timer = Some(Instant::now() - Duration::from_millis(DEFAULT_LINE_PAUSE_MS + 1));
                tw.tick();
            } else {
                // Last line also gets LineHold first.
                assert_eq!(tw.phase, TypewriterPhase::LineHold);
                tw.pause_timer = Some(Instant::now() - Duration::from_millis(DEFAULT_LINE_PAUSE_MS + 1));
                tw.tick();
                assert_eq!(tw.phase, TypewriterPhase::FinalPause);
            }
        }

        // Fast-forward final pause.
        tw.pause_timer = Some(Instant::now() - Duration::from_millis(FINAL_PAUSE_MS + 1));
        tw.tick();
        assert_eq!(tw.phase, TypewriterPhase::Done);

        let action = tw.tick();
        assert_eq!(action, IntroAction::NextScreen);
    }

    // -- Ellipsis detection -----------------------------------------------

    #[test]
    fn ellipsis_chars_detected_in_trailing_dots() {
        let line = "Wake up, anon...";
        let chars: Vec<char> = line.chars().collect();
        // The last 3 chars are '.' (indices 13, 14, 15).
        let dot_start = chars.len() - 3;
        assert!(is_ellipsis_char(line, dot_start));
        assert!(is_ellipsis_char(line, dot_start + 1));
        assert!(is_ellipsis_char(line, dot_start + 2));
    }

    #[test]
    fn non_ellipsis_chars_not_detected() {
        let line = "Wake up, anon...";
        // 'W' at index 0 is not an ellipsis char.
        assert!(!is_ellipsis_char(line, 0));
        // comma at some index.
        assert!(!is_ellipsis_char(line, 4));
    }

    #[test]
    fn no_ellipsis_in_line_without_trailing_dots() {
        let line = "Knock, knock.";
        // The single trailing '.' is not three dots.
        let last_idx = line.chars().count() - 1;
        assert!(!is_ellipsis_char(line, last_idx));
    }

    #[test]
    fn ellipsis_speed_is_double() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        let line = "Wake up, anon...";
        let normal_delay = tw.delay_for_char(line, 0);
        let dot_idx = line.chars().count() - 1;
        let ellipsis_delay = tw.delay_for_char(line, dot_idx);
        assert_eq!(ellipsis_delay, normal_delay * ELLIPSIS_SPEED_MULTIPLIER as u32);
    }

    // -- Cursor blink timing ----------------------------------------------

    #[test]
    fn cursor_starts_visible() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        assert!(tw.cursor_visible);
    }

    #[test]
    fn cursor_toggles_after_blink_interval() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        assert!(tw.cursor_visible);

        // Set cursor_timer in the past so the next tick toggles it.
        tw.cursor_timer = Instant::now() - Duration::from_millis(CURSOR_BLINK_MS + 1);
        tw.tick();
        assert!(!tw.cursor_visible);

        tw.cursor_timer = Instant::now() - Duration::from_millis(CURSOR_BLINK_MS + 1);
        tw.tick();
        assert!(tw.cursor_visible);
    }

    // -- handle_input always returns Continue -----------------------------

    #[test]
    fn handle_input_returns_continue() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        assert_eq!(tw.handle_input(key(KeyCode::Char('a'))), IntroAction::Continue);
        assert_eq!(tw.handle_input(key(KeyCode::Enter)), IntroAction::Continue);
        assert_eq!(tw.handle_input(key(KeyCode::Esc)), IntroAction::Continue);
    }

    // -- Text centering ---------------------------------------------------

    #[test]
    fn text_centered_in_large_terminal() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        let backend = TestBackend::new(120, 40);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal.draw(|frame| tw.render(frame)).unwrap();

        // "Wake up, Anon..." = 16 chars, centered in 120 cols: (120 - 16) / 2 = 52
        let expected_x = (120 - 16) / 2;
        // Single line centered vertically: 40 / 2 = 20
        let expected_y = 40u16 / 2;

        // current_char is 0, so only cursor is visible at start position.
        let buf = terminal.backend().buffer();
        let cell = &buf[(expected_x, expected_y)];
        assert_eq!(cell.symbol(), CURSOR_CHAR.to_string());
    }

    #[test]
    fn text_centered_in_small_terminal() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Minimal);
        let backend = TestBackend::new(60, 20);
        let mut terminal = Terminal::new(backend).unwrap();

        // Should not panic even in a small terminal.
        terminal.draw(|frame| tw.render(frame)).unwrap();
    }

    #[test]
    fn text_centered_in_compact_terminal() {
        let tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Compact);
        let backend = TestBackend::new(80, 24);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal.draw(|frame| tw.render(frame)).unwrap();

        // Single line centered: row = 24 / 2 = 12
        let expected_y = 24u16 / 2;
        // "Wake up, Anon..." = 16 chars; start_x = (80 - 16) / 2 = 32
        let expected_x = (80 - 16) / 2;

        let buf = terminal.backend().buffer();
        let cell = &buf[(expected_x, expected_y)];
        assert_eq!(cell.symbol(), CURSOR_CHAR.to_string());
    }

    #[test]
    fn only_current_line_rendered() {
        let mut tw = TypewriterState::new(&default_config(), &default_theme(), LayoutMode::Full);
        // Move to line 1 (typing phase)
        tw.current_line = 1;
        tw.current_char = 3;
        tw.phase = TypewriterPhase::Typing;

        let backend = TestBackend::new(120, 40);
        let mut terminal = Terminal::new(backend).unwrap();

        terminal.draw(|frame| tw.render(frame)).unwrap();

        let buf = terminal.backend().buffer();
        let row = 40u16 / 2;
        // "The Ether has you..." = 20 chars; start_x = (120 - 20) / 2 = 50
        let start_x = (120u16 - 20) / 2;

        // First 3 chars of line 1 should be rendered: "The"
        assert_eq!(buf[(start_x, row)].symbol(), "T");
        assert_eq!(buf[(start_x + 1, row)].symbol(), "h");
        assert_eq!(buf[(start_x + 2, row)].symbol(), "e");
    }

    // -- char_to_byte_index -----------------------------------------------

    #[test]
    fn char_to_byte_index_ascii() {
        assert_eq!(char_to_byte_index("hello", 0), 0);
        assert_eq!(char_to_byte_index("hello", 3), 3);
        assert_eq!(char_to_byte_index("hello", 5), 5); // past end
    }

    #[test]
    fn char_to_byte_index_past_end() {
        assert_eq!(char_to_byte_index("hi", 10), 2);
    }
}

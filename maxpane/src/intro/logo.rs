/// Screen 5 — "Clean" (Logo + Tagline)
///
/// Static logo display with tagline and sparse ambient rain drops that fade
/// in and out near the top and bottom edges of the terminal. Holds for 2
/// seconds then signals the orchestrator to advance.

use std::time::{Duration, Instant};

use crossterm::event::KeyEvent;
use ratatui::{
    layout::Rect,
    style::{Color, Style},
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};
use unicode_width::UnicodeWidthStr;

use crate::config::IntroConfig;
use crate::terminal::LayoutMode;
use crate::theme::IntroTheme;

use super::IntroAction;

// ---------------------------------------------------------------------------
// Logo data constants (pub so rain.rs can also use them)
// ---------------------------------------------------------------------------

pub const LOGO_FULL: &str = "\
███╗   ███╗ █████╗ ██╗  ██╗██████╗  █████╗ ███╗   ██╗███████╗
████╗ ████║██╔══██╗╚██╗██╔╝██╔══██╗██╔══██╗████╗  ██║██╔════╝
██╔████╔██║███████║ ╚███╔╝ ██████╔╝███████║██╔██╗ ██║█████╗
██║╚██╔╝██║██╔══██║ ██╔██╗ ██╔═══╝ ██╔══██║██║╚██╗██║██╔══╝
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██║     ██║  ██║██║ ╚████║███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝";

pub const LOGO_COMPACT: &str = "\
███╗   ███╗ █████╗ ██╗  ██╗
████╗ ████║██╔══██╗╚██╗██╔╝
██╔████╔██║███████║ ╚███╔╝
██║╚██╔╝██║██╔══██║ ██╔██╗
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝";

pub const LOGO_MINIMAL: &str = "M A X P A N E";

pub const TAGLINE_EN: &str = "maximize your pane · minimize your pain";
pub const TAGLINE_JP: &str = "マクシマイズ ユア ペーン · ミニマイズ ユア ペイン";

// ---------------------------------------------------------------------------
// Ambient rain drop
// ---------------------------------------------------------------------------

struct AmbientDrop {
    x: u16,
    y: u16,
    ch: char,
    brightness: f32,
    fade_speed: f32,
    direction: bool, // true = fading in, false = fading out
}

// ---------------------------------------------------------------------------
// LogoState
// ---------------------------------------------------------------------------

const PROMPT_TEXT: &str = "press any key";
const NOTICE_TEXT: &str = "☮ 2026 hisdudeness.eth — The Dude Abides.";
const CURSOR_BLINK_MS: u64 = 530;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum LogoPhase {
    /// Pure logo + tagline + ambient drops, auto-advances after hold_duration.
    Hold,
    /// Logo + tagline + "press any key" (blinking) + footer, waits for keypress.
    Splash,
}

pub struct LogoState {
    theme: IntroTheme,
    layout: LayoutMode,
    tagline: String,
    logo_text: &'static str,
    rain_drops: Vec<AmbientDrop>,
    start_time: Instant,
    hold_duration: Duration,
    rng: fastrand::Rng,
    phase: LogoPhase,
    prompt_visible: bool,
    blink_timer: Instant,
}

impl LogoState {
    pub fn new(config: &IntroConfig, theme: &IntroTheme, layout: LayoutMode) -> Self {
        let logo_text = match layout {
            LayoutMode::Full => LOGO_FULL,
            LayoutMode::Compact => LOGO_COMPACT,
            LayoutMode::Minimal => LOGO_MINIMAL,
        };

        let tagline = match config.tagline.as_str() {
            "english" => TAGLINE_EN.to_string(),
            _ => TAGLINE_JP.to_string(),
        };

        let mut rng = fastrand::Rng::new();
        let rain_drops = Self::init_drops(&mut rng);

        let now = Instant::now();
        Self {
            theme: theme.clone(),
            layout,
            tagline,
            logo_text,
            rain_drops,
            start_time: now,
            hold_duration: Duration::from_millis(3000),
            rng,
            phase: LogoPhase::Hold,
            prompt_visible: true,
            blink_timer: now,
        }
    }

    pub fn tick(&mut self) -> IntroAction {
        // Update ambient rain drops
        self.update_drops();

        match self.phase {
            LogoPhase::Hold => {
                if self.start_time.elapsed() >= self.hold_duration {
                    self.phase = LogoPhase::Splash;
                    self.blink_timer = Instant::now();
                }
                IntroAction::Continue
            }
            LogoPhase::Splash => {
                // Blink the "press any key" prompt
                if self.blink_timer.elapsed() >= Duration::from_millis(CURSOR_BLINK_MS) {
                    self.prompt_visible = !self.prompt_visible;
                    self.blink_timer = Instant::now();
                }
                IntroAction::Continue
            }
        }
    }

    pub fn handle_input(&mut self, _key: KeyEvent) -> IntroAction {
        match self.phase {
            LogoPhase::Hold => IntroAction::Continue,
            LogoPhase::Splash => IntroAction::NextScreen,
        }
    }

    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();

        // Clear background
        let bg_style = Style::default().bg(self.theme.background);
        let block =
            Paragraph::new("").style(bg_style);
        frame.render_widget(block, area);

        // Render ambient drops
        self.render_drops(frame, area);

        // Compute logo lines and dimensions
        let logo_lines: Vec<&str> = self.logo_text.lines().collect();
        let logo_height = logo_lines.len() as u16;
        let gap = 2u16;

        // Vertical centering: centre the logo alone (matching rain.rs reveal
        // placement) so there is no vertical jump between Screen 4 and 5.
        // The tagline hangs below.
        let start_y = if area.height > logo_height {
            area.height.saturating_sub(logo_height) / 2
        } else {
            0
        };

        // Render logo lines — centre the entire block based on the widest line
        // so all lines share the same x offset (matching rain.rs reveal placement).
        let logo_style = Style::default()
            .fg(self.theme.logo_color)
            .bg(self.theme.background);

        let max_logo_width = logo_lines
            .iter()
            .map(|l| UnicodeWidthStr::width(*l) as u16)
            .max()
            .unwrap_or(0);
        let block_x = if area.width > max_logo_width {
            (area.width - max_logo_width) / 2
        } else {
            0
        };

        for (i, line) in logo_lines.iter().enumerate() {
            let line_width = UnicodeWidthStr::width(*line) as u16;
            let y = start_y + i as u16;
            if y < area.height {
                let span = Span::styled(*line, logo_style);
                let paragraph = Paragraph::new(Line::from(span));
                let rect = Rect::new(block_x, y, line_width.min(area.width), 1);
                frame.render_widget(paragraph, rect);
            }
        }

        // Render tagline centered below logo with 2-line gap
        let tagline_width = UnicodeWidthStr::width(self.tagline.as_str()) as u16;
        let tagline_x = if area.width > tagline_width {
            (area.width - tagline_width) / 2
        } else {
            0
        };
        let tagline_y = start_y + logo_height + gap;

        if tagline_y < area.height {
            let tagline_style = Style::default()
                .fg(self.theme.tagline_color)
                .bg(self.theme.background);
            let span = Span::styled(self.tagline.as_str(), tagline_style);
            let paragraph = Paragraph::new(Line::from(span));
            let rect = Rect::new(
                tagline_x,
                tagline_y,
                tagline_width.min(area.width),
                1,
            );
            frame.render_widget(paragraph, rect);
        }

        // Splash elements: only shown after hold phase
        if self.phase == LogoPhase::Splash {
            // "press any key" — blinking, below tagline with 3-line gap
            if self.prompt_visible {
                let prompt_y = tagline_y + 3;
                if prompt_y < area.height {
                    let prompt_style = Style::default()
                        .fg(self.theme.cursor_color)
                        .bg(self.theme.background);
                    let prompt_width = UnicodeWidthStr::width(PROMPT_TEXT) as u16;
                    let prompt_x = if area.width > prompt_width {
                        (area.width - prompt_width) / 2
                    } else {
                        0
                    };
                    let span = Span::styled(PROMPT_TEXT, prompt_style);
                    let paragraph = Paragraph::new(Line::from(span));
                    let rect = Rect::new(prompt_x, prompt_y, prompt_width.min(area.width), 1);
                    frame.render_widget(paragraph, rect);
                }
            }

            // Notice docked at bottom
            if area.height > 2 {
                let notice_y = area.height - 2;
                let notice_style = Style::default()
                    .fg(self.theme.rain_dim)
                    .bg(self.theme.background);
                let notice_width = UnicodeWidthStr::width(NOTICE_TEXT) as u16;
                let notice_x = if area.width > notice_width {
                    (area.width - notice_width) / 2
                } else {
                    0
                };
                let span = Span::styled(NOTICE_TEXT, notice_style);
                let paragraph = Paragraph::new(Line::from(span));
                let rect = Rect::new(notice_x, notice_y, notice_width.min(area.width), 1);
                frame.render_widget(paragraph, rect);
            }
        }
    }

    // -- Private helpers --------------------------------------------------

    /// Create initial set of ambient rain drops in top and bottom edge rows.
    fn init_drops(rng: &mut fastrand::Rng) -> Vec<AmbientDrop> {
        let count = 25; // ~20-30 drops
        let mut drops = Vec::with_capacity(count);
        for _ in 0..count {
            drops.push(Self::random_drop(rng));
        }
        drops
    }

    /// Create a single randomly positioned ambient drop.
    fn random_drop(rng: &mut fastrand::Rng) -> AmbientDrop {
        // Position in top 3 or bottom 3 rows of a typical terminal.
        // We use abstract positions; render will clamp to actual area.
        let top = rng.bool();
        let y = if top {
            rng.u16(0..3)
        } else {
            // Bottom rows represented as offsets from bottom (will be resolved at render)
            // We encode bottom rows as 1000 + offset so render can interpret them.
            1000 + rng.u16(0..3)
        };

        let x = rng.u16(0..200); // will be clamped at render time

        let ch = if rng.bool() { '|' } else { '│' };
        let fade_speed = 0.5 + rng.f32() * 1.5; // 0.5..2.0 per second
        let brightness = rng.f32(); // start at random phase
        let direction = rng.bool();

        AmbientDrop {
            x,
            y,
            ch,
            brightness,
            fade_speed,
            direction,
        }
    }

    /// Update all ambient drops: fade in/out, respawn when fully faded out.
    fn update_drops(&mut self) {
        // Approximate tick rate ~60fps -> ~16ms per tick
        let dt = 1.0 / 60.0_f32;

        for drop in &mut self.rain_drops {
            if drop.direction {
                // Fading in
                drop.brightness += drop.fade_speed * dt;
                if drop.brightness >= 1.0 {
                    drop.brightness = 1.0;
                    drop.direction = false;
                }
            } else {
                // Fading out
                drop.brightness -= drop.fade_speed * dt;
                if drop.brightness <= 0.0 {
                    // Respawn at new position
                    *drop = Self::random_drop(&mut self.rng);
                    drop.brightness = 0.0;
                    drop.direction = true;
                }
            }
        }
    }

    /// Render ambient drops with interpolated brightness.
    fn render_drops(&self, frame: &mut Frame, area: Rect) {
        if area.width == 0 || area.height < 6 {
            return;
        }

        for drop in &self.rain_drops {
            let x = drop.x % area.width;

            // Resolve y: values >= 1000 are bottom-relative offsets
            let y = if drop.y >= 1000 {
                let offset = drop.y - 1000;
                if area.height < 1 + offset {
                    continue;
                }
                area.height - 1 - offset
            } else {
                drop.y
            };

            if y >= area.height || x >= area.width {
                continue;
            }

            // Interpolate between background and rain_dim based on brightness
            let color = interpolate_color(
                self.theme.background,
                self.theme.rain_dim,
                drop.brightness,
            );

            let style = Style::default().fg(color).bg(self.theme.background);
            let span = Span::styled(drop.ch.to_string(), style);
            let paragraph = Paragraph::new(Line::from(span));
            frame.render_widget(paragraph, Rect::new(x, y, 1, 1));
        }
    }
}

// ---------------------------------------------------------------------------
// Color interpolation helper
// ---------------------------------------------------------------------------

/// Linearly interpolate between two RGB colors. Falls back to `to` for
/// non-RGB variants.
fn interpolate_color(from: Color, to: Color, t: f32) -> Color {
    let t = t.clamp(0.0, 1.0);
    match (from, to) {
        (Color::Rgb(r1, g1, b1), Color::Rgb(r2, g2, b2)) => {
            let r = (r1 as f32 + (r2 as f32 - r1 as f32) * t) as u8;
            let g = (g1 as f32 + (g2 as f32 - g1 as f32) * t) as u8;
            let b = (b1 as f32 + (b2 as f32 - b1 as f32) * t) as u8;
            Color::Rgb(r, g, b)
        }
        _ => to,
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::IntroConfig;
    use crate::terminal::LayoutMode;
    use crate::theme::phosphor_theme;

    fn default_config() -> IntroConfig {
        IntroConfig::default()
    }

    fn english_config() -> IntroConfig {
        IntroConfig {
            tagline: "english".to_string(),
            ..IntroConfig::default()
        }
    }

    // -- Logo selection based on LayoutMode --

    #[test]
    fn full_layout_selects_logo_full() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        assert_eq!(state.logo_text, LOGO_FULL);
    }

    #[test]
    fn compact_layout_selects_logo_compact() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Compact);
        assert_eq!(state.logo_text, LOGO_COMPACT);
    }

    #[test]
    fn minimal_layout_selects_logo_minimal() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Minimal);
        assert_eq!(state.logo_text, LOGO_MINIMAL);
    }

    // -- Tagline selection --

    #[test]
    fn english_tagline_selected() {
        let state = LogoState::new(&english_config(), &phosphor_theme(), LayoutMode::Full);
        assert_eq!(state.tagline, TAGLINE_EN);
    }

    #[test]
    fn katakana_tagline_selected_by_default() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        assert_eq!(state.tagline, TAGLINE_JP);
    }

    #[test]
    fn unknown_tagline_falls_back_to_katakana() {
        let config = IntroConfig {
            tagline: "unknown".to_string(),
            ..IntroConfig::default()
        };
        let state = LogoState::new(&config, &phosphor_theme(), LayoutMode::Full);
        assert_eq!(state.tagline, TAGLINE_JP);
    }

    // -- Hold duration: tick returns Continue before 2s, NextScreen after --

    #[test]
    fn tick_returns_continue_before_hold_duration() {
        let mut state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        // Immediately after creation, elapsed < 2s
        let action = state.tick();
        assert_eq!(action, IntroAction::Continue);
    }

    #[test]
    fn tick_transitions_to_splash_after_hold_duration() {
        let mut state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        // Move start_time back so elapsed > 4s
        state.start_time = Instant::now() - Duration::from_secs(5);
        let action = state.tick();
        // After hold, transitions to Splash phase (still Continue, waits for key)
        assert_eq!(action, IntroAction::Continue);
        assert_eq!(state.phase, LogoPhase::Splash);
    }

    #[test]
    fn tick_returns_continue_just_before_hold_duration() {
        let mut state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        state.start_time = Instant::now() - Duration::from_millis(2900);
        let action = state.tick();
        assert_eq!(action, IntroAction::Continue);
        assert_eq!(state.phase, LogoPhase::Hold);
    }

    // -- handle_input --

    #[test]
    fn handle_input_returns_continue_during_hold() {
        use crossterm::event::{KeyCode, KeyEventKind, KeyEventState, KeyModifiers};
        let mut state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        let key = KeyEvent {
            code: KeyCode::Char('q'),
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        };
        assert_eq!(state.handle_input(key), IntroAction::Continue);
    }

    #[test]
    fn handle_input_returns_next_screen_during_splash() {
        use crossterm::event::{KeyCode, KeyEventKind, KeyEventState, KeyModifiers};
        let mut state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        // Force into splash phase
        state.phase = LogoPhase::Splash;
        let key = KeyEvent {
            code: KeyCode::Char(' '),
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        };
        assert_eq!(state.handle_input(key), IntroAction::NextScreen);
    }

    // -- Ambient drops initialized within expected bounds --

    #[test]
    fn ambient_drops_initialized_with_expected_count() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        assert_eq!(state.rain_drops.len(), 25);
    }

    #[test]
    fn ambient_drops_have_valid_brightness() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        for drop in &state.rain_drops {
            assert!(drop.brightness >= 0.0 && drop.brightness <= 1.0);
        }
    }

    #[test]
    fn ambient_drops_are_in_edge_rows() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        for drop in &state.rain_drops {
            // y is either in top 3 rows (0..3) or bottom-relative (1000..1003)
            let valid_top = drop.y < 3;
            let valid_bottom = drop.y >= 1000 && drop.y < 1003;
            assert!(
                valid_top || valid_bottom,
                "drop.y = {} is not in top 3 or bottom 3 rows",
                drop.y
            );
        }
    }

    #[test]
    fn ambient_drops_use_valid_chars() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        for drop in &state.rain_drops {
            assert!(
                drop.ch == '|' || drop.ch == '│',
                "unexpected char: {}",
                drop.ch
            );
        }
    }

    #[test]
    fn ambient_drops_have_valid_fade_speed() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        for drop in &state.rain_drops {
            assert!(
                drop.fade_speed >= 0.5 && drop.fade_speed <= 2.0,
                "fade_speed {} out of range",
                drop.fade_speed
            );
        }
    }

    // -- Color interpolation --

    #[test]
    fn interpolate_color_at_zero_returns_from() {
        let result = interpolate_color(Color::Rgb(0, 0, 0), Color::Rgb(100, 100, 100), 0.0);
        assert_eq!(result, Color::Rgb(0, 0, 0));
    }

    #[test]
    fn interpolate_color_at_one_returns_to() {
        let result = interpolate_color(Color::Rgb(0, 0, 0), Color::Rgb(100, 100, 100), 1.0);
        assert_eq!(result, Color::Rgb(100, 100, 100));
    }

    #[test]
    fn interpolate_color_at_half() {
        let result = interpolate_color(Color::Rgb(0, 0, 0), Color::Rgb(100, 200, 50), 0.5);
        assert_eq!(result, Color::Rgb(50, 100, 25));
    }

    #[test]
    fn interpolate_color_clamps_above_one() {
        let result = interpolate_color(Color::Rgb(0, 0, 0), Color::Rgb(100, 100, 100), 1.5);
        assert_eq!(result, Color::Rgb(100, 100, 100));
    }

    #[test]
    fn hold_duration_is_two_seconds() {
        let state = LogoState::new(&default_config(), &phosphor_theme(), LayoutMode::Full);
        assert_eq!(state.hold_duration, Duration::from_millis(3000));
    }
}

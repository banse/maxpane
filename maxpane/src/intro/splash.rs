/// Screen 6 — "Splash" (App splash screen)
///
/// Shows the MAXPANE logo, katakana tagline, "press any key" prompt with
/// blinking animation, and a copyright notice docked at the bottom.
/// Waits for any keypress before transitioning to Done.

use std::time::{Duration, Instant};

use crossterm::event::KeyEvent;
use ratatui::{
    layout::Rect,
    style::Style,
    text::{Line, Span},
    widgets::Paragraph,
    Frame,
};
use unicode_width::UnicodeWidthStr;

use super::logo::{LOGO_COMPACT, LOGO_FULL, LOGO_MINIMAL, TAGLINE_EN, TAGLINE_JP};
use crate::config::IntroConfig;
use crate::terminal::LayoutMode;
use crate::theme::IntroTheme;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PROMPT_TEXT: &str = "press any key";
const NOTICE_TEXT: &str = "☮ 2026 hisdudeness.eth — The Dude Abides.";
const CURSOR_BLINK_MS: u64 = 530;

// ---------------------------------------------------------------------------
// SplashState
// ---------------------------------------------------------------------------

pub struct SplashState {
    theme: IntroTheme,
    layout: LayoutMode,
    tagline: String,
    logo_text: &'static str,
    prompt_visible: bool,
    blink_timer: Instant,
}

impl SplashState {
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

        Self {
            theme: theme.clone(),
            layout,
            tagline,
            logo_text,
            prompt_visible: true,
            blink_timer: Instant::now(),
        }
    }

    pub fn tick(&mut self) -> super::IntroAction {
        // Blink the "press any key" prompt
        if self.blink_timer.elapsed() >= Duration::from_millis(CURSOR_BLINK_MS) {
            self.prompt_visible = !self.prompt_visible;
            self.blink_timer = Instant::now();
        }
        super::IntroAction::Continue
    }

    pub fn handle_input(&mut self, _key: KeyEvent) -> super::IntroAction {
        // Any key dismisses the splash
        super::IntroAction::NextScreen
    }

    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();

        // Clear background
        let bg_style = Style::default().bg(self.theme.background);
        frame.render_widget(Paragraph::new("").style(bg_style), area);

        // Compute logo lines
        let logo_lines: Vec<&str> = self.logo_text.lines().collect();
        let logo_height = logo_lines.len() as u16;

        // Vertical centering: centre the logo alone (matching rain.rs placement)
        let start_y = if area.height > logo_height {
            area.height.saturating_sub(logo_height) / 2
        } else {
            0
        };

        // Logo: block-centred based on widest line
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

        // Tagline below logo with 2-line gap
        let gap = 2u16;
        let tagline_y = start_y + logo_height + gap;
        let tagline_style = Style::default()
            .fg(self.theme.tagline_color)
            .bg(self.theme.background);
        self.render_centered_text(frame, area, &self.tagline, tagline_y, tagline_style);

        // "press any key" prompt below tagline with 3-line gap, blinking
        if self.prompt_visible {
            let prompt_y = tagline_y + 3;
            let prompt_style = Style::default()
                .fg(self.theme.cursor_color)
                .bg(self.theme.background);
            self.render_centered_text(frame, area, PROMPT_TEXT, prompt_y, prompt_style);
        }

        // Notice docked at bottom
        if area.height > 2 {
            let notice_y = area.height - 2;
            let notice_style = Style::default()
                .fg(self.theme.rain_dim)
                .bg(self.theme.background);
            self.render_centered_text(frame, area, NOTICE_TEXT, notice_y, notice_style);
        }
    }

    fn render_centered_text(
        &self,
        frame: &mut Frame,
        area: Rect,
        text: &str,
        y: u16,
        style: Style,
    ) {
        if y >= area.height {
            return;
        }
        let text_width = UnicodeWidthStr::width(text) as u16;
        let x = if area.width > text_width {
            (area.width - text_width) / 2
        } else {
            0
        };
        let span = Span::styled(text, style);
        let paragraph = Paragraph::new(Line::from(span));
        let rect = Rect::new(x, y, text_width.min(area.width), 1);
        frame.render_widget(paragraph, rect);
    }
}

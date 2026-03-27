/// Screen 3+4 -- "Matrix Rain" and "Reveal"
///
/// Fullscreen falling code rain that transitions into the MAXPANE logo
/// crystallisation. The module implements two phases within a single state
/// machine:
///
/// - **FullRain**: columns of random characters fall at varying speeds with
///   exponential brightness decay. Duration is configurable via
///   `IntroConfig::rain_duration_ms`.
///
/// - **Revealing**: rain decelerates while logo characters "freeze" into place
///   from the outside edges inward. Once all logo cells are revealed and
///   non-frozen cells have faded, the state transitions to `Done` and returns
///   `IntroAction::NextScreen`.

use std::time::{Duration, Instant};

use crossterm::event::KeyEvent;
use ratatui::Frame;

use super::IntroAction;
use crate::config::IntroConfig;
use crate::intro::{animation, charset};
use crate::terminal::LayoutMode;
use crate::theme::IntroTheme;

// ---------------------------------------------------------------------------
// Logo data
// ---------------------------------------------------------------------------

const LOGO_FULL: &str = "\
███╗   ███╗ █████╗ ██╗  ██╗██████╗  █████╗ ███╗   ██╗███████╗\n\
████╗ ████║██╔══██╗╚██╗██╔╝██╔══██╗██╔══██╗████╗  ██║██╔════╝\n\
██╔████╔██║███████║ ╚███╔╝ ██████╔╝███████║██╔██╗ ██║█████╗\n\
██║╚██╔╝██║██╔══██║ ██╔██╗ ██╔═══╝ ██╔══██║██║╚██╗██║██╔══╝\n\
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██║     ██║  ██║██║ ╚████║███████╗\n\
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝";

const LOGO_COMPACT: &str = "\
███╗   ███╗ █████╗ ██╗  ██╗\n\
████╗ ████║██╔══██╗╚██╗██╔╝\n\
██╔████╔██║███████║ ╚███╔╝\n\
██║╚██╔╝██║██╔══██║ ██╔██╗\n\
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗\n\
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝";

const LOGO_MINIMAL: &str = "MAXPANE";

// ---------------------------------------------------------------------------
// RainPhase
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum RainPhase {
    /// Screen 3: full rain, all columns active.
    FullRain,
    /// Screen 4: rain decelerates, logo crystallises from edges inward.
    Revealing,
    /// Both phases complete.
    Done,
}

// ---------------------------------------------------------------------------
// RainCell
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct RainCell {
    y: u16,
    ch: char,
    brightness: f32,
    frozen: bool,
}

// ---------------------------------------------------------------------------
// RainColumn
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct RainColumn {
    x: u16,
    head_y: f32,
    speed: f32,
    trail_length: u16,
    chars: Vec<RainCell>,
    active: bool,
}

// ---------------------------------------------------------------------------
// LogoMask
// ---------------------------------------------------------------------------

struct LogoMask {
    /// (x, y, char) for each non-space character in the logo.
    cells: Vec<(u16, u16, char)>,
    center_x: u16,
    center_y: u16,
    width: u16,
    height: u16,
}

impl LogoMask {
    /// Build a `LogoMask` from one of the logo strings, centred in the
    /// given terminal dimensions.
    fn new(logo: &str, term_width: u16, term_height: u16) -> Self {
        let lines: Vec<&str> = logo.lines().collect();
        let logo_height = lines.len() as u16;
        let logo_width = lines.iter().map(|l| l.chars().count()).max().unwrap_or(0) as u16;

        // Centre the logo in the terminal.
        let center_x = term_width.saturating_sub(logo_width) / 2;
        let center_y = term_height.saturating_sub(logo_height) / 2;

        let mut cells = Vec::new();
        for (row, line) in lines.iter().enumerate() {
            let mut col: u16 = 0;
            for ch in line.chars() {
                if ch != ' ' {
                    cells.push((center_x + col, center_y + row as u16, ch));
                }
                col += 1;
            }
        }

        Self {
            cells,
            center_x,
            center_y,
            width: logo_width,
            height: logo_height,
        }
    }

    /// Normalised reveal order for position `(x, y)`. Values closer to 0.0
    /// reveal first (edges), values closer to 1.0 reveal last (centre).
    ///
    /// This is the *inverted* normalised distance from the centre of the logo
    /// so that edges (distance = max) map to order 0.0 (first to reveal).
    fn reveal_order(&self, x: u16, y: u16) -> f32 {
        let cx = self.center_x as f32 + self.width as f32 / 2.0;
        let cy = self.center_y as f32 + self.height as f32 / 2.0;
        let dx = x as f32 - cx;
        let dy = y as f32 - cy;
        let dist = (dx * dx + dy * dy).sqrt();
        let max_dist = ((self.width as f32 / 2.0).powi(2)
            + (self.height as f32 / 2.0).powi(2))
        .sqrt();
        if max_dist < f32::EPSILON {
            return 0.0;
        }
        // Invert: edges (high distance) get low order (reveal first).
        1.0 - dist / max_dist
    }
}

// ---------------------------------------------------------------------------
// RainState (public)
// ---------------------------------------------------------------------------

pub struct RainState {
    columns: Vec<RainColumn>,
    phase: RainPhase,
    logo_mask: LogoMask,
    rng: fastrand::Rng,
    frame_count: u64,
    start_time: Instant,
    last_tick: Instant,
    rain_duration: Duration,
    reveal_start: Option<Instant>,
    reveal_duration: Duration,
    theme: IntroTheme,
    layout: LayoutMode,
    width: u16,
    height: u16,
}

impl RainState {
    pub fn new(
        config: &IntroConfig,
        theme: &IntroTheme,
        layout: LayoutMode,
        width: u16,
        height: u16,
    ) -> Self {
        let mut rng = fastrand::Rng::new();

        let logo_str = match layout {
            LayoutMode::Full => LOGO_FULL,
            LayoutMode::Compact => LOGO_COMPACT,
            LayoutMode::Minimal => LOGO_MINIMAL,
        };

        let logo_mask = LogoMask::new(logo_str, width, height);

        // Number of rain columns scales with terminal width.
        let num_columns = match layout {
            LayoutMode::Full => width,
            LayoutMode::Compact => width,
            LayoutMode::Minimal => width / 2,
        };

        let mut columns = Vec::with_capacity(num_columns as usize);
        for x in 0..num_columns {
            columns.push(Self::new_column(x, height, &mut rng));
        }

        let now = Instant::now();

        Self {
            columns,
            phase: RainPhase::FullRain,
            logo_mask,
            rng,
            frame_count: 0,
            start_time: now,
            last_tick: now,
            rain_duration: Duration::from_millis(config.rain_duration_ms),
            reveal_start: None,
            reveal_duration: Duration::from_millis(4000),
            theme: theme.clone(),
            layout,
            width,
            height,
        }
    }

    pub fn tick(&mut self) -> IntroAction {
        let now = Instant::now();
        let dt = now.duration_since(self.last_tick).as_secs_f32();
        self.last_tick = now;
        self.frame_count += 1;

        match self.phase {
            RainPhase::FullRain => {
                self.tick_rain(dt);

                if now.duration_since(self.start_time) >= self.rain_duration {
                    self.phase = RainPhase::Revealing;
                    self.reveal_start = Some(now);
                }
                IntroAction::Continue
            }
            RainPhase::Revealing => {
                self.tick_rain(dt);
                self.tick_reveal(now);

                let reveal_elapsed = now
                    .duration_since(self.reveal_start.unwrap_or(now))
                    .as_secs_f32();
                let progress = (reveal_elapsed / self.reveal_duration.as_secs_f32()).clamp(0.0, 1.0);

                // Check completion: all logo cells revealed and all non-frozen
                // cells gone (or progress is fully done).
                if progress >= 1.0 && self.non_frozen_cells_gone() {
                    self.phase = RainPhase::Done;
                    return IntroAction::NextScreen;
                }
                IntroAction::Continue
            }
            RainPhase::Done => IntroAction::NextScreen,
        }
    }

    pub fn handle_input(&mut self, _key: KeyEvent) -> IntroAction {
        IntroAction::Continue
    }

    pub fn render(&self, frame: &mut Frame) {
        let area = frame.area();
        let buf = frame.buffer_mut();

        // Clear to background.
        for y in area.top()..area.bottom() {
            for x in area.left()..area.right() {
                buf[(x, y)]
                    .set_char(' ')
                    .set_bg(self.theme.background);
            }
        }

        // Draw rain cells.
        for col in &self.columns {
            for cell in &col.chars {
                if col.x < area.width && cell.y < area.height {
                    let color = animation::brightness_to_color(
                        cell.brightness,
                        cell.frozen,
                        self.theme.rain_dim,
                        self.theme.rain_bright,
                        self.theme.logo_color,
                    );
                    buf[(col.x, cell.y)]
                        .set_char(cell.ch)
                        .set_fg(color)
                        .set_bg(self.theme.background);
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // Private helpers
    // -----------------------------------------------------------------------

    /// Create a fresh rain column starting at a random vertical offset.
    fn new_column(x: u16, height: u16, rng: &mut fastrand::Rng) -> RainColumn {
        let speed = 4.0 + rng.f32() * 8.0; // 4.0 - 12.0
        let trail_length = 5 + rng.u16(..16); // 5 - 20
        // Start head above the screen by a random amount so columns don't all
        // start at the same time.
        let head_y = -(rng.f32() * height as f32);

        RainColumn {
            x,
            head_y,
            speed,
            trail_length,
            chars: Vec::new(),
            active: true,
        }
    }

    /// Advance rain physics for one frame.
    fn tick_rain(&mut self, dt: f32) {
        let height = self.height;

        for col in &mut self.columns {
            if !col.active {
                // Inactive columns still decay their remaining cells.
                for cell in &mut col.chars {
                    if !cell.frozen {
                        cell.brightness *= 0.85;
                    }
                }
                col.chars.retain(|c| c.frozen || c.brightness >= 0.05);
                continue;
            }

            let prev_y = col.head_y as i32;
            col.head_y += col.speed * dt;
            let new_y = col.head_y as i32;

            // Spawn new cells for each integer row the head passed.
            for y in (prev_y + 1)..=new_y {
                if y >= 0 && y < height as i32 {
                    let ch = charset::random_rain_char_single_width(&mut self.rng);
                    col.chars.push(RainCell {
                        y: y as u16,
                        ch,
                        brightness: 1.0,
                        frozen: false,
                    });
                }
            }

            // Decay brightness for trail cells.
            for cell in &mut col.chars {
                if !cell.frozen {
                    cell.brightness *= 0.85;
                }
            }

            // Character flicker: 2% chance per frame to replace a cell's char.
            for cell in &mut col.chars {
                if !cell.frozen && self.rng.u8(..100) < 2 {
                    cell.ch = charset::random_rain_char_single_width(&mut self.rng);
                }
            }

            // Remove faded cells.
            col.chars.retain(|c| c.frozen || c.brightness >= 0.05);

            // If the head has fallen past the screen plus trail, wrap it back
            // to the top with a new random offset.
            if col.head_y > (height + col.trail_length) as f32 {
                col.head_y = -(self.rng.f32() * height as f32 * 0.5);
                col.speed = 4.0 + self.rng.f32() * 8.0;
                col.trail_length = 5 + self.rng.u16(..16);
            }
        }
    }

    /// Run the reveal phase logic: freeze logo cells and decelerate non-logo
    /// columns.
    fn tick_reveal(&mut self, now: Instant) {
        let reveal_elapsed = now
            .duration_since(self.reveal_start.unwrap_or(now))
            .as_secs_f32();
        let progress =
            (reveal_elapsed / self.reveal_duration.as_secs_f32()).clamp(0.0, 1.0);

        // Apply ease-out for a satisfying deceleration feel.
        let eased = animation::ease_out_quad(progress);

        // Build a set of logo cell positions for fast lookup.
        // For each logo cell, check if it should be revealed at this progress.
        for &(lx, ly, lch) in &self.logo_mask.cells {
            let order = self.logo_mask.reveal_order(lx, ly);
            if order <= eased {
                // Find or create the cell in the appropriate column.
                if let Some(col) = self.columns.iter_mut().find(|c| c.x == lx) {
                    // Check if a frozen cell already exists at this position.
                    let already_frozen = col.chars.iter().any(|c| c.y == ly && c.frozen);
                    if !already_frozen {
                        // Remove any non-frozen cell at this position.
                        col.chars.retain(|c| c.y != ly || c.frozen);
                        // Insert frozen logo cell.
                        col.chars.push(RainCell {
                            y: ly,
                            ch: lch,
                            brightness: 1.0,
                            frozen: true,
                        });
                    }
                }
            }
        }

        // Decelerate all columns during reveal: reduce speed and stop spawning
        // new rain cells so the animation converges to the static logo.
        for col in &mut self.columns {
            col.speed *= 0.97;
            // Once speed is negligible, deactivate (stops new cell spawning).
            if col.speed < 0.5 {
                col.active = false;
            }
        }
    }

    /// Returns `true` when all non-frozen rain cells have faded away.
    fn non_frozen_cells_gone(&self) -> bool {
        self.columns
            .iter()
            .all(|col| col.chars.iter().all(|c| c.frozen || c.brightness < 0.05))
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::IntroConfig;
    use crate::theme::phosphor_theme;

    /// Helper: build a RainState with default config for Full layout.
    fn make_rain() -> RainState {
        let config = IntroConfig::default();
        let theme = phosphor_theme();
        RainState::new(&config, &theme, LayoutMode::Full, 120, 40)
    }

    /// Helper: build a RainState with a very short rain duration so we can
    /// test phase transitions quickly.
    fn make_fast_rain() -> RainState {
        let config = IntroConfig {
            rain_duration_ms: 0, // instant transition to Revealing
            ..IntroConfig::default()
        };
        let theme = phosphor_theme();
        RainState::new(&config, &theme, LayoutMode::Full, 120, 40)
    }

    // -- Column initialisation ------------------------------------------------

    #[test]
    fn column_speed_in_range() {
        let rain = make_rain();
        for col in &rain.columns {
            assert!(
                col.speed >= 4.0 && col.speed <= 12.0,
                "speed {} out of range 4.0-12.0",
                col.speed,
            );
        }
    }

    #[test]
    fn column_trail_length_in_range() {
        let rain = make_rain();
        for col in &rain.columns {
            assert!(
                col.trail_length >= 5 && col.trail_length <= 20,
                "trail_length {} out of range 5-20",
                col.trail_length,
            );
        }
    }

    #[test]
    fn columns_cover_full_width() {
        let rain = make_rain();
        assert_eq!(rain.columns.len(), rain.width as usize);
    }

    #[test]
    fn all_columns_start_active() {
        let rain = make_rain();
        assert!(rain.columns.iter().all(|c| c.active));
    }

    // -- Brightness decay -----------------------------------------------------

    #[test]
    fn brightness_decays_over_ticks() {
        let mut rain = make_rain();

        // Force a cell with known brightness into column 0.
        rain.columns[0].chars.push(RainCell {
            y: 5,
            ch: 'X',
            brightness: 1.0,
            frozen: false,
        });

        let initial = 1.0_f32;

        // Tick a few times (small dt so head doesn't move much).
        for _ in 0..10 {
            rain.tick_rain(0.033);
        }

        // The cell at y=5 (if it still exists) should have decayed.
        if let Some(cell) = rain.columns[0].chars.iter().find(|c| c.y == 5 && !c.frozen) {
            assert!(
                cell.brightness < initial,
                "brightness should have decayed from {} but is {}",
                initial,
                cell.brightness,
            );
        }
        // If the cell was removed (brightness < 0.05), that also proves decay.
    }

    #[test]
    fn frozen_cells_do_not_decay() {
        let mut rain = make_rain();
        rain.columns[0].chars.push(RainCell {
            y: 5,
            ch: '█',
            brightness: 1.0,
            frozen: true,
        });

        for _ in 0..20 {
            rain.tick_rain(0.033);
        }

        let cell = rain.columns[0]
            .chars
            .iter()
            .find(|c| c.y == 5 && c.frozen)
            .expect("frozen cell should still exist");
        assert!(
            (cell.brightness - 1.0).abs() < f32::EPSILON,
            "frozen cell brightness should remain 1.0, got {}",
            cell.brightness,
        );
    }

    // -- LogoMask reveal_order ------------------------------------------------

    #[test]
    fn reveal_order_edges_lower_than_center() {
        let mask = LogoMask::new(LOGO_FULL, 120, 40);
        assert!(!mask.cells.is_empty(), "mask should have cells");

        // Find an edge cell and a centre cell.
        let cx = mask.center_x + mask.width / 2;
        let cy = mask.center_y + mask.height / 2;

        // Edge: first cell in the mask (likely top-left area).
        let edge = &mask.cells[0];
        let edge_order = mask.reveal_order(edge.0, edge.1);

        // Centre: find cell closest to the computed centre.
        let centre_cell = mask
            .cells
            .iter()
            .min_by(|a, b| {
                let da = (a.0 as f32 - cx as f32).powi(2) + (a.1 as f32 - cy as f32).powi(2);
                let db = (b.0 as f32 - cx as f32).powi(2) + (b.1 as f32 - cy as f32).powi(2);
                da.partial_cmp(&db).unwrap()
            })
            .unwrap();
        let centre_order = mask.reveal_order(centre_cell.0, centre_cell.1);

        assert!(
            edge_order < centre_order,
            "edge order ({}) should be less than centre order ({}) so edges reveal first",
            edge_order,
            centre_order,
        );
    }

    #[test]
    fn reveal_order_bounded_zero_to_one() {
        let mask = LogoMask::new(LOGO_FULL, 120, 40);
        for &(x, y, _) in &mask.cells {
            let order = mask.reveal_order(x, y);
            assert!(
                order >= 0.0 && order <= 1.0,
                "reveal_order({},{}) = {} out of [0,1]",
                x,
                y,
                order,
            );
        }
    }

    // -- Phase transitions ----------------------------------------------------

    #[test]
    fn starts_in_full_rain() {
        let rain = make_rain();
        assert_eq!(rain.phase, RainPhase::FullRain);
    }

    #[test]
    fn transitions_to_revealing_after_duration() {
        let mut rain = make_fast_rain();
        // The rain duration is 0ms, so the very first tick should transition.
        // We need a small sleep to ensure Instant::now() > start_time.
        std::thread::sleep(Duration::from_millis(5));
        let _action = rain.tick();
        assert_eq!(
            rain.phase,
            RainPhase::Revealing,
            "should transition to Revealing after rain_duration",
        );
    }

    #[test]
    fn transitions_to_done_after_reveal_complete() {
        let mut rain = make_fast_rain();
        // Transition to Revealing.
        std::thread::sleep(Duration::from_millis(5));
        rain.tick();
        assert_eq!(rain.phase, RainPhase::Revealing);

        // Set reveal_start far in the past so progress >= 1.0.
        rain.reveal_start = Some(Instant::now() - Duration::from_secs(10));
        // Clear all non-frozen cells to satisfy the completion check.
        for col in &mut rain.columns {
            col.chars.retain(|c| c.frozen);
        }

        let action = rain.tick();
        assert_eq!(rain.phase, RainPhase::Done);
        assert_eq!(action, IntroAction::NextScreen);
    }

    // -- handle_input ---------------------------------------------------------

    #[test]
    fn handle_input_always_returns_continue() {
        let mut rain = make_rain();
        let key = crossterm::event::KeyEvent {
            code: crossterm::event::KeyCode::Char('x'),
            modifiers: crossterm::event::KeyModifiers::NONE,
            kind: crossterm::event::KeyEventKind::Press,
            state: crossterm::event::KeyEventState::NONE,
        };
        assert_eq!(rain.handle_input(key), IntroAction::Continue);
    }

    // -- Layout variants ------------------------------------------------------

    #[test]
    fn compact_layout_creates_columns() {
        let config = IntroConfig::default();
        let theme = phosphor_theme();
        let rain = RainState::new(&config, &theme, LayoutMode::Compact, 80, 24);
        assert_eq!(rain.columns.len(), 80);
    }

    #[test]
    fn minimal_layout_creates_fewer_columns() {
        let config = IntroConfig::default();
        let theme = phosphor_theme();
        let rain = RainState::new(&config, &theme, LayoutMode::Minimal, 60, 20);
        // 60 / 2 = 30
        assert_eq!(rain.columns.len(), 30);
    }

    // -- LogoMask construction ------------------------------------------------

    #[test]
    fn logo_mask_full_has_cells() {
        let mask = LogoMask::new(LOGO_FULL, 120, 40);
        assert!(!mask.cells.is_empty());
        assert!(mask.width > 0);
        assert!(mask.height > 0);
    }

    #[test]
    fn logo_mask_compact_has_cells() {
        let mask = LogoMask::new(LOGO_COMPACT, 80, 24);
        assert!(!mask.cells.is_empty());
    }

    #[test]
    fn logo_mask_minimal_has_cells() {
        let mask = LogoMask::new(LOGO_MINIMAL, 60, 20);
        assert!(!mask.cells.is_empty());
        // "MAXPANE" is 7 characters.
        assert_eq!(mask.cells.len(), 7);
    }

    #[test]
    fn logo_mask_centred_in_terminal() {
        let mask = LogoMask::new(LOGO_MINIMAL, 80, 24);
        // "MAXPANE" is 7 chars wide, 1 line tall.
        // center_x should be (80 - 7) / 2 = 36
        assert_eq!(mask.center_x, 36);
        // center_y should be (24 - 1) / 2 = 11
        assert_eq!(mask.center_y, 11);
    }

    // -- Done phase returns NextScreen repeatedly -----------------------------

    #[test]
    fn done_phase_returns_next_screen() {
        let mut rain = make_rain();
        rain.phase = RainPhase::Done;
        assert_eq!(rain.tick(), IntroAction::NextScreen);
        assert_eq!(rain.tick(), IntroAction::NextScreen);
    }
}

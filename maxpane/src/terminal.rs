use std::io::{self, Stdout};

use crossterm::{
    cursor,
    execute,
    terminal::{self, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};

// ---------------------------------------------------------------------------
// Layout mode — responsive sizing for the intro sequence
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LayoutMode {
    /// >= 100x30: full logo, full rain
    Full,
    /// >= 80x24: compact logo, reduced rain
    Compact,
    /// < 80x24: text only, minimal rain
    Minimal,
}

/// Determine the appropriate layout mode based on terminal dimensions.
pub fn detect_layout(width: u16, height: u16) -> LayoutMode {
    match (width, height) {
        (w, h) if w >= 100 && h >= 30 => LayoutMode::Full,
        (w, h) if w >= 80 && h >= 24 => LayoutMode::Compact,
        _ => LayoutMode::Minimal,
    }
}

// ---------------------------------------------------------------------------
// Terminal setup / teardown
// ---------------------------------------------------------------------------

/// Initialise the terminal for TUI rendering.
///
/// - Enables raw mode
/// - Switches to the alternate screen buffer
/// - Hides the cursor
/// - Installs a panic hook that restores the terminal before unwinding
pub fn setup_terminal() -> Result<Terminal<CrosstermBackend<Stdout>>, Box<dyn std::error::Error>> {
    // Install a panic hook *before* entering raw mode so that any panic
    // during setup still gets caught by the default handler, and any panic
    // after setup restores the terminal first.
    let original_hook = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |info| {
        // Best-effort restore — ignore errors since we are already panicking.
        let _ = terminal::disable_raw_mode();
        let _ = execute!(io::stdout(), LeaveAlternateScreen, cursor::Show);
        original_hook(info);
    }));

    terminal::enable_raw_mode()?;

    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, cursor::Hide)?;

    let backend = CrosstermBackend::new(stdout);
    let terminal = Terminal::new(backend)?;

    Ok(terminal)
}

/// Restore the terminal to its normal state.
///
/// - Disables raw mode
/// - Leaves the alternate screen buffer
/// - Shows the cursor
pub fn restore_terminal(
    terminal: &mut Terminal<CrosstermBackend<Stdout>>,
) -> Result<(), Box<dyn std::error::Error>> {
    terminal::disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen, cursor::Show)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_at_exact_threshold() {
        assert_eq!(detect_layout(100, 30), LayoutMode::Full);
    }

    #[test]
    fn compact_when_width_below_full() {
        assert_eq!(detect_layout(99, 30), LayoutMode::Compact);
    }

    #[test]
    fn compact_when_height_below_full() {
        assert_eq!(detect_layout(100, 29), LayoutMode::Compact);
    }

    #[test]
    fn compact_at_exact_threshold() {
        assert_eq!(detect_layout(80, 24), LayoutMode::Compact);
    }

    #[test]
    fn minimal_when_width_below_compact() {
        assert_eq!(detect_layout(79, 24), LayoutMode::Minimal);
    }

    #[test]
    fn minimal_when_height_below_compact() {
        assert_eq!(detect_layout(80, 23), LayoutMode::Minimal);
    }

    #[test]
    fn full_at_large_dimensions() {
        assert_eq!(detect_layout(200, 50), LayoutMode::Full);
    }
}

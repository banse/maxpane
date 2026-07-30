#![allow(dead_code)]

mod config;
mod intro;
mod terminal;
mod theme;

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // 1. Load config (use defaults on missing file)
    let config = config::Config::load().unwrap_or_else(|e| {
        eprintln!("Warning: config error: {e}, using defaults");
        config::Config::default()
    });

    // 2. Resolve theme from config
    let theme = theme::theme_from_config(
        &config.intro.color_scheme,
        config.intro.colors.as_ref().and_then(|c| c.text.as_deref()),
        config
            .intro
            .colors
            .as_ref()
            .and_then(|c| c.background.as_deref()),
        config
            .intro
            .colors
            .as_ref()
            .and_then(|c| c.rain_bright.as_deref()),
        config
            .intro
            .colors
            .as_ref()
            .and_then(|c| c.rain_dim.as_deref()),
        config
            .intro
            .colors
            .as_ref()
            .and_then(|c| c.logo.as_deref()),
    );

    // 3. Check if intro should show
    if !config.intro.should_show() {
        println!("MaxPane v0.1.0 ready.");
        return Ok(());
    }

    // 4. Setup terminal (raw mode, alternate screen)
    let mut term = terminal::setup_terminal()?;

    // 5. Run intro
    let result = run_intro(&mut term, &config.intro, &theme).await;

    // 6. ALWAYS restore terminal before handling result
    terminal::restore_terminal(&mut term)?;

    // 7. Handle result
    match result? {
        intro::IntroResult::Exit => {
            // User chose to exit at prompt
        }
        intro::IntroResult::Dashboard => {
            // Mark intro as seen for first_run mode
            if config.intro.mode == "first_run" {
                let _ = config::mark_intro_seen();
            }
            println!("MaxPane v0.1.0 — Entering dashboard...");
        }
    }

    Ok(())
}

/// Decide what a key event means for the intro run loop.
///
/// Returns `Some(result)` when the loop should stop and return that result,
/// or `None` to keep the animation running.
///
/// Non-press events are dropped here as well as in `IntroSequence` — Windows
/// Terminal and terminals with the kitty keyboard protocol enabled report a
/// Release for every Press, and an unfiltered loop would act on each
/// keystroke twice.
fn dispatch_key(
    seq: &mut intro::IntroSequence,
    key: crossterm::event::KeyEvent,
) -> Option<intro::IntroResult> {
    if key.kind != crossterm::event::KeyEventKind::Press {
        return None;
    }

    match seq.handle_input(key) {
        intro::IntroAction::Skip => Some(intro::IntroResult::Dashboard),
        // Includes Ctrl+C: raw mode swallows SIGINT, so the interrupt comes
        // back to us as a key event and must break the loop.
        intro::IntroAction::Exit => Some(intro::IntroResult::Exit),
        _ => None,
    }
}

async fn run_intro(
    terminal: &mut ratatui::Terminal<ratatui::backend::CrosstermBackend<std::io::Stdout>>,
    config: &config::IntroConfig,
    theme: &theme::IntroTheme,
) -> Result<intro::IntroResult, Box<dyn std::error::Error>> {
    let size = terminal.size()?;
    let mut seq = intro::IntroSequence::new(config.clone(), theme.clone(), size.width, size.height);
    let mut interval = tokio::time::interval(std::time::Duration::from_millis(33)); // ~30 FPS

    loop {
        interval.tick().await;

        // Non-blocking input poll
        while crossterm::event::poll(std::time::Duration::ZERO)? {
            if let crossterm::event::Event::Key(key) = crossterm::event::read()? {
                if let Some(result) = dispatch_key(&mut seq, key) {
                    return Ok(result);
                }
            }
        }

        // Render
        terminal.draw(|frame| seq.render(frame))?;

        // Tick — IntroSequence::tick() calls advance() internally on NextScreen,
        // so we only need to check for Skip/Exit here.
        match seq.tick() {
            intro::IntroAction::Skip => return Ok(intro::IntroResult::Dashboard),
            intro::IntroAction::Exit => return Ok(intro::IntroResult::Exit),
            _ => {}
        }

        if seq.is_done() {
            return Ok(seq.result());
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crossterm::event::{KeyCode, KeyEvent, KeyEventKind, KeyEventState, KeyModifiers};

    fn seq_with_skip_key(skip_key: &str) -> intro::IntroSequence {
        let cfg = config::IntroConfig {
            skip_key: skip_key.to_string(),
            ..config::IntroConfig::default()
        };
        intro::IntroSequence::new(cfg, theme::phosphor_theme(), 120, 40)
    }

    fn press(code: KeyCode, modifiers: KeyModifiers) -> KeyEvent {
        KeyEvent {
            code,
            modifiers,
            kind: KeyEventKind::Press,
            state: KeyEventState::NONE,
        }
    }

    fn release(code: KeyCode) -> KeyEvent {
        KeyEvent {
            code,
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Release,
            state: KeyEventState::NONE,
        }
    }

    // -- LOW-1: the run loop returns on interrupt -------------------------

    /// Ctrl+C must break the run loop with Exit — not Dashboard, which is
    /// what "any key skips" would otherwise produce.
    #[test]
    fn dispatch_key_returns_exit_on_ctrl_c() {
        for skip_key in ["any", "esc", "none"] {
            let mut seq = seq_with_skip_key(skip_key);
            let result = dispatch_key(&mut seq, press(KeyCode::Char('c'), KeyModifiers::CONTROL));
            assert_eq!(
                result,
                Some(intro::IntroResult::Exit),
                "Ctrl+C should return Exit from the run loop with skip_key = {skip_key:?}"
            );
        }
    }

    /// Ctrl+C on a later screen must break the loop just as it does on the
    /// first one — the whole animation is interruptible.
    #[test]
    fn dispatch_key_returns_exit_on_ctrl_c_on_every_screen() {
        for screens in 0..4 {
            let mut seq = seq_with_skip_key("none");
            for _ in 0..screens {
                seq.advance();
            }
            assert_eq!(
                dispatch_key(&mut seq, press(KeyCode::Char('c'), KeyModifiers::CONTROL)),
                Some(intro::IntroResult::Exit),
                "Ctrl+C should exit on screen {screens}"
            );
        }
    }

    // -- LOW-2: release events are not keystrokes -------------------------

    /// The Release half of a keystroke must not reach the sequence — with
    /// skip_key = "any" the release of the Enter that launched the binary
    /// would otherwise skip the entire intro instantly.
    #[test]
    fn dispatch_key_ignores_key_release() {
        let mut seq = seq_with_skip_key("any");
        assert_eq!(dispatch_key(&mut seq, release(KeyCode::Enter)), None);
        assert!(!seq.is_done());
    }

    /// Auto-repeat is not a fresh keystroke either.
    #[test]
    fn dispatch_key_ignores_key_repeat() {
        let mut seq = seq_with_skip_key("any");
        let repeat = KeyEvent {
            code: KeyCode::Char('x'),
            modifiers: KeyModifiers::NONE,
            kind: KeyEventKind::Repeat,
            state: KeyEventState::NONE,
        };
        assert_eq!(dispatch_key(&mut seq, repeat), None);
        assert!(!seq.is_done());
    }

    /// A real press still skips, so filtering has not broken the feature.
    #[test]
    fn dispatch_key_still_skips_on_press() {
        let mut seq = seq_with_skip_key("any");
        assert_eq!(
            dispatch_key(&mut seq, press(KeyCode::Char('x'), KeyModifiers::NONE)),
            Some(intro::IntroResult::Dashboard)
        );
    }

    /// An ordinary keypress that no screen acts on keeps the loop running.
    #[test]
    fn dispatch_key_returns_none_for_unhandled_press() {
        let mut seq = seq_with_skip_key("none");
        assert_eq!(
            dispatch_key(&mut seq, press(KeyCode::Char('x'), KeyModifiers::NONE)),
            None
        );
    }
}

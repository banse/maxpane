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
                match seq.handle_input(key) {
                    intro::IntroAction::Skip => return Ok(intro::IntroResult::Dashboard),
                    intro::IntroAction::Exit => return Ok(intro::IntroResult::Exit),
                    _ => {}
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

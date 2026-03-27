# MAXPANE Intro Sequence — Product Requirements Document

**Version:** 0.1 (Draft)
**Date:** 2026-03-27
**Scope:** Nur die Boot-/Intro-Sequenz von MAXPANE
**Parent PRD:** MAXPANE_PRD.md

---

## 1. Überblick

Die Intro-Sequenz ist der erste Kontakt des Users mit MAXPANE. Inspiriert von der legendären Matrix-Szene, in der Trinity Neo zum ersten Mal über sein Terminal kontaktiert ("Wake up, Neo..."), wird der User durch eine mehrstufige, animierte Terminal-Sequenz in die MAXPANE-Welt gezogen. Das Intro ist kein Gimmick — es ist Brand Identity. Es setzt den Ton für das gesamte Produkt und ist der primäre virale Moment (Screenshot/Video auf CT).

## 2. Die Sequenz — 5 Screens

### Screen 1 — "Stille" (Typewriter)

Schwarzer Screen. Cursor blinkt. Dann tickern Zeichen einzeln ein, wie jemand in Echtzeit tippt:

```
                        Wake up, anon...

                        The chain has you...

                        Follow the white rabbit.

                        Knock, knock.
```

Jede Zeile erscheint nach einer Pause. Dann: harter Cut zu Schwarz.

### Screen 2 — "Entscheidung" (Prompt)

Ein CLI-Prompt erscheint. Der User gibt tatsächlich Input:

```
        > Do you want to see the chain?
        > [Y/N]: _
```

Bei `Y` oder `Enter`: Text "JACKING IN..." erscheint, dann Cut.
Bei `N`: MAXPANE schliesst sich mit der Nachricht "Maybe next time, anon."
Bei beliebigem anderem Input: "There is no spoon. Try again." → zurück zum Prompt.

### Screen 3 — "Matrix Rain" (Fullscreen Noise)

Der gesamte Bildschirm füllt sich mit fallendem Code-Rain. Die Zeichen sind bewusst aus dem Unicode-Set das auch das MAXPANE-Logo bildet: `╔═║╗╚╝██▓▒░╠╣╬`. Vertikale Spalten fallen mit unterschiedlicher Geschwindigkeit. Dauer: 3-4 Sekunden.

### Screen 4 — "Reveal" (Rain → Logo)

Der Rain verlangsamt sich. In der Mitte des Screens beginnen Zeichen zu "kristallisieren" — sie hören auf zu fallen und formen stattdessen das MAXPANE Block-Font Logo. Von aussen nach innen: erst die Ränder des Logos werden sichtbar, dann füllt es sich. Der umgebende Rain wird dünner und verschwindet.

### Screen 5 — "Clean" (Logo + Tagline)

Nur das Logo. Viel Schwarz. Die Tagline darunter.

**Variante A (English):**
```
          maximize your pane · minimize your pain
```

**Variante B (Katakana):**
```
       マクシマイズ ユア ペーン · ミニマイズ ユア ペイン
```

Mit Rain-Tropfen die von oben/unten verblassen (|). Pause, dann Transition zum Hauptdashboard.

---

## 3. User Stories

1. Als User will ich beim ersten Start von MAXPANE eine unvergessliche Intro-Sequenz erleben, die den Demoscene/Matrix-Vibe des Produkts vermittelt.
2. Als User will ich das Intro überspringen können (ESC oder jede Taste bei Screen 1), weil ich nach dem ersten Mal direkt arbeiten will.
3. Als User will ich in der Config einstellen können ob das Intro bei jedem Start, nur beim ersten Start, oder nie gezeigt wird.
4. Als User will ich dass die Intro-Sequenz sich an meine Terminalgrösse anpasst (responsive).
5. Als User will ich die Tagline-Variante (EN/JP) in der Config wählen können.
6. Als User will ich dass das Intro auch in kleinen Terminal-Fenstern (80x24) funktioniert, mit reduziertem Logo.

---

## 4. Konfiguration

```toml
# ~/.maxpane/config.toml

[intro]
enabled = true              # false = intro komplett aus
mode = "first_run"          # "always" | "first_run" | "never"
tagline = "katakana"        # "english" | "katakana"
skip_key = "any"            # "any" | "esc" | "none" (kein Skip möglich)
rain_duration_ms = 3500     # Dauer des Matrix Rain in Screen 3
typewriter_speed_ms = 45    # Millisekunden pro Zeichen in Screen 1
color_scheme = "phosphor"   # "phosphor" | "amber" | "c64" | "custom"

[intro.colors]
# Nur relevant bei color_scheme = "custom"
text = "#33ff33"
background = "#000000"
rain_bright = "#ffffff"
rain_dim = "#005500"
logo = "#33ff33"
```

---

## 5. Technische Architektur

### 5.1 Tech Stack

| Komponente | Technologie | Warum |
|------------|-------------|-------|
| Sprache | **Rust** (Edition 2021+) | Performance für Frame-by-Frame Animation. Kein GC. MAXPANE Core ist Rust. |
| TUI Framework | **Ratatui** 0.29+ | De-facto Standard für Rust TUIs. Immediate-mode rendering. Crossterm-Backend. |
| Terminal Backend | **Crossterm** | Cross-platform Terminal-Manipulation (Windows, macOS, Linux). Raw mode, event handling. |
| Async Runtime | **Tokio** (single-threaded) | Für Timer, Input-Handling und spätere RPC-Calls. `tokio::time::interval` für Frame-Ticks. |
| RNG | **fastrand** | Leichtgewichtiger PRNG für Rain-Spalten-Geschwindigkeit und Zeichen-Auswahl. Kein crypto-grade nötig. |
| Config | **toml** + **serde** | Config-Parsing aus `~/.maxpane/config.toml`. |

### 5.2 Modul-Struktur

```
maxpane/
├── src/
│   ├── main.rs                 # Entry point, Config laden, Intro starten
│   ├── intro/
│   │   ├── mod.rs              # Intro-Orchestrator (State Machine)
│   │   ├── typewriter.rs       # Screen 1: Character-by-character text
│   │   ├── prompt.rs           # Screen 2: Y/N Input handling
│   │   ├── rain.rs             # Screen 3+4: Matrix Rain + Logo Reveal
│   │   ├── logo.rs             # Screen 5: Static logo display
│   │   ├── animation.rs        # Shared animation primitives (easing, timing)
│   │   └── charset.rs          # Unicode character sets für Rain
│   ├── config.rs               # Config struct + TOML parsing
│   ├── theme.rs                # Color schemes (phosphor, amber, c64)
│   └── terminal.rs             # Terminal setup/teardown, size detection
```

### 5.3 State Machine

Die Intro-Sequenz ist eine lineare State Machine:

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│  Screen1  │───▶│  Screen2  │───▶│  Screen3  │───▶│  Screen4  │───▶│  Screen5  │──▶ Dashboard
│ Typewriter│    │  Prompt   │    │   Rain    │    │  Reveal   │    │   Logo    │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     │               │
     │ ESC/skip       │ 'N'
     ▼               ▼
  Dashboard         Exit
```

```rust
// src/intro/mod.rs

pub enum IntroState {
    Typewriter(TypewriterState),
    Prompt(PromptState),
    Rain(RainState),
    Reveal(RevealState),
    Logo(LogoState),
    Done,
    Exit,
}

pub struct IntroSequence {
    state: IntroState,
    config: IntroConfig,
    start_time: Instant,
}

impl IntroSequence {
    pub fn tick(&mut self, terminal: &mut Terminal<impl Backend>) -> IntroAction {
        match &mut self.state {
            IntroState::Typewriter(s) => s.tick(terminal),
            IntroState::Prompt(s) => s.tick(terminal),
            IntroState::Rain(s) => s.tick(terminal),
            IntroState::Reveal(s) => s.tick(terminal),
            IntroState::Logo(s) => s.tick(terminal),
            _ => IntroAction::Continue,
        }
    }

    pub fn handle_input(&mut self, event: KeyEvent) -> IntroAction {
        // ESC in jedem State → Skip zum Dashboard
        if event.code == KeyCode::Esc {
            return IntroAction::Skip;
        }
        match &mut self.state {
            IntroState::Prompt(s) => s.handle_input(event),
            _ => IntroAction::Continue,
        }
    }
}

pub enum IntroAction {
    Continue,
    NextScreen,
    Skip,       // → Dashboard
    Exit,       // → quit MAXPANE
}
```

### 5.4 Screen 1 — Typewriter Engine

```rust
// src/intro/typewriter.rs

pub struct TypewriterState {
    lines: Vec<TypewriterLine>,
    current_line: usize,
    current_char: usize,
    char_timer: Instant,
    pause_timer: Option<Instant>,
    speed_ms: u64,          // aus config, default 45ms
    line_pause_ms: u64,     // Pause zwischen Zeilen, default 1200ms
    ellipsis_speed_ms: u64, // Langsamere Geschwindigkeit für "..." am Ende
}

struct TypewriterLine {
    text: String,
    position: (u16, u16),   // (x, y) im Terminal
    style: Style,
}
```

**Rendering-Logik:**
- Jedes Zeichen wird einzeln gerendert mit konfigurierbarem Delay (`typewriter_speed_ms`)
- `...` am Ende einer Zeile werden langsamer gerendert (2x `speed_ms`) für dramatischen Effekt
- Zwischen Zeilen: `line_pause_ms` Pause (default 1.2s)
- Cursor blinkt (`▌`) am Ende der aktuellen Zeile, verschwindet wenn nächste Zeile beginnt
- Text ist zentriert basierend auf `terminal.size()`

**Easing:** Linear für einzelne Zeichen. Keine Ease-in/out nötig — der Effekt kommt von den Pausen.

### 5.5 Screen 2 — Interactive Prompt

```rust
// src/intro/prompt.rs

pub struct PromptState {
    phase: PromptPhase,
    input_buffer: String,
    cursor_visible: bool,
    cursor_timer: Instant,
}

enum PromptPhase {
    Question,           // "> Do you want to see the chain?"
    WaitingForInput,    // "> [Y/N]: _"  (blinkender Cursor)
    ResponseY,          // "> JACKING IN..."
    ResponseN,          // "Maybe next time, anon."
    ResponseOther,      // "There is no spoon. Try again."
}
```

**Input-Handling:**
- Akzeptiert: `y`, `Y`, `Enter` → JACKING IN → Screen 3
- Akzeptiert: `n`, `N` → Exit-Nachricht → `IntroAction::Exit`
- Alles andere → Easter Egg Message → Reset zu `WaitingForInput`
- Cursor blinkt mit 530ms Intervall (Standard-Terminal-Cursor-Rate)

### 5.6 Screen 3+4 — Matrix Rain Engine

Das Herzstück der Intro-Sequenz. Rain und Reveal sind ein zusammenhängender Algorithmus mit zwei Phasen.

```rust
// src/intro/rain.rs

pub struct RainState {
    columns: Vec<RainColumn>,
    phase: RainPhase,
    logo_mask: LogoMask,
    frame_count: u64,
    target_fps: u16,            // 30 FPS
    tick_interval: Duration,    // 33.3ms bei 30 FPS
    rain_duration: Duration,    // aus config
    reveal_progress: f32,       // 0.0 → 1.0
}

enum RainPhase {
    FullRain,   // Screen 3: alles fällt
    Revealing,  // Screen 4: Rain löst sich auf, Logo erscheint
    Done,
}

struct RainColumn {
    x: u16,
    chars: Vec<RainChar>,
    speed: f32,             // Zeilen pro Sekunde (variiert 4.0-12.0)
    head_y: f32,            // aktuelle Position des "Kopfes"
    trail_length: u16,      // Länge des Schweifs (5-20)
    active: bool,           // false = Spalte ist im Reveal "eingefroren"
}

struct RainChar {
    char: char,
    brightness: f32,        // 0.0 (dim) → 1.0 (bright)
    frozen: bool,           // true = Teil des Logos, bewegt sich nicht mehr
}
```

**Character Set (charset.rs):**

```rust
// src/intro/charset.rs

pub const RAIN_CHARS: &[char] = &[
    // Box-drawing (auch im Logo verwendet → nahtloser Übergang)
    '╔', '═', '║', '╗', '╚', '╝', '╠', '╣', '╬', '╦', '╩',
    // Block elements
    '█', '▓', '▒', '░', '▄', '▀', '▌', '▐',
    // Katakana (Matrix-Referenz)
    'ア', 'イ', 'ウ', 'エ', 'オ', 'カ', 'キ', 'ク', 'ケ', 'コ',
    'サ', 'シ', 'ス', 'セ', 'ソ', 'タ', 'チ', 'ツ', 'テ', 'ト',
    'ナ', 'ニ', 'ヌ', 'ネ', 'ノ', 'ハ', 'ヒ', 'フ', 'ヘ', 'ホ',
    'マ', 'ミ', 'ム', 'メ', 'モ', 'ヤ', 'ユ', 'ヨ',
    // Zahlen + Symbols
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    ':', '.', '"', '=', '*', '+', '-', '<', '>', '¦',
];

/// Gibt ein zufälliges Rain-Zeichen zurück
pub fn random_rain_char(rng: &mut fastrand::Rng) -> char {
    RAIN_CHARS[rng.usize(..RAIN_CHARS.len())]
}
```

**Rain-Algorithmus (pro Frame, 30 FPS):**

```
1. Für jede aktive RainColumn:
   a. head_y += speed * delta_time
   b. Am head_y: neues zufälliges Zeichen, brightness = 1.0
   c. Alle Zeichen im Trail: brightness *= 0.85 (exponentieller Fade)
   d. Zeichen unter brightness 0.05: entfernen
   e. Zufällig (2% pro Frame): bestehendes Zeichen durch neues ersetzen ("Flicker")

2. Wenn phase == FullRain && elapsed >= rain_duration:
   → Transition zu Revealing

3. Wenn phase == Revealing:
   a. reveal_progress += delta_time / reveal_duration (2.5s total)
   b. Logo-Mask berechnen: Welche Zellen gehören zum Logo?
   c. Von aussen nach innen (basierend auf reveal_progress):
      - Rain-Zeichen an Logo-Positionen "einfrieren" (frozen = true)
      - Frozen chars durch das tatsächliche Logo-Zeichen ersetzen
      - Brightness auf 1.0 setzen
   d. Nicht-Logo Rain-Spalten: speed *= 0.95 (verlangsamen + verschwinden)
   e. Wenn reveal_progress >= 1.0 && alle Non-Logo chars verschwunden → Done
```

**Logo-Mask:**

```rust
// src/intro/rain.rs

struct LogoMask {
    chars: Vec<Vec<Option<char>>>,  // 2D Grid des Logo-ASCII-Arts
    center_x: u16,                   // Zentriert im Terminal
    center_y: u16,
    width: u16,
    height: u16,
}

impl LogoMask {
    /// Berechnet Reveal-Reihenfolge: Distanz von aussen nach innen
    fn reveal_order(&self, x: u16, y: u16) -> f32 {
        let center_x = self.center_x + self.width / 2;
        let center_y = self.center_y + self.height / 2;
        let dx = (x as f32 - center_x as f32).abs();
        let dy = (y as f32 - center_y as f32).abs();
        // Normalisierte Distanz zum Zentrum (0.0 = aussen, 1.0 = mitte)
        1.0 - ((dx * dx + dy * dy).sqrt()
            / ((self.width as f32 / 2.0).powi(2)
                + (self.height as f32 / 2.0).powi(2)).sqrt())
    }

    /// Gibt true zurück wenn Position (x,y) bei gegebenem progress revealed sein soll
    fn is_revealed(&self, x: u16, y: u16, progress: f32) -> bool {
        self.reveal_order(x, y) <= progress
    }
}
```

**Rendering (Ratatui):**

```rust
fn render_rain(frame: &mut Frame, state: &RainState) {
    let area = frame.area();
    let buf = frame.buffer_mut();

    for col in &state.columns {
        for rain_char in &col.chars {
            let x = col.x;
            let y = rain_char.y;
            if x >= area.width || y >= area.height { continue; }

            let color = brightness_to_color(
                rain_char.brightness,
                rain_char.frozen,
                &state.theme,
            );

            buf[(x, y)]
                .set_char(rain_char.char)
                .set_fg(color);
        }
    }
}

fn brightness_to_color(brightness: f32, frozen: bool, theme: &Theme) -> Color {
    if frozen {
        return theme.logo_color; // Volle Logo-Farbe
    }
    // Interpolation: dim_color → bright_color basierend auf brightness
    // Head (brightness 1.0) = weiss/bright
    // Trail = grün/amber mit abnehmendem brightness
    let r = lerp(theme.rain_dim.r, theme.rain_bright.r, brightness);
    let g = lerp(theme.rain_dim.g, theme.rain_bright.g, brightness);
    let b = lerp(theme.rain_dim.b, theme.rain_bright.b, brightness);
    Color::Rgb(r as u8, g as u8, b as u8)
}
```

### 5.7 Screen 5 — Static Logo

```rust
// src/intro/logo.rs

pub struct LogoState {
    tagline_variant: TaglineVariant,
    rain_drops: Vec<RainDrop>,  // Verblassende Tropfen oben/unten
    fade_in_progress: f32,      // 0.0 → 1.0 für sanften Übergang
    hold_duration: Duration,    // 2s halten bevor Transition zum Dashboard
}

enum TaglineVariant {
    English,   // "maximize your pane · minimize your pain"
    Katakana,  // "マクシマイズ ユア ペーン · ミニマイズ ユア ペイン"
}

struct RainDrop {
    x: u16,
    y: u16,
    char: char,     // '|'
    brightness: f32,
    fade_speed: f32,
}
```

**Logo-Daten:**

```rust
pub const LOGO_BLOCK: &str = "\
███╗   ███╗ █████╗ ██╗  ██╗██████╗  █████╗ ███╗   ██╗███████╗
████╗ ████║██╔══██╗╚██╗██╔╝██╔══██╗██╔══██╗████╗  ██║██╔════╝
██╔████╔██║███████║ ╚███╔╝ ██████╔╝███████║██╔██╗ ██║█████╗
██║╚██╔╝██║██╔══██║ ██╔██╗ ██╔═══╝ ██╔══██║██║╚██╗██║██╔══╝
██║ ╚═╝ ██║██║  ██║██╔╝ ██╗██║     ██║  ██║██║ ╚████║███████╗
╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝  ╚═══╝╚══════╝";

pub const TAGLINE_EN: &str = "maximize your pane · minimize your pain";
pub const TAGLINE_JP: &str = "マクシマイズ ユア ペーン · ミニマイズ ユア ペイン";
```

### 5.8 Responsive Layout

```rust
// src/intro/mod.rs

enum LayoutMode {
    Full,       // >= 100x30: volles Logo, voller Rain
    Compact,    // >= 80x24: Logo, reduzierter Rain
    Minimal,    // < 80x24: nur Tagline, kein Logo-Art
}

fn detect_layout(width: u16, height: u16) -> LayoutMode {
    match (width, height) {
        (w, h) if w >= 100 && h >= 30 => LayoutMode::Full,
        (w, h) if w >= 80 && h >= 24 => LayoutMode::Compact,
        _ => LayoutMode::Minimal,
    }
}
```

Compact-Modus: Logo wird ohne "PANE" Teil gezeigt (nur "MAX" + Tagline).
Minimal-Modus: Kein ASCII-Art Logo, nur Text "MAXPANE" + Tagline. Rain hat weniger Spalten.

### 5.9 Color Themes

```rust
// src/theme.rs

pub struct IntroTheme {
    pub background: Color,
    pub text: Color,
    pub rain_bright: Color,     // Head des Rain-Trails
    pub rain_dim: Color,        // Ende des Rain-Trails
    pub logo_color: Color,      // Farbe des enthüllten Logos
    pub tagline_color: Color,
    pub cursor_color: Color,
}

pub fn phosphor_theme() -> IntroTheme {
    IntroTheme {
        background: Color::Rgb(0, 0, 0),
        text: Color::Rgb(51, 255, 51),         // #33ff33
        rain_bright: Color::Rgb(200, 255, 200),
        rain_dim: Color::Rgb(0, 85, 0),        // #005500
        logo_color: Color::Rgb(51, 255, 51),
        tagline_color: Color::Rgb(51, 255, 51),
        cursor_color: Color::Rgb(51, 255, 51),
    }
}

pub fn amber_theme() -> IntroTheme {
    IntroTheme {
        background: Color::Rgb(0, 0, 0),
        text: Color::Rgb(255, 176, 0),         // #ffb000
        rain_bright: Color::Rgb(255, 220, 150),
        rain_dim: Color::Rgb(100, 60, 0),
        logo_color: Color::Rgb(255, 176, 0),
        tagline_color: Color::Rgb(255, 176, 0),
        cursor_color: Color::Rgb(255, 176, 0),
    }
}

pub fn c64_theme() -> IntroTheme {
    IntroTheme {
        background: Color::Rgb(64, 49, 141),   // #40318D
        text: Color::Rgb(108, 94, 181),        // #6C5EB5
        rain_bright: Color::Rgb(160, 150, 220),
        rain_dim: Color::Rgb(64, 49, 141),
        logo_color: Color::Rgb(108, 94, 181),
        tagline_color: Color::Rgb(108, 94, 181),
        cursor_color: Color::Rgb(108, 94, 181),
    }
}
```

### 5.10 Performance Budget

| Metrik | Target | Warum |
|--------|--------|-------|
| Frame Rate | 30 FPS stabil | Flüssige Rain-Animation. 60 FPS unnötig für Terminal. |
| Frame Time | < 33ms | Inclusive Rendering + Input Polling. |
| Memory | < 5 MB | Rain-Buffer für max. 300 Spalten × 100 Zeilen. |
| Startup bis Screen 1 | < 100ms | Config laden, Terminal raw mode, erster Frame. |
| Gesamte Intro-Dauer | ~12-15s | Typewriter 5s + Prompt 1-2s + Rain 3.5s + Reveal 2.5s + Logo Hold 2s. |
| CPU | < 10% single core | Reines Terminal-Rendering, keine GPU. |

### 5.11 Event Loop

```rust
// src/main.rs (vereinfacht)

#[tokio::main(flavor = "current_thread")]
async fn main() -> Result<()> {
    let config = Config::load()?;
    let mut terminal = setup_terminal()?;

    if config.intro.should_show() {
        let result = run_intro(&mut terminal, &config.intro).await?;
        if result == IntroResult::Exit {
            restore_terminal(&mut terminal)?;
            return Ok(());
        }
    }

    // → Dashboard starten
    run_dashboard(&mut terminal, &config).await?;
    restore_terminal(&mut terminal)?;
    Ok(())
}

async fn run_intro(
    terminal: &mut Terminal<CrosstermBackend<Stdout>>,
    config: &IntroConfig,
) -> Result<IntroResult> {
    let mut intro = IntroSequence::new(config);
    let mut interval = tokio::time::interval(Duration::from_millis(33)); // ~30 FPS

    loop {
        interval.tick().await;

        // Input handling (non-blocking)
        while crossterm::event::poll(Duration::ZERO)? {
            if let Event::Key(key) = crossterm::event::read()? {
                match intro.handle_input(key) {
                    IntroAction::Skip => return Ok(IntroResult::Dashboard),
                    IntroAction::Exit => return Ok(IntroResult::Exit),
                    IntroAction::NextScreen => intro.advance(),
                    IntroAction::Continue => {},
                }
            }
        }

        // Tick + Render
        terminal.draw(|frame| intro.render(frame))?;

        match intro.tick() {
            IntroAction::Skip => return Ok(IntroResult::Dashboard),
            IntroAction::Exit => return Ok(IntroResult::Exit),
            _ => {},
        }

        if intro.is_done() {
            return Ok(IntroResult::Dashboard);
        }
    }
}
```

---

## 6. Dependencies (Cargo.toml)

```toml
[package]
name = "maxpane"
version = "0.1.0"
edition = "2021"

[dependencies]
ratatui = "0.29"
crossterm = "0.28"
tokio = { version = "1", features = ["rt", "time", "macros"] }
serde = { version = "1", features = ["derive"] }
toml = "0.8"
fastrand = "2"
dirs = "5"              # für ~/.maxpane/ Pfad
```

Keine weiteren Dependencies für das Intro. Keine HTTP-Clients, keine Blockchain-Libs — das Intro ist pure Terminal-Animation.

---

## 7. Testing-Strategie

| Test | Typ | Was wird getestet |
|------|-----|-------------------|
| State Machine Transitions | Unit | Jeder State → nächster State, ESC → Skip, N → Exit |
| Typewriter Timing | Unit | Korrekte Zeichen-Emission nach `speed_ms` |
| Rain Column Physics | Unit | Speed, Trail-Length, Brightness-Decay |
| Logo Mask Reveal Order | Unit | Aussen→Innen Reihenfolge korrekt |
| Responsive Layout | Unit | Layout-Mode-Detection für verschiedene Terminal-Grössen |
| Config Parsing | Unit | Alle Config-Varianten laden korrekt |
| Full Sequence | Integration | Headless Terminal, kompletter Durchlauf ohne Panic |
| Skip Behavior | Integration | ESC in jedem Screen → sauberer Übergang zu Dashboard |
| Small Terminal | Integration | 80x24 Minimum → kein Overflow, kein Panic |

---

## 8. Entschiedene Fragen

| # | Frage | Entscheidung | Details |
|---|-------|-------------|---------|
| 1 | **Audio** | Phase 2 Feature | Kein Sound im MVP. Später optional via `rodio` Crate mit Chiptune während Rain. Hält den MVP schlank und vermeidet plattformabhängige Probleme. |
| 2 | **Unicode Fallback** | Unicode only (Phase 1), Auto-Detection (Phase 2) | MVP setzt Unicode voraus. In Phase 2: Terminal-Capabilities prüfen und bei fehlendem Unicode automatisch auf vereinfachte Darstellung degraden. |
| 3 | **First-Run Detection** | Flag-File `~/.maxpane/.intro_seen` | Simpel und zuverlässig. Datei existiert = Intro schon gesehen. Wird nach erstem Durchlauf geschrieben. Kein Config-Overhead. |
| 4 | **Transition zum Dashboard** | Harter Cut | Matrix-Film-Stil: Logo Screen → Schwarz → Dashboard. Dramatisch, clean, keine halben Sachen. |
| 5 | **Easter Eggs** | Extensible via Config | Default-Set wird mitgeliefert + User kann eigene in config.toml definieren. Community kann kreativ werden. |

### 5a. First-Run Detection Implementation

```rust
// src/config.rs

use std::path::PathBuf;

fn intro_seen_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_default()
        .join(".maxpane")
        .join(".intro_seen")
}

pub fn has_seen_intro() -> bool {
    intro_seen_path().exists()
}

pub fn mark_intro_seen() -> std::io::Result<()> {
    let path = intro_seen_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, "")
}
```

```rust
// In IntroConfig::should_show()
pub fn should_show(&self) -> bool {
    match self.mode.as_str() {
        "always" => self.enabled,
        "never" => false,
        "first_run" | _ => self.enabled && !has_seen_intro(),
    }
}
```

### 5b. Easter Egg System

**Default Easter Eggs (mitgeliefert):**

| Input | Response |
|-------|----------|
| `n` / `N` | "Maybe next time, anon." → Exit |
| beliebig (default) | "There is no spoon. Try again." → Retry |
| `morpheus` | "I can only show you the door. You're the one that has to walk through it." → Retry |
| `vitalik` | "The merge is complete. Are you ready to see what's next?" → Proceed |
| `gm` | "gm anon. Let's go." → Proceed |
| `wagmi` | "We're all gonna make it. Starting up..." → Proceed |
| `ngmi` | "Not with that attitude. Try again." → Retry |
| `satoshi` | "Chancellor on brink of second bailout for banks." → Proceed |

**Config-Format für custom Easter Eggs:**

```toml
# ~/.maxpane/config.toml

[[intro.easter_eggs]]
input = "hodl"
response = "Diamond hands activated."
action = "proceed"    # "proceed" | "retry" | "exit"

[[intro.easter_eggs]]
input = "rug"
response = "Trust no one. Verify everything."
action = "retry"
```

```rust
// src/intro/prompt.rs

#[derive(Deserialize)]
pub struct EasterEgg {
    pub input: String,
    pub response: String,
    pub action: EasterEggAction,  // Proceed, Retry, Exit
}

impl PromptState {
    fn check_easter_egg(&self, input: &str) -> Option<&EasterEgg> {
        // Custom eggs first (user override), then defaults
        self.config.custom_eggs.iter()
            .chain(DEFAULT_EGGS.iter())
            .find(|egg| egg.input.eq_ignore_ascii_case(input))
    }
}
```

---

*Generated by IdeaRalph · Part of MAXPANE PRD Suite · Alle offenen Fragen geklärt am 2026-03-27*

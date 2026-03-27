use ratatui::style::Color;

/// Color theme for the MAXPANE intro sequence.
///
/// Each field controls a specific visual element across all five intro screens:
/// typewriter text, cursor blink, matrix rain trails, logo reveal, and tagline.
#[derive(Debug, Clone)]
pub struct IntroTheme {
    pub background: Color,
    pub text: Color,
    pub rain_bright: Color,
    pub rain_dim: Color,
    pub logo_color: Color,
    pub tagline_color: Color,
    pub cursor_color: Color,
}

// ---------------------------------------------------------------------------
// Built-in themes (RGB values from PRD section 5.9)
// ---------------------------------------------------------------------------

/// Classic green-on-black phosphor CRT look.
pub fn phosphor_theme() -> IntroTheme {
    IntroTheme {
        background: Color::Rgb(0, 0, 0),
        text: Color::Rgb(51, 255, 51),
        rain_bright: Color::Rgb(200, 255, 200),
        rain_dim: Color::Rgb(0, 85, 0),
        logo_color: Color::Rgb(51, 255, 51),
        tagline_color: Color::Rgb(51, 255, 51),
        cursor_color: Color::Rgb(51, 255, 51),
    }
}

/// Warm amber CRT monitor look.
pub fn amber_theme() -> IntroTheme {
    IntroTheme {
        background: Color::Rgb(0, 0, 0),
        text: Color::Rgb(255, 176, 0),
        rain_bright: Color::Rgb(255, 220, 150),
        rain_dim: Color::Rgb(100, 60, 0),
        logo_color: Color::Rgb(255, 176, 0),
        tagline_color: Color::Rgb(255, 176, 0),
        cursor_color: Color::Rgb(255, 176, 0),
    }
}

/// Commodore 64 inspired palette.
pub fn c64_theme() -> IntroTheme {
    IntroTheme {
        background: Color::Rgb(64, 49, 141),
        text: Color::Rgb(108, 94, 181),
        rain_bright: Color::Rgb(160, 150, 220),
        rain_dim: Color::Rgb(64, 49, 141),
        logo_color: Color::Rgb(108, 94, 181),
        tagline_color: Color::Rgb(108, 94, 181),
        cursor_color: Color::Rgb(108, 94, 181),
    }
}

// ---------------------------------------------------------------------------
// Hex color parsing
// ---------------------------------------------------------------------------

/// Parse a `#RRGGBB` hex string into a [`Color::Rgb`].
///
/// Returns `None` when the input is not exactly 7 characters starting with `#`
/// or contains non-hex digits.
pub fn parse_hex_color(hex: &str) -> Option<Color> {
    let hex = hex.strip_prefix('#')?;
    if hex.len() != 6 {
        return None;
    }
    let r = u8::from_str_radix(&hex[0..2], 16).ok()?;
    let g = u8::from_str_radix(&hex[2..4], 16).ok()?;
    let b = u8::from_str_radix(&hex[4..6], 16).ok()?;
    Some(Color::Rgb(r, g, b))
}

// ---------------------------------------------------------------------------
// Theme construction from config strings
// ---------------------------------------------------------------------------

/// Build an [`IntroTheme`] from user-facing config values.
///
/// `color_scheme` selects a built-in theme (`"phosphor"`, `"amber"`, `"c64"`)
/// or `"custom"`. For custom schemes the optional hex parameters override
/// individual fields; any `None` or unparseable value falls back to the
/// phosphor default for that field. Unknown scheme names also fall back to
/// phosphor.
pub fn theme_from_config(
    color_scheme: &str,
    custom_text: Option<&str>,
    custom_bg: Option<&str>,
    custom_rain_bright: Option<&str>,
    custom_rain_dim: Option<&str>,
    custom_logo: Option<&str>,
) -> IntroTheme {
    match color_scheme {
        "phosphor" => phosphor_theme(),
        "amber" => amber_theme(),
        "c64" => c64_theme(),
        "custom" => {
            let base = phosphor_theme();
            let text = custom_text
                .and_then(parse_hex_color)
                .unwrap_or(base.text);
            let bg = custom_bg
                .and_then(parse_hex_color)
                .unwrap_or(base.background);
            let rain_bright = custom_rain_bright
                .and_then(parse_hex_color)
                .unwrap_or(base.rain_bright);
            let rain_dim = custom_rain_dim
                .and_then(parse_hex_color)
                .unwrap_or(base.rain_dim);
            let logo = custom_logo
                .and_then(parse_hex_color)
                .unwrap_or(base.logo_color);

            IntroTheme {
                background: bg,
                text,
                rain_bright,
                rain_dim,
                logo_color: logo,
                tagline_color: text,
                cursor_color: text,
            }
        }
        _ => phosphor_theme(), // unknown scheme falls back to phosphor
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use ratatui::style::Color;

    // -- Helper to unwrap Rgb values for assertions --

    fn rgb(c: Color) -> (u8, u8, u8) {
        match c {
            Color::Rgb(r, g, b) => (r, g, b),
            other => panic!("expected Color::Rgb, got {:?}", other),
        }
    }

    // -- Built-in theme correctness -------------------------------------------

    #[test]
    fn phosphor_theme_has_correct_values() {
        let t = phosphor_theme();
        assert_eq!(rgb(t.background), (0, 0, 0));
        assert_eq!(rgb(t.text), (51, 255, 51));
        assert_eq!(rgb(t.rain_bright), (200, 255, 200));
        assert_eq!(rgb(t.rain_dim), (0, 85, 0));
        assert_eq!(rgb(t.logo_color), (51, 255, 51));
        assert_eq!(rgb(t.tagline_color), (51, 255, 51));
        assert_eq!(rgb(t.cursor_color), (51, 255, 51));
    }

    #[test]
    fn amber_theme_has_correct_values() {
        let t = amber_theme();
        assert_eq!(rgb(t.background), (0, 0, 0));
        assert_eq!(rgb(t.text), (255, 176, 0));
        assert_eq!(rgb(t.rain_bright), (255, 220, 150));
        assert_eq!(rgb(t.rain_dim), (100, 60, 0));
        assert_eq!(rgb(t.logo_color), (255, 176, 0));
        assert_eq!(rgb(t.tagline_color), (255, 176, 0));
        assert_eq!(rgb(t.cursor_color), (255, 176, 0));
    }

    #[test]
    fn c64_theme_has_correct_values() {
        let t = c64_theme();
        assert_eq!(rgb(t.background), (64, 49, 141));
        assert_eq!(rgb(t.text), (108, 94, 181));
        assert_eq!(rgb(t.rain_bright), (160, 150, 220));
        assert_eq!(rgb(t.rain_dim), (64, 49, 141));
        assert_eq!(rgb(t.logo_color), (108, 94, 181));
        assert_eq!(rgb(t.tagline_color), (108, 94, 181));
        assert_eq!(rgb(t.cursor_color), (108, 94, 181));
    }

    // -- Hex parsing ----------------------------------------------------------

    #[test]
    fn parse_hex_valid() {
        assert_eq!(parse_hex_color("#33ff33"), Some(Color::Rgb(51, 255, 51)));
        assert_eq!(parse_hex_color("#000000"), Some(Color::Rgb(0, 0, 0)));
        assert_eq!(parse_hex_color("#FFAA00"), Some(Color::Rgb(255, 170, 0)));
    }

    #[test]
    fn parse_hex_missing_hash() {
        assert_eq!(parse_hex_color("33ff33"), None);
    }

    #[test]
    fn parse_hex_invalid_chars() {
        assert_eq!(parse_hex_color("#xyzxyz"), None);
    }

    #[test]
    fn parse_hex_empty() {
        assert_eq!(parse_hex_color(""), None);
    }

    #[test]
    fn parse_hex_wrong_length() {
        assert_eq!(parse_hex_color("#fff"), None);
        assert_eq!(parse_hex_color("#1234567"), None);
    }

    // -- theme_from_config dispatch -------------------------------------------

    #[test]
    fn config_dispatches_phosphor() {
        let t = theme_from_config("phosphor", None, None, None, None, None);
        assert_eq!(rgb(t.text), (51, 255, 51));
    }

    #[test]
    fn config_dispatches_amber() {
        let t = theme_from_config("amber", None, None, None, None, None);
        assert_eq!(rgb(t.text), (255, 176, 0));
    }

    #[test]
    fn config_dispatches_c64() {
        let t = theme_from_config("c64", None, None, None, None, None);
        assert_eq!(rgb(t.background), (64, 49, 141));
    }

    #[test]
    fn config_unknown_scheme_falls_back_to_phosphor() {
        let t = theme_from_config("vaporwave", None, None, None, None, None);
        assert_eq!(rgb(t.text), (51, 255, 51));
    }

    // -- Custom theme ---------------------------------------------------------

    #[test]
    fn config_custom_full() {
        let t = theme_from_config(
            "custom",
            Some("#ff0000"),
            Some("#0000ff"),
            Some("#ffffff"),
            Some("#111111"),
            Some("#00ff00"),
        );
        assert_eq!(rgb(t.text), (255, 0, 0));
        assert_eq!(rgb(t.background), (0, 0, 255));
        assert_eq!(rgb(t.rain_bright), (255, 255, 255));
        assert_eq!(rgb(t.rain_dim), (17, 17, 17));
        assert_eq!(rgb(t.logo_color), (0, 255, 0));
        // tagline and cursor derive from text color
        assert_eq!(rgb(t.tagline_color), (255, 0, 0));
        assert_eq!(rgb(t.cursor_color), (255, 0, 0));
    }

    #[test]
    fn config_custom_partial_uses_phosphor_defaults() {
        let t = theme_from_config(
            "custom",
            Some("#ff0000"), // only text overridden
            None,            // bg -> phosphor default
            None,            // rain_bright -> phosphor default
            None,            // rain_dim -> phosphor default
            None,            // logo -> phosphor default
        );
        assert_eq!(rgb(t.text), (255, 0, 0));
        assert_eq!(rgb(t.background), (0, 0, 0));            // phosphor default
        assert_eq!(rgb(t.rain_bright), (200, 255, 200));      // phosphor default
        assert_eq!(rgb(t.rain_dim), (0, 85, 0));              // phosphor default
        assert_eq!(rgb(t.logo_color), (51, 255, 51));         // phosphor default
    }

    #[test]
    fn config_custom_invalid_hex_uses_phosphor_defaults() {
        let t = theme_from_config(
            "custom",
            Some("not-a-color"),
            Some("#zzzzzz"),
            None,
            None,
            None,
        );
        // All should be phosphor defaults since hex parsing fails
        assert_eq!(rgb(t.text), (51, 255, 51));
        assert_eq!(rgb(t.background), (0, 0, 0));
    }
}

use serde::Deserialize;
use std::path::PathBuf;

// ---------------------------------------------------------------------------
// Top-level Config
// ---------------------------------------------------------------------------

#[derive(Debug, Deserialize)]
pub struct Config {
    #[serde(default)]
    pub intro: IntroConfig,
}

impl Config {
    /// Load configuration from `~/.maxpane/config.toml`.
    ///
    /// - If the file does not exist, returns all defaults (no error).
    /// - If the file exists but has parse errors, returns an error.
    pub fn load() -> Result<Self, ConfigError> {
        let path = config_path();
        if !path.exists() {
            return Ok(Config::default());
        }
        let contents = std::fs::read_to_string(&path)
            .map_err(|e| ConfigError::Io(path.clone(), e))?;
        let config: Config =
            toml::from_str(&contents).map_err(|e| ConfigError::Parse(path.clone(), e))?;
        Ok(config)
    }
}

impl Default for Config {
    fn default() -> Self {
        Self {
            intro: IntroConfig::default(),
        }
    }
}

// ---------------------------------------------------------------------------
// IntroConfig
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct IntroConfig {
    #[serde(default = "default_true")]
    pub enabled: bool,

    #[serde(default = "default_mode")]
    pub mode: String,

    #[serde(default = "default_tagline")]
    pub tagline: String,

    #[serde(default = "default_skip_key")]
    pub skip_key: String,

    #[serde(default = "default_rain_duration_ms")]
    pub rain_duration_ms: u64,

    #[serde(default = "default_typewriter_speed_ms")]
    pub typewriter_speed_ms: u64,

    #[serde(default = "default_color_scheme")]
    pub color_scheme: String,

    #[serde(default)]
    pub colors: Option<CustomColors>,

    #[serde(default)]
    pub easter_eggs: Vec<EasterEgg>,
}

impl Default for IntroConfig {
    fn default() -> Self {
        Self {
            enabled: true,
            mode: "first_run".to_string(),
            tagline: "katakana".to_string(),
            skip_key: "any".to_string(),
            rain_duration_ms: 3500,
            typewriter_speed_ms: 45,
            color_scheme: "phosphor".to_string(),
            colors: None,
            easter_eggs: Vec::new(),
        }
    }
}

impl IntroConfig {
    /// Determine whether the intro sequence should be shown based on the
    /// current configuration and first-run state.
    pub fn should_show(&self) -> bool {
        match self.mode.as_str() {
            "always" => self.enabled,
            "never" => false,
            // "first_run" and any unrecognised value fall through here
            _ => self.enabled && !has_seen_intro(),
        }
    }
}

// ---------------------------------------------------------------------------
// CustomColors
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct CustomColors {
    pub text: Option<String>,
    pub background: Option<String>,
    pub rain_bright: Option<String>,
    pub rain_dim: Option<String>,
    pub logo: Option<String>,
}

// ---------------------------------------------------------------------------
// EasterEgg
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Deserialize)]
pub struct EasterEgg {
    pub input: String,
    pub response: String,
    pub action: String, // "proceed" | "retry" | "exit"
}

// ---------------------------------------------------------------------------
// First-run detection
// ---------------------------------------------------------------------------

fn intro_seen_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_default()
        .join(".maxpane")
        .join(".intro_seen")
}

/// Returns `true` if the intro has already been shown (flag file exists).
pub fn has_seen_intro() -> bool {
    intro_seen_path().exists()
}

/// Create the flag file that records the intro has been shown.
/// Parent directories are created automatically.
pub fn mark_intro_seen() -> std::io::Result<()> {
    let path = intro_seen_path();
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }
    std::fs::write(path, "")
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

fn config_path() -> PathBuf {
    dirs::home_dir()
        .unwrap_or_default()
        .join(".maxpane")
        .join("config.toml")
}

fn default_true() -> bool {
    true
}
fn default_mode() -> String {
    "first_run".to_string()
}
fn default_tagline() -> String {
    "katakana".to_string()
}
fn default_skip_key() -> String {
    "any".to_string()
}
fn default_rain_duration_ms() -> u64 {
    3500
}
fn default_typewriter_speed_ms() -> u64 {
    45
}
fn default_color_scheme() -> String {
    "phosphor".to_string()
}

// ---------------------------------------------------------------------------
// Error type
// ---------------------------------------------------------------------------

#[derive(Debug)]
pub enum ConfigError {
    Io(PathBuf, std::io::Error),
    Parse(PathBuf, toml::de::Error),
}

impl std::fmt::Display for ConfigError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ConfigError::Io(path, err) => {
                write!(f, "failed to read config at {}: {}", path.display(), err)
            }
            ConfigError::Parse(path, err) => {
                write!(f, "failed to parse config at {}: {}", path.display(), err)
            }
        }
    }
}

impl std::error::Error for ConfigError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ConfigError::Io(_, err) => Some(err),
            ConfigError::Parse(_, err) => Some(err),
        }
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    // -- Default values ---------------------------------------------------

    #[test]
    fn test_default_intro_config() {
        let cfg = IntroConfig::default();
        assert!(cfg.enabled);
        assert_eq!(cfg.mode, "first_run");
        assert_eq!(cfg.tagline, "katakana");
        assert_eq!(cfg.skip_key, "any");
        assert_eq!(cfg.rain_duration_ms, 3500);
        assert_eq!(cfg.typewriter_speed_ms, 45);
        assert_eq!(cfg.color_scheme, "phosphor");
        assert!(cfg.colors.is_none());
        assert!(cfg.easter_eggs.is_empty());
    }

    #[test]
    fn test_default_config() {
        let cfg = Config::default();
        assert!(cfg.intro.enabled);
        assert_eq!(cfg.intro.mode, "first_run");
    }

    // -- TOML parsing -----------------------------------------------------

    #[test]
    fn test_parse_full_config() {
        let toml_str = r##"
[intro]
enabled = false
mode = "always"
tagline = "english"
skip_key = "esc"
rain_duration_ms = 5000
typewriter_speed_ms = 30
color_scheme = "custom"

[intro.colors]
text = "#33ff33"
background = "#000000"
rain_bright = "#ffffff"
rain_dim = "#005500"
logo = "#33ff33"

[[intro.easter_eggs]]
input = "hodl"
response = "Diamond hands activated."
action = "proceed"

[[intro.easter_eggs]]
input = "rug"
response = "Trust no one."
action = "retry"
"##;
        let cfg: Config = toml::from_str(toml_str).expect("failed to parse full config");
        assert!(!cfg.intro.enabled);
        assert_eq!(cfg.intro.mode, "always");
        assert_eq!(cfg.intro.tagline, "english");
        assert_eq!(cfg.intro.skip_key, "esc");
        assert_eq!(cfg.intro.rain_duration_ms, 5000);
        assert_eq!(cfg.intro.typewriter_speed_ms, 30);
        assert_eq!(cfg.intro.color_scheme, "custom");

        let colors = cfg.intro.colors.as_ref().expect("colors should be Some");
        assert_eq!(colors.text.as_deref(), Some("#33ff33"));
        assert_eq!(colors.background.as_deref(), Some("#000000"));
        assert_eq!(colors.rain_bright.as_deref(), Some("#ffffff"));
        assert_eq!(colors.rain_dim.as_deref(), Some("#005500"));
        assert_eq!(colors.logo.as_deref(), Some("#33ff33"));

        assert_eq!(cfg.intro.easter_eggs.len(), 2);
        assert_eq!(cfg.intro.easter_eggs[0].input, "hodl");
        assert_eq!(cfg.intro.easter_eggs[0].response, "Diamond hands activated.");
        assert_eq!(cfg.intro.easter_eggs[0].action, "proceed");
        assert_eq!(cfg.intro.easter_eggs[1].input, "rug");
        assert_eq!(cfg.intro.easter_eggs[1].action, "retry");
    }

    #[test]
    fn test_parse_minimal_config() {
        let toml_str = "[intro]\n";
        let cfg: Config = toml::from_str(toml_str).expect("failed to parse minimal config");
        // All defaults should apply
        assert!(cfg.intro.enabled);
        assert_eq!(cfg.intro.mode, "first_run");
        assert_eq!(cfg.intro.tagline, "katakana");
    }

    #[test]
    fn test_parse_empty_config() {
        let toml_str = "";
        let cfg: Config = toml::from_str(toml_str).expect("failed to parse empty config");
        assert!(cfg.intro.enabled);
        assert_eq!(cfg.intro.mode, "first_run");
    }

    #[test]
    fn test_parse_partial_colors() {
        let toml_str = r##"
[intro.colors]
text = "#ff0000"
"##;
        let cfg: Config = toml::from_str(toml_str).expect("failed to parse partial colors");
        let colors = cfg.intro.colors.as_ref().expect("colors should be Some");
        assert_eq!(colors.text.as_deref(), Some("#ff0000"));
        assert!(colors.background.is_none());
        assert!(colors.rain_bright.is_none());
        assert!(colors.rain_dim.is_none());
        assert!(colors.logo.is_none());
    }

    // -- should_show() ----------------------------------------------------

    #[test]
    fn test_should_show_always_enabled() {
        let cfg = IntroConfig {
            enabled: true,
            mode: "always".to_string(),
            ..IntroConfig::default()
        };
        assert!(cfg.should_show());
    }

    #[test]
    fn test_should_show_always_disabled() {
        let cfg = IntroConfig {
            enabled: false,
            mode: "always".to_string(),
            ..IntroConfig::default()
        };
        assert!(!cfg.should_show());
    }

    #[test]
    fn test_should_show_never() {
        let cfg = IntroConfig {
            enabled: true,
            mode: "never".to_string(),
            ..IntroConfig::default()
        };
        assert!(!cfg.should_show());
    }

    #[test]
    fn test_should_show_never_even_if_enabled() {
        let cfg = IntroConfig {
            enabled: true,
            mode: "never".to_string(),
            ..IntroConfig::default()
        };
        assert!(!cfg.should_show());
    }

    // Note: first_run mode depends on the filesystem (.intro_seen file),
    // so we test the logic indirectly. When has_seen_intro() returns false
    // (no flag file), first_run + enabled = true.
    #[test]
    fn test_should_show_first_run_enabled_depends_on_flag() {
        let cfg = IntroConfig {
            enabled: true,
            mode: "first_run".to_string(),
            ..IntroConfig::default()
        };
        // Result depends on whether ~/.maxpane/.intro_seen exists.
        // We verify the logic is consistent: enabled && !has_seen_intro()
        let expected = !has_seen_intro();
        assert_eq!(cfg.should_show(), expected);
    }

    #[test]
    fn test_should_show_first_run_disabled() {
        let cfg = IntroConfig {
            enabled: false,
            mode: "first_run".to_string(),
            ..IntroConfig::default()
        };
        // disabled always means false regardless of flag file
        assert!(!cfg.should_show());
    }

    // -- Easter egg deserialization ---------------------------------------

    #[test]
    fn test_easter_egg_deserialization() {
        let toml_str = r#"
[[intro.easter_eggs]]
input = "gm"
response = "gm anon. Let's go."
action = "proceed"

[[intro.easter_eggs]]
input = "ngmi"
response = "Not with that attitude."
action = "exit"
"#;
        let cfg: Config = toml::from_str(toml_str).expect("failed to parse easter eggs");
        assert_eq!(cfg.intro.easter_eggs.len(), 2);

        let egg = &cfg.intro.easter_eggs[0];
        assert_eq!(egg.input, "gm");
        assert_eq!(egg.response, "gm anon. Let's go.");
        assert_eq!(egg.action, "proceed");

        let egg = &cfg.intro.easter_eggs[1];
        assert_eq!(egg.input, "ngmi");
        assert_eq!(egg.action, "exit");
    }

    #[test]
    fn test_easter_egg_clone() {
        let egg = EasterEgg {
            input: "test".to_string(),
            response: "response".to_string(),
            action: "retry".to_string(),
        };
        let cloned = egg.clone();
        assert_eq!(cloned.input, "test");
        assert_eq!(cloned.response, "response");
        assert_eq!(cloned.action, "retry");
    }

    // -- Config::load() with missing file ---------------------------------

    #[test]
    fn test_load_missing_file_returns_defaults() {
        // Config::load() reads from ~/.maxpane/config.toml.
        // If the file doesn't exist on this machine, we get defaults.
        // This test is environment-dependent but should not fail.
        let result = Config::load();
        assert!(result.is_ok());
    }

    // -- ConfigError display ----------------------------------------------

    #[test]
    fn test_config_error_display() {
        let err = ConfigError::Io(
            PathBuf::from("/tmp/test.toml"),
            std::io::Error::new(std::io::ErrorKind::NotFound, "not found"),
        );
        let msg = format!("{}", err);
        assert!(msg.contains("/tmp/test.toml"));
        assert!(msg.contains("not found"));
    }
}

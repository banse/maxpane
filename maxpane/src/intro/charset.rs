// Character set definitions for intro rendering.
//
// Defines the Unicode character pools used by the Matrix rain effect.
// Two variants are provided: a full set (including double-width Katakana)
// and a single-width-only fallback for terminals that cannot handle
// double-width characters.

/// Full rain character set including double-width Katakana.
pub const RAIN_CHARS: &[char] = &[
    // Box-drawing (also used in the logo for seamless reveal transition)
    '╔', '═', '║', '╗', '╚', '╝', '╠', '╣', '╬', '╦', '╩',
    // Block elements
    '█', '▓', '▒', '░', '▄', '▀', '▌', '▐',
    // Katakana (Matrix reference)
    'ア', 'イ', 'ウ', 'エ', 'オ', 'カ', 'キ', 'ク', 'ケ', 'コ',
    'サ', 'シ', 'ス', 'セ', 'ソ', 'タ', 'チ', 'ツ', 'テ', 'ト',
    'ナ', 'ニ', 'ヌ', 'ネ', 'ノ', 'ハ', 'ヒ', 'フ', 'ヘ', 'ホ',
    'マ', 'ミ', 'ム', 'メ', 'モ', 'ヤ', 'ユ', 'ヨ',
    // Digits + symbols
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    ':', '.', '"', '=', '*', '+', '-', '<', '>', '¦',
];

/// Single-width rain characters only (no Katakana).
///
/// Use this set when the terminal or layout mode cannot handle double-width
/// characters, for example in compact column layouts where a double-width
/// glyph would overflow into the adjacent column.
pub const RAIN_CHARS_SINGLE_WIDTH: &[char] = &[
    // Box-drawing
    '╔', '═', '║', '╗', '╚', '╝', '╠', '╣', '╬', '╦', '╩',
    // Block elements
    '█', '▓', '▒', '░', '▄', '▀', '▌', '▐',
    // Digits + symbols
    '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
    ':', '.', '"', '=', '*', '+', '-', '<', '>', '¦',
];

/// Returns a random character from the full rain set (including Katakana).
pub fn random_rain_char(rng: &mut fastrand::Rng) -> char {
    RAIN_CHARS[rng.usize(..RAIN_CHARS.len())]
}

/// Returns a random character from the single-width rain set (no Katakana).
pub fn random_rain_char_single_width(rng: &mut fastrand::Rng) -> char {
    RAIN_CHARS_SINGLE_WIDTH[rng.usize(..RAIN_CHARS_SINGLE_WIDTH.len())]
}

#[cfg(test)]
mod tests {
    use super::*;

    // 11 box-drawing + 8 block + 38 katakana + 10 digits + 10 symbols = 77
    const EXPECTED_RAIN_CHARS_LEN: usize = 77;
    // 11 box-drawing + 8 block + 10 digits + 10 symbols = 39
    const EXPECTED_SINGLE_WIDTH_LEN: usize = 39;

    #[test]
    fn rain_chars_has_expected_length() {
        assert_eq!(
            RAIN_CHARS.len(),
            EXPECTED_RAIN_CHARS_LEN,
            "RAIN_CHARS should contain exactly {} characters, got {}",
            EXPECTED_RAIN_CHARS_LEN,
            RAIN_CHARS.len(),
        );
    }

    #[test]
    fn rain_chars_single_width_has_expected_length() {
        assert_eq!(
            RAIN_CHARS_SINGLE_WIDTH.len(),
            EXPECTED_SINGLE_WIDTH_LEN,
            "RAIN_CHARS_SINGLE_WIDTH should contain exactly {} characters, got {}",
            EXPECTED_SINGLE_WIDTH_LEN,
            RAIN_CHARS_SINGLE_WIDTH.len(),
        );
    }

    #[test]
    fn single_width_is_subset_of_full() {
        for &ch in RAIN_CHARS_SINGLE_WIDTH {
            assert!(
                RAIN_CHARS.contains(&ch),
                "Single-width char {:?} is not in RAIN_CHARS",
                ch,
            );
        }
    }

    #[test]
    fn single_width_contains_no_katakana() {
        let katakana_range = '\u{30A0}'..='\u{30FF}';
        for &ch in RAIN_CHARS_SINGLE_WIDTH {
            assert!(
                !katakana_range.contains(&ch),
                "Single-width set should not contain Katakana char {:?}",
                ch,
            );
        }
    }

    #[test]
    fn rain_chars_contains_expected_categories() {
        // Box-drawing
        assert!(RAIN_CHARS.contains(&'╔'));
        assert!(RAIN_CHARS.contains(&'╬'));
        assert!(RAIN_CHARS.contains(&'╩'));
        // Block elements
        assert!(RAIN_CHARS.contains(&'█'));
        assert!(RAIN_CHARS.contains(&'░'));
        assert!(RAIN_CHARS.contains(&'▐'));
        // Katakana
        assert!(RAIN_CHARS.contains(&'ア'));
        assert!(RAIN_CHARS.contains(&'ヨ'));
        // Digits
        assert!(RAIN_CHARS.contains(&'0'));
        assert!(RAIN_CHARS.contains(&'9'));
        // Symbols
        assert!(RAIN_CHARS.contains(&'¦'));
        assert!(RAIN_CHARS.contains(&'<'));
        assert!(RAIN_CHARS.contains(&'>'));
    }

    #[test]
    fn random_rain_char_returns_valid_chars() {
        let mut rng = fastrand::Rng::with_seed(42);
        for _ in 0..1000 {
            let ch = random_rain_char(&mut rng);
            assert!(
                RAIN_CHARS.contains(&ch),
                "random_rain_char returned {:?} which is not in RAIN_CHARS",
                ch,
            );
        }
    }

    #[test]
    fn random_rain_char_single_width_returns_valid_chars() {
        let mut rng = fastrand::Rng::with_seed(42);
        for _ in 0..1000 {
            let ch = random_rain_char_single_width(&mut rng);
            assert!(
                RAIN_CHARS_SINGLE_WIDTH.contains(&ch),
                "random_rain_char_single_width returned {:?} which is not in RAIN_CHARS_SINGLE_WIDTH",
                ch,
            );
        }
    }

    #[test]
    fn no_duplicate_chars_in_rain_chars() {
        let mut seen = std::collections::HashSet::new();
        for &ch in RAIN_CHARS {
            assert!(seen.insert(ch), "Duplicate char {:?} in RAIN_CHARS", ch);
        }
    }

    #[test]
    fn no_duplicate_chars_in_single_width() {
        let mut seen = std::collections::HashSet::new();
        for &ch in RAIN_CHARS_SINGLE_WIDTH {
            assert!(
                seen.insert(ch),
                "Duplicate char {:?} in RAIN_CHARS_SINGLE_WIDTH",
                ch,
            );
        }
    }
}

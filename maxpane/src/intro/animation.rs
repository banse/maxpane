// Animation primitives for intro sequence: easing, interpolation, color mapping.

use ratatui::style::Color;

/// Linear interpolation between two f32 values.
#[inline]
pub fn lerp(a: f32, b: f32, t: f32) -> f32 {
    a + (b - a) * t
}

/// Linear interpolation for u8 values, clamped to 0..=255.
#[inline]
pub fn lerp_u8(a: u8, b: u8, t: f32) -> u8 {
    let result = a as f32 + (b as f32 - a as f32) * t;
    result.round().clamp(0.0, 255.0) as u8
}

/// Quadratic ease-out (decelerating). Input clamped to 0..=1.
#[inline]
pub fn ease_out_quad(t: f32) -> f32 {
    let t = t.clamp(0.0, 1.0);
    1.0 - (1.0 - t) * (1.0 - t)
}

/// Cubic ease-in (accelerating). Input clamped to 0..=1.
#[inline]
pub fn ease_in_cubic(t: f32) -> f32 {
    let t = t.clamp(0.0, 1.0);
    t * t * t
}

/// Maps a brightness value (0.0–1.0) to a terminal color.
///
/// If `frozen` is true, returns `logo_color` directly (the cell is part of the
/// crystallised logo). Otherwise interpolates each RGB channel between
/// `rain_dim` and `rain_bright` using `brightness` as the interpolation factor.
///
/// Falls back to a simple threshold when the supplied colors are not
/// `Color::Rgb` variants.
pub fn brightness_to_color(
    brightness: f32,
    frozen: bool,
    rain_dim: Color,
    rain_bright: Color,
    logo_color: Color,
) -> Color {
    if frozen {
        return logo_color;
    }

    // Extract RGB channels; fall back to threshold selection for non-Rgb colors.
    let (dim_r, dim_g, dim_b) = match rain_dim {
        Color::Rgb(r, g, b) => (r, g, b),
        _ => {
            return if brightness > 0.5 {
                rain_bright
            } else {
                rain_dim
            };
        }
    };

    let (bright_r, bright_g, bright_b) = match rain_bright {
        Color::Rgb(r, g, b) => (r, g, b),
        _ => {
            return if brightness > 0.5 {
                rain_bright
            } else {
                rain_dim
            };
        }
    };

    Color::Rgb(
        lerp_u8(dim_r, bright_r, brightness),
        lerp_u8(dim_g, bright_g, brightness),
        lerp_u8(dim_b, bright_b, brightness),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    // ---- lerp ----

    #[test]
    fn lerp_midpoint() {
        assert!((lerp(0.0, 10.0, 0.5) - 5.0).abs() < f32::EPSILON);
    }

    #[test]
    fn lerp_start() {
        assert!((lerp(0.0, 10.0, 0.0) - 0.0).abs() < f32::EPSILON);
    }

    #[test]
    fn lerp_end() {
        assert!((lerp(0.0, 10.0, 1.0) - 10.0).abs() < f32::EPSILON);
    }

    // ---- lerp_u8 ----

    #[test]
    fn lerp_u8_midpoint() {
        let v = lerp_u8(0, 255, 0.5);
        // 127.5 rounds to 128
        assert!(v == 127 || v == 128, "got {v}");
    }

    #[test]
    fn lerp_u8_clamps_high() {
        // t=2.0 would give 200 unclamped, but result is clamped to 255
        let v = lerp_u8(0, 100, 2.0);
        assert!(v <= 200, "got {v}");
        // The raw calc: 0 + 100*2 = 200, clamped to 255 max → 200 fits in u8
        assert_eq!(v, 200);
    }

    #[test]
    fn lerp_u8_clamps_to_255() {
        // Demonstrate the 255 ceiling
        let v = lerp_u8(0, 200, 2.0);
        assert_eq!(v, 255);
    }

    // ---- ease_out_quad ----

    #[test]
    fn ease_out_quad_boundaries() {
        assert!((ease_out_quad(0.0) - 0.0).abs() < f32::EPSILON);
        assert!((ease_out_quad(1.0) - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn ease_out_quad_midpoint() {
        // At t=0.5: 1 - (0.5)^2 = 0.75
        assert!((ease_out_quad(0.5) - 0.75).abs() < f32::EPSILON);
    }

    #[test]
    fn ease_out_quad_clamps_input() {
        assert!((ease_out_quad(-1.0) - 0.0).abs() < f32::EPSILON);
        assert!((ease_out_quad(2.0) - 1.0).abs() < f32::EPSILON);
    }

    // ---- ease_in_cubic ----

    #[test]
    fn ease_in_cubic_boundaries() {
        assert!((ease_in_cubic(0.0) - 0.0).abs() < f32::EPSILON);
        assert!((ease_in_cubic(1.0) - 1.0).abs() < f32::EPSILON);
    }

    #[test]
    fn ease_in_cubic_midpoint() {
        // At t=0.5: 0.125
        assert!((ease_in_cubic(0.5) - 0.125).abs() < f32::EPSILON);
    }

    #[test]
    fn ease_in_cubic_clamps_input() {
        assert!((ease_in_cubic(-0.5) - 0.0).abs() < f32::EPSILON);
        assert!((ease_in_cubic(1.5) - 1.0).abs() < f32::EPSILON);
    }

    // ---- brightness_to_color ----

    #[test]
    fn frozen_returns_logo_color() {
        let logo = Color::Rgb(0, 255, 0);
        let result = brightness_to_color(
            0.5,
            true,
            Color::Rgb(0, 50, 0),
            Color::Rgb(255, 255, 255),
            logo,
        );
        assert_eq!(result, logo);
    }

    #[test]
    fn brightness_zero_returns_dim() {
        let dim = Color::Rgb(0, 85, 0);
        let bright = Color::Rgb(255, 255, 255);
        let logo = Color::Rgb(0, 255, 0);
        let result = brightness_to_color(0.0, false, dim, bright, logo);
        assert_eq!(result, dim);
    }

    #[test]
    fn brightness_one_returns_bright() {
        let dim = Color::Rgb(0, 85, 0);
        let bright = Color::Rgb(255, 255, 255);
        let logo = Color::Rgb(0, 255, 0);
        let result = brightness_to_color(1.0, false, dim, bright, logo);
        assert_eq!(result, bright);
    }

    #[test]
    fn brightness_interpolates_channels() {
        let dim = Color::Rgb(0, 0, 0);
        let bright = Color::Rgb(100, 200, 50);
        let logo = Color::Rgb(0, 255, 0);
        let result = brightness_to_color(0.5, false, dim, bright, logo);
        assert_eq!(result, Color::Rgb(50, 100, 25));
    }

    #[test]
    fn non_rgb_fallback_above_threshold() {
        let result = brightness_to_color(
            0.8,
            false,
            Color::Green,
            Color::White,
            Color::Green,
        );
        assert_eq!(result, Color::White);
    }

    #[test]
    fn non_rgb_fallback_below_threshold() {
        let result = brightness_to_color(
            0.3,
            false,
            Color::Green,
            Color::White,
            Color::Green,
        );
        assert_eq!(result, Color::Green);
    }

    #[test]
    fn non_rgb_bright_fallback() {
        // dim is Rgb but bright is not — should still fall back
        let result = brightness_to_color(
            0.8,
            false,
            Color::Rgb(0, 50, 0),
            Color::White,
            Color::Green,
        );
        assert_eq!(result, Color::White);
    }
}

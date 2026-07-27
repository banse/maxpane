"""MaxPane theme definitions using Textual's native Theme system."""

from __future__ import annotations

from textual.theme import Theme

THEMES: dict[str, Theme] = {}

# 1. Matrix -- green phosphor terminal, default theme
THEMES["matrix"] = Theme(
    name="matrix",
    primary="#00ff41",
    secondary="#00cc33",
    background="#1c1c1c",
    surface="#262626",
    panel="#303030",
    accent="#00ff41",
    warning="#33ff33",
    error="#ff0040",
    success="#00ff41",
    foreground="#00dd33",
    dark=True,
)

# 2. Minimal -- dark blue-gray, clean
THEMES["minimal"] = Theme(
    name="minimal",
    primary="#88aacc",
    secondary="#6688aa",
    background="#1a1a2e",
    surface="#16213e",
    panel="#0f3460",
    accent="#88aacc",
    warning="#e2b93d",
    error="#e74c3c",
    success="#2ecc71",
    dark=True,
)

# 2. Bloomberg -- financial terminal: green/amber on black
THEMES["bloomberg"] = Theme(
    name="bloomberg",
    primary="#00ff41",
    secondary="#ffb000",
    background="#0a0a0a",
    surface="#111111",
    panel="#1a1a1a",
    accent="#00ff41",
    warning="#ffb000",
    error="#ff4444",
    success="#00ff41",
    dark=True,
)

# 3. htop -- system monitor: multi-colored on dark
THEMES["htop"] = Theme(
    name="htop",
    primary="#39d353",
    secondary="#58a6ff",
    background="#0d1117",
    surface="#161b22",
    panel="#21262d",
    accent="#58a6ff",
    warning="#d29922",
    error="#f85149",
    success="#39d353",
    dark=True,
)

# 4. Retro Game -- RPG aesthetic: bright/colorful
THEMES["retro"] = Theme(
    name="retro",
    primary="#ffd700",
    secondary="#ff6b6b",
    background="#1a0a2e",
    surface="#2d1b4e",
    panel="#3d2b5e",
    accent="#ffd700",
    warning="#ff6b6b",
    error="#ff4757",
    success="#2ed573",
    dark=True,
)

# 5. Bakery -- game website colors: warm/playful
THEMES["bakery"] = Theme(
    name="bakery",
    primary="#1b96ca",
    secondary="#DC8360",
    background="#2a1f1a",
    surface="#3d2e26",
    panel="#4a3830",
    accent="#e5719a",
    warning="#DC8360",
    error="#e5719a",
    success="#1b96ca",
    dark=True,
)

# 7. FrenPet -- brand colors: mint green on dark brown
THEMES["frenpet"] = Theme(
    name="frenpet",
    primary="#DBFEE6",
    secondary="#a8e6b4",
    background="#2a2525",
    surface="#342E2E",
    panel="#3d3535",
    accent="#DBFEE6",
    warning="#e6db99",
    error="#e67272",
    success="#DBFEE6",
    foreground="#d4d0d0",
    dark=True,
)

# 8. Base -- Base chain brand: blue on dark navy
THEMES["base"] = Theme(
    name="base",
    primary="#0052FF",
    secondary="#578AFF",
    background="#0a0f1a",
    surface="#111827",
    panel="#1e293b",
    accent="#0052FF",
    warning="#f59e0b",
    error="#ef4444",
    success="#22c55e",
    dark=True,
)

# 9. Talismans -- alchemical: antique gold + violet on near-black
THEMES["talismans"] = Theme(
    name="talismans",
    primary="#b8860b",
    secondary="#8a6fd6",
    background="#0c0a12",
    surface="#16121f",
    panel="#241c33",
    accent="#d4af37",
    warning="#f59e0b",
    error="#ef4444",
    success="#22c55e",
    dark=True,
)

# 10. FWA -- gacha terminal: cold chrome so the reserved warm semantics pop.
#
# The register PRD §11 asks for is "gachapon/casino", but almost every warm
# colour on the FWA screen is already spoken for: green/red carry the EV sign,
# amber carries a warning, and gold is reserved *exclusively* for the crown.
# The design answer is therefore inversion rather than addition -- the chrome
# (titles, borders, scrollbars, chart ink) goes cool and desaturated so that
# the three semantic ramps below are the only saturated things on screen. The
# numbers stay the content; the theme stays out of their way.
#
# Nothing here is gold: `accent`/`primary` are teal, and `warning` is pushed
# orange (#f2842f, hue 26deg, lightness 57%) rather than amber, so the crown's
# #f0c040 (hue 44deg, lightness 60%) owns both the yellow band of the spectrum
# and the title of brightest warm thing on the screen.
FWA_VARIABLES: dict[str, str] = {
    # -- crown: gold, and nothing else on the screen may use it -----------
    #    Must stay equal to ``_GOLD`` in widgets/fwa/fwa_hero_metrics.py.
    "fwa-crown-gold": "#f0c040",
    # -- EV sign ----------------------------------------------------------
    #    Colour is *redundant* here by design: widgets/fwa/fwa_hero_metrics.py
    #    pairs every EV figure with a `▲`/`▼` glyph and an explicit `+`/`-`
    #    sign, so the metric survives greyscale and colour blindness. Do not
    #    let the presence of these variables tempt anyone into dropping the
    #    glyph -- the glyph is the carrier, the colour is the echo.
    "fwa-ev-up": "#4ade80",
    "fwa-ev-down": "#ff7085",
    # -- pool temperature: cold -> hot ------------------------------------
    #    analytics/fwa_signals.py:pool_temp_signal_for() paints the row by the
    #    *share*, not the clock: COLD (surcharge 100% -> YOU) is green, WARM
    #    (partial share, or the dial pinned) is amber, HOT (surcharge ->
    #    depositors) is muted. Each state also names its direction in words,
    #    so the ramp is never the only cue.
    "fwa-pool-cold": "#4ade80",
    "fwa-pool-warm": "#f2842f",
    "fwa-pool-hot": "#8fa0b8",
}

THEMES["fwa"] = Theme(
    name="fwa",
    primary="#4fb3c4",
    secondary="#8f86d6",
    background="#0a0d13",
    surface="#12161f",
    panel="#1d2330",
    accent="#66d3e0",
    # `success`/`error`/`warning` are deliberately the *same* values as the
    # ramps above, so the screen has exactly one green, one red and one amber
    # rather than two vocabularies for the same three ideas. It also means a
    # widget can move from the literal `[green]`/`[red]` to `[$success]`/
    # `[$error]` -- which Textual content markup resolves per theme, and which
    # every theme defines -- without any colour changing under `fwa`.
    warning=FWA_VARIABLES["fwa-pool-warm"],
    error=FWA_VARIABLES["fwa-ev-down"],
    success=FWA_VARIABLES["fwa-ev-up"],
    foreground="#ccd4e0",
    dark=True,
    variables=dict(FWA_VARIABLES),
)

THEME_NAMES: list[str] = list(THEMES.keys())

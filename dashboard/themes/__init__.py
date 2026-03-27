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
    dark=False,
)

THEME_NAMES: list[str] = list(THEMES.keys())

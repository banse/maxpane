"""The registered ``fwa`` theme, its palette, and the CSS block that pairs with it.

Three things are worth stating up front, because they shaped how these tests
are written.

**1. The theme is global, not screen-local.** ``THEMES`` is a single registry
shared by all nine dashboards, and ``THEME_NAMES`` is ``list(THEMES.keys())``,
so registration order *is* the ``t``-key cycle order. A palette that only works
on the FWA screen would be a defect, so the assertions below are about the
palette's structure -- every slot filled, gold reserved, adequate contrast --
rather than about how the FWA screen happens to look.

**2. Colour is never the sole carrier of meaning.** The EV sign, the pool
temperature and the buy gate each pair their colour with a glyph and with words
(``▲``/``▼``, ``→ YOU`` / ``→ depositors``, ``open``/``closed``). The palette
here is deliberately the *echo* of those cues, not their replacement;
``test_ev_ramp_is_redundant_with_the_glyphs`` pins the widget-side guarantee so
a future palette change cannot quietly make the glyph look superfluous.

**3. Gold belongs to the crown alone.** ``fwa-crown-gold`` must equal the
literal the hero card renders with, and no other entry in the palette may come
near it -- otherwise the one element the theme reserves stops being reserved.

The vertical-budget rule for ``FWAHeroBox`` (``padding: 0 2``, never ``1 2``)
is asserted here against the stylesheet *source*, which is cheap and names the
mistake precisely; ``tests/screens/test_fwa_screen.py::
test_ev_coverage_badge_survives_the_real_stylesheet`` asserts the *consequence*
by rendering. Both exist on purpose: the render test proves the badge is on
screen, this one says why it stopped being there.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from maxpane_dashboard.themes import FWA_VARIABLES, THEME_NAMES, THEMES

TCSS = (
    Path(__file__).resolve().parents[1]
    / "maxpane_dashboard"
    / "themes"
    / "minimal.tcss"
)

#: The colour the CROWN hero card is literally rendered with today. Kept as a
#: literal rather than imported so that a change on either side is a *test*
#: failure and not a silently agreeing pair of constants.
CROWN_GOLD_IN_WIDGET = "#f0c040"


# ---------------------------------------------------------------------------
# contrast helpers (WCAG 2.1 relative luminance)
# ---------------------------------------------------------------------------


def _channel(value: int) -> float:
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG contrast ratio between two ``#rrggbb`` strings."""
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _hue_degrees(hex_color: str) -> float:
    r, g, b = (v / 255.0 for v in _rgb(hex_color))
    hi, lo = max(r, g, b), min(r, g, b)
    if hi == lo:
        return 0.0
    d = hi - lo
    if hi == r:
        h = ((g - b) / d) % 6
    elif hi == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60.0


def _hue_distance(a: str, b: str) -> float:
    d = abs(_hue_degrees(a) - _hue_degrees(b)) % 360.0
    return min(d, 360.0 - d)


@pytest.fixture(scope="module")
def tcss_text() -> str:
    return TCSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def fwa_css_block(tcss_text: str) -> str:
    """Just the ``/* ── FWA screen ── */`` block, to EOF."""
    marker = "/* ── FWA screen"
    assert marker in tcss_text, "the FWA CSS block is missing from minimal.tcss"
    return tcss_text[tcss_text.index(marker) :]


# ---------------------------------------------------------------------------
# registration
# ---------------------------------------------------------------------------


def test_fwa_theme_registered():
    assert "fwa" in THEMES
    assert THEMES["fwa"].name == "fwa"


def test_fwa_in_theme_names():
    """``THEME_NAMES`` is derived from ``THEMES``, so ``t`` can reach it."""
    assert "fwa" in THEME_NAMES
    assert THEME_NAMES == list(THEMES.keys())
    # Nine dashboards' themes plus fwa. Stated as a number so that adding a
    # theme without thinking about the cycle is a conscious edit.
    assert len(THEME_NAMES) == 10


def test_theme_cycle_includes_fwa_and_wraps():
    """Reproduces ``MaxPaneApp.action_cycle_theme`` (app.py:338) exactly.

    The app is not imported: this WP may not touch ``app.py``, and the cycle
    is a pure function of ``THEME_NAMES``.
    """

    def next_theme(current: str) -> str:
        idx = THEME_NAMES.index(current) if current in THEME_NAMES else 0
        return THEME_NAMES[(idx + 1) % len(THEME_NAMES)]

    # fwa is reachable...
    seen, cursor = [], THEME_NAMES[0]
    for _ in range(len(THEME_NAMES)):
        cursor = next_theme(cursor)
        seen.append(cursor)
    assert "fwa" in seen
    assert seen[-1] == THEME_NAMES[0], "a full cycle must return to the start"

    # ...and cycling *from* fwa lands on a registered theme, not off the end.
    after_fwa = next_theme("fwa")
    assert after_fwa in THEMES

    # An unknown current theme must not throw the cycle off.
    assert next_theme("not-a-theme") == THEME_NAMES[1]


# ---------------------------------------------------------------------------
# palette
# ---------------------------------------------------------------------------

#: Theme slots the shared stylesheet resolves. ``$text``/``$text-muted`` are
#: derived by Textual from ``foreground``/``background``, so filling these
#: fills those too.
REQUIRED_SLOTS = (
    "primary",
    "secondary",
    "background",
    "surface",
    "panel",
    "accent",
    "warning",
    "error",
    "success",
    "foreground",
)

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_fwa_theme_defines_required_colors():
    theme = THEMES["fwa"]
    for slot in REQUIRED_SLOTS:
        value = getattr(theme, slot)
        assert value, f"theme slot {slot!r} is unset"
        assert HEX.match(value), f"theme slot {slot!r} is not a #rrggbb value: {value!r}"

    for name, value in FWA_VARIABLES.items():
        assert value, f"palette variable {name!r} is empty"
        assert HEX.match(value), f"palette variable {name!r} is not #rrggbb: {value!r}"
        assert theme.variables[name] == value

    # The three semantic ramps PRD §11 asks for, and nothing beyond them.
    assert set(FWA_VARIABLES) == {
        "fwa-crown-gold",
        "fwa-ev-up",
        "fwa-ev-down",
        "fwa-pool-cold",
        "fwa-pool-warm",
        "fwa-pool-hot",
    }

    assert theme.dark is True, (
        "the palette is tuned against dark backgrounds, and dark=True is also "
        "what keeps ANSI-named markup resolving through ansi_theme_dark "
        "regardless of the host terminal's own light/dark setting"
    )


def test_crown_gold_distinct_from_ev_colors():
    """The crown can never be mistaken for an EV state."""
    theme = THEMES["fwa"]
    gold = FWA_VARIABLES["fwa-crown-gold"]
    up = FWA_VARIABLES["fwa-ev-up"]
    down = FWA_VARIABLES["fwa-ev-down"]

    assert gold != up
    assert gold != down
    assert up != down
    # Equality is the floor; a near-miss would be just as confusing at 1 cell.
    assert _hue_distance(gold, up) > 30
    assert _hue_distance(gold, down) > 30
    assert _hue_distance(up, down) > 30
    # ...and the sign itself must be unmistakable, glyph or no glyph.
    assert _hue_distance(theme.success, theme.error) > 60


def test_gold_is_reserved_for_the_crown():
    """No other palette entry may wear the crown's colour.

    ``warning`` is the one at risk -- amber is the obvious caution colour and
    it sits right next to gold -- so it is pushed orange, and the crown is kept
    the brightest warm thing on the screen.
    """
    theme = THEMES["fwa"]
    gold = FWA_VARIABLES["fwa-crown-gold"]

    assert gold == CROWN_GOLD_IN_WIDGET, (
        "fwa-crown-gold must match the literal the CROWN hero card renders "
        "with (widgets/fwa/fwa_hero_metrics.py::_GOLD)"
    )

    for slot in REQUIRED_SLOTS:
        assert getattr(theme, slot) != gold, f"{slot} must not be gold"
    for name, value in FWA_VARIABLES.items():
        if name == "fwa-crown-gold":
            continue
        assert value != gold, f"{name} must not be gold"

    assert _hue_distance(gold, theme.warning) > 15, (
        "warning is too close to gold in hue; the crown stops reading as "
        "reserved"
    )
    assert _luminance(gold) > _luminance(theme.warning), (
        "gold should stay the brightest warm colour in the palette"
    )


def test_fwa_palette_clears_wcag_aa():
    """Every colour the *theme* controls clears 4.5:1 on every surface.

    This covers the palette, not the screen: some widgets still emit CSS colour
    names (``[green]`` resolves to #008000 in Textual content markup, a
    ceiling of 4.09:1 against pure black), which no theme can rescue. That is
    tracked as a widget-side finding, not papered over here.
    """
    theme = THEMES["fwa"]
    backgrounds = {
        "background": theme.background,
        "surface": theme.surface,
        "panel": theme.panel,
    }
    foregrounds = {
        "foreground": theme.foreground,
        "primary": theme.primary,
        "secondary": theme.secondary,
        "accent": theme.accent,
        "success": theme.success,
        "error": theme.error,
        "warning": theme.warning,
        **FWA_VARIABLES,
    }

    failures = [
        f"{fg_name} on {bg_name}: {contrast_ratio(fg, bg):.2f}"
        for fg_name, fg in foregrounds.items()
        for bg_name, bg in backgrounds.items()
        if contrast_ratio(fg, bg) < 4.5
    ]
    assert not failures, "below WCAG AA 4.5:1 -> " + "; ".join(failures)


def test_ev_ramp_is_redundant_with_the_glyphs():
    """The palette must never become the only carrier of the EV sign.

    Guarding the widget from the theme's side: if someone deletes the ``▲``/
    ``▼`` because "the colour already says it", this fails.
    """
    from maxpane_dashboard.widgets.fwa.fwa_hero_metrics import _ev_sign

    up_glyph, up_color = _ev_sign(1.0)
    down_glyph, down_color = _ev_sign(-1.0)
    assert up_glyph == "▲"
    assert down_glyph == "▼"
    assert up_color != down_color


# ---------------------------------------------------------------------------
# the CSS block
# ---------------------------------------------------------------------------


def _rule_body(css: str, selector: str) -> str:
    match = re.search(
        r"(?m)^" + re.escape(selector) + r"\s*\{(.*?)\}", css, re.DOTALL
    )
    assert match, f"no rule for {selector!r} in the FWA CSS block"
    return match.group(1)


def test_hero_box_padding_is_zero_two(fwa_css_block: str):
    """``padding: 0 2`` -- the single rule this whole block must not get wrong.

    ``FWAHeroBox`` is ``height: 7`` with a border: five interior rows for the
    four lines a hero card composes (title, value, second line, coverage
    badge). ``padding: 1 2`` spends two rows on whitespace and clips the
    fourth. On the PULL EV card that fourth line is the coverage badge, and an
    EV number shown without its coverage is what PRD §3 forbids outright.

    Theme rules outrank ``DEFAULT_CSS`` in Textual, so stating it in the
    widget is not enough -- it has to be restated here, correctly.
    """
    body = _rule_body(fwa_css_block, "FWAHeroBox")
    assert re.search(r"padding:\s*0\s+2\s*;", body), (
        "FWAHeroBox must be `padding: 0 2` -- see the docstring"
    )
    assert not re.search(r"padding:\s*1\s+2\s*;", body)
    assert re.search(r"height:\s*7\s*;", body)


def test_fwa_css_block_restates_the_screen_structure(fwa_css_block: str):
    """An app stylesheet replaces ``DEFAULT_CSS``; it does not merge with it.

    So anything the screen's ``DEFAULT_CSS`` establishes and this block omits
    is simply lost. These are the proportions the layout depends on.
    """
    assert re.search(r"width:\s*3fr", _rule_body(fwa_css_block, "FWAOddsBoard"))
    assert re.search(r"width:\s*3fr", _rule_body(fwa_css_block, "FWAActivityFeed"))
    two_fr = _rule_body(fwa_css_block, "FWAChaseBoard, FWASettlementTable")
    assert re.search(r"width:\s*2fr", two_fr)
    assert re.search(r"height:\s*7", _rule_body(fwa_css_block, "FWAHeroMetrics"))
    assert re.search(r"height:\s*auto", _rule_body(fwa_css_block, "FWASparkline"))
    signals = _rule_body(fwa_css_block, "FWASignals")
    assert re.search(r"height:\s*1fr", signals)
    assert re.search(r"overflow-y:\s*auto", signals)


def test_fwa_css_block_uses_only_universal_variables(fwa_css_block: str):
    """The stylesheet is shared by all ten themes.

    Naming an ``fwa``-only variable such as ``$fwa-crown-gold`` here would make
    the file fail to parse under the other nine, taking every dashboard with
    it. The FWA palette therefore lives in the Theme, not in this block.
    """
    universal = {
        "$background",
        "$surface",
        "$panel",
        "$text",
        "$text-muted",
        "$primary",
        "$secondary",
        "$accent",
        "$warning",
        "$error",
        "$success",
        "$boost",
    }
    # Comments are prose and may name fwa-only variables while explaining why
    # they cannot be used; only live declarations count.
    live = re.sub(r"/\*.*?\*/", "", fwa_css_block, flags=re.DOTALL)
    used = set(re.findall(r"\$[a-z][a-z0-9-]*", live))
    assert used <= universal, f"non-universal CSS variables used: {used - universal}"


def test_fwa_css_block_is_appended_at_eof(tcss_text: str):
    """Acceptance criterion: appended only, nothing above it disturbed.

    The Talismans block must still be the last thing before it, and the FWA
    block must be the last thing in the file.
    """
    tal = tcss_text.index("/* ── Talismans screen")
    fwa = tcss_text.index("/* ── FWA screen")
    assert tal < fwa
    assert "/* ──" not in tcss_text[fwa + 10 :], (
        "the FWA block must be the last section in minimal.tcss"
    )


# ── WP-17 CLI selection tests below ──
#
# These drive the *real* ``maxpane_dashboard.__main__.main()`` argparse parser
# rather than re-declaring the choice lists, because the failure mode being
# guarded is a registration that was added to ``THEMES`` / ``_GAME_CYCLE`` but
# never to the CLI. Asserting against a copied list would pass in exactly that
# case. ``MaxPaneApp`` is stubbed out (no Textual app, no network, no manager
# construction) and ``logging.basicConfig`` is neutered so a test run never
# truncates the user's ~/.maxpane/maxpane.log.


def _run_cli(monkeypatch, argv: list[str]) -> dict:
    """Invoke ``__main__.main()`` with *argv*, returning the app's kwargs."""
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):  # never starts a real TUI
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(cli, "_maximize_terminal", lambda: None)
    monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    cli.main()
    return captured


def test_theme_cli_choice_includes_fwa(monkeypatch):
    """``--theme fwa`` is an accepted choice and reaches the app.

    Guards the ``--theme`` choices list in ``__main__.py``, which PRD §10 omits
    and which an ``fwa`` Theme in ``THEMES`` makes mandatory.
    """
    captured = _run_cli(monkeypatch, ["--theme", "fwa"])
    assert captured["theme"] == "fwa"
    assert captured.get("ran") is True
    # The theme must actually resolve, not just be spelled correctly.
    assert "fwa" in THEMES

    # And the list is still a closed set -- otherwise the assertion above would
    # pass for any string.
    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--theme", "not-a-theme"])


def test_game_cli_choice_includes_fwa(monkeypatch):
    """``--game fwa`` is an accepted choice and reaches the app as initial_game."""
    from maxpane_dashboard.app import MaxPaneApp
    from maxpane_dashboard.screens.game_select import GAMES

    captured = _run_cli(monkeypatch, ["--game", "fwa"])
    assert captured["initial_game"] == "fwa"
    assert captured.get("ran") is True

    with pytest.raises(SystemExit):
        _run_cli(monkeypatch, ["--game", "not-a-game"])

    # The three registration sites must agree on the id.
    assert "fwa" in MaxPaneApp._GAME_CYCLE

    # Assert on the *id*, not the hotkey. The hotkey is a menu position that
    # legitimately moves whenever a dashboard above it is hidden (it went 9 -> 8
    # when DOTA was hidden after its backend went NXDOMAIN); pinning it made this
    # test fail for a change it was never meant to guard.
    row = next((g for g in GAMES if g[1] == "fwa"), None)
    assert row is not None, "fwa is not registered in GAMES"
    assert row[2] == "Fake World Assets"
    assert row[3] == "NFT gacha pool w/ inverse-weighted VRF draws on Ethereum"

    # The hotkeys are what a user actually presses, so they must stay a
    # contiguous 1..N with no gaps or duplicates -- which is the real invariant
    # the hardcoded "9" was standing in for, and it survives future hiding.
    keys = [g[0] for g in GAMES]
    assert keys == [str(i) for i in range(1, len(GAMES) + 1)], (
        f"game-select hotkeys must be contiguous 1..N, got {keys}"
    )


def test_theme_cli_choices_match_theme_names(monkeypatch):
    """Every ``--theme`` choice is a registered theme, and ``fwa`` is last.

    CLI order must match ``THEME_NAMES`` so the ``t``-key cycle and the flag
    present the same sequence.
    """
    import maxpane_dashboard.__main__ as cli

    src = Path(cli.__file__).read_text(encoding="utf-8")
    match = re.search(r'"--theme",\s*\n\s*default="[^"]*",\s*\n\s*choices=\[([^\]]*)\]', src)
    assert match, "could not locate the --theme choices list in __main__.py"
    choices = re.findall(r'"([^"]+)"', match.group(1))
    assert choices[-1] == "fwa", "fwa must be appended last to match THEME_NAMES"
    assert set(choices) <= set(THEME_NAMES), (
        f"CLI offers themes that are not registered: {set(choices) - set(THEME_NAMES)}"
    )

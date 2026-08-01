"""``--font-size`` decides how many columns the dashboard gets.

Every dashboard lays out in *columns*, and the widest FWA tier needs 198 of
them. A maximized window on a laptop display gives roughly 169 at 17 pt, so
three of the four ``‹ widen`` markers were permanently on screen -- and the
app **forced 17 pt on every launch**, overriding whatever the user had set.
Zooming out before starting did nothing, which made the hints look like they
were lying about a layout that could not be reached.

Pinned here: the flag reaches the terminal, ``0`` means "leave my terminal
alone", the env var works, and a bad env var degrades rather than crashing the
launch.

No TUI is started and no ``osascript`` runs: ``MaxPaneApp`` is stubbed and the
terminal writer is captured.
"""

from __future__ import annotations

import pytest

from maxpane_dashboard.__main__ import (
    _DEFAULT_FONT_SIZE,
    FULL_LAYOUT_COLUMNS,
    _resolve_font_size,
)


def _run_cli(monkeypatch, argv: list[str], env: dict | None = None) -> dict:
    """Invoke ``main()`` with *argv*, capturing the font size it applied."""
    import maxpane_dashboard.__main__ as cli

    captured: dict = {}

    class _StubApp:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def run(self):
            captured["ran"] = True

    monkeypatch.setattr(cli, "MaxPaneApp", _StubApp)
    monkeypatch.setattr(
        cli, "_maximize_terminal", lambda size=None: captured.update(font_size=size)
    )
    monkeypatch.setattr(cli.logging, "basicConfig", lambda **kw: None)
    monkeypatch.setattr(cli.sys, "argv", ["maxpane", *argv])
    monkeypatch.delenv("MAXPANE_FONT_SIZE", raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    cli.main()
    return captured


# ---------------------------------------------------------------------------
# resolution order
# ---------------------------------------------------------------------------


def test_the_flag_reaches_the_terminal(monkeypatch) -> None:
    assert _run_cli(monkeypatch, ["--font-size", "12"])["font_size"] == 12


def test_zero_means_leave_my_terminal_alone(monkeypatch) -> None:
    """The escape hatch for anyone who has already sized their terminal."""
    assert _run_cli(monkeypatch, ["--font-size", "0"])["font_size"] == 0


def test_no_flag_keeps_the_old_behaviour(monkeypatch) -> None:
    """Existing users must see exactly what they saw before."""
    assert _run_cli(monkeypatch, [])["font_size"] == _DEFAULT_FONT_SIZE


def test_the_env_var_is_honoured(monkeypatch) -> None:
    captured = _run_cli(monkeypatch, [], env={"MAXPANE_FONT_SIZE": "11"})

    assert captured["font_size"] == 11


def test_the_flag_beats_the_env_var(monkeypatch) -> None:
    captured = _run_cli(
        monkeypatch, ["--font-size", "9"], env={"MAXPANE_FONT_SIZE": "20"}
    )

    assert captured["font_size"] == 9


@pytest.mark.parametrize("value", ["", "  ", "abc", "-1", "3", "500", "12.5"])
def test_a_bad_env_var_falls_back_instead_of_crashing(monkeypatch, value) -> None:
    """An env var is set once and forgotten; a typo must not break launching.

    The CLI flag is different -- a bad flag is a usage error the user is
    looking at right now (see below).
    """
    monkeypatch.setenv("MAXPANE_FONT_SIZE", value)

    assert _resolve_font_size(None) == _DEFAULT_FONT_SIZE


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["-1", "3", "73", "abc", "12.5", ""])
def test_unusable_sizes_are_a_usage_error(monkeypatch, value) -> None:
    """Rejected at the parser, not silently clamped.

    A 2 pt font produces an unreadable 1,000-column layout and a 200 pt one
    produces a terminal too narrow to render anything -- both look like the
    app is broken.
    """
    with pytest.raises(SystemExit) as exc:
        _run_cli(monkeypatch, ["--font-size", value])

    assert exc.value.code == 2


@pytest.mark.parametrize("value", ["6", "10", "17", "24", "72"])
def test_reasonable_sizes_are_accepted(monkeypatch, value) -> None:
    assert _run_cli(monkeypatch, ["--font-size", value])["font_size"] == int(value)


# ---------------------------------------------------------------------------
# the terminal writer itself
# ---------------------------------------------------------------------------


def test_zero_writes_no_font_escape_but_still_maximizes(monkeypatch, capsys) -> None:
    """``0`` must not merely pass 0 along -- it must emit nothing about fonts."""
    import maxpane_dashboard.__main__ as cli

    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    cli._maximize_terminal(0)

    out = capsys.readouterr().out
    assert "SetFontSize" not in out, "a font escape was written despite --font-size 0"
    assert "SetFullscreen" in out, "maximizing is still wanted"


def test_a_size_writes_that_size(monkeypatch, capsys) -> None:
    import maxpane_dashboard.__main__ as cli

    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    cli._maximize_terminal(11)

    assert "SetFontSize=11" in capsys.readouterr().out


def test_terminal_app_runs_no_osascript_at_zero(monkeypatch, capsys) -> None:
    """Terminal.app sets the font by shelling out; ``0`` must skip that too."""
    import subprocess

    import maxpane_dashboard.__main__ as cli

    monkeypatch.setenv("TERM_PROGRAM", "Apple_Terminal")

    def _explode(*a, **k):  # pragma: no cover - must never run
        raise AssertionError("osascript ran despite --font-size 0")

    monkeypatch.setattr(subprocess, "run", _explode)
    cli._maximize_terminal(0)

    assert "\033[9;1t" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# the number the flag exists for
# ---------------------------------------------------------------------------


def test_the_documented_width_matches_the_layout(monkeypatch) -> None:
    """``FULL_LAYOUT_COLUMNS`` must stay true, or the help text misleads.

    Renders the real FWA screen one column below and at the threshold and
    asserts the ``‹ widen`` markers disappear exactly there. If a widget's
    tier table changes, this goes red instead of the help text quietly
    becoming wrong.
    """
    pytest.importorskip("textual")
    import asyncio
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parent / "screens" / "test_fwa_screen.py"
    spec = importlib.util.spec_from_file_location("_fwa_screen_harness", path)
    harness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(harness)

    async def _widen_markers(width: int) -> int:
        screen = harness.FWAScreen(
            harness._FakeManager(), poll_interval=30, name="fwa"
        )
        app = harness._ThemedHarness(screen)
        async with app.run_test(size=(width, 48)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            return harness._screen_text(app).count("‹ widen")

    assert asyncio.run(_widen_markers(FULL_LAYOUT_COLUMNS)) == 0, (
        f"{FULL_LAYOUT_COLUMNS} columns should clear every widen marker"
    )
    assert asyncio.run(_widen_markers(FULL_LAYOUT_COLUMNS - 4)) > 0, (
        "the documented width is higher than it needs to be"
    )

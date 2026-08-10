"""``--font-size`` decides how many columns the dashboard gets.

Every dashboard lays out in *columns*, and the widest layout needs
``FULL_LAYOUT_COLUMNS`` of them (198 when this file was written and FWA was
the widest; 152 today, and it is surf's). A maximized window on a laptop
display gives roughly 169 at 17 pt, so ``‹ widen`` markers were permanently on
screen -- and the app **forced 17 pt on every launch**, overriding whatever the
user had set. Zooming out before starting did nothing, which made the hints
look like they were lying about a layout that could not be reached.

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


def _load_harness(relative: str):
    """Import a screen test module as a harness, without collecting it."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parent / relative
    spec = importlib.util.spec_from_file_location(f"_harness_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_documented_width_clears_every_dashboard(monkeypatch) -> None:
    """``FULL_LAYOUT_COLUMNS`` must stay true, or the help text misleads.

    The help text promises "the widest dashboard layout needs N", so the claim
    is about *every* dashboard, not one of them: at ``FULL_LAYOUT_COLUMNS`` no
    screen may still be advertising a shed column.  FWA is checked because it
    set this number for most of the project's life; surf because it sets it
    now.  If a widget's tier table changes, this goes red instead of the help
    text quietly becoming wrong.
    """
    pytest.importorskip("textual")
    import asyncio

    fwa = _load_harness("screens/test_fwa_screen.py")

    async def _fwa_markers(width: int) -> int:
        screen = fwa.FWAScreen(fwa._FakeManager(), poll_interval=30, name="fwa")
        app = fwa._ThemedHarness(screen)
        async with app.run_test(size=(width, 48)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            return fwa._screen_text(app).count("‹ widen")

    surf = _load_harness("screens/test_surf_screen.py")

    assert asyncio.run(_fwa_markers(FULL_LAYOUT_COLUMNS)) == 0, (
        f"{FULL_LAYOUT_COLUMNS} columns should clear every FWA widen marker"
    )
    assert asyncio.run(surf._widen_markers(FULL_LAYOUT_COLUMNS)) == 0, (
        f"{FULL_LAYOUT_COLUMNS} columns should clear every surf widen marker"
    )


def test_the_documented_width_is_tight_against_the_widest_dashboard() -> None:
    """The other half: the number is not padded *without a reason on record*.

    This assertion used to be made against FWA (``FULL_LAYOUT_COLUMNS - 4``
    still showed a marker), and that was right while FWA was the widest
    layout.  It moved to surf when surf's dev-activity panel took the number
    to 176, and it read ``surf._widen_markers(FULL_LAYOUT_COLUMNS - 1) > 0``.

    That form briefly stopped holding.  On 2026-08-10 the surf screen's column
    seam moved 3:2 -> 7:6 and its full layout came down 176 -> 152, but the
    seam commit deliberately touched no constant -- reconciling this one,
    ``screens/surf.SURF_FULL_LAYOUT_COLUMNS``, the ``--font-size`` help text,
    the README width table and CLAUDE.md is a step of its own -- so for one
    commit the documented width was generous by 24 columns and ``_SLACK``
    recorded exactly that.  **The reconciliation has since landed**: both
    constants read 152, ``_SLACK`` is back to 0, and the assertion below is
    the strict form again.

    Generous would be safe; *short* is what clips.  The claim is therefore
    made in two halves, neither of which is a constant compared against
    itself:

    * every dashboard must clear at the documented width (the test above), and
    * the documented width must equal the widest dashboard's own measured
      width -- a separate literal in the surf harness, which pins it to the
      real screen in both directions right below.

    ``_SLACK`` stays, at 0, because it is the thing that may only ever shrink:
    a future re-measurement is allowed to leave the documented number
    temporarily generous, and must say by how much.
    """
    pytest.importorskip("textual")
    import asyncio

    surf = _load_harness("screens/test_surf_screen.py")

    #: Columns by which the documented width currently exceeds the widest
    #: dashboard's measured one.  Must only ever shrink.
    _SLACK = 0

    measured = surf.MEASURED_FULL_LAYOUT_COLUMNS
    assert FULL_LAYOUT_COLUMNS - measured == _SLACK, (
        f"the documented width is {FULL_LAYOUT_COLUMNS} and the widest "
        f"dashboard measures {measured}: {FULL_LAYOUT_COLUMNS - measured} "
        f"columns of slack, not the {_SLACK} on record. If the "
        "reconciliation landed, set _SLACK to 0."
    )
    # The measured number is a real render, not a second literal: it is clean
    # at that width and marked one column below it.
    assert asyncio.run(surf._widen_markers(measured)) == 0
    assert asyncio.run(surf._widen_markers(measured - 1)) > 0, (
        "the widest dashboard is clean below its measured width -- re-measure"
    )

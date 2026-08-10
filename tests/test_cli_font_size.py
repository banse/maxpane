"""``--font-size`` decides how many columns the dashboard gets.

Every dashboard lays out in *columns*, and the widest layout needs
``FULL_LAYOUT_COLUMNS`` of them (198 when this file was written and FWA was
the widest; 176 then 152 while surf was; 143 today, FWA's again). A maximized
window on a laptop
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


def _fwa_markers(width: int) -> int:
    """Composited ``‹ widen`` count on the real FWA screen at *width*.

    Module-level because two tests need it now that FWA is the dashboard the
    documented width is measured against again -- one for "clears", one for
    "and not one column more".
    """
    import asyncio

    fwa = _load_harness("screens/test_fwa_screen.py")

    async def _run() -> int:
        screen = fwa.FWAScreen(fwa._FakeManager(), poll_interval=30, name="fwa")
        app = fwa._ThemedHarness(screen)
        async with app.run_test(size=(width, 48)) as pilot:
            await pilot.pause()
            await screen._do_refresh()
            await pilot.pause()
            return fwa._screen_text(app).count("‹ widen")

    return asyncio.run(_run())


def test_the_documented_width_clears_every_dashboard(monkeypatch) -> None:
    """``FULL_LAYOUT_COLUMNS`` must stay true, or the help text misleads.

    The help text promises "the widest dashboard layout needs N", so the claim
    is about *every* dashboard, not one of them: at ``FULL_LAYOUT_COLUMNS`` no
    screen may still be advertising a shed column.  FWA is checked because it
    sets this number -- as it did for most of the project's life, and does
    again since surf came down under it; surf because it set it in between and
    is the one that moves.  If a widget's tier table changes, this goes red
    instead of the help text quietly becoming wrong.
    """
    pytest.importorskip("textual")
    import asyncio

    surf = _load_harness("screens/test_surf_screen.py")

    assert _fwa_markers(FULL_LAYOUT_COLUMNS) == 0, (
        f"{FULL_LAYOUT_COLUMNS} columns should clear every FWA widen marker"
    )
    assert asyncio.run(surf._widen_markers(FULL_LAYOUT_COLUMNS)) == 0, (
        f"{FULL_LAYOUT_COLUMNS} columns should clear every surf widen marker"
    )


def test_the_documented_width_is_tight_against_the_widest_dashboard() -> None:
    """The other half: the number is not padded *without a reason on record*.

    **Which dashboard "widest" names is itself a measurement, and it has now
    changed twice.**  It was FWA (``FULL_LAYOUT_COLUMNS - 4`` still showed a
    marker); it moved to surf when surf's dev-activity panel took the number
    to 176, and read ``surf._widen_markers(FULL_LAYOUT_COLUMNS - 1) > 0``
    through the 176 and 152 eras; and it is FWA's again since 2026-08-10 --
    not because FWA moved, but because surf came down *under* it.  Sizing the
    surf activity row's wallet and kind cells to the vocabularies their
    producer emits took ``widgets/surf/activity.FULL_WIDTH`` 66 -> 58, so that
    panel clears from a 135-column terminal and ``SurfFeed``'s **142** is what
    the surf screen measures -- one column below the **143** FWA has needed
    since its buy-gate signal was shortened.

    So the tightness is asserted where it lives: against FWA, in both
    directions, both sides a real render.  Clean at the documented width,
    still shedding one column below it.  Neither half is a constant compared
    against itself -- ``FULL_LAYOUT_COLUMNS`` meets pixels both times -- and
    if surf (or anything else) ever grows past FWA again, the second assertion
    is what says so, because FWA will then be clean below the documented
    number.

    The surf half stays as the record of *how far under* it now sits.
    Generous would be safe; *short* is what clips, which is why the surf
    screen's own measurement is pinned to its own render right below.
    """
    pytest.importorskip("textual")
    import asyncio

    assert _fwa_markers(FULL_LAYOUT_COLUMNS) == 0, (
        f"FWA sheds a column at {FULL_LAYOUT_COLUMNS}, the width the help text "
        "promises clears every dashboard"
    )
    assert _fwa_markers(FULL_LAYOUT_COLUMNS - 1) > 0, (
        f"FWA is already clean at {FULL_LAYOUT_COLUMNS - 1}: either the "
        "documented width is padded, or some other dashboard is the widest "
        "now and this assertion belongs against that one"
    )

    surf = _load_harness("screens/test_surf_screen.py")

    #: Columns by which the documented width exceeds *surf's* measured one.
    #: Not a tolerance: 24 -> 0 -> 10 -> 1 is the real gap at each step, and
    #: it is an ``==``, never a ``<=``, precisely so it cannot be quietly
    #: generous.  The first three were re-measurements waiting on their
    #: reconciliation commit; this one is not -- surf simply is one column
    #: narrower than FWA, which is the dashboard the number now comes from.
    _SURF_SLACK = 1

    measured = surf.MEASURED_FULL_LAYOUT_COLUMNS
    assert FULL_LAYOUT_COLUMNS - measured == _SURF_SLACK, (
        f"the documented width is {FULL_LAYOUT_COLUMNS} and surf measures "
        f"{measured}: {FULL_LAYOUT_COLUMNS - measured} columns of slack, not "
        f"the {_SURF_SLACK} on record. If surf grew past the documented "
        "width, reconcile the five surfaces; if it shrank, record the new gap"
    )
    # Surf's own number is a real render too, not a second literal: clean at
    # that width and marked one column below it.
    assert asyncio.run(surf._widen_markers(measured)) == 0
    assert asyncio.run(surf._widen_markers(measured - 1)) > 0, (
        "surf is clean below its measured width -- re-measure"
    )
